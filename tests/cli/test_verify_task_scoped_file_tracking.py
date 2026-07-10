"""Behavioral contract for incremental brownfield file tracking in verify."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

from maid_runner.core.result import (
    FileTrackingEntry,
    FileTrackingReport,
    FileTrackingStatus,
)


def _git(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_brownfield_project(project_root: Path) -> str:
    (project_root / "manifests").mkdir()
    (project_root / "src").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "src" / "legacy.py").write_text(
        "def legacy() -> str:\n    return 'historical'\n"
    )
    (project_root / "src" / "current.py").write_text(
        "def current() -> str:\n" "    value = 'before'\n" "    return value\n"
    )
    (project_root / "tests" / "test_current.py").write_text(
        "from src.current import current\n\n\n"
        "def test_current_contract():\n"
        "    assert current() == 'after'\n"
    )
    manifest = {
        "schema": "2",
        "goal": "Change one covered file in a brownfield repository",
        "type": "fix",
        "created": "2026-07-09T22:24:43Z",
        "files": {
            "edit": [
                {
                    "path": "src/current.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "current",
                            "args": [],
                            "returns": "str",
                        }
                    ],
                }
            ],
            "read": ["tests/test_current.py"],
        },
        "validate": ["python -m pytest -q tests/test_current.py"],
    }
    (project_root / "manifests" / "current-task.manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False)
    )
    _git(project_root, "init", "-q")
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-q", "-m", "brownfield baseline")
    baseline = _git(project_root, "rev-parse", "HEAD")
    (project_root / "src" / "current.py").write_text(
        "def current() -> str:\n" "    value = 'after'\n" "    return value\n"
    )
    return baseline


def _stages(capsys) -> dict[str, dict]:
    payload = json.loads(capsys.readouterr().out)
    return {stage["name"]: stage for stage in payload["stages"]}


def _commit_task_change(project_root: Path) -> None:
    _git(project_root, "add", "src/current.py")
    _git(project_root, "commit", "-q", "-m", "covered task change")


def test_filter_file_tracking_report_keeps_only_normalized_task_paths() -> None:
    from maid_runner.core._file_tracking import filter_file_tracking_report

    report = FileTrackingReport(
        entries=(
            FileTrackingEntry(
                path="src/legacy.py", status=FileTrackingStatus.UNDECLARED
            ),
            FileTrackingEntry(
                path="src\\context.py",
                status=FileTrackingStatus.REGISTERED,
                manifests=("current-task",),
                issues=("Only in readonlyFiles",),
            ),
            FileTrackingEntry(
                path="src/current.py",
                status=FileTrackingStatus.TRACKED,
                manifests=("current-task",),
            ),
        )
    )

    filtered = filter_file_tracking_report(
        report, {"src\\current.py", "src/context.py"}
    )

    assert filtered.entries == report.entries[1:]


def test_repository_file_tracking_remains_strict_by_default(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    baseline = _write_brownfield_project(tmp_path)

    exit_code = main(
        [
            "verify",
            "--since",
            baseline,
            "--keep-going",
            "--json",
        ]
    )

    stages = _stages(capsys)
    assert exit_code == 1
    assert stages["file_tracking"]["success"] is False
    assert "src/legacy.py" in stages["file_tracking"]["details"]["undeclared"]


def test_task_scoped_file_tracking_ignores_untouched_historical_inventory(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.verify import cmd_verify

    os.chdir(tmp_path)
    baseline = _write_brownfield_project(tmp_path)
    _commit_task_change(tmp_path)

    args = build_parser().parse_args(
        [
            "verify",
            "--file-tracking-scope",
            "task",
            "--since",
            baseline,
            "--keep-going",
            "--json",
        ]
    )

    exit_code = cmd_verify(args)

    stages = _stages(capsys)
    assert exit_code == 0
    assert stages["file_tracking"]["success"] is True
    assert "src/legacy.py" not in stages["file_tracking"]["details"]["undeclared"]
    assert "src/current.py" in stages["file_tracking"]["details"]["tracked"]


def test_task_scoped_file_tracking_accepts_explicit_base_ref(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    baseline = _write_brownfield_project(tmp_path)
    _commit_task_change(tmp_path)

    exit_code = main(
        [
            "verify",
            "--file-tracking-scope",
            "task",
            "--base-ref",
            baseline,
            "--keep-going",
            "--json",
        ]
    )

    stages = _stages(capsys)
    assert exit_code == 0
    assert stages["file_tracking"]["success"] is True
    assert "src/current.py" in stages["file_tracking"]["details"]["tracked"]


def test_task_scoped_file_tracking_accepts_manifest_metadata_baseline(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    baseline = _write_brownfield_project(tmp_path)
    manifest_path = tmp_path / "manifests" / "current-task.manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["metadata"] = {"maid_task_base": baseline}
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    exit_code = main(
        [
            "verify",
            "--file-tracking-scope",
            "task",
            "--no-changed-scope",
            "--keep-going",
            "--json",
        ]
    )

    stages = _stages(capsys)
    assert exit_code == 0
    assert stages["file_tracking"]["success"] is True
    assert "src/current.py" in stages["file_tracking"]["details"]["tracked"]


def test_task_scoped_file_tracking_blocks_new_undeclared_source_even_when_changed_scope_is_disabled(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    baseline = _write_brownfield_project(tmp_path)
    (tmp_path / "src" / "new_uncovered.py").write_text("value = 'new'\n")

    exit_code = main(
        [
            "verify",
            "--file-tracking-scope",
            "task",
            "--since",
            baseline,
            "--advisory",
            "--no-changed-scope",
            "--keep-going",
            "--json",
        ]
    )

    stages = _stages(capsys)
    assert exit_code == 1
    assert stages["file_tracking"]["success"] is False
    assert "src/new_uncovered.py" in (stages["file_tracking"]["details"]["undeclared"])
    assert "src/legacy.py" not in stages["file_tracking"]["details"]["undeclared"]


def test_task_scoped_file_tracking_blocks_changed_read_only_production_file(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    baseline = _write_brownfield_project(tmp_path)
    context_path = "src/new_context.py"
    (tmp_path / context_path).write_text("value = 'context'\n")
    manifest_path = tmp_path / "manifests" / "current-task.manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["files"]["read"].append(context_path)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    exit_code = main(
        [
            "verify",
            "--file-tracking-scope",
            "task",
            "--since",
            baseline,
            "--no-changed-scope",
            "--keep-going",
            "--json",
        ]
    )

    stages = _stages(capsys)
    assert exit_code == 1
    assert stages["file_tracking"]["success"] is False
    assert context_path in stages["file_tracking"]["details"]["registered"]
    assert "src/legacy.py" not in stages["file_tracking"]["details"]["undeclared"]


def test_task_scoped_file_tracking_fails_closed_without_resolvable_baseline(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_brownfield_project(tmp_path)

    exit_code = main(
        [
            "verify",
            "--file-tracking-scope",
            "task",
            "--no-changed-scope",
            "--keep-going",
            "--json",
        ]
    )

    stages = _stages(capsys)
    assert exit_code == 1
    errors = stages["file_tracking"]["details"]["errors"]
    assert errors[0]["code"] == "E115"


def test_task_scoped_file_tracking_reports_invalid_explicit_baseline(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_brownfield_project(tmp_path)

    exit_code = main(
        [
            "verify",
            "--file-tracking-scope",
            "task",
            "--since",
            "definitely-missing-baseline",
            "--no-changed-scope",
            "--keep-going",
            "--json",
        ]
    )

    stages = _stages(capsys)
    assert exit_code == 1
    errors = stages["file_tracking"]["details"]["errors"]
    assert errors[0]["code"] == "E116"


def test_readme_documents_task_scoped_file_tracking_recipe() -> None:
    readme = Path("README.md").read_text()

    assert "--file-tracking-scope task" in readme
    assert "repository-wide file tracking remains the default" in readme
    assert "maid files" in readme
    assert "full repository inventory" in readme
