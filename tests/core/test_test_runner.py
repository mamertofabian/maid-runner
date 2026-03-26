"""Tests for maid_runner.core.test_runner - test execution."""

from maid_runner.core.test_runner import run_command, run_manifest_tests, run_tests
from maid_runner.core.types import TestStream


class TestRunCommand:
    def test_successful_command(self, tmp_path):
        result = run_command(("echo", "hello"), cwd=tmp_path)
        assert result.success is True
        assert result.exit_code == 0
        assert "hello" in result.stdout
        assert result.duration_ms > 0

    def test_failing_command(self, tmp_path):
        result = run_command(("python", "-c", "import sys; sys.exit(1)"), cwd=tmp_path)
        assert result.success is False
        assert result.exit_code == 1

    def test_command_with_stderr(self, tmp_path):
        result = run_command(
            ("python", "-c", "import sys; sys.stderr.write('err\\n')"),
            cwd=tmp_path,
        )
        assert "err" in result.stderr

    def test_timeout(self, tmp_path):
        result = run_command(
            ("python", "-c", "import time; time.sleep(10)"),
            cwd=tmp_path,
            timeout=1,
        )
        assert result.success is False
        assert result.exit_code == -1

    def test_stream_defaults_to_implementation(self, tmp_path):
        result = run_command(("echo", "hello"), cwd=tmp_path)
        assert result.stream == TestStream.IMPLEMENTATION

    def test_stream_acceptance(self, tmp_path):
        result = run_command(
            ("echo", "acceptance-test"),
            cwd=tmp_path,
            stream=TestStream.ACCEPTANCE,
        )
        assert result.stream == TestStream.ACCEPTANCE


class TestRunManifestTests:
    def test_single_manifest(self, tmp_path):
        manifest = tmp_path / "manifests" / "test.manifest.yaml"
        manifest.parent.mkdir()
        manifest.write_text(
            """schema: "2"
goal: "Test"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: main
validate:
  - echo test-passed
"""
        )

        result = run_manifest_tests(manifest, project_root=tmp_path)
        assert result.success is True
        assert result.total == 1
        assert result.passed == 1

    def test_fail_fast(self, tmp_path):
        manifest = tmp_path / "manifests" / "test.manifest.yaml"
        manifest.parent.mkdir()
        manifest.write_text(
            """schema: "2"
goal: "Test"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: main
validate:
  - python -c "import sys; sys.exit(1)"
  - echo should-not-run
"""
        )

        result = run_manifest_tests(manifest, fail_fast=True, project_root=tmp_path)
        assert result.failed >= 1
        # With fail_fast, second command should not run
        assert result.total <= 1


class TestBatchMode:
    def test_batch_combines_pytest_commands(self, tmp_path):
        """Multiple pytest commands batched into single invocation."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest tests/test_a.py -v
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest tests/test_b.py -v
"""
        )
        # With batch=True, should produce fewer commands than manifests
        result = run_tests(manifest_dir="manifests/", project_root=tmp_path, batch=True)
        # Batched: one combined command instead of two separate
        assert result.total == 1

    def test_batch_false_runs_sequentially(self, tmp_path):
        """batch=False runs each command separately."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - echo a-passed
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - echo b-passed
"""
        )
        result = run_tests(
            manifest_dir="manifests/", project_root=tmp_path, batch=False
        )
        assert result.total == 2

    def test_batch_with_acceptance_still_batches_impl(self, tmp_path):
        """Implementation commands are batched even when acceptance tests exist."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
acceptance:
  tests:
    - echo acceptance-a
validate:
  - pytest tests/test_a.py -v
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest tests/test_b.py -v
"""
        )
        result = run_tests(manifest_dir="manifests/", project_root=tmp_path, batch=True)
        # 1 acceptance (sequential) + 1 batched impl = 2 commands
        assert result.total == 2
        assert len(result.acceptance_results) == 1
        assert len(result.implementation_results) == 1  # batched into one

    def test_mixed_runners_not_batched(self, tmp_path):
        """Mixed pytest + non-pytest commands cannot be batched."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest tests/test_a.py -v
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - echo b-passed
"""
        )
        # With batch=True but mixed runners, should fall back to sequential
        result = run_tests(manifest_dir="manifests/", project_root=tmp_path, batch=True)
        assert result.total == 2


class TestAcceptanceInManifestTests:
    def test_acceptance_runs_first(self, tmp_path):
        """Acceptance tests run before implementation tests."""
        manifest = tmp_path / "manifests" / "test.manifest.yaml"
        manifest.parent.mkdir()
        manifest.write_text(
            """schema: "2"
goal: "Test"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: main
acceptance:
  tests:
    - echo acceptance-passed
validate:
  - echo implementation-passed
"""
        )

        result = run_manifest_tests(manifest, project_root=tmp_path)
        assert result.success is True
        assert result.total == 2
        assert len(result.acceptance_results) == 1
        assert len(result.implementation_results) == 1
        assert result.acceptance_results[0].stream == TestStream.ACCEPTANCE
        assert result.implementation_results[0].stream == TestStream.IMPLEMENTATION

    def test_acceptance_fail_fast(self, tmp_path):
        """Failing acceptance test with fail_fast stops execution."""
        manifest = tmp_path / "manifests" / "test.manifest.yaml"
        manifest.parent.mkdir()
        manifest.write_text(
            """schema: "2"
goal: "Test"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: main
acceptance:
  tests:
    - python -c "import sys; sys.exit(1)"
validate:
  - echo should-not-run
"""
        )

        result = run_manifest_tests(manifest, fail_fast=True, project_root=tmp_path)
        assert result.failed >= 1
        # Implementation tests should not run
        assert result.total == 1
        assert result.implementation_results == []

    def test_no_acceptance_backward_compat(self, tmp_path):
        """Manifest without acceptance works unchanged."""
        manifest = tmp_path / "manifests" / "test.manifest.yaml"
        manifest.parent.mkdir()
        manifest.write_text(
            """schema: "2"
goal: "Test"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: main
validate:
  - echo test-passed
"""
        )

        result = run_manifest_tests(manifest, project_root=tmp_path)
        assert result.success is True
        assert result.total == 1
        assert result.acceptance_results == []
        assert len(result.implementation_results) == 1


class TestRunTests:
    def test_all_manifests(self, tmp_path):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - echo a-passed
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - echo b-passed
"""
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)
        assert result.success is True
        assert result.total == 2
        assert result.passed == 2

    def test_empty_manifest_dir(self, tmp_path):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)
        assert result.success is True
        assert result.total == 0

    def test_manifests_with_acceptance(self, tmp_path):
        """Multi-manifest run includes acceptance tests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
acceptance:
  tests:
    - echo acceptance-a
validate:
  - echo impl-a
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - echo impl-b
"""
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)
        assert result.success is True
        assert result.total == 3  # 1 acceptance + 2 implementation
        assert len(result.acceptance_results) == 1
        assert len(result.implementation_results) == 2
