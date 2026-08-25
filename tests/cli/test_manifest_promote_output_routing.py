"""Behavioral contract for manifest promotion output routing."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import yaml

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.manifest import cmd_manifest


def _write_draft(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Route nested promotion",
                "type": "fix",
                "created": "2026-08-25T00:00:00Z",
                "files": {"scope": [{"path": "src/example.py", "reason": "fixture"}]},
                "validate": ["pytest tests/test_example.py -q"],
            },
            sort_keys=False,
        )
    )


def _promote(path: Path, *, output_dir: str | None, project_root: Path) -> int:
    return cmd_manifest(
        Namespace(
            manifest_command="promote",
            manifest_path=str(path),
            output_dir=output_dir,
            project_root=str(project_root),
            no_run=True,
            json=False,
        )
    )


def test_promote_infers_nested_manifest_chain_from_draft_path(tmp_path: Path) -> None:
    draft = (
        tmp_path
        / "apps"
        / "studyfinder"
        / "manifests"
        / "drafts"
        / "nested.manifest.yaml"
    )
    _write_draft(draft)

    assert _promote(draft, output_dir=None, project_root=tmp_path) == 0
    assert (draft.parent.parent / draft.name).exists()
    assert not (tmp_path / "manifests" / draft.name).exists()
    assert not draft.exists()


def test_promote_infers_standard_root_manifest_chain(tmp_path: Path) -> None:
    draft = tmp_path / "manifests" / "drafts" / "root.manifest.yaml"
    _write_draft(draft)

    assert _promote(draft, output_dir=None, project_root=tmp_path) == 0
    assert (tmp_path / "manifests" / draft.name).exists()
    assert not draft.exists()


def test_promote_explicit_output_directory_overrides_draft_owner(
    tmp_path: Path,
) -> None:
    draft = (
        tmp_path / "apps" / "example" / "manifests" / "drafts" / "task.manifest.yaml"
    )
    explicit = tmp_path / "promoted"
    _write_draft(draft)

    assert _promote(draft, output_dir=str(explicit), project_root=tmp_path) == 0
    assert (explicit / draft.name).exists()
    assert not (draft.parent.parent / draft.name).exists()


def test_promote_rejects_ambiguous_source_without_output_directory(
    tmp_path: Path, capsys
) -> None:
    source = tmp_path / "incoming" / "ambiguous.manifest.yaml"
    _write_draft(source)

    assert _promote(source, output_dir=None, project_root=tmp_path) == 2
    assert "--output-dir" in capsys.readouterr().err
    assert source.exists()
    assert not (tmp_path / "manifests" / source.name).exists()
    assert not (source.parent.parent / source.name).exists()


def test_promote_parser_preserves_omitted_output_directory(tmp_path: Path) -> None:
    draft = tmp_path / "manifests" / "drafts" / "task.manifest.yaml"

    omitted = build_parser().parse_args(["manifest", "promote", str(draft)])
    explicit = build_parser().parse_args(
        ["manifest", "promote", str(draft), "--output-dir", "custom/manifests"]
    )

    assert omitted.output_dir is None
    assert explicit.output_dir == "custom/manifests"
