"""Behavioral tests for the `maid learn` CLI command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_learn_parser_and_dispatch_are_registered(tmp_path: Path, monkeypatch):
    from maid_runner.cli.commands import learn as learn_mod
    from maid_runner.cli.commands._main import build_parser, main

    manifest_dir = tmp_path / "manifests"
    output = tmp_path / "outcomes.json"
    manifest_dir.mkdir()
    seen: dict[str, argparse.Namespace] = {}

    def fake_cmd_learn(args: argparse.Namespace) -> int:
        seen["args"] = args
        return 0

    monkeypatch.setattr(learn_mod, "cmd_learn", fake_cmd_learn)

    parser = build_parser()
    args = parser.parse_args(
        [
            "learn",
            "--manifest-dir",
            str(manifest_dir),
            "--output",
            str(output),
            "--include-status",
            "failed",
            "--json",
            "--quiet",
        ]
    )
    assert args.command == "learn"
    assert args.manifest_dir == str(manifest_dir)
    assert args.output == str(output)
    assert args.include_status == ["failed"]
    assert args.json is True
    assert args.quiet is True

    assert (
        main(["learn", "--manifest-dir", str(manifest_dir), "--output", str(output)])
        == 0
    )
    assert seen["args"].command == "learn"


def test_cmd_learn_writes_index_and_reports_counts(tmp_path: Path, capsys):
    from maid_runner.cli.commands.learn import cmd_learn
    from maid_runner.core.outcomes import read_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    _write_manifest(
        manifest_dir / "failed.manifest.yaml",
        slug_goal="failed outcome",
        outcome_status="failed",
    )
    output = tmp_path / ".maid" / "outcomes.json"

    exit_code = cmd_learn(_args(manifest_dir, output))

    assert exit_code == 0
    assert output.exists()
    index = read_outcome_index(output)
    assert [record.manifest_slug for record in index.records] == ["completed"]
    text = capsys.readouterr().out
    assert "indexed 1" in text
    assert "skipped 1" in text


def test_cmd_learn_include_status_replaces_completed_default(tmp_path: Path, capsys):
    from maid_runner.cli.commands.learn import cmd_learn
    from maid_runner.core.outcomes import read_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    _write_manifest(
        manifest_dir / "failed.manifest.yaml",
        slug_goal="failed outcome",
        outcome_status="failed",
    )
    _write_manifest(
        manifest_dir / "partial.manifest.yaml",
        slug_goal="partial outcome",
        outcome_status="partial",
    )
    output = tmp_path / "outcomes.json"

    exit_code = cmd_learn(
        _args(
            manifest_dir, output, include_status=["failed", "partial"], json_mode=True
        )
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["indexed"] == 2
    assert payload["skipped"] == 1
    assert read_outcome_index(output).records[0].status == "failed"
    assert [record.status for record in read_outcome_index(output).records] == [
        "failed",
        "partial",
    ]


def test_cmd_learn_rejects_invalid_include_status(tmp_path: Path, capsys):
    from maid_runner.cli.commands.learn import cmd_learn

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    output = tmp_path / "outcomes.json"

    exit_code = cmd_learn(_args(manifest_dir, output, include_status=["done"]))

    assert exit_code == 2
    assert not output.exists()
    assert "done" in capsys.readouterr().err


def test_cmd_learn_returns_nonzero_for_missing_manifest_dir(tmp_path: Path, capsys):
    from maid_runner.cli.commands.learn import cmd_learn

    missing_manifest_dir = tmp_path / "missing"
    output = tmp_path / "outcomes.json"

    exit_code = cmd_learn(_args(missing_manifest_dir, output))

    assert exit_code == 2
    assert not output.exists()
    assert "Manifest directory not found" in capsys.readouterr().err


def test_cmd_learn_returns_nonzero_for_malformed_existing_index(tmp_path: Path, capsys):
    from maid_runner.cli.commands.learn import cmd_learn

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    output = tmp_path / "outcomes.json"
    output.write_text(
        json.dumps(
            {
                "generated_from": "source",
                "included_statuses": ["completed"],
                "manifest_dir": "manifests",
                "project_root": ".",
                "records": [{"status": "done"}],
                "schema_version": "1",
            }
        )
    )

    exit_code = cmd_learn(_args(manifest_dir, output))

    assert exit_code == 2
    assert "done" in capsys.readouterr().err


def test_cmd_learn_returns_nonzero_for_malformed_outcome(tmp_path: Path, capsys):
    from maid_runner.cli.commands.learn import cmd_learn

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    bad_path = manifest_dir / "bad.manifest.yaml"
    _write_manifest(bad_path, outcome_status="done")
    output = tmp_path / "outcomes.json"

    exit_code = cmd_learn(_args(manifest_dir, output))

    assert exit_code == 2
    assert not output.exists()
    error = capsys.readouterr().err
    assert "bad.manifest.yaml" in error
    assert "done" in error


def _args(
    manifest_dir: Path,
    output: Path,
    *,
    include_status: list[str] | None = None,
    json_mode: bool = False,
    quiet: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="learn",
        manifest_dir=str(manifest_dir),
        output=str(output),
        include_status=include_status or [],
        json=json_mode,
        quiet=quiet,
    )


def _write_manifest(
    path: Path,
    *,
    slug_goal: str = "completed outcome",
    outcome_status: str = "completed",
) -> None:
    slug = path.name.removesuffix(".manifest.yaml")
    data = {
        "schema": "2",
        "goal": slug_goal,
        "type": "feature",
        "created": "2026-05-30",
        "metadata": {"tags": ["outcome", "learning"]},
        "files": {
            "create": [
                {
                    "path": f"src/{slug}.py",
                    "artifacts": [
                        {"kind": "function", "name": f"{slug.replace('-', '_')}_task"}
                    ],
                }
            ]
        },
        "validate": [f"uv run python -m pytest -q tests/test_{slug}.py"],
        "outcome": {
            "status": outcome_status,
            "summary": f"{slug} implementation completed.",
            "lessons": [
                {
                    "lesson_type": "testing",
                    "summary": "Focused tests preserve behavior.",
                }
            ],
            "validation": [
                {
                    "command": ["uv", "run", "maid", "test"],
                    "status": "passed",
                    "summary": "Declared validation passed.",
                }
            ],
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))
