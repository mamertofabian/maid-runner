"""Tests for maid_runner.core.test_runner - test execution."""

from maid_runner.core.test_runner import (
    run_command,
    run_manifest_tests,
    run_tests,
    _resolve_command,
    _is_python_command,
    _can_batch,
    _batch_pytest,
)
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


class TestRunTestsChainDiagnostics:
    def test_invalid_manifest_prevents_batch_run(self, tmp_path):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "broken.manifest.yaml").write_text(
            """schema: "2"
goal: "Broken"
files:
  create:
    - path: src/broken.py
validate:
  - echo broken
"""
        )
        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)
        assert result.success is False
        assert result.total == 0
        assert len(result.chain_errors) == 1


class TestBatchMode:
    def test_default_does_not_auto_batch(self, tmp_path):
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
        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)
        assert result.total == 2

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

    def test_complex_pytest_commands_are_not_batched(self, tmp_path):
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
  - pytest tests/test_a.py -k auth
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
  - pytest tests/test_b.py -k auth
"""
        )
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


class TestResolveCommand:
    """Tests for _resolve_command() — uv run prefix for Python commands."""

    def test_pytest_gets_uv_run_prefix(self, tmp_path):
        """pytest command gets uv run prepended when uv.lock exists."""
        (tmp_path / "uv.lock").write_text("")
        result = _resolve_command(("pytest", "tests/test_foo.py", "-v"), cwd=tmp_path)
        assert result == ("uv", "run", "pytest", "tests/test_foo.py", "-v")

    def test_python_gets_uv_run_prefix(self, tmp_path):
        """python command gets uv run prepended when uv.lock exists."""
        (tmp_path / "uv.lock").write_text("")
        result = _resolve_command(("python", "-m", "pytest", "tests/"), cwd=tmp_path)
        assert result == ("uv", "run", "python", "-m", "pytest", "tests/")

    def test_python3_gets_uv_run_prefix(self, tmp_path):
        """python3 command gets uv run prepended when uv.lock exists."""
        (tmp_path / "uv.lock").write_text("")
        result = _resolve_command(("python3", "-m", "pytest", "tests/"), cwd=tmp_path)
        assert result == ("uv", "run", "python3", "-m", "pytest", "tests/")

    def test_py_test_gets_uv_run_prefix(self, tmp_path):
        """Legacy py.test command gets uv run prepended when uv.lock exists."""
        (tmp_path / "uv.lock").write_text("")
        result = _resolve_command(("py.test", "tests/", "-v"), cwd=tmp_path)
        assert result == ("uv", "run", "py.test", "tests/", "-v")

    def test_no_uv_lock_no_prefix(self, tmp_path):
        """Without uv.lock, commands pass through unchanged."""
        result = _resolve_command(("pytest", "tests/test_foo.py", "-v"), cwd=tmp_path)
        assert result == ("pytest", "tests/test_foo.py", "-v")

    def test_pyproject_without_uv_lock_no_prefix(self, tmp_path):
        """pyproject.toml alone (e.g. Poetry project) does not trigger uv run."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        result = _resolve_command(("pytest", "tests/test_foo.py", "-v"), cwd=tmp_path)
        assert result == ("pytest", "tests/test_foo.py", "-v")

    def test_non_python_command_unchanged(self, tmp_path):
        """Non-Python commands (echo, npm, etc.) are never prefixed."""
        (tmp_path / "uv.lock").write_text("")
        result = _resolve_command(("echo", "hello"), cwd=tmp_path)
        assert result == ("echo", "hello")

    def test_already_uv_run_no_double_wrap(self, tmp_path):
        """Commands already starting with uv run are not double-wrapped."""
        (tmp_path / "uv.lock").write_text("")
        result = _resolve_command(("uv", "run", "pytest", "tests/"), cwd=tmp_path)
        assert result == ("uv", "run", "pytest", "tests/")

    def test_npm_command_unchanged(self, tmp_path):
        """npm test commands pass through unchanged even with uv.lock."""
        (tmp_path / "uv.lock").write_text("")
        result = _resolve_command(("npm", "test"), cwd=tmp_path)
        assert result == ("npm", "test")

    def test_empty_command_unchanged(self, tmp_path):
        """Empty command tuple passes through unchanged."""
        result = _resolve_command((), cwd=tmp_path)
        assert result == ()

    def test_versioned_python_gets_prefix(self, tmp_path):
        """Versioned python3.12 gets uv run prepended."""
        (tmp_path / "uv.lock").write_text("")
        result = _resolve_command(
            ("python3.12", "-m", "pytest", "tests/"), cwd=tmp_path
        )
        assert result == ("uv", "run", "python3.12", "-m", "pytest", "tests/")


class TestIsPythonCommand:
    """Tests for _is_python_command()."""

    def test_known_commands(self):
        assert _is_python_command("pytest") is True
        assert _is_python_command("python") is True
        assert _is_python_command("python3") is True
        assert _is_python_command("py.test") is True

    def test_versioned_python(self):
        assert _is_python_command("python3.12") is True
        assert _is_python_command("python3.11") is True
        assert _is_python_command("python3.8") is True

    def test_non_python(self):
        assert _is_python_command("echo") is False
        assert _is_python_command("npm") is False
        assert _is_python_command("node") is False
        assert _is_python_command("uv") is False


class TestCanBatch:
    """Direct tests for _can_batch()."""

    def test_empty_commands(self):
        assert _can_batch([]) is False

    def test_single_pytest(self):
        assert _can_batch([("pytest", "tests/test_a.py", "-v")]) is True

    def test_multiple_pytest(self):
        cmds = [
            ("pytest", "tests/test_a.py", "-v"),
            ("pytest", "tests/test_b.py", "-v"),
        ]
        assert _can_batch(cmds) is True

    def test_python_m_pytest(self):
        assert _can_batch([("python", "-m", "pytest", "tests/")]) is True

    def test_python3_m_pytest(self):
        assert _can_batch([("python3", "-m", "pytest", "tests/")]) is True

    def test_mixed_runners_not_batchable(self):
        cmds = [("pytest", "tests/test_a.py"), ("echo", "hello")]
        assert _can_batch(cmds) is False

    def test_echo_not_batchable(self):
        assert _can_batch([("echo", "hello")]) is False


class TestBatchPytest:
    """Direct tests for _batch_pytest()."""

    def test_combines_test_files(self):
        cmds = [
            ("pytest", "tests/test_a.py", "-v"),
            ("pytest", "tests/test_b.py", "-v"),
        ]
        result = _batch_pytest(cmds)
        assert result == ("pytest", "tests/test_a.py", "tests/test_b.py", "-v")

    def test_deduplicates_files(self):
        cmds = [
            ("pytest", "tests/test_a.py", "-v"),
            ("pytest", "tests/test_a.py", "-v"),
        ]
        result = _batch_pytest(cmds)
        assert result == ("pytest", "tests/test_a.py", "-v")

    def test_extracts_only_py_files(self):
        cmds = [("pytest", "tests/test_a.py", "-v", "--tb=short")]
        result = _batch_pytest(cmds)
        assert result == ("pytest", "tests/test_a.py", "-v", "--tb=short")


class TestRunCommandExceptionPath:
    """Tests for run_command exception handling (exit_code=-2)."""

    def test_nonexistent_binary_returns_error(self, tmp_path):
        """Running a nonexistent binary hits the exception handler."""
        result = run_command(("__nonexistent_binary_xyz__",), cwd=tmp_path)
        assert result.success is False
        assert result.exit_code == -2
        assert result.stderr  # Should contain the error message
