"""Behavioral tests for the `maid evaluate run` CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import build_parser, main


def test_evaluate_run_text_and_json_render_same_evaluation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    from maid_runner.cli.commands.evaluate import cmd_evaluate

    monkeypatch.chdir(tmp_path)
    manifest_path = _write_manifest(tmp_path)
    _write_lock(tmp_path, red_evidence=_valid_red_evidence())

    assert main(["evaluate", "run", str(manifest_path)]) == 0
    text = capsys.readouterr().out

    assert main(["evaluate", "run", str(manifest_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["manifest_slug"] == "demo-task"
    assert f"Manifest: {payload['manifest_path']}" in text
    assert f"Red evidence: {payload['red_evidence_status']}" in text
    assert f"Incidents: {payload['incidents_total']}" in text
    assert payload["findings"]
    assert payload["findings"][0]["summary"] in text

    parser = build_parser()
    args = parser.parse_args(["evaluate", "run", str(manifest_path), "--quiet"])
    assert args.command == "evaluate"
    assert args.evaluate_command == "run"
    assert args.quiet is True
    assert callable(cmd_evaluate)


def test_evaluate_run_exits_zero_despite_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = _write_manifest(tmp_path)
    _write_lock(tmp_path, red_evidence={"red": False, "commands": []})

    assert main(["evaluate", "run", str(manifest_path)]) == 0
    output = capsys.readouterr().out
    assert "warning" in output
    assert "invalid" in output


def test_evaluate_run_malformed_lock_exits_zero_with_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = _write_manifest(tmp_path)
    lock_path = tmp_path / ".maid" / "plan-locks" / "demo-task.lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("{not json", encoding="utf-8")

    assert main(["evaluate", "run", str(manifest_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["lock_present"] is True
    assert payload["red_evidence_status"] == "invalid"
    assert any(
        finding["category"] == "red-evidence"
        and "unreadable" in finding["summary"].lower()
        for finding in payload["findings"]
    )


def test_evaluate_run_missing_manifest_fails_loud_with_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "manifests" / "missing.manifest.yaml"

    assert main(["evaluate", "run", str(missing)]) == 2
    assert str(missing) in capsys.readouterr().err


def test_evaluate_run_project_root_resolves_relative_manifest_from_other_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    project_root = tmp_path / "project"
    other_cwd = tmp_path / "outside"
    other_cwd.mkdir()
    manifest_path = _write_manifest(project_root)
    _write_lock(project_root, red_evidence=_valid_red_evidence())
    monkeypatch.chdir(other_cwd)

    assert (
        main(
            [
                "evaluate",
                "run",
                "manifests/demo-task.manifest.yaml",
                "--project-root",
                str(project_root),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert (
        payload["manifest_path"] == manifest_path.relative_to(project_root).as_posix()
    )
    assert payload["manifest_slug"] == "demo-task"


def test_evaluate_run_quiet_drops_info_from_text_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = _write_manifest(tmp_path)
    _write_lock(tmp_path, red_evidence=_valid_red_evidence())

    assert main(["evaluate", "run", str(manifest_path), "--quiet"]) == 0
    text = capsys.readouterr().out
    assert "info" not in text

    assert main(["evaluate", "run", str(manifest_path), "--quiet", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(finding["severity"] == "info" for finding in payload["findings"])


def test_readme_documents_evaluate_command() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "| `maid evaluate run <manifest>` |" in readme
    assert "after-action" in readme


def _write_manifest(project_root: Path) -> Path:
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "2",
        "goal": "Demo task",
        "type": "feature",
        "created": "2026-07-06T00:00:00Z",
        "files": {
            "create": [
                {
                    "path": "src/demo.py",
                    "artifacts": [{"kind": "function", "name": "demo"}],
                }
            ],
            "read": ["tests/test_demo.py"],
        },
        "validate": ["uv run pytest -q tests/test_demo.py"],
    }
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return manifest_path


def _write_lock(project_root: Path, *, red_evidence: dict) -> None:
    lock_path = project_root / ".maid" / "plan-locks" / "demo-task.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "manifest_path": "manifests/demo-task.manifest.yaml",
                "manifest_hash": "hash",
                "test_hashes": {},
                "created_at": "2026-07-06T00:00:00Z",
                "revision": 1,
                "revisions": [
                    {
                        "prior_manifest_hash": "old",
                        "prior_test_hashes": {},
                        "revised_at": "2026-07-06T00:00:00Z",
                        "reason": "add test",
                        "agent": None,
                        "contract_delta": {
                            "artifacts_added": ["src/demo.py:function:demo"],
                            "artifacts_removed": [],
                            "files_added": [],
                            "files_removed": [],
                            "validate_commands_added": [],
                            "validate_commands_removed": [],
                        },
                    }
                ],
                "red_evidence": red_evidence,
                "agent": {"model": "gpt-5-codex", "source": "flags"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _valid_red_evidence() -> dict:
    return {
        "red": True,
        "captured_at": "2026-07-06T00:00:00Z",
        "commands": [
            {
                "command": "uv run pytest -q tests/test_demo.py",
                "exit_code": 1,
                "output_tail": "assert 1 == 2",
                "classification": "red",
            }
        ],
    }
