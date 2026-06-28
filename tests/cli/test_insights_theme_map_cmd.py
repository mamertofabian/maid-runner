"""Behavioral tests for `maid insights --theme-map`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_insights_without_theme_map_keeps_default_aggregation(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.insights import cmd_insights
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", lesson_type="validation")
    _write_manifest(
        manifest_dir / "beta.manifest.yaml",
        lesson_type="validator-hardening",
    )
    index_path = tmp_path / ".maid" / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path),
        index_path,
    )
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"

    parsed = build_parser().parse_args(
        [
            "insights",
            "--index",
            str(index_path),
            "--theme-map",
            str(digest_path),
        ]
    )
    assert parsed.theme_map == str(digest_path)

    assert cmd_insights(_args(index_path, json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert _group(payload, "by_lesson_type", "validation") == {
        "count": 1,
        "key": "validation",
        "lesson_types": ["validation"],
        "review_severities": ["info"],
        "source_manifests": ["alpha"],
    }
    assert _group(payload, "by_lesson_type", "validator-hardening") == {
        "count": 1,
        "key": "validator-hardening",
        "lesson_types": ["validator-hardening"],
        "review_severities": ["info"],
        "source_manifests": ["beta"],
    }


def test_insights_with_theme_map_collapses_lesson_types(tmp_path: Path, capsys):
    from maid_runner.cli.commands.insights import cmd_insights
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", lesson_type="validation")
    _write_manifest(
        manifest_dir / "beta.manifest.yaml",
        lesson_type="validator-hardening",
    )
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(digest_path, index.generated_from)

    assert cmd_insights(_args(index_path, theme_map=digest_path, json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert _group(payload, "by_lesson_type", "validation") == {
        "count": 2,
        "key": "validation",
        "lesson_types": ["validation", "validator-hardening"],
        "review_severities": ["info"],
        "source_manifests": ["alpha", "beta"],
    }
    assert _group(payload, "by_lesson_type", "validator-hardening") is None


def test_insights_with_theme_map_emits_no_generated_narrative(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.insights import cmd_insights
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", lesson_type="validation")
    _write_manifest(
        manifest_dir / "beta.manifest.yaml",
        lesson_type="validator-hardening",
    )
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        index.generated_from,
        theme_summary="Generated theme summary must stay out.",
        entry_summary="Generated recurring lesson must stay out.",
    )

    assert cmd_insights(_args(index_path, theme_map=digest_path, json_mode=True)) == 0
    payload_text = json.dumps(json.loads(capsys.readouterr().out), sort_keys=True)

    assert "Generated theme summary" not in payload_text
    assert "Generated recurring lesson" not in payload_text
    assert "validation" in payload_text
    assert "alpha" in payload_text


def test_insights_rejects_stale_theme_map_without_allow_flag(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.insights import cmd_insights
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", lesson_type="validation")
    _write_manifest(
        manifest_dir / "beta.manifest.yaml",
        lesson_type="validator-hardening",
    )
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path),
        index_path,
    )
    _write_digest(digest_path, "old-index-fingerprint")

    assert cmd_insights(_args(index_path, theme_map=digest_path)) == 2
    assert "stale" in capsys.readouterr().err.lower()

    assert (
        cmd_insights(_args(index_path, theme_map=digest_path, allow_stale_index=True))
        == 0
    )
    assert "validation" in capsys.readouterr().out


def test_insights_rejects_fabricated_theme_map(tmp_path: Path, capsys):
    from maid_runner.cli.commands.insights import cmd_insights
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", lesson_type="validation")
    _write_manifest(
        manifest_dir / "beta.manifest.yaml",
        lesson_type="validator-hardening",
    )
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        index.generated_from,
        source_manifest="alpha",
        source_lesson_type="validator-hardening",
    )

    assert cmd_insights(_args(index_path, theme_map=digest_path)) == 2

    error = capsys.readouterr().err
    assert "alpha" in error
    assert "validator-hardening" in error


def test_outcome_enrichment_guidance_documents_advisory_artifacts():
    root = Path(__file__).resolve().parents[2]

    for relative_path in (
        "docs/manifest-outcome-records.md",
        "maid_runner/docs/manifest-outcome-records.md",
    ):
        text = (root / relative_path).read_text(encoding="utf-8")

        assert "maid enrich" in text
        assert ".maid/outcomes-digest.json" in text
        assert ".maid/outcomes-digest.md" in text
        assert "maid insights --theme-map" in text
        assert "advisory" in text
        assert "generated and ignored" in text


def _args(
    index: Path,
    *,
    theme_map: Path | None = None,
    manifest_dir: str | None = None,
    project_root: str | None = None,
    allow_stale_index: bool = False,
    limit: int = 10,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="insights",
        index=str(index),
        theme_map=str(theme_map) if theme_map is not None else None,
        manifest_dir=manifest_dir,
        project_root=project_root,
        allow_stale_index=allow_stale_index,
        limit=limit,
        json=json_mode,
    )


def _group(payload: dict, section: str, key: str) -> dict | None:
    return next((group for group in payload[section] if group["key"] == key), None)


def _write_manifest(path: Path, *, lesson_type: str) -> None:
    slug = path.name.removesuffix(".manifest.yaml")
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": f"{slug} outcome",
                "type": "feature",
                "created": "2026-06-28",
                "metadata": {"tags": ["outcome", "insights"]},
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
                "outcome": {
                    "status": "completed",
                    "summary": f"{slug} implementation completed.",
                    "lessons": [
                        {
                            "lesson_type": lesson_type,
                            "summary": f"{lesson_type} lessons stay deterministic.",
                            "tags": ["outcome"],
                            "paths": [f"src/{slug}.py"],
                        }
                    ],
                    "review_notes": [
                        {
                            "source": "implementation-review",
                            "severity": "info",
                            "summary": "Ready for insights.",
                        }
                    ],
                    "validation": [
                        {
                            "command": ["uv", "run", "maid", "test"],
                            "status": "passed",
                            "summary": "Insight validation evidence.",
                        }
                    ],
                    "completed_at": "2026-06-28T01:02:03Z",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_digest(
    path: Path,
    generated_from: str,
    *,
    theme_summary: str = "Validation lessons share a canonical theme.",
    entry_summary: str = "Validate deterministic insight enrichment.",
    source_manifest: str = "alpha",
    source_lesson_type: str = "validation",
) -> None:
    data = {
        "schema_version": "1",
        "source_generated_from": generated_from,
        "advisory": True,
        "themes": [
            {
                "canonical_name": "validation",
                "member_lesson_types": ["validation", "validator-hardening"],
                "summary": theme_summary,
                "source_manifests": ["alpha", "beta"],
            }
        ],
        "digest_entries": [
            {
                "theme": "validation",
                "summary": entry_summary,
                "source_lessons": [
                    {
                        "manifest_slug": source_manifest,
                        "lesson_type": source_lesson_type,
                    }
                ],
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
