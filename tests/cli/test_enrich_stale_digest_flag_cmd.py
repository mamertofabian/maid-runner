"""Behavioral tests for explicit stale-digest opt-in flags."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import yaml


def test_stale_digest_rejected_without_any_allow_flag(tmp_path: Path, capsys):
    from maid_runner.cli.commands.enrich import cmd_enrich
    from maid_runner.cli.commands.insights import cmd_insights

    paths = _write_index_and_stale_digest(tmp_path)

    assert cmd_enrich(_enrich_args("validate", paths.index, digest=paths.digest)) == 2
    assert "stale" in capsys.readouterr().err.lower()

    assert (
        cmd_enrich(
            _enrich_args(
                "render",
                paths.index,
                digest=paths.digest,
                md_output=paths.markdown,
            )
        )
        == 2
    )
    assert "stale" in capsys.readouterr().err.lower()

    assert cmd_insights(_insights_args(paths.index, theme_map=paths.digest)) == 2
    assert "stale" in capsys.readouterr().err.lower()


def test_allow_stale_digest_waives_only_digest_staleness(tmp_path: Path, capsys):
    from maid_runner.cli.commands.enrich import cmd_enrich
    from maid_runner.cli.commands.insights import cmd_insights

    paths = _write_index_and_stale_digest(tmp_path)

    assert (
        cmd_enrich(
            _enrich_args(
                "validate",
                paths.index,
                digest=paths.digest,
                allow_stale_digest=True,
            )
        )
        == 0
    )
    assert "valid" in capsys.readouterr().out.lower()

    assert (
        cmd_enrich(
            _enrich_args(
                "render",
                paths.index,
                digest=paths.digest,
                md_output=paths.markdown,
                allow_stale_digest=True,
            )
        )
        == 0
    )
    assert paths.markdown.exists()
    capsys.readouterr()

    assert (
        cmd_insights(
            _insights_args(
                paths.index,
                theme_map=paths.digest,
                allow_stale_digest=True,
                json_mode=True,
            )
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["by_lesson_type"][0]["key"]

    stale_index_paths = _write_stale_index_and_matching_digest(tmp_path / "stale-index")
    assert (
        cmd_enrich(
            _enrich_args(
                "validate",
                stale_index_paths.index,
                digest=stale_index_paths.digest,
                manifest_dir=stale_index_paths.manifest_dir,
                project_root=stale_index_paths.project_root,
                allow_stale_digest=True,
            )
        )
        == 2
    )
    assert "index is stale" in capsys.readouterr().err.lower()


def test_allow_stale_index_keeps_backward_compatible_double_duty(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.enrich import cmd_enrich
    from maid_runner.cli.commands.insights import cmd_insights

    paths = _write_index_and_stale_digest(tmp_path)

    assert (
        cmd_enrich(
            _enrich_args(
                "validate",
                paths.index,
                digest=paths.digest,
                allow_stale_index=True,
            )
        )
        == 0
    )
    assert "valid" in capsys.readouterr().out.lower()

    assert (
        cmd_enrich(
            _enrich_args(
                "render",
                paths.index,
                digest=paths.digest,
                md_output=paths.markdown,
                allow_stale_index=True,
            )
        )
        == 0
    )
    assert "# Outcome Enrichment Digest" in paths.markdown.read_text(encoding="utf-8")

    assert (
        cmd_insights(
            _insights_args(
                paths.index,
                theme_map=paths.digest,
                allow_stale_index=True,
                json_mode=True,
            )
        )
        == 0
    )
    assert "validation" in capsys.readouterr().out


def test_stale_digest_flag_is_registered_unabbreviated(tmp_path: Path):
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"

    enrich_validate = parser.parse_args(
        [
            "enrich",
            "validate",
            "--index",
            str(index_path),
            "--digest",
            str(digest_path),
            "--allow-stale-digest",
        ]
    )
    assert enrich_validate.allow_stale_digest is True

    enrich_render = parser.parse_args(
        [
            "enrich",
            "render",
            "--index",
            str(index_path),
            "--digest",
            str(digest_path),
            "--allow-stale-digest",
        ]
    )
    assert enrich_render.allow_stale_digest is True

    insights = parser.parse_args(
        [
            "insights",
            "--index",
            str(index_path),
            "--theme-map",
            str(digest_path),
            "--allow-stale-digest",
        ]
    )
    assert insights.allow_stale_digest is True

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "enrich",
                "validate",
                "--index",
                str(index_path),
                "--digest",
                str(digest_path),
                "--allow-stale-dig",
            ]
        )
    assert exc_info.value.code == 2


def _enrich_args(
    enrich_command: str,
    index: Path,
    *,
    digest: Path,
    md_output: Path | None = None,
    manifest_dir: Path | None = None,
    project_root: Path | None = None,
    allow_stale_index: bool = False,
    allow_stale_digest: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="enrich",
        enrich_command=enrich_command,
        index=str(index),
        digest=str(digest),
        md_output=(
            str(md_output) if md_output is not None else ".maid/outcomes-digest.md"
        ),
        output=None,
        manifest_dir=str(manifest_dir) if manifest_dir is not None else None,
        project_root=str(project_root) if project_root is not None else None,
        allow_stale_index=allow_stale_index,
        allow_stale_digest=allow_stale_digest,
        json=False,
    )


def _insights_args(
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
        command="insights",
        index=str(index),
        theme_map=str(theme_map),
        manifest_dir=str(manifest_dir) if manifest_dir is not None else None,
        project_root=str(project_root) if project_root is not None else None,
        allow_stale_index=allow_stale_index,
        allow_stale_digest=allow_stale_digest,
        limit=10,
        json=json_mode,
    )


def _write_index_and_stale_digest(tmp_path: Path):
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
    markdown_path = tmp_path / ".maid" / "outcomes-digest.md"
    write_outcome_index(index, index_path)
    _write_digest(digest_path, "old-index-fingerprint")
    return _Paths(
        index=index_path,
        digest=digest_path,
        markdown=markdown_path,
        manifest_dir=manifest_dir,
        project_root=tmp_path,
    )


def _write_stale_index_and_matching_digest(tmp_path: Path):
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(parents=True)
    _write_manifest(manifest_dir / "alpha.manifest.yaml", lesson_type="validation")
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    markdown_path = tmp_path / ".maid" / "outcomes-digest.md"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path, index.generated_from, member_lesson_types=("validation",)
    )
    _write_manifest(manifest_dir / "gamma.manifest.yaml", lesson_type="testing")
    return _Paths(
        index=index_path,
        digest=digest_path,
        markdown=markdown_path,
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
                "created": "2026-07-04",
                "metadata": {"tags": ["outcome-records", "cli"]},
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
                    "completed_at": "2026-07-04T01:02:03Z",
                    "summary": f"{slug} implementation completed.",
                    "lessons": [
                        {
                            "lesson_type": lesson_type,
                            "summary": f"{lesson_type} lessons stay grounded.",
                            "tags": ["outcome-records"],
                            "paths": [f"src/{slug}.py"],
                        }
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
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_digest(
    path: Path,
    generated_from: str,
    *,
    member_lesson_types: tuple[str, ...] = ("validation", "validator-hardening"),
) -> None:
    data = {
        "schema_version": "1",
        "source_generated_from": generated_from,
        "advisory": True,
        "themes": [
            {
                "canonical_name": "validation",
                "member_lesson_types": list(member_lesson_types),
                "summary": "Validation lessons share a canonical theme.",
                "source_manifests": ["alpha", "beta"],
            }
        ],
        "digest_entries": [
            {
                "theme": "validation",
                "summary": "Validate deterministic enrichment artifacts.",
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


class _Paths(argparse.Namespace):
    index: Path
    digest: Path
    markdown: Path
    manifest_dir: Path
    project_root: Path
