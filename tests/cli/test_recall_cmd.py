"""Behavioral tests for the `maid recall` CLI command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_recall_parser_and_dispatch_are_registered(tmp_path: Path, monkeypatch):
    from maid_runner.cli.commands import recall as recall_mod
    from maid_runner.cli.commands._main import build_parser, main

    index_path = tmp_path / "outcomes.json"
    seen: dict[str, argparse.Namespace] = {}

    def fake_cmd_recall(args: argparse.Namespace) -> int:
        seen["args"] = args
        return 0

    monkeypatch.setattr(recall_mod, "cmd_recall", fake_cmd_recall)

    parser = build_parser()
    args = parser.parse_args(
        [
            "recall",
            "--index",
            str(index_path),
            "--text",
            "manifest",
            "--tag",
            "validation",
            "--path",
            "maid_runner/core/manifest.py",
            "--artifact",
            "validate_manifest",
            "--validation-command",
            "pytest",
            "--review-text",
            "ready",
            "--manifest-slug",
            "alpha",
            "--manifest-dir",
            "manifests",
            "--project-root",
            ".",
            "--allow-stale-index",
            "--limit",
            "3",
            "--json",
        ]
    )

    assert args.command == "recall"
    assert args.index == str(index_path)
    assert args.text == "manifest"
    assert args.tag == ["validation"]
    assert args.path == ["maid_runner/core/manifest.py"]
    assert args.artifact == ["validate_manifest"]
    assert args.validation_command == ["pytest"]
    assert args.review_text == "ready"
    assert args.manifest_slug == ["alpha"]
    assert args.manifest_dir == "manifests"
    assert args.project_root == "."
    assert args.allow_stale_index is True
    assert args.limit == 3
    assert args.json is True

    assert main(["recall", "--index", str(index_path), "--tag", "validation"]) == 0
    assert seen["args"].command == "recall"


def test_cmd_recall_outputs_ranked_traceable_matches(tmp_path: Path, capsys):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml")
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path),
        index_path,
    )

    exit_code = cmd_recall(
        _args(
            index_path,
            tag=["validation"],
            path=[str(tmp_path / "src" / "alpha.py")],
            review_text="ready",
            json_mode=True,
        )
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    result = payload["matches"][0]
    assert result["manifest_path"] == "manifests/alpha.manifest.yaml"
    assert result["score"] == 140
    assert "path:src/alpha.py (+80)" in result["reasons"]
    assert "tag:validation (+40)" in result["reasons"]
    assert "review_text:ready (+20)" in result["reasons"]
    assert result["lessons"] == ["Recall results stay deterministic."]
    assert result["review_notes"] == ["implementation-review/info: Ready for recall."]


def test_cmd_recall_rejects_missing_malformed_or_stale_index(tmp_path: Path, capsys):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    missing = tmp_path / "missing.json"
    assert cmd_recall(_args(missing, tag=["validation"])) == 2
    assert "not found" in capsys.readouterr().err

    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"schema_version": "999", "records": []}\n')
    assert cmd_recall(_args(malformed, tag=["validation"])) == 2
    assert "Malformed Outcome index" in capsys.readouterr().err

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    source = manifest_dir / "alpha.manifest.yaml"
    _write_manifest(source)
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path),
        index_path,
    )
    data = yaml.safe_load(source.read_text())
    data["outcome"]["summary"] = "Changed after learning."
    source.write_text(yaml.safe_dump(data, sort_keys=False))

    assert cmd_recall(_args(index_path, tag=["validation"])) == 2
    assert "stale" in capsys.readouterr().err.lower()


def test_cmd_recall_allows_stale_index_only_with_explicit_flag(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    source = manifest_dir / "alpha.manifest.yaml"
    _write_manifest(source)
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path),
        index_path,
    )
    source.unlink()

    assert cmd_recall(_args(index_path, tag=["validation"])) == 2
    assert "stale" in capsys.readouterr().err.lower()

    assert (
        cmd_recall(_args(index_path, tag=["validation"], allow_stale_index=True)) == 0
    )
    assert "alpha" in capsys.readouterr().out

    assert (
        cmd_recall(
            _args(
                index_path,
                tag=["validation"],
                manifest_dir=str(tmp_path / "other-manifests"),
                project_root=str(tmp_path),
            )
        )
        == 2
    )
    assert "stale" in capsys.readouterr().err.lower()


def _args(
    index: Path,
    *,
    text: str | None = None,
    tag: list[str] | None = None,
    path: list[str] | None = None,
    artifact: list[str] | None = None,
    validation_command: list[str] | None = None,
    review_text: str | None = None,
    manifest_slug: list[str] | None = None,
    manifest_dir: str | None = None,
    project_root: str | None = None,
    allow_stale_index: bool = False,
    limit: int = 10,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="recall",
        index=str(index),
        text=text,
        tag=tag or [],
        path=path or [],
        artifact=artifact or [],
        validation_command=validation_command or [],
        review_text=review_text,
        manifest_slug=manifest_slug or [],
        manifest_dir=manifest_dir,
        project_root=project_root,
        allow_stale_index=allow_stale_index,
        limit=limit,
        json=json_mode,
    )


def _write_manifest(path: Path) -> None:
    data = {
        "schema": "2",
        "goal": "alpha outcome",
        "type": "feature",
        "created": "2026-05-30",
        "metadata": {"tags": ["validation", "recall"]},
        "files": {
            "create": [
                {
                    "path": "src/alpha.py",
                    "artifacts": [
                        {"kind": "function", "name": "alpha_task"},
                    ],
                }
            ],
            "read": ["tests/test_alpha.py"],
        },
        "validate": ["uv run python -m pytest -q tests/test_alpha.py"],
        "outcome": {
            "status": "completed",
            "summary": "alpha implementation completed.",
            "lessons": [
                {
                    "lesson_type": "testing",
                    "summary": "Recall results stay deterministic.",
                    "tags": ["validation"],
                    "paths": ["src/alpha.py"],
                }
            ],
            "review_notes": [
                {
                    "source": "implementation-review",
                    "severity": "info",
                    "summary": "Ready for recall.",
                }
            ],
            "validation": [
                {
                    "command": ["uv", "run", "maid", "test"],
                    "status": "passed",
                    "summary": "Recall validation passed.",
                }
            ],
            "completed_at": "2026-05-31T01:02:03Z",
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
