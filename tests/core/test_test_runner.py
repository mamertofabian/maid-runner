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
from maid_runner.core.result import ErrorCode, TestRunResult
from maid_runner.core.types import TestStream


def _write_noop_behavioral_test_project(tmp_path, slug: str = "noop-gate"):
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir(exist_ok=True)
    src_dir = tmp_path / "src"
    src_dir.mkdir(exist_ok=True)
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    (src_dir / "gate.py").write_text("def gate() -> str:\n    return 'ok'\n")
    (tests_dir / "test_gate.py").write_text(
        "from src.gate import gate\n\ndef test_gate():\n    assert gate() == 'not ok'\n"
    )
    manifest_path = manifests_dir / f"{slug}.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Reject no-op test command"
type: fix
files:
  edit:
    - path: src/gate.py
      artifacts:
        - kind: function
          name: gate
  read:
    - tests/test_gate.py
validate:
  - python -c "raise SystemExit(0)"
"""
    )
    return manifest_path


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

    def test_run_manifest_tests_rejects_noop_validate_command_for_behavioral_tests(
        self, tmp_path
    ):
        manifest = _write_noop_behavioral_test_project(tmp_path)

        result = run_manifest_tests(manifest, project_root=tmp_path)

        assert result.success is False
        assert result.total == 0
        assert [error.code for error in result.chain_errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]

    def test_run_manifest_tests_ignores_ambient_pytest_addopts(
        self, tmp_path, monkeypatch
    ):
        manifest = tmp_path / "manifests" / "ambient.manifest.yaml"
        manifest.parent.mkdir()
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (src_dir / "gate.py").write_text("def gate() -> str:\n    return 'ok'\n")
        (tests_dir / "test_gate.py").write_text(
            "from src.gate import gate\n\n"
            "def test_gate():\n"
            "    assert gate() == 'not ok'\n\n"
            "def test_other():\n"
            "    assert gate() == 'ok'\n"
        )
        manifest.write_text(
            """schema: "2"
goal: "Run pytest without ambient selectors"
type: fix
files:
  edit:
    - path: src/gate.py
      artifacts:
        - kind: function
          name: gate
  read:
    - tests/test_gate.py
validate:
  - python -m pytest tests -q
"""
        )
        monkeypatch.setenv("PYTEST_ADDOPTS", "-ktest_other")

        result = run_manifest_tests(manifest, project_root=tmp_path)

        assert result.success is False
        assert result.total == 1
        assert result.failed == 1
        assert "test_gate" in result.results[0].stdout


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

    def test_run_tests_rejects_noop_validate_command_for_behavioral_tests(
        self, tmp_path
    ):
        _write_noop_behavioral_test_project(tmp_path)

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is False
        assert result.total == 0
        assert [error.code for error in result.chain_errors] == [
            ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
        ]


class TestBatchMode:
    def test_default_auto_batches_compatible_pytest_commands(self, tmp_path):
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
        assert result.total == 1
        assert result.results[0].manifest_slug == "batch"
        assert result.results[0].command == (
            "pytest",
            "tests/test_a.py",
            "tests/test_b.py",
            "-v",
        )

    def test_batch_combines_pytest_commands(self, tmp_path):
        """Multiple pytest commands batched into single invocation."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
type: snapshot
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

    def test_default_batches_compatible_subset_with_mixed_commands(self, tmp_path):
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
        (manifests_dir / "c.manifest.yaml").write_text(
            """schema: "2"
goal: "C"
files:
  create:
    - path: src/c.py
      artifacts:
        - kind: function
          name: c
validate:
  - echo c-passed
"""
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.total == 2
        assert result.results[0].manifest_slug == "batch"
        assert result.results[0].command == (
            "pytest",
            "tests/test_a.py",
            "tests/test_b.py",
            "-v",
        )
        assert result.results[1].command == ("echo", "c-passed")

    def test_default_batches_uv_wrapped_pytest_commands(self, tmp_path):
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
  - uv run pytest tests/test_a.py -v
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
  - uv run pytest tests/test_b.py -v
"""
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.total == 1
        assert result.results[0].manifest_slug == "batch"
        assert result.results[0].command == (
            "uv",
            "run",
            "pytest",
            "tests/test_a.py",
            "tests/test_b.py",
            "-v",
        )

    def test_default_prunes_directory_pytest_target_when_focused_targets_exist(
        self, tmp_path, monkeypatch
    ):
        (tmp_path / "uv.lock").write_text("")
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
  - pytest tests/ -v
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
  - python -m pytest tests/test_a.py -q
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 1
        assert observed == [("python", "-m", "pytest", "tests/test_a.py", "-q")]

    def test_default_runs_duplicate_implementation_commands_once(
        self, tmp_path, monkeypatch
    ):
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
  - echo shared-validation
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
  - echo shared-validation
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 1
        assert observed == [("echo", "shared-validation")]

    def test_default_batches_pytest_commands_with_only_verbosity_differences(
        self, tmp_path, monkeypatch
    ):
        (tmp_path / "uv.lock").write_text("")
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
  - python -m pytest tests/test_b.py -q
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 1
        assert observed == [("pytest", "tests/test_a.py", "tests/test_b.py")]

    def test_default_keeps_same_pytest_target_with_behavior_option_difference(
        self, tmp_path, monkeypatch
    ):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
type: snapshot
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest tests/test_a.py --lf
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
type: snapshot
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest tests/test_a.py
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 2
        assert observed == [
            ("pytest", "tests/test_a.py", "--lf"),
            ("pytest", "tests/test_a.py"),
        ]

    def test_default_keeps_pytest_fail_fast_commands_separate(
        self, tmp_path, monkeypatch
    ):
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
  - pytest tests/test_a.py -x
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
type: snapshot
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest tests/test_b.py -x
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 2
        assert observed == [
            ("pytest", "tests/test_a.py", "-x"),
            ("pytest", "tests/test_b.py", "-x"),
        ]

    def test_default_keeps_duplicate_stateful_pytest_commands_separate(
        self, tmp_path, monkeypatch
    ):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
type: snapshot
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest tests/test_a.py --lf
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
type: snapshot
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest tests/test_a.py --lf
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 2
        assert observed == [
            ("pytest", "tests/test_a.py", "--lf"),
            ("pytest", "tests/test_a.py", "--lf"),
        ]

    def test_default_keeps_duplicate_unknown_pytest_state_alias_commands_separate(
        self, tmp_path, monkeypatch
    ):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
type: snapshot
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest tests/test_a.py --last-failed
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
type: snapshot
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest tests/test_a.py --last-failed
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 2
        assert observed == [
            ("pytest", "tests/test_a.py", "--last-failed"),
            ("pytest", "tests/test_a.py", "--last-failed"),
        ]

    def test_default_keeps_same_pytest_target_with_different_interpreters(
        self, tmp_path, monkeypatch
    ):
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
  - python3.11 -m pytest tests/test_a.py
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
  - python3.12 -m pytest tests/test_a.py
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 2
        assert observed == [
            ("python3.11", "-m", "pytest", "tests/test_a.py"),
            ("python3.12", "-m", "pytest", "tests/test_a.py"),
        ]

    def test_default_executes_simple_maid_validate_commands_in_process(
        self, tmp_path, monkeypatch
    ):
        manifests_dir = tmp_path / "manifests"
        contracts_dir = tmp_path / "contracts"
        src_dir = tmp_path / "src"
        manifests_dir.mkdir()
        contracts_dir.mkdir()
        src_dir.mkdir()
        (src_dir / "target.py").write_text("def target():\n    return None\n")
        (src_dir / "driver.py").write_text("def driver():\n    return None\n")
        (contracts_dir / "target.manifest.yaml").write_text(
            """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - echo target
"""
        )
        (manifests_dir / "driver.manifest.yaml").write_text(
            """schema: "2"
goal: "Driver"
type: snapshot
files:
  snapshot:
    - path: src/driver.py
      artifacts:
        - kind: function
          name: driver
          args: []
          returns: "None"
validate:
  - uv run maid validate contracts/target.manifest.yaml
"""
        )

        def fail_if_subprocess_runner_is_used(command, **kwargs):
            raise AssertionError(f"unexpected subprocess command: {command}")

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command",
            fail_if_subprocess_runner_is_used,
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 1
        assert result.results[0].command == (
            "uv",
            "run",
            "maid",
            "validate",
            "contracts/target.manifest.yaml",
        )

    def test_default_executes_simple_maid_validate_without_existing_chain_dir(
        self, tmp_path, monkeypatch
    ):
        manifests_dir = tmp_path / "manifests"
        contracts_dir = tmp_path / "contracts"
        src_dir = tmp_path / "src"
        manifests_dir.mkdir()
        contracts_dir.mkdir()
        src_dir.mkdir()
        (src_dir / "target.py").write_text("def target():\n    return None\n")
        (src_dir / "driver.py").write_text("def driver():\n    return None\n")
        (contracts_dir / "target.manifest.yaml").write_text(
            """schema: "2"
goal: "Target"
type: snapshot
files:
  snapshot:
    - path: src/target.py
      artifacts:
        - kind: function
          name: target
          args: []
          returns: "None"
validate:
  - echo target
"""
        )
        (manifests_dir / "driver.manifest.yaml").write_text(
            """schema: "2"
goal: "Driver"
type: snapshot
files:
  snapshot:
    - path: src/driver.py
      artifacts:
        - kind: function
          name: driver
          args: []
          returns: "None"
validate:
  - uv run maid validate contracts/target.manifest.yaml --manifest-dir missing-manifests
"""
        )

        def fail_if_subprocess_runner_is_used(command, **kwargs):
            raise AssertionError(f"unexpected subprocess command: {command}")

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command",
            fail_if_subprocess_runner_is_used,
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.success is True
        assert result.total == 1
        assert result.results[0].command == (
            "uv",
            "run",
            "maid",
            "validate",
            "contracts/target.manifest.yaml",
            "--manifest-dir",
            "missing-manifests",
        )

    def test_default_batches_compatible_vitest_commands(self, tmp_path, monkeypatch):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
type: snapshot
files:
  create:
    - path: src/a.ts
      artifacts:
        - kind: function
          name: a
validate:
  - npx vitest run tests/test_a.test.ts --reporter=verbose
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.ts
      artifacts:
        - kind: function
          name: b
validate:
  - npx vitest run tests/test_b.test.ts --reporter=verbose
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.total == 1
        assert result.results[0].manifest_slug == "batch"
        assert observed == [
            (
                "npx",
                "vitest",
                "run",
                "tests/test_a.test.ts",
                "tests/test_b.test.ts",
                "--reporter=verbose",
            )
        ]

    def test_default_does_not_batch_unknown_vitest_value_flags(
        self, tmp_path, monkeypatch
    ):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
type: snapshot
files:
  create:
    - path: src/a.ts
      artifacts:
        - kind: function
          name: a
validate:
  - npx vitest run tests/test_a.test.ts --shard=1/2
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
type: snapshot
files:
  create:
    - path: src/b.ts
      artifacts:
        - kind: function
          name: b
validate:
  - npx vitest run tests/test_b.test.ts --shard=1/2
"""
        )
        observed: list[tuple[str, ...]] = []

        def fake_run_command(command, **kwargs):
            observed.append(command)
            return TestRunResult(
                manifest_slug=kwargs.get("manifest_slug", ""),
                command=command,
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1.0,
                stream=kwargs.get("stream", TestStream.IMPLEMENTATION),
            )

        monkeypatch.setattr(
            "maid_runner.core.test_runner.run_command", fake_run_command
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.total == 2
        assert observed == [
            ("npx", "vitest", "run", "tests/test_a.test.ts", "--shard=1/2"),
            ("npx", "vitest", "run", "tests/test_b.test.ts", "--shard=1/2"),
        ]

        observed.clear()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.ts
      artifacts:
        - kind: function
          name: a
validate:
  - npx vitest run tests/test_a.test.ts --allowOnly
"""
        )
        (manifests_dir / "b.manifest.yaml").write_text(
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.ts
      artifacts:
        - kind: function
          name: b
validate:
  - npx vitest run tests/test_b.test.ts --allowOnly
"""
        )

        result = run_tests(manifest_dir="manifests/", project_root=tmp_path)

        assert result.total == 2
        assert observed == [
            ("npx", "vitest", "run", "tests/test_a.test.ts", "--allowOnly"),
            ("npx", "vitest", "run", "tests/test_b.test.ts", "--allowOnly"),
        ]

    def test_complex_pytest_commands_are_not_batched(self, tmp_path):
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "a.manifest.yaml").write_text(
            """schema: "2"
goal: "A"
type: snapshot
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
type: snapshot
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

    def test_uv_run_pytest(self):
        assert _can_batch([("uv", "run", "pytest", "tests/test_a.py", "-v")]) is True

    def test_uv_run_python_m_pytest(self):
        assert (
            _can_batch(
                [("uv", "run", "python", "-m", "pytest", "tests/test_a.py", "-v")]
            )
            is True
        )

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

    def test_preserves_uv_run_prefix(self):
        cmds = [
            ("uv", "run", "pytest", "tests/test_a.py", "-v"),
            ("uv", "run", "pytest", "tests/test_b.py", "-v"),
        ]
        result = _batch_pytest(cmds)
        assert result == (
            "uv",
            "run",
            "pytest",
            "tests/test_a.py",
            "tests/test_b.py",
            "-v",
        )


class TestRunCommandExceptionPath:
    """Tests for run_command exception handling (exit_code=-2)."""

    def test_nonexistent_binary_returns_error(self, tmp_path):
        """Running a nonexistent binary hits the exception handler."""
        result = run_command(("__nonexistent_binary_xyz__",), cwd=tmp_path)
        assert result.success is False
        assert result.exit_code == -2
        assert result.stderr  # Should contain the error message
