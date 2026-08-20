"""Behavioral coverage for bounded repository manifest-test execution."""

import inspect
from pathlib import Path

import pytest

from maid_runner.core.result import TestRunResult
from maid_runner.core.test_runner import run_command, run_tests
from maid_runner.core.types import TestStream


def test_manifest_test_commands_use_release_safe_bounded_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("def main() -> str:\n    return 'ok'\n")
    test_file = tmp_path / "tests" / "test_app.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "from src.app import main\n\n"
        "def test_main():\n"
        "    assert main() == 'ok'\n"
    )
    manifest = tmp_path / "manifests" / "bounded-timeout.manifest.yaml"
    manifest.parent.mkdir()
    manifest.write_text(
        """schema: "2"
goal: Exercise a bounded manifest test command
type: fix
files:
  edit:
  - path: src/app.py
    artifacts:
    - kind: function
      name: main
  read:
  - tests/test_app.py
validate:
- python -m pytest -q tests/test_app.py
"""
    )
    other_source = tmp_path / "src" / "other.py"
    other_source.write_text("def other() -> str:\n    return 'ok'\n")
    other_test = tmp_path / "tests" / "test_other.py"
    other_test.write_text(
        "from src.other import other\n\n"
        "def test_other():\n"
        "    assert other() == 'ok'\n"
    )
    other_manifest = tmp_path / "manifests" / "other-timeout.manifest.yaml"
    other_manifest.write_text(
        """schema: "2"
goal: Exercise a second compatible manifest test command
type: fix
files:
  edit:
  - path: src/other.py
    artifacts:
    - kind: function
      name: other
  read:
  - tests/test_other.py
validate:
- python -m pytest -q tests/test_other.py
"""
    )
    observed_timeouts: list[int] = []
    observed_commands: list[tuple[str, ...]] = []

    def execute(
        command: tuple[str, ...],
        *,
        cwd: str | Path = ".",
        timeout: int = 300,
        manifest_slug: str = "",
        stream: TestStream = TestStream.IMPLEMENTATION,
        environment_overrides: dict[str, str] | None = None,
    ) -> TestRunResult:
        observed_timeouts.append(timeout)
        observed_commands.append(command)
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
            stream=stream,
        )

    monkeypatch.setattr("maid_runner.core.test_runner.run_command", execute)

    result = run_tests(manifest_dir="manifests", project_root=tmp_path, jobs=1)

    assert result.success is True
    assert observed_timeouts == [600]
    assert len(observed_commands) == 1
    assert "tests/test_app.py" in observed_commands[0]
    assert "tests/test_other.py" in observed_commands[0]
    assert inspect.signature(run_command).parameters["timeout"].default == 300
