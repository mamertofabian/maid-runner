"""Behavioral contract for optimized exact artifact-coverage equivalence."""

from __future__ import annotations

from pathlib import Path

import yaml

from maid_runner.core._runtime_command_executor import (
    RuntimeCommandRecord,
    RuntimeFileExecution,
)
from maid_runner.core.manifest import load_manifest


class _ExactExecutor:
    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self,
        command,
        target_files,
        project_root,
        timeout_seconds,
        environment_overrides=None,
        environment_removals=(),
    ) -> RuntimeCommandRecord:
        target = str((self.root / "src/target.py").resolve())
        return RuntimeCommandRecord(
            command=tuple(command),
            returncode=0,
            stdout="",
            stderr="",
            execution_data={
                target: RuntimeFileExecution(
                    executed_lines=frozenset({2}),
                    called_qualnames=frozenset({"target"}),
                )
            },
            report_errors=(),
        )


def test_exact_single_and_batch_reports_share_provenance_and_payload(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import (
        run_artifact_coverage,
        run_artifact_coverage_batch,
    )

    manifest = _write_manifest_project(tmp_path)
    executor = _ExactExecutor(tmp_path)

    single = run_artifact_coverage(manifest, tmp_path, executor=executor)
    batched = run_artifact_coverage_batch(
        [manifest],
        tmp_path,
        executor=executor,
        jobs=1,
    )[manifest.source_path]

    assert single.provenance == "exact"
    assert batched.provenance == "exact"
    assert single.to_dict() == batched.to_dict()


def test_sysmon_coverage_keeps_instrumentation_observable_until_pytest_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    target = tmp_path / "target_module.py"
    target.write_text("def target() -> bool:\n    return True\n")
    (tmp_path / "test_target_module.py").write_text(
        "import sys\n"
        "from target_module import target\n\n"
        "def test_target_runs_under_observable_instrumentation():\n"
        "    assert target() is True\n"
        "    assert sys.getprofile() is not None\n"
    )
    monkeypatch.setenv("COVERAGE_CORE", "sysmon")

    record = SubprocessRuntimeCommandExecutor().execute(
        ("-p", "no:cacheprovider", "-q", "test_target_module.py"),
        {str(target.resolve())},
        tmp_path,
        120.0,
    )

    assert record.returncode == 0, f"{record.stdout}\n{record.stderr}"
    assert not record.report_errors
    assert "target" in record.execution_data[str(target.resolve())].called_qualnames


def _write_manifest_project(root: Path):
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/target.py").write_text("def target() -> bool:\n    return True\n")
    (root / "tests/test_target.py").write_text(
        "from src.target import target\n\n"
        "def test_target():\n"
        "    assert target() is True\n"
    )
    payload = {
        "schema": "2",
        "goal": "Exercise exact coverage equivalence",
        "type": "fix",
        "created": "2026-08-13T12:45:00Z",
        "files": {
            "edit": [
                {
                    "path": "src/target.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "target",
                            "args": [],
                            "returns": "bool",
                        }
                    ],
                }
            ],
            "read": ["tests/test_target.py"],
        },
        "validate": ["python -m pytest -q tests/test_target.py"],
    }
    path = root / "manifests/target.manifest.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return load_manifest(path)
