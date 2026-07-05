"""Behavioral tests for keeping hypotheses out of deterministic insights."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_theme_map_insights_output_identical_with_and_without_hypotheses(
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
    plain_digest = tmp_path / ".maid" / "plain-digest.json"
    hypothesis_digest = tmp_path / ".maid" / "hypothesis-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(plain_digest, index.generated_from, include_hypotheses=False)
    _write_digest(hypothesis_digest, index.generated_from, include_hypotheses=True)

    assert cmd_insights(_args(index_path, theme_map=plain_digest, json_mode=True)) == 0
    plain_output = capsys.readouterr().out

    assert (
        cmd_insights(_args(index_path, theme_map=hypothesis_digest, json_mode=True))
        == 0
    )
    hypothesis_output = capsys.readouterr().out

    assert hypothesis_output == plain_output
    assert "improvement_hypotheses" not in hypothesis_output
    assert "Add a focused validation hardening fixture" not in hypothesis_output


def test_theme_map_insights_ignores_invalid_hypotheses(
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
        include_hypotheses=True,
        hypothesis_source_lessons=(
            {"manifest_slug": "alpha", "lesson_type": "validation"},
        ),
    )

    assert cmd_insights(_args(index_path, theme_map=digest_path, json_mode=True)) == 0
    output = capsys.readouterr().out

    assert json.loads(output)["by_lesson_type"][0]["key"] == "validation"
    assert "improvement_hypotheses" not in output


def _args(
    index: Path,
    *,
    theme_map: Path,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="insights",
        index=str(index),
        theme_map=str(theme_map),
        manifest_dir=None,
        project_root=None,
        allow_stale_index=False,
        allow_stale_digest=False,
        limit=10,
        json=json_mode,
    )


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
    include_hypotheses: bool,
    hypothesis_source_lessons: tuple[dict[str, str], ...] = (
        {"manifest_slug": "alpha", "lesson_type": "validation"},
        {"manifest_slug": "beta", "lesson_type": "validator-hardening"},
    ),
) -> None:
    data = {
        "schema_version": "1",
        "source_generated_from": generated_from,
        "advisory": True,
        "themes": [
            {
                "canonical_name": "validation",
                "member_lesson_types": ["validation", "validator-hardening"],
                "summary": "Validation lessons share a canonical theme.",
                "source_manifests": ["alpha", "beta"],
            }
        ],
        "digest_entries": [
            {
                "theme": "validation",
                "summary": "Validate deterministic insight enrichment.",
                "source_lessons": [
                    {"manifest_slug": "alpha", "lesson_type": "validation"}
                ],
            }
        ],
    }
    if include_hypotheses:
        data["improvement_hypotheses"] = [
            {
                "summary": "Add a focused validation hardening fixture.",
                "source_lessons": list(hypothesis_source_lessons),
            }
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
