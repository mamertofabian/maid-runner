"""Behavioral tests for the `maid insights` CLI command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_insights_parser_and_dispatch_are_registered(tmp_path: Path, monkeypatch):
    from maid_runner.cli.commands import insights as insights_mod
    from maid_runner.cli.commands._main import build_parser, main

    index_path = tmp_path / "outcomes.json"
    seen: dict[str, argparse.Namespace] = {}

    def fake_cmd_insights(args: argparse.Namespace) -> int:
        seen["args"] = args
        return 0

    monkeypatch.setattr(insights_mod, "cmd_insights", fake_cmd_insights)

    parser = build_parser()
    args = parser.parse_args(
        [
            "insights",
            "--index",
            str(index_path),
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

    assert args.command == "insights"
    assert args.index == str(index_path)
    assert args.manifest_dir == "manifests"
    assert args.project_root == "."
    assert args.allow_stale_index is True
    assert args.limit == 3
    assert args.json is True

    assert main(["insights", "--index", str(index_path), "--json"]) == 0
    assert seen["args"].command == "insights"


def test_cmd_insights_outputs_traceable_aggregates(tmp_path: Path, capsys):
    from maid_runner.cli.commands.insights import cmd_insights
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml")
    _write_manifest(
        manifest_dir / "beta.manifest.yaml",
        tags=["outcome", "cli"],
        task_type="fix",
        completed_at=None,
        validation_status="failed",
        review_severity="warning",
    )
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path),
        index_path,
    )

    exit_code = cmd_insights(_args(index_path, json_mode=True))

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_records"] == 2
    assert payload["by_tag"][0] == {
        "count": 2,
        "key": "cli",
        "lesson_types": ["testing"],
        "review_severities": ["info", "warning"],
        "source_manifests": ["alpha", "beta"],
    }
    assert {
        "key": "feature",
        "count": 1,
        "source_manifests": ["alpha"],
        "lesson_types": ["testing"],
        "review_severities": ["info"],
    } in payload["by_change_type"]
    assert {
        "key": "unknown",
        "count": 1,
        "source_manifests": ["beta"],
        "lesson_types": ["testing"],
        "review_severities": ["warning"],
    } in payload["by_completion_month"]
    assert "generated" not in json.dumps(payload).lower()


def test_cmd_insights_rejects_missing_malformed_or_stale_index(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.insights import cmd_insights
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    missing = tmp_path / "missing.json"
    assert cmd_insights(_args(missing)) == 2
    assert "not found" in capsys.readouterr().err

    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"schema_version": "999", "records": []}\n')
    assert cmd_insights(_args(malformed)) == 2
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

    assert cmd_insights(_args(index_path)) == 2
    assert "stale" in capsys.readouterr().err.lower()


def test_cmd_insights_allows_stale_index_only_with_explicit_flag(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.insights import cmd_insights
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

    assert cmd_insights(_args(index_path)) == 2
    assert "stale" in capsys.readouterr().err.lower()

    assert cmd_insights(_args(index_path, allow_stale_index=True)) == 0
    assert "alpha" in capsys.readouterr().out

    assert (
        cmd_insights(
            _args(
                index_path,
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
    manifest_dir: str | None = None,
    project_root: str | None = None,
    allow_stale_index: bool = False,
    limit: int = 10,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="insights",
        index=str(index),
        manifest_dir=manifest_dir,
        project_root=project_root,
        allow_stale_index=allow_stale_index,
        limit=limit,
        json=json_mode,
    )


def _write_manifest(
    path: Path,
    *,
    tags: list[str] | None = None,
    task_type: str = "feature",
    completed_at: str | None = "2026-05-31T01:02:03Z",
    validation_status: str = "passed",
    review_severity: str = "info",
) -> None:
    slug = path.name.removesuffix(".manifest.yaml")
    outcome = {
        "status": "completed",
        "summary": f"{slug} implementation completed.",
        "lessons": [
            {
                "lesson_type": "testing",
                "summary": "Insight results stay deterministic.",
                "tags": ["outcome"],
                "paths": [f"src/{slug}.py"],
            }
        ],
        "review_notes": [
            {
                "source": "implementation-review",
                "severity": review_severity,
                "summary": "Ready for insights.",
            }
        ],
        "validation": [
            {
                "command": ["uv", "run", "maid", "test"],
                "status": validation_status,
                "summary": "Insight validation evidence.",
            }
        ],
    }
    if completed_at is not None:
        outcome["completed_at"] = completed_at

    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": f"{slug} outcome",
                "type": task_type,
                "created": "2026-05-30",
                "metadata": {"tags": tags or ["outcome", "cli"]},
                "files": {
                    "create": [
                        {
                            "path": f"src/{slug}.py",
                            "artifacts": [
                                {"kind": "function", "name": f"{slug}_task"},
                            ],
                        }
                    ],
                    "read": [f"tests/test_{slug}.py"],
                },
                "validate": [f"uv run python -m pytest -q tests/test_{slug}.py"],
                "outcome": outcome,
            },
            sort_keys=False,
        )
    )
