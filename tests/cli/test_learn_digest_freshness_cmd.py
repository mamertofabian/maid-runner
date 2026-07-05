"""Behavioral tests for `maid learn` enrichment digest freshness reporting."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_learn_without_digest_is_silent_and_reports_missing_in_json(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.learn import cmd_learn

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    output = tmp_path / ".maid" / "outcomes.json"

    text_exit = cmd_learn(_args(manifest_dir, output))
    text = capsys.readouterr()

    assert text_exit == 0
    assert "enrichment digest" not in text.err.lower()

    json_exit = cmd_learn(_args(manifest_dir, output, json_mode=True))
    payload = json.loads(capsys.readouterr().out)

    assert json_exit == 0
    assert payload["enrichment_digest"] == {
        "path": str(output.with_name("outcomes-digest.json")),
        "status": "missing",
    }


def test_learn_with_matching_digest_reports_fresh(tmp_path: Path, capsys) -> None:
    from maid_runner.cli.commands.learn import cmd_learn
    from maid_runner.core.outcomes import read_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    output = tmp_path / ".maid" / "outcomes.json"
    digest_path = output.with_name("outcomes-digest.json")

    assert cmd_learn(_args(manifest_dir, output)) == 0
    capsys.readouterr()
    _write_digest(digest_path, read_outcome_index(output).generated_from)

    json_exit = cmd_learn(_args(manifest_dir, output, json_mode=True))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert json_exit == 0
    assert payload["enrichment_digest"] == {
        "path": str(digest_path),
        "status": "fresh",
    }
    assert "enrichment digest" not in captured.err.lower()


def test_learn_reports_stale_digest_after_index_changes(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.learn import cmd_learn
    from maid_runner.core.outcomes import read_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    output = tmp_path / ".maid" / "outcomes.json"
    digest_path = output.with_name("outcomes-digest.json")

    assert cmd_learn(_args(manifest_dir, output)) == 0
    capsys.readouterr()
    _write_digest(digest_path, read_outcome_index(output).generated_from)
    _write_manifest(manifest_dir / "second.manifest.yaml")

    text_exit = cmd_learn(_args(manifest_dir, output))
    text = capsys.readouterr()

    assert text_exit == 0
    assert "stale enrichment digest" in text.err.lower()
    assert str(digest_path) in text.err
    assert "maid-outcome-enrich" in text.err

    json_exit = cmd_learn(_args(manifest_dir, output, json_mode=True))
    payload = json.loads(capsys.readouterr().out)

    assert json_exit == 0
    assert payload["enrichment_digest"] == {
        "path": str(digest_path),
        "status": "stale",
    }


def test_learn_reports_malformed_digest_without_failing_or_mutating_it(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.learn import cmd_learn

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    output = tmp_path / ".maid" / "outcomes.json"
    digest_path = output.with_name("outcomes-digest.json")
    digest_path.parent.mkdir(parents=True)
    original_bytes = b"{not json"
    digest_path.write_bytes(original_bytes)

    json_exit = cmd_learn(_args(manifest_dir, output, json_mode=True))
    payload = json.loads(capsys.readouterr().out)

    assert json_exit == 0
    assert payload["enrichment_digest"] == {
        "path": str(digest_path),
        "status": "malformed",
    }
    assert digest_path.read_bytes() == original_bytes


def test_learn_quiet_suppresses_digest_advisory_text_only(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.learn import cmd_learn
    from maid_runner.core.outcomes import read_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    output = tmp_path / ".maid" / "outcomes.json"
    digest_path = output.with_name("outcomes-digest.json")

    assert cmd_learn(_args(manifest_dir, output)) == 0
    capsys.readouterr()
    _write_digest(digest_path, read_outcome_index(output).generated_from)
    _write_manifest(manifest_dir / "second.manifest.yaml")

    quiet_exit = cmd_learn(_args(manifest_dir, output, quiet=True))
    quiet = capsys.readouterr()

    assert quiet_exit == 0
    assert quiet.out == ""
    assert quiet.err == ""

    json_exit = cmd_learn(_args(manifest_dir, output, json_mode=True, quiet=True))
    payload = json.loads(capsys.readouterr().out)

    assert json_exit == 0
    assert payload["enrichment_digest"] == {
        "path": str(digest_path),
        "status": "stale",
    }


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


def _write_digest(path: Path, source_generated_from: str) -> None:
    from maid_runner.core.outcome_enrichment import (
        EnrichmentDigest,
        write_enrichment_digest,
    )

    write_enrichment_digest(
        EnrichmentDigest(
            schema_version="1",
            source_generated_from=source_generated_from,
            advisory=True,
            themes=(),
            digest_entries=(),
        ),
        path,
    )


def _write_manifest(path: Path) -> None:
    slug = path.name.removesuffix(".manifest.yaml")
    data = {
        "schema": "2",
        "goal": f"{slug} outcome",
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
            "status": "completed",
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
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
