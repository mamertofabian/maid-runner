"""Behavioral tests for `maid recall --theme-map`."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_recall_without_theme_map_output_unchanged(tmp_path: Path, capsys):
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", ("validation",))
    index_path = tmp_path / ".maid" / "outcomes.json"
    write_outcome_index(build_outcome_index(manifest_dir, tmp_path), index_path)
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"

    parsed = build_parser().parse_args(
        ["recall", "--index", str(index_path), "--theme-map", str(digest_path)]
    )
    assert parsed.theme_map == str(digest_path)

    assert cmd_recall(_args(index_path, tag=["recall"], json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload == {
        "count": 1,
        "matches": [
            {
                "lessons": ["validation lesson for recall."],
                "manifest_path": "manifests/alpha.manifest.yaml",
                "manifest_slug": "alpha",
                "reasons": ["tag:recall (+40)"],
                "review_notes": ["implementation-review/info: Recall result is ready."],
                "score": 40,
            }
        ],
    }


def test_recall_theme_map_annotates_matches_without_changing_selection(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", ("validation",))
    _write_manifest(manifest_dir / "beta.manifest.yaml", ("validator-hardening",))
    index = build_outcome_index(manifest_dir, tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        index.generated_from,
        source_manifests=("alpha",),
    )

    assert cmd_recall(_args(index_path, tag=["recall"], json_mode=True)) == 0
    plain_payload = json.loads(capsys.readouterr().out)
    assert (
        cmd_recall(
            _args(
                index_path,
                tag=["recall"],
                theme_map=digest_path,
                json_mode=True,
            )
        )
        == 0
    )
    themed_payload = json.loads(capsys.readouterr().out)

    assert _stable_match_trace(themed_payload) == _stable_match_trace(plain_payload)
    assert [match["themes"] for match in themed_payload["matches"]] == [
        ["Validation Discipline"],
        ["Validation Discipline"],
    ]
    assert all("themes" not in match for match in plain_payload["matches"])


def test_recall_theme_map_passes_unmapped_lesson_types_through(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "alpha.manifest.yaml",
        ("validation", "testing"),
    )
    index = build_outcome_index(manifest_dir, tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        index.generated_from,
        member_lesson_types=("validation",),
        source_manifests=("alpha",),
    )

    assert (
        cmd_recall(
            _args(index_path, tag=["recall"], theme_map=digest_path, json_mode=True)
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["matches"][0]["themes"] == ["Validation Discipline", "testing"]


def test_recall_rejects_stale_theme_map_without_allow_flag(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", ("validation",))
    index = build_outcome_index(manifest_dir, tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        "old-index-fingerprint",
        member_lesson_types=("validation",),
        source_manifests=("alpha",),
    )

    assert cmd_recall(_args(index_path, tag=["recall"], theme_map=digest_path)) == 2
    assert "stale" in capsys.readouterr().err.lower()

    assert (
        cmd_recall(
            _args(
                index_path,
                tag=["recall"],
                theme_map=digest_path,
                allow_stale_index=True,
            )
        )
        == 0
    )
    assert "Validation Discipline (validation)" in capsys.readouterr().out


def test_recall_rejects_fabricated_theme_map(tmp_path: Path, capsys):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", ("validation",))
    index = build_outcome_index(manifest_dir, tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        index.generated_from,
        member_lesson_types=("validation", "fabricated-type"),
        source_manifests=("alpha",),
    )

    assert cmd_recall(_args(index_path, tag=["recall"], theme_map=digest_path)) == 2

    error = capsys.readouterr().err
    assert "fabricated-type" in error


def test_recall_theme_map_emits_no_generated_narrative(tmp_path: Path, capsys):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", ("validation",))
    index = build_outcome_index(manifest_dir, tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        index.generated_from,
        member_lesson_types=("validation",),
        source_manifests=("alpha",),
        theme_summary="Generated theme summary must stay out.",
        entry_summary="Generated recurring lesson must stay out.",
    )

    assert (
        cmd_recall(
            _args(index_path, tag=["recall"], theme_map=digest_path, json_mode=True)
        )
        == 0
    )
    json_output = capsys.readouterr().out
    assert "Generated theme summary" not in json_output
    assert "Generated recurring lesson" not in json_output
    assert "Validation Discipline" in json_output

    assert cmd_recall(_args(index_path, tag=["recall"], theme_map=digest_path)) == 0
    text_output = capsys.readouterr().out
    assert "Generated theme summary" not in text_output
    assert "Generated recurring lesson" not in text_output
    assert "Validation Discipline (validation)" in text_output


def test_recall_theme_map_ignores_invalid_hypotheses(tmp_path: Path, capsys):
    from maid_runner.cli.commands.recall import cmd_recall
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", ("validation",))
    _write_manifest(manifest_dir / "beta.manifest.yaml", ("validator-hardening",))
    index = build_outcome_index(manifest_dir, tmp_path)
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

    assert (
        cmd_recall(
            _args(index_path, tag=["recall"], theme_map=digest_path, json_mode=True)
        )
        == 0
    )
    output = capsys.readouterr().out

    assert json.loads(output)["matches"][0]["themes"] == ["Validation Discipline"]
    assert "improvement_hypotheses" not in output


def _args(
    index: Path,
    *,
    tag: list[str] | None = None,
    theme_map: Path | None = None,
    allow_stale_index: bool = False,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="recall",
        index=str(index),
        text=None,
        tag=tag or [],
        path=[],
        artifact=[],
        validation_command=[],
        review_text=None,
        manifest_slug=[],
        for_manifest=None,
        plan_packet=False,
        theme_map=str(theme_map) if theme_map is not None else None,
        manifest_dir=None,
        project_root=None,
        allow_stale_index=allow_stale_index,
        limit=10,
        json=json_mode,
    )


def _stable_match_trace(payload: dict) -> list[dict]:
    return [
        {
            "manifest_path": match["manifest_path"],
            "manifest_slug": match["manifest_slug"],
            "reasons": match["reasons"],
            "score": match["score"],
        }
        for match in payload["matches"]
    ]


def _write_manifest(path: Path, lesson_types: tuple[str, ...]) -> None:
    slug = path.name.removesuffix(".manifest.yaml")
    data = {
        "schema": "2",
        "goal": f"{slug} outcome",
        "type": "feature",
        "created": "2026-06-30",
        "metadata": {"tags": ["recall"]},
        "files": {
            "create": [
                {
                    "path": f"src/{slug}.py",
                    "artifacts": [
                        {"kind": "function", "name": f"{slug}_task"},
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
                    "lesson_type": lesson_type,
                    "summary": f"{lesson_type} lesson for recall.",
                    "tags": ["recall"],
                    "paths": [f"src/{slug}.py"],
                }
                for lesson_type in lesson_types
            ],
            "review_notes": [
                {
                    "source": "implementation-review",
                    "severity": "info",
                    "summary": "Recall result is ready.",
                }
            ],
            "validation": [
                {
                    "command": ["uv", "run", "maid", "test"],
                    "status": "passed",
                    "summary": "Recall validation passed.",
                }
            ],
            "completed_at": "2026-06-30T01:02:03Z",
        },
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _write_digest(
    path: Path,
    generated_from: str,
    *,
    member_lesson_types: tuple[str, ...] = ("validation", "validator-hardening"),
    source_manifests: tuple[str, ...] = ("alpha", "beta"),
    theme_summary: str = "Validation and hardening share a theme.",
    entry_summary: str = "Keep recall annotations deterministic.",
    include_hypotheses: bool = False,
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
                "canonical_name": "Validation Discipline",
                "member_lesson_types": list(member_lesson_types),
                "summary": theme_summary,
                "source_manifests": list(source_manifests),
            }
        ],
        "digest_entries": [
            {
                "theme": "Validation Discipline",
                "summary": entry_summary,
                "source_lessons": [
                    {"manifest_slug": "alpha", "lesson_type": "validation"}
                ],
            }
        ],
    }
    if include_hypotheses:
        data["improvement_hypotheses"] = [
            {
                "summary": "Add a focused recall hardening fixture.",
                "source_lessons": list(hypothesis_source_lessons),
            }
        ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
