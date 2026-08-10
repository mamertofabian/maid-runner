"""Behavioral tests for local-only `maid feedback export`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_feedback_parser_registers_local_export_without_submission() -> None:
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "feedback",
            "export",
            "--index",
            "learned.json",
            "--output",
            "bundle.json",
            "--allow-stale-index",
            "--force",
            "--json",
        ]
    )

    assert args.command == "feedback"
    assert args.feedback_command == "export"
    assert args.index == "learned.json"
    assert args.output == "bundle.json"
    assert args.allow_stale_index is True
    assert args.force is True
    assert args.json is True
    feedback_parser = parser._subparsers._group_actions[0].choices["feedback"]
    assert "submit" not in feedback_parser._subparsers._group_actions[0].choices


def test_feedback_export_writes_bundle_and_requires_authored_text_review(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.feedback import cmd_feedback

    index_path, manifest_dir = _learned_index(tmp_path)
    output = tmp_path / "feedback.json"

    assert cmd_feedback(_args(index_path, output, manifest_dir, json_mode=True)) == 0

    result = json.loads(capsys.readouterr().out)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert result["exported"] == 1
    assert result["review_required"] is True
    assert "inspect" in result["notice"].lower()
    assert payload["records"][0]["summary"] == "Portable runner lesson."
    assert payload["records"][0]["source_count"] == 1


def test_feedback_export_rejects_stale_index_unless_explicitly_allowed(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.feedback import cmd_feedback

    index_path, manifest_dir = _learned_index(tmp_path)
    (manifest_dir / "alpha.manifest.yaml").unlink()
    output = tmp_path / "feedback.json"

    assert cmd_feedback(_args(index_path, output, manifest_dir)) == 2
    assert "stale" in capsys.readouterr().err.lower()
    assert not output.exists()

    assert (
        cmd_feedback(_args(index_path, output, manifest_dir, allow_stale_index=True))
        == 0
    )
    assert output.exists()


def test_feedback_export_preserves_existing_output_unless_force_is_explicit(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.feedback import cmd_feedback

    index_path, manifest_dir = _learned_index(tmp_path)
    output = tmp_path / "feedback.json"
    output.write_text("keep me\n", encoding="utf-8")

    assert cmd_feedback(_args(index_path, output, manifest_dir)) == 2
    assert "--force" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "keep me\n"

    assert cmd_feedback(_args(index_path, output, manifest_dir, force=True)) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["records"]


def test_feedback_export_rejects_missing_or_malformed_index(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.feedback import cmd_feedback

    missing = tmp_path / "missing.json"
    assert cmd_feedback(_args(missing, tmp_path / "out.json", tmp_path)) == 2
    assert "not found" in capsys.readouterr().err.lower()

    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"schema_version": "999", "records": []}\n')
    assert cmd_feedback(_args(malformed, tmp_path / "out.json", tmp_path)) == 2
    assert "malformed" in capsys.readouterr().err.lower()


def _args(
    index: Path,
    output: Path,
    manifest_dir: Path,
    *,
    allow_stale_index: bool = False,
    force: bool = False,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="feedback",
        feedback_command="export",
        index=str(index),
        output=str(output),
        manifest_dir=str(manifest_dir),
        project_root=str(manifest_dir.parent),
        allow_stale_index=allow_stale_index,
        force=force,
        json=json_mode,
    )


def _learned_index(tmp_path: Path) -> tuple[Path, Path]:
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest = {
        "schema": "2",
        "goal": "Downstream project Outcome",
        "type": "feature",
        "created": "2026-08-08",
        "metadata": {"tags": ["downstream"]},
        "files": {
            "create": [
                {
                    "path": "src/alpha.py",
                    "artifacts": [{"kind": "function", "name": "alpha"}],
                }
            ]
        },
        "validate": ["uv run pytest -q tests/test_alpha.py"],
        "outcome": {
            "status": "completed",
            "summary": "Downstream implementation completed.",
            "lessons": [
                {
                    "lesson_type": "runner-gap",
                    "summary": "Portable runner lesson.",
                    "tags": ["maid-runner-feedback"],
                    "paths": ["src/alpha.py"],
                },
                {
                    "lesson_type": "project-only",
                    "summary": "Do not export this.",
                    "tags": ["downstream"],
                    "paths": ["src/alpha.py"],
                },
            ],
            "review_notes": [
                {
                    "source": "reviewer@example.com",
                    "severity": "ready",
                    "summary": "Private review prose.",
                }
            ],
            "validation": [
                {
                    "command": ["uv", "run", "pytest"],
                    "status": "passed",
                    "summary": "Private validation prose.",
                }
            ],
        },
    }
    (manifest_dir / "alpha.manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path), index_path
    )
    return index_path, manifest_dir
