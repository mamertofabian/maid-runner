"""Behavioral tests for recall's explicit stale-digest opt-in flag."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import yaml


def test_recall_stale_digest_rejected_without_any_allow_flag(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.recall import cmd_recall

    paths = _write_index_and_stale_digest(tmp_path)

    assert cmd_recall(_recall_args(paths.index, theme_map=paths.digest)) == 2

    error = capsys.readouterr().err
    assert "stale" in error.lower()
    assert "--allow-stale-digest" in error


def test_recall_allow_stale_digest_accepts_stale_theme_map(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.recall import cmd_recall

    paths = _write_index_and_stale_digest(tmp_path)

    assert (
        cmd_recall(
            _recall_args(
                paths.index,
                theme_map=paths.digest,
                allow_stale_digest=True,
                json_mode=True,
            )
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["matches"][0]["manifest_slug"] == "alpha"
    assert payload["matches"][0]["themes"] == ["Validation Discipline"]
    assert payload["matches"][0]["score"] == 40


def test_recall_allow_stale_index_keeps_backward_compatible_double_duty(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.recall import cmd_recall

    paths = _write_index_and_stale_digest(tmp_path)

    assert (
        cmd_recall(
            _recall_args(
                paths.index,
                theme_map=paths.digest,
                allow_stale_index=True,
            )
        )
        == 0
    )

    assert "Validation Discipline (validation)" in capsys.readouterr().out


def test_recall_allow_stale_digest_does_not_waive_index_staleness(
    tmp_path: Path,
    capsys,
) -> None:
    from maid_runner.cli.commands.recall import cmd_recall

    paths = _write_stale_index_and_matching_digest(tmp_path)

    assert (
        cmd_recall(
            _recall_args(
                paths.index,
                theme_map=paths.digest,
                manifest_dir=paths.manifest_dir,
                project_root=paths.project_root,
                allow_stale_digest=True,
            )
        )
        == 2
    )

    error = capsys.readouterr().err
    assert "index is stale" in error.lower()
    assert "--allow-stale-index" in error


def test_recall_stale_digest_flag_is_registered_unabbreviated(
    tmp_path: Path,
) -> None:
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"

    parsed = parser.parse_args(
        [
            "recall",
            "--index",
            str(index_path),
            "--theme-map",
            str(digest_path),
            "--allow-stale-digest",
        ]
    )
    assert parsed.allow_stale_digest is True

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "recall",
                "--index",
                str(index_path),
                "--theme-map",
                str(digest_path),
                "--allow-stale-dig",
            ]
        )
    assert exc_info.value.code == 2


def test_instruction_payload_version_bumped_for_recall_docs_payload_change() -> None:
    from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION

    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple("2026.07.04.2")


def _recall_args(
    index: Path,
    *,
    theme_map: Path,
    manifest_dir: Path | None = None,
    project_root: Path | None = None,
    allow_stale_index: bool = False,
    allow_stale_digest: bool = False,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="recall",
        index=str(index),
        text=None,
        tag=["recall"],
        path=[],
        artifact=[],
        validation_command=[],
        review_text=None,
        manifest_slug=[],
        for_manifest=None,
        plan_packet=False,
        theme_map=str(theme_map),
        manifest_dir=str(manifest_dir) if manifest_dir is not None else None,
        project_root=str(project_root) if project_root is not None else None,
        allow_stale_index=allow_stale_index,
        allow_stale_digest=allow_stale_digest,
        limit=10,
        json=json_mode,
    )


def _write_index_and_stale_digest(tmp_path: Path) -> argparse.Namespace:
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", lesson_type="validation")
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(digest_path, "old-index-fingerprint")
    return argparse.Namespace(
        index=index_path,
        digest=digest_path,
        manifest_dir=manifest_dir,
        project_root=tmp_path,
    )


def _write_stale_index_and_matching_digest(tmp_path: Path) -> argparse.Namespace:
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml", lesson_type="validation")
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(digest_path, index.generated_from)
    _write_manifest(manifest_dir / "beta.manifest.yaml", lesson_type="testing")
    return argparse.Namespace(
        index=index_path,
        digest=digest_path,
        manifest_dir=manifest_dir,
        project_root=tmp_path,
    )


def _write_manifest(path: Path, *, lesson_type: str) -> None:
    slug = path.name.removesuffix(".manifest.yaml")
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": f"{slug} outcome",
                "type": "feature",
                "created": "2026-07-05",
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
                    "completed_at": "2026-07-05T01:02:03Z",
                    "summary": f"{slug} implementation completed.",
                    "lessons": [
                        {
                            "lesson_type": lesson_type,
                            "summary": f"{lesson_type} lesson for recall.",
                            "tags": ["recall"],
                            "paths": [f"src/{slug}.py"],
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
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_digest(path: Path, generated_from: str) -> None:
    data = {
        "schema_version": "1",
        "source_generated_from": generated_from,
        "advisory": True,
        "themes": [
            {
                "canonical_name": "Validation Discipline",
                "member_lesson_types": ["validation"],
                "summary": "Validation lessons share a canonical theme.",
                "source_manifests": ["alpha"],
            }
        ],
        "digest_entries": [
            {
                "theme": "Validation Discipline",
                "summary": "Keep recall annotations deterministic.",
                "source_lessons": [
                    {
                        "manifest_slug": "alpha",
                        "lesson_type": "validation",
                    }
                ],
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))
