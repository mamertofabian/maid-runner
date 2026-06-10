"""Behavioral tests for `maid recall --for-manifest`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_recall_parser_accepts_for_manifest_and_dispatches(
    tmp_path: Path,
    monkeypatch,
):
    from maid_runner.cli.commands import recall as recall_mod
    from maid_runner.cli.commands._main import build_parser, main

    seen: dict[str, argparse.Namespace] = {}

    def fake_cmd_recall(args: argparse.Namespace) -> int:
        seen["args"] = args
        return 0

    monkeypatch.setattr(recall_mod, "cmd_recall", fake_cmd_recall)

    manifest_path = tmp_path / "query.manifest.yaml"
    parser = build_parser()
    args = parser.parse_args(
        [
            "recall",
            "--index",
            str(tmp_path / "outcomes.json"),
            "--for-manifest",
            str(manifest_path),
            "--allow-stale-index",
            "--json",
        ]
    )

    assert args.command == "recall"
    assert args.for_manifest == str(manifest_path)
    assert args.allow_stale_index is True
    assert args.json is True

    assert main(["recall", "--for-manifest", str(manifest_path)]) == 0
    assert seen["args"].for_manifest == str(manifest_path)


def test_cmd_recall_for_manifest_outputs_derived_signals_and_matches(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_outcome_manifest(manifest_dir / "alpha.manifest.yaml")
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(build_outcome_index(manifest_dir, tmp_path), index_path)

    query_manifest = tmp_path / "drafts" / "query.manifest.yaml"
    _write_query_manifest(query_manifest)
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    exit_code = cmd_recall(
        _args(
            index_path,
            for_manifest="drafts/query.manifest.yaml",
            project_root=str(tmp_path),
            json_mode=True,
        )
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert {
        "dimension": "path",
        "source_field": "files.edit[0].path",
        "value": "src/cli.py",
    } in payload["derived_signals"]
    assert {
        "dimension": "artifact",
        "source_field": "files.edit[0].artifacts[0].name",
        "value": "src/cli.py:function:cli_task",
    } in payload["derived_signals"]
    result = payload["matches"][0]
    assert result["manifest_slug"] == "alpha"
    assert "path:src/cli.py (+80)" in result["reasons"]
    assert "artifact:src/cli.py:function:cli_task (+60)" in result["reasons"]
    assert "tag:planning (+40)" in result["reasons"]
    assert "validation_command:pytest (+30)" in result["reasons"]


def test_cmd_recall_for_manifest_preserves_stale_index_failure(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    source = manifest_dir / "alpha.manifest.yaml"
    _write_outcome_manifest(source)
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(build_outcome_index(manifest_dir, tmp_path), index_path)
    source.unlink()

    query_manifest = tmp_path / "query.manifest.yaml"
    _write_query_manifest(query_manifest)

    assert cmd_recall(_args(index_path, for_manifest=str(query_manifest))) == 2
    assert "stale" in capsys.readouterr().err.lower()

    assert (
        cmd_recall(
            _args(
                index_path,
                for_manifest=str(query_manifest),
                allow_stale_index=True,
            )
        )
        == 0
    )
    assert "alpha" in capsys.readouterr().out


def test_cmd_recall_for_manifest_reports_missing_and_empty_derivations(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(build_outcome_index(manifest_dir, tmp_path), index_path)

    missing = tmp_path / "missing.manifest.yaml"
    assert cmd_recall(_args(index_path, for_manifest=str(missing))) == 2
    assert str(missing) in capsys.readouterr().err

    empty_manifest = tmp_path / "empty.manifest.yaml"
    _write_query_manifest(
        empty_manifest,
        files={"read": ["README.md"]},
        tags=[],
        validate=[],
    )
    assert (
        cmd_recall(_args(index_path, for_manifest=str(empty_manifest), json_mode=True))
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert str(empty_manifest) in payload["error"]
    assert "no recall query signals" in payload["error"]


def test_cmd_recall_for_manifest_rejects_manual_query_filters(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(build_outcome_index(manifest_dir, tmp_path), index_path)
    query_manifest = tmp_path / "query.manifest.yaml"
    _write_query_manifest(query_manifest)

    args = _args(index_path, for_manifest=str(query_manifest), json_mode=True)
    args.manifest_slug = ["alpha"]

    assert cmd_recall(args) == 2
    payload = json.loads(capsys.readouterr().out)
    assert "--for-manifest" in payload["error"]
    assert "--manifest-slug" in payload["error"]


def test_cmd_recall_for_manifest_reports_json_parse_errors_with_path(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(build_outcome_index(manifest_dir, tmp_path), index_path)
    bad_manifest = tmp_path / "bad.manifest.json"
    bad_manifest.write_text("{not valid json")

    assert (
        cmd_recall(_args(index_path, for_manifest=str(bad_manifest), json_mode=True))
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert str(bad_manifest) in payload["error"]


def _args(
    index: Path,
    *,
    for_manifest: str | None = None,
    project_root: str | None = None,
    allow_stale_index: bool = False,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="recall",
        index=str(index),
        text=None,
        tag=[],
        path=[],
        artifact=[],
        validation_command=[],
        review_text=None,
        manifest_slug=[],
        for_manifest=for_manifest,
        manifest_dir=None,
        project_root=project_root,
        allow_stale_index=allow_stale_index,
        limit=10,
        json=json_mode,
    )


def _write_query_manifest(
    path: Path,
    *,
    files: dict | None = None,
    tags: list[str] | None = None,
    validate: list[str] | None = None,
) -> None:
    data = {
        "schema": "2",
        "goal": "query related outcomes",
        "type": "feature",
        "created": "2026-06-10T06:01:00Z",
        "metadata": {"tags": ["planning"] if tags is None else tags},
        "files": files
        or {
            "edit": [
                {
                    "path": "src/cli.py",
                    "artifacts": [{"kind": "function", "name": "cli_task"}],
                }
            ]
        },
        "validate": (
            ["uv run python -m pytest -q tests/cli/test_recall_for_manifest_cmd.py"]
            if validate is None
            else validate
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _write_outcome_manifest(path: Path) -> None:
    data = {
        "schema": "2",
        "goal": "alpha outcome",
        "type": "feature",
        "created": "2026-05-30",
        "metadata": {"tags": ["planning"]},
        "files": {
            "edit": [
                {
                    "path": "src/cli.py",
                    "artifacts": [{"kind": "function", "name": "cli_task"}],
                }
            ]
        },
        "validate": ["uv run python -m pytest -q tests/cli/test_recall_cmd.py"],
        "outcome": {
            "status": "completed",
            "summary": "alpha implementation completed.",
            "validation": [
                {
                    "command": ["uv", "run", "python", "-m", "pytest"],
                    "status": "passed",
                    "summary": "Recall validation passed.",
                }
            ],
            "completed_at": "2026-05-31T01:02:03Z",
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
