"""Behavioral tests for `maid recall --for-manifest --plan-packet`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import yaml


def test_recall_parser_accepts_plan_packet_and_dispatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            "--plan-packet",
            "--json",
        ]
    )

    assert args.command == "recall"
    assert args.for_manifest == str(manifest_path)
    assert args.plan_packet is True
    assert args.json is True

    assert main(["recall", "--for-manifest", str(manifest_path), "--plan-packet"]) == 0
    assert seen["args"].for_manifest == str(manifest_path)
    assert seen["args"].plan_packet is True


def test_cmd_recall_plan_packet_outputs_text_and_json_sections(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_outcome_manifest(manifest_dir / "alpha.manifest.yaml")
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, tmp_path, include_statuses={"completed"}),
        index_path,
    )
    query_manifest = tmp_path / "query.manifest.yaml"
    _write_query_manifest(query_manifest)

    assert (
        cmd_recall(
            _args(index_path, for_manifest=str(query_manifest), plan_packet=True)
        )
        == 0
    )
    text_output = capsys.readouterr().out
    assert "Planning recall packet for" in text_output
    assert "Related manifests:" in text_output
    assert "alpha (manifests/alpha.manifest.yaml)" in text_output
    assert "Outcome statuses:" in text_output
    assert "alpha: completed" in text_output
    assert "Recurring lessons touching the same paths:" in text_output
    assert "Keep path lessons tied to declared files." in text_output
    assert "Prior validation-command failures:" in text_output
    assert "failed: uv run pytest tests/alpha.py - Regression failed." in text_output

    assert (
        cmd_recall(
            _args(
                index_path,
                for_manifest=str(query_manifest),
                plan_packet=True,
                json_mode=True,
            )
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan_packet"]["manifest_path"] == "query.manifest.yaml"
    assert [section["title"] for section in payload["plan_packet"]["sections"]] == [
        "Related manifests",
        "Outcome statuses",
        "Recurring lessons touching the same paths",
        "Prior validation-command failures",
    ]
    assert payload["plan_packet"]["sections"][0]["entries"] == [
        "alpha (manifests/alpha.manifest.yaml)"
    ]
    assert payload["plan_packet"]["sections"][3]["omitted_count"] == 0


def test_cmd_recall_plan_packet_requires_for_manifest_and_preserves_stale_index_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    source = manifest_dir / "alpha.manifest.yaml"
    _write_outcome_manifest(source)
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(build_outcome_index(manifest_dir, tmp_path), index_path)

    assert cmd_recall(_args(index_path, plan_packet=True, json_mode=True)) == 2
    assert (
        "--plan-packet requires --for-manifest"
        in json.loads(capsys.readouterr().out)["error"]
    )

    query_manifest = tmp_path / "query.manifest.yaml"
    _write_query_manifest(query_manifest)
    source.unlink()

    assert (
        cmd_recall(
            _args(index_path, for_manifest=str(query_manifest), plan_packet=True)
        )
        == 2
    )
    assert "stale" in capsys.readouterr().err.lower()

    assert (
        cmd_recall(
            _args(
                index_path,
                for_manifest=str(query_manifest),
                plan_packet=True,
                allow_stale_index=True,
            )
        )
        == 0
    )
    assert "Planning recall packet" in capsys.readouterr().out


def _args(
    index: Path,
    *,
    for_manifest: str | None = None,
    allow_stale_index: bool = False,
    json_mode: bool = False,
    plan_packet: bool = False,
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
        plan_packet=plan_packet,
        manifest_dir=None,
        project_root=None,
        allow_stale_index=allow_stale_index,
        limit=10,
        json=json_mode,
    )


def _write_query_manifest(path: Path) -> None:
    data = {
        "schema": "2",
        "goal": "query related outcomes",
        "type": "feature",
        "created": "2026-06-10T06:02:00Z",
        "metadata": {"tags": ["planning"]},
        "files": {
            "edit": [
                {
                    "path": "src/cli.py",
                    "artifacts": [{"kind": "function", "name": "cli_task"}],
                }
            ]
        },
        "validate": [
            "uv run python -m pytest -q tests/cli/test_recall_plan_packet_cmd.py"
        ],
    }
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
            "lessons": [
                {
                    "lesson_type": "testing",
                    "summary": "Keep path lessons tied to declared files.",
                    "paths": ["src/cli.py"],
                }
            ],
            "validation": [
                {
                    "command": ["uv", "run", "pytest", "tests/alpha.py"],
                    "status": "failed",
                    "summary": "Regression failed.",
                }
            ],
            "completed_at": "2026-05-31T01:02:03Z",
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
