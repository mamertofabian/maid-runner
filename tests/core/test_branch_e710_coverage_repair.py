"""Behavioral contract for branch-introduced E710 coverage repair."""

from __future__ import annotations

from pathlib import Path

import yaml

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


def test_methodless_class_has_no_runtime_body_obligation(tmp_path: Path) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source="class ValueRecord:\n    label: str\n",
        artifacts=[
            {"kind": "class", "name": "ValueRecord"},
            {
                "kind": "attribute",
                "name": "label",
                "of": "ValueRecord",
                "type": "str",
            },
        ],
    )

    report = run_artifact_coverage(
        load_manifest(manifest_path),
        tmp_path,
        executor=_FailIfCalledExecutor(),
    )

    assert report.success is True
    assert report.findings == ()
    assert report.errors == ()


def test_class_with_declared_method_still_requires_runtime_execution(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage

    manifest_path = _write_project(
        tmp_path,
        source=(
            "class Service:\n" "    def run(self) -> str:\n" "        return 'ran'\n"
        ),
        artifacts=[
            {"kind": "class", "name": "Service"},
            {
                "kind": "method",
                "name": "run",
                "of": "Service",
                "args": [],
                "returns": "str",
            },
        ],
    )

    report = run_artifact_coverage(
        load_manifest(manifest_path),
        tmp_path,
        executor=_EmptyExecutionExecutor(),
    )

    assert report.success is False
    assert [finding.executed for finding in report.findings] == [False, False]
    assert [error.code for error in report.errors] == [
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
    ]


class _FailIfCalledExecutor:
    def execute(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("methodless classes must not launch runtime coverage")


class _EmptyExecutionExecutor:
    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
    ) -> object:
        from maid_runner.core._runtime_command_executor import RuntimeCommandRecord

        del target_files, project_root, timeout_seconds
        return RuntimeCommandRecord(
            command=command,
            returncode=0,
            stdout="",
            stderr="",
            execution_data={},
            report_errors=(),
        )


def _write_project(
    root: Path,
    *,
    source: str,
    artifacts: list[dict[str, object]],
) -> Path:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "target.py").write_text(source, encoding="utf-8")
    (root / "tests" / "test_target.py").write_text(
        "def test_contract():\n    assert True\n",
        encoding="utf-8",
    )
    manifest_path = root / "manifests" / "contract.manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Exercise the class runtime coverage boundary",
                "type": "fix",
                "created": "2026-08-14T00:00:00Z",
                "files": {
                    "edit": [
                        {"path": "src/target.py", "artifacts": artifacts},
                    ],
                    "read": ["tests/test_target.py"],
                },
                "validate": ["python -m pytest -q tests/test_target.py"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return manifest_path
