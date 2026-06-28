"""Behavioral tests for the `maid enrich` CLI command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def test_enrich_prompt_emits_bounded_corpus_from_index(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    from maid_runner.cli.commands import enrich as enrich_mod
    from maid_runner.cli.commands._main import build_parser, main
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml")
    index_path = tmp_path / ".maid" / "outcomes.json"
    prompt_path = tmp_path / ".maid" / "prompt.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path),
        index_path,
    )
    seen: dict[str, argparse.Namespace] = {}

    def fake_cmd_enrich(args: argparse.Namespace) -> int:
        seen["args"] = args
        return 0

    real_cmd_enrich = enrich_mod.cmd_enrich
    parser = build_parser()
    args = parser.parse_args(
        [
            "enrich",
            "prompt",
            "--index",
            str(index_path),
            "--output",
            str(prompt_path),
            "--allow-stale-index",
            "--json",
        ]
    )
    assert args.command == "enrich"
    assert args.enrich_command == "prompt"
    assert args.index == str(index_path)
    assert args.output == str(prompt_path)
    assert args.allow_stale_index is True

    monkeypatch.setattr(enrich_mod, "cmd_enrich", fake_cmd_enrich)
    assert main(["enrich", "prompt", "--index", str(index_path)]) == 0
    assert seen["args"].command == "enrich"
    monkeypatch.setattr(enrich_mod, "cmd_enrich", real_cmd_enrich)

    assert enrich_mod.cmd_enrich(_args("prompt", index_path, output=prompt_path)) == 0
    payload = json.loads(prompt_path.read_text(encoding="utf-8"))

    assert payload["known_lesson_types"] == ["validation"]
    assert payload["known_manifest_slugs"] == ["alpha"]
    assert payload["validation_universe"] == {
        "known_lesson_types": ["validation"],
        "known_manifest_slugs": ["alpha"],
    }
    assert "cluster and summarize only" in payload["system_prompt"]
    assert "alpha" in payload["user_prompt"]
    assert "validation" in payload["user_prompt"]
    assert capsys.readouterr().out == ""


def test_enrich_validate_accepts_grounded_digest(tmp_path: Path, capsys):
    from maid_runner.cli.commands.enrich import cmd_enrich
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml")
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(digest_path, index.generated_from)

    assert cmd_enrich(_args("validate", index_path, digest=digest_path)) == 0

    assert "valid" in capsys.readouterr().out.lower()


def test_enrich_validate_rejects_fabricated_digest(tmp_path: Path, capsys):
    from maid_runner.cli.commands.enrich import cmd_enrich
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml")
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(index, index_path)
    _write_digest(
        digest_path,
        index.generated_from,
        source_manifest="missing",
        source_lesson_type="fabricated",
    )

    assert cmd_enrich(_args("validate", index_path, digest=digest_path)) == 2

    error = capsys.readouterr().err
    assert "missing" in error
    assert "fabricated" in error


def test_enrich_validate_rejects_stale_digest_without_allow_flag(
    tmp_path: Path,
    capsys,
):
    from maid_runner.cli.commands.enrich import cmd_enrich
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml")
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path),
        index_path,
    )
    _write_digest(digest_path, "old-index-fingerprint")

    assert cmd_enrich(_args("validate", index_path, digest=digest_path)) == 2
    assert "stale" in capsys.readouterr().err.lower()

    assert (
        cmd_enrich(
            _args(
                "validate",
                index_path,
                digest=digest_path,
                allow_stale_index=True,
            )
        )
        == 0
    )
    assert "valid" in capsys.readouterr().out.lower()


def test_enrich_render_writes_markdown_atomically(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    from maid_runner.cli.commands import enrich as enrich_mod
    from maid_runner.core.outcomes import build_outcome_index, write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "alpha.manifest.yaml")
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    index_path = tmp_path / ".maid" / "outcomes.json"
    digest_path = tmp_path / ".maid" / "outcomes-digest.json"
    markdown_path = tmp_path / ".maid" / "outcomes-digest.md"
    write_outcome_index(index, index_path)
    _write_digest(digest_path, index.generated_from)

    assert (
        enrich_mod.cmd_enrich(
            _args("render", index_path, digest=digest_path, md_output=markdown_path)
        )
        == 0
    )
    assert "# Outcome Enrichment Digest" in markdown_path.read_text(encoding="utf-8")

    markdown_path.write_text("previous complete digest\n", encoding="utf-8")

    def interrupted_render(_digest):
        raise RuntimeError("render interrupted")

    monkeypatch.setattr(enrich_mod, "render_digest_markdown", interrupted_render)

    assert (
        enrich_mod.cmd_enrich(
            _args("render", index_path, digest=digest_path, md_output=markdown_path)
        )
        == 2
    )
    assert markdown_path.read_text(encoding="utf-8") == "previous complete digest\n"
    assert "render interrupted" in capsys.readouterr().err


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


def _write_digest(
    path: Path,
    generated_from: str,
    *,
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
                "member_lesson_types": ["validation"],
                "summary": "Validation lessons stay grounded.",
                "source_manifests": ["alpha"],
            }
        ],
        "digest_entries": [
            {
                "theme": "validation",
                "summary": "Use validation evidence before handoff.",
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


def _write_manifest(path: Path) -> None:
    data = {
        "schema": "2",
        "goal": "alpha outcome",
        "type": "feature",
        "created": "2026-06-01",
        "metadata": {"tags": ["outcome-records", "cli"]},
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
                    "lesson_type": "validation",
                    "summary": "Validation evidence should stay grounded.",
                    "tags": ["outcome-records"],
                    "paths": ["src/alpha.py"],
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
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
