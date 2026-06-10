"""Behavioral tests for plan-lock red-phase evidence capture."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.plan_lock import (
    RedPhaseCommandEvidence,
    RedPhaseEvidence,
    capture_red_phase_evidence,
    classify_red_exit_code,
)


def _write_project(tmp_path: Path, validate_commands: list[str]) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    validate_block = "\n".join(f"  - {command}" for command in validate_commands)
    manifest_path.write_text(
        f"""schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
  read:
    - tests/test_demo.py
validate:
{validate_block}
"""
    )
    return manifest_path


def _write_script(tmp_path: Path, name: str, body: str) -> str:
    scripts = tmp_path / "scripts"
    scripts.mkdir(exist_ok=True)
    path = scripts / name
    path.write_text(body)
    return path.relative_to(tmp_path).as_posix()


class TestClassifyRedExitCode:
    def test_exit_one_is_red(self) -> None:
        assert classify_red_exit_code(1) == "red"

    def test_exit_zero_is_not_red(self) -> None:
        assert classify_red_exit_code(0) == "not_red"

    def test_pytest_usage_internal_and_collection_errors_are_invalid(self) -> None:
        for exit_code in (2, 3, 4, 5):
            assert classify_red_exit_code(exit_code) == "invalid"

    def test_spawn_failures_and_other_nonzero_exits_are_invalid(self) -> None:
        for exit_code in (-2, -1, 99):
            assert classify_red_exit_code(exit_code) == "invalid"


class TestCaptureRedPhaseEvidence:
    def test_validate_command_exiting_one_records_red_evidence(
        self, tmp_path: Path
    ) -> None:
        script = _write_script(
            tmp_path,
            "red.py",
            "print('assertion failed before implementation')\n"
            "import sys\n"
            "sys.exit(1)\n",
        )
        manifest_path = _write_project(tmp_path, [f"python {script}"])

        evidence = capture_red_phase_evidence(manifest_path, tmp_path)

        assert isinstance(evidence, RedPhaseEvidence)
        assert evidence.red is True
        assert evidence.captured_at
        assert len(evidence.commands) == 1
        command = evidence.commands[0]
        assert isinstance(command, RedPhaseCommandEvidence)
        assert command.command == f"python {script}"
        assert command.exit_code == 1
        assert command.classification == "red"
        assert "assertion failed before implementation" in command.output_tail
        assert evidence.to_payload()["commands"][0]["classification"] == "red"

    def test_validate_command_exiting_two_is_invalid_not_red(
        self, tmp_path: Path
    ) -> None:
        script = _write_script(
            tmp_path,
            "collection_error.py",
            "print('pytest collection error pass-off')\n"
            "import sys\n"
            "sys.exit(2)\n",
        )
        manifest_path = _write_project(tmp_path, [f"python {script}"])

        evidence = capture_red_phase_evidence(manifest_path, tmp_path)

        assert evidence.red is False
        assert evidence.commands[0].exit_code == 2
        assert evidence.commands[0].classification == "invalid"

    def test_validate_command_exiting_zero_is_not_red(self, tmp_path: Path) -> None:
        script = _write_script(
            tmp_path,
            "green.py",
            "print('tests already pass')\n",
        )
        manifest_path = _write_project(tmp_path, [f"python {script}"])

        evidence = capture_red_phase_evidence(manifest_path, tmp_path)

        assert evidence.red is False
        assert evidence.commands[0].exit_code == 0
        assert evidence.commands[0].classification == "not_red"

    def test_invalid_command_prevents_aggregate_red(self, tmp_path: Path) -> None:
        red_script = _write_script(
            tmp_path,
            "red.py",
            "import sys\nsys.exit(1)\n",
        )
        invalid_script = _write_script(
            tmp_path,
            "invalid.py",
            "import sys\nsys.exit(2)\n",
        )
        manifest_path = _write_project(
            tmp_path,
            [f"python {red_script}", f"python {invalid_script}"],
        )

        evidence = capture_red_phase_evidence(manifest_path, tmp_path)

        assert evidence.red is False
        assert [command.classification for command in evidence.commands] == [
            "red",
            "invalid",
        ]

    def test_output_tail_keeps_only_final_twenty_combined_lines(
        self, tmp_path: Path
    ) -> None:
        body = "\n".join(f"print('line-{index:02d}')" for index in range(1, 26))
        script = _write_script(
            tmp_path,
            "long_output.py",
            f"{body}\nimport sys\nsys.exit(1)\n",
        )
        manifest_path = _write_project(tmp_path, [f"python {script}"])

        evidence = capture_red_phase_evidence(manifest_path, tmp_path)

        assert evidence.commands[0].output_tail.splitlines() == [
            f"line-{index:02d}" for index in range(6, 26)
        ]
