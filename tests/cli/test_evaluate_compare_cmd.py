"""Behavioral tests for the `maid evaluate compare` CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import build_parser, main


def test_evaluate_compare_renders_grouped_table_with_unknown_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        tmp_path,
        "codex-run",
        agent={"model": "gpt-5-codex", "provider": "openai", "client": "codex-cli"},
    )
    _write_manifest(tmp_path, "anonymous-run", agent=None)

    assert main(["evaluate", "compare", "--manifest-dir", str(manifest_dir)]) == 0
    output = capsys.readouterr().out

    header = output.splitlines()[0]
    assert header.startswith("runs ")
    assert "agent" in header
    assert "gpt-5-codex" in output
    assert "openai" in output
    assert "codex-cli" in output
    assert "(unknown agent)" in output


def test_evaluate_compare_reports_skipped_evidence_free_manifests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        tmp_path,
        "codex-run",
        agent={"model": "gpt-5-codex", "provider": "openai", "client": "codex-cli"},
    )
    _write_manifest(tmp_path, "evidence-free", outcome=False)

    assert main(["evaluate", "compare", "--manifest-dir", str(manifest_dir)]) == 0
    output = capsys.readouterr().out

    assert "skipped: 1" in output
    assert "evidence-free" not in output


def test_evaluate_compare_json_matches_text_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        tmp_path,
        "codex-run",
        agent={"model": "gpt-5-codex", "provider": "openai", "client": "codex-cli"},
    )
    _write_manifest(tmp_path, "anonymous-run", agent=None)

    assert main(["evaluate", "compare", "--manifest-dir", str(manifest_dir)]) == 0
    text = capsys.readouterr().out

    assert (
        main(["evaluate", "compare", "--manifest-dir", str(manifest_dir), "--json"])
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["skipped"] == 0
    assert payload["rows"] == [
        {
            "provider": None,
            "model": None,
            "client": None,
            "runs": 1,
            "outcomes_completed": 1,
            "outcomes_other": 0,
            "revisions_narrowing_total": 0,
            "revisions_unclassified_total": 0,
            "red_evidence_valid": 0,
            "incidents_total": 0,
        },
        {
            "provider": "openai",
            "model": "gpt-5-codex",
            "client": "codex-cli",
            "runs": 1,
            "outcomes_completed": 1,
            "outcomes_other": 0,
            "revisions_narrowing_total": 0,
            "revisions_unclassified_total": 0,
            "red_evidence_valid": 0,
            "incidents_total": 0,
        },
    ]
    assert "(unknown agent)" in text
    assert "gpt-5-codex" in text
    assert str(payload["rows"][0]["runs"]) in text


def test_evaluate_compare_project_root_resolves_default_manifest_dir_from_other_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_root = tmp_path / "project"
    other_cwd = tmp_path / "outside"
    other_cwd.mkdir()
    _write_manifest(
        project_root,
        "codex-run",
        agent={"model": "gpt-5-codex", "provider": "openai", "client": "codex-cli"},
    )
    monkeypatch.chdir(other_cwd)

    assert main(["evaluate", "compare", "--project-root", str(project_root)]) == 0
    output = capsys.readouterr().out

    assert "gpt-5-codex" in output
    assert "skipped: 0" in output


def test_evaluate_compare_relative_project_root_does_not_double_prefix_manifest_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_root = tmp_path / "project"
    _write_manifest(
        project_root,
        "relative-root-run",
        agent={"model": "gpt-5-codex", "provider": "openai", "client": "codex-cli"},
    )
    monkeypatch.chdir(tmp_path)

    assert main(["evaluate", "compare", "--project-root", "project"]) == 0
    captured = capsys.readouterr()

    assert "gpt-5-codex" in captured.out
    assert "skipped: 0" in captured.out
    assert captured.err == ""


def test_evaluate_compare_continues_past_unparseable_manifest_loudly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        tmp_path,
        "codex-run",
        agent={"model": "gpt-5-codex", "provider": "openai", "client": "codex-cli"},
    )
    broken = manifest_dir / "broken.manifest.yaml"
    broken.write_text("schema: [", encoding="utf-8")

    assert main(["evaluate", "compare", "--manifest-dir", str(manifest_dir)]) == 0
    captured = capsys.readouterr()

    assert "gpt-5-codex" in captured.out
    assert "skipped: 1" in captured.out
    assert str(broken) in captured.err


def test_evaluate_compare_missing_manifest_dir_fails_loud(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.evaluate import cmd_evaluate

    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "missing-manifests"

    assert main(["evaluate", "compare", "--manifest-dir", str(missing)]) == 2
    assert str(missing) in capsys.readouterr().err

    parser = build_parser()
    args = parser.parse_args(["evaluate", "compare", "--manifest-dir", str(missing)])
    assert args.command == "evaluate"
    assert args.evaluate_command == "compare"
    assert args.manifest_dir == str(missing)
    assert callable(cmd_evaluate)


def _write_manifest(
    project_root: Path,
    slug: str,
    *,
    agent: dict | None = None,
    outcome: bool = True,
) -> Path:
    manifest_path = project_root / "manifests" / f"{slug}.manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {
        "schema": "2",
        "goal": f"Demo task {slug}",
        "type": "feature",
        "created": "2026-07-06T00:00:00Z",
        "files": {
            "create": [
                {
                    "path": f"src/{slug}.py",
                    "artifacts": [{"kind": "function", "name": slug.replace("-", "_")}],
                }
            ],
            "read": [f"tests/test_{slug.replace('-', '_')}.py"],
        },
        "validate": [f"uv run pytest -q tests/test_{slug.replace('-', '_')}.py"],
    }
    if outcome:
        payload["outcome"] = {
            "status": "completed",
            "summary": "Done",
            "validation": [
                {
                    "command": [
                        "uv",
                        "run",
                        "pytest",
                        "-q",
                        f"tests/test_{slug.replace('-', '_')}.py",
                    ],
                    "status": "passed",
                    "summary": "focused tests passed",
                }
            ],
        }
        if agent is not None:
            payload["outcome"]["agent"] = agent
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return manifest_path
