"""Behavioral coverage for draft lifecycle markers created by the CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from maid_runner.cli.commands.manifest import cmd_manifest
from maid_runner.core.chain import ManifestChain


def test_manifest_create_under_drafts_writes_required_lifecycle_marker(
    tmp_path: Path,
) -> None:
    project_root = tmp_path
    output_dir = project_root / "manifests" / "drafts" / "selected"
    args = argparse.Namespace(
        manifest_command="create",
        file_path="src/example.py",
        goal="Add example",
        task_type="feature",
        artifacts='[{"kind": "function", "name": "example"}]',
        temptations=None,
        dry_run=False,
        json=False,
        output_dir=str(output_dir),
    )

    exit_code = cmd_manifest(args)

    assert exit_code == 0
    created_path = output_dir / "add-example.manifest.yaml"
    assert created_path.read_text().splitlines()[0] == "# draft-kind: implementation"
    assert (
        ManifestChain(
            project_root / "manifests", project_root
        ).inactive_manifest_diagnostics()
        == []
    )


def test_manifest_create_in_active_directory_keeps_generic_header(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "manifests"
    args = argparse.Namespace(
        manifest_command="create",
        file_path="src/example.py",
        goal="Add active example",
        task_type="feature",
        artifacts='[{"kind": "function", "name": "example"}]',
        temptations=None,
        dry_run=False,
        json=False,
        output_dir=str(output_dir),
    )

    exit_code = cmd_manifest(args)

    assert exit_code == 0
    created_path = output_dir / "add-active-example.manifest.yaml"
    first_line = created_path.read_text().splitlines()[0]
    assert first_line.startswith("# MAID manifest")
    assert first_line != "# draft-kind: implementation"
