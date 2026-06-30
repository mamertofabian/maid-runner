"""Behavioral tests for advisory `maid enrich validate` quality warnings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_validate_text_mode_writes_quality_warnings_to_stderr_and_exits_zero(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.enrich import cmd_enrich

    index_path, digest_path = _write_index_and_digest(tmp_path, hollow=True)

    assert cmd_enrich(_args("validate", index_path, digest=digest_path)) == 0

    captured = capsys.readouterr()
    assert captured.out == f"Enrichment digest valid: {digest_path}\n"
    assert "Advisory digest quality warning" in captured.err
    assert "low_coverage" in captured.err
    assert "singleton_theme_map" in captured.err
    assert "single_source_entry" in captured.err


def test_validate_json_mode_includes_quality_warnings_array_on_single_object(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.enrich import cmd_enrich

    index_path, digest_path = _write_index_and_digest(tmp_path, hollow=True)

    assert (
        cmd_enrich(_args("validate", index_path, digest=digest_path, json_mode=True))
        == 0
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["digest"] == str(digest_path)
    assert payload["valid"] is True
    assert payload["quality_warnings"] == [
        {
            "code": "low_coverage",
            "message": payload["quality_warnings"][0]["message"],
        },
        {
            "code": "singleton_theme_map",
            "message": payload["quality_warnings"][1]["message"],
        },
        {
            "code": "single_source_entry",
            "message": payload["quality_warnings"][2]["message"],
        },
    ]
    assert all(warning["message"] for warning in payload["quality_warnings"])


def test_validate_still_fails_on_fabricated_digest(tmp_path: Path, capsys):
    from maid_runner.cli.commands.enrich import cmd_enrich

    index_path, digest_path = _write_index_and_digest(
        tmp_path,
        hollow=True,
        source_manifest="missing",
        source_lesson_type="fabricated",
    )

    assert cmd_enrich(_args("validate", index_path, digest=digest_path)) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "missing" in captured.err
    assert "fabricated" in captured.err
    assert "quality warning" not in captured.err.lower()


def _args(
    enrich_command: str,
    index: Path,
    *,
    digest: Path | None = None,
    md_output: Path | None = None,
    output: Path | None = None,
    manifest_dir: str | None = None,
    project_root: str | None = None,
    allow_stale_index: bool = False,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="enrich",
        enrich_command=enrich_command,
        index=str(index),
        digest=str(digest) if digest is not None else ".maid/outcomes-digest.json",
        md_output=(
            str(md_output) if md_output is not None else ".maid/outcomes-digest.md"
        ),
        output=str(output) if output is not None else None,
        manifest_dir=manifest_dir,
        project_root=project_root,
        allow_stale_index=allow_stale_index,
        json=json_mode,
    )


def _write_index_and_digest(
    tmp_path: Path,
    *,
    hollow: bool,
    source_manifest: str = "alpha",
    source_lesson_type: str = "validation",
) -> tuple[Path, Path]:
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", "alpha")
    _write_manifest(manifest_dir / "beta.manifest.yaml", "beta")
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        index.generated_from,
        hollow=hollow,
        source_manifest=source_manifest,
        source_lesson_type=source_lesson_type,
    )
    return index_path, digest_path


def _write_digest(
    path: Path,
    generated_from: str,
    *,
    hollow: bool,
    source_manifest: str,
    source_lesson_type: str,
) -> None:
    if hollow:
        themes = [
            {
                "canonical_name": "validation",
                "member_lesson_types": ["validation"],
                "summary": "Validation lessons stay grounded.",
                "source_manifests": ["alpha"],
            },
            {
                "canonical_name": "testing",
                "member_lesson_types": ["testing"],
                "summary": "Testing lessons stay grounded.",
                "source_manifests": ["alpha"],
            },
        ]
        source_lessons = [
            {
                "manifest_slug": source_manifest,
                "lesson_type": source_lesson_type,
            }
        ]
    else:
        themes = [
            {
                "canonical_name": "validation",
                "member_lesson_types": ["validation", "testing"],
                "summary": "Validation lessons stay grounded.",
                "source_manifests": ["alpha", "beta"],
            },
            {
                "canonical_name": "delivery",
                "member_lesson_types": ["workflow", "cli"],
                "summary": "Delivery lessons stay grounded.",
                "source_manifests": ["alpha", "beta"],
            },
        ]
        source_lessons = [
            {"manifest_slug": "alpha", "lesson_type": "validation"},
            {"manifest_slug": "beta", "lesson_type": "testing"},
        ]

    data = {
        "schema_version": "1",
        "source_generated_from": generated_from,
        "advisory": True,
        "themes": themes,
        "digest_entries": [
            {
                "theme": "validation",
                "summary": "Use validation evidence before handoff.",
                "source_lessons": source_lessons,
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_manifest(path: Path, slug: str) -> None:
    data = {
        "schema": "2",
        "goal": f"{slug} outcome",
        "type": "feature",
        "created": "2026-06-01",
        "metadata": {"tags": ["outcome-records", "cli"]},
        "files": {
            "create": [
                {
                    "path": f"src/{slug}.py",
                    "artifacts": [{"kind": "function", "name": f"{slug}_task"}],
                }
            ],
            "read": [f"tests/test_{slug}.py"],
        },
        "validate": [f"uv run python -m pytest -q tests/test_{slug}.py"],
        "outcome": {
            "status": "completed",
            "summary": f"{slug} implementation completed.",
            "lessons": [
                {
                    "lesson_type": "validation",
                    "summary": "Validation evidence should stay grounded.",
                    "tags": ["outcome-records"],
                    "paths": [f"src/{slug}.py"],
                },
                {
                    "lesson_type": "testing",
                    "summary": "Testing should capture behavior.",
                    "tags": ["outcome-records"],
                    "paths": [f"src/{slug}.py"],
                },
                {
                    "lesson_type": "workflow",
                    "summary": "Workflow evidence should remain visible.",
                    "tags": ["outcome-records"],
                    "paths": [f"src/{slug}.py"],
                },
                {
                    "lesson_type": "cli",
                    "summary": "CLI output should remain parseable.",
                    "tags": ["outcome-records"],
                    "paths": [f"src/{slug}.py"],
                },
            ],
            "review_notes": [
                {
                    "source": "implementation-review",
                    "severity": "info",
                    "summary": "Ready for enrichment.",
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
