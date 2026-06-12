"""Tests for YAML rendering style in 'maid manifest promote'.

Promote rewrites the promoted manifest file. Multiline strings such as
`description:` must stay readable literal block scalars instead of escaped
double-quoted scalars full of `\\n` markers and backslash continuations.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from maid_runner.cli.commands.manifest import cmd_manifest

DRAFT_NAME = "add-example.manifest.yaml"

MULTILINE_DESCRIPTION = (
    "Implement the detection signal recorded in the incident.\n"
    "\n"
    "Decisions for the implementer — do not redesign these:\n"
    "\n"
    "1. Snapshot: the lock extends the existing payload with\n"
    "   validate_commands, captured at save time.\n"
    "2. Check: enforcement gains an integrity check.\n"
)

LONG_INSTEAD = (
    "Compare against the snapshot written at lock save time: legal post-lock "
    "additive manifest edits do not fail and only lock-record inconsistency "
    "does, which keeps the gate honest."
)


def _write_draft(project_root: Path) -> Path:
    draft_dir = project_root / "manifests" / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / DRAFT_NAME
    data = {
        "schema": "2",
        "goal": "Add example",
        "type": "feature",
        "created": "2026-06-12T00:00:00Z",
        "description": MULTILINE_DESCRIPTION,
        "temptations": [
            {"risk": "Do not compare against HEAD.", "instead": LONG_INSTEAD}
        ],
        "files": {
            "create": [
                {
                    "path": "src/example.py",
                    "artifacts": [{"kind": "function", "name": "example_func"}],
                }
            ]
        },
        "validate": ["pytest tests/test_example.py -v"],
    }
    draft_path.write_text(yaml.safe_dump(data, sort_keys=False))
    return draft_path


def _promote_args(project_root: Path, draft_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        manifest_command="promote",
        manifest_path=str(draft_path),
        output_dir=str(project_root / "manifests"),
        project_root=str(project_root),
        no_run=True,
        json=False,
    )


def _promoted_text(project_root: Path) -> str:
    return (project_root / "manifests" / DRAFT_NAME).read_text()


def test_promote_renders_multiline_description_as_literal_block(tmp_path: Path):
    draft_path = _write_draft(tmp_path)

    exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))

    text = _promoted_text(tmp_path)
    assert exit_code == 0
    assert "description: |" in text
    assert "\\n" not in text
    assert "—" in text


def test_promote_round_trips_multiline_description_content(tmp_path: Path):
    draft_path = _write_draft(tmp_path)

    exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))

    promoted = yaml.safe_load(_promoted_text(tmp_path))
    assert exit_code == 0
    assert promoted["description"] == MULTILINE_DESCRIPTION


def test_promote_does_not_wrap_long_strings_with_backslashes(tmp_path: Path):
    draft_path = _write_draft(tmp_path)

    exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))

    text = _promoted_text(tmp_path)
    promoted = yaml.safe_load(text)
    assert exit_code == 0
    assert all(not line.endswith("\\") for line in text.splitlines())
    assert promoted["temptations"][0]["instead"] == LONG_INSTEAD
