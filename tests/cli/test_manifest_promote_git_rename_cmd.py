"""Behavioral contract for source-preserving draft promotion."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

import yaml

from maid_runner.cli.commands.manifest import cmd_manifest


DRAFT_NAME = "preserve-history.manifest.yaml"
DRAFT_TEXT = """# Keep this planning context for reviewers.
schema: "2"
goal: "Preserve promotion history"
type: fix
created: "2026-07-20T00:00:00Z"
metadata:
  draft_defaults: &draft_defaults {status: draft, author: codex}
  active_defaults: &active_defaults {priority: high}
  <<: [*draft_defaults, *active_defaults] # Clear only the inherited lifecycle marker.
  tags: ["git-history", "yaml-style", "promotion"]
description: >
  Preserve human-authored YAML presentation during promotion.

  Git should recognize the tracked path transition as a rename while the
  semantic promotion fields still change through the sanctioned workflow.
temptations:
  - risk: "Do not mutate the Git index."
    instead: "Preserve source similarity in the promoted YAML."
  - risk: "Do not rewrite unrelated presentation."
    instead: "Change only values required by promotion."
files:
  create:
    - path: src/example.py
      artifacts:
        - {kind: function, name: example_func, args: [], returns: str}
  read:
    - tests/test_example.py
validate:
  - "uv run maid validate manifests/drafts/preserve-history.manifest.yaml --mode behavioral"
  - ["uv", "run", "pytest", "-q", "tests/test_example.py"]
"""


def _write_draft(project_root: Path) -> Path:
    draft_dir = project_root / "manifests" / "drafts"
    draft_dir.mkdir(parents=True)
    draft_path = draft_dir / DRAFT_NAME
    draft_path.write_text(DRAFT_TEXT)
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


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_promote_preserves_untouched_yaml_presentation(tmp_path: Path):
    draft_path = _write_draft(tmp_path)

    exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))

    promoted_text = (tmp_path / "manifests" / DRAFT_NAME).read_text()
    assert exit_code == 0
    assert "# Keep this planning context for reviewers." in promoted_text
    assert 'tags: ["git-history", "yaml-style", "promotion"]' in promoted_text
    assert (
        "{kind: function, name: example_func, args: [], returns: str}" in promoted_text
    )
    assert "description: >" in promoted_text
    metadata = yaml.safe_load(promoted_text)["metadata"]
    assert "status" not in metadata
    assert metadata["draft_defaults"]["status"] == "draft"
    assert "manifests/drafts/preserve-history.manifest.yaml" not in promoted_text
    assert "manifests/preserve-history.manifest.yaml" in promoted_text


def test_staged_promotion_is_detected_as_git_rename(tmp_path: Path):
    draft_path = _write_draft(tmp_path)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "maid-test@example.com")
    _git(tmp_path, "config", "user.name", "MAID Test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "track draft")

    exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))
    _git(tmp_path, "add", "-A")
    summary = _git(tmp_path, "diff", "--cached", "--summary").stdout

    assert exit_code == 0
    assert "rename manifests/{drafts => }/preserve-history.manifest.yaml" in summary
    assert "create mode" not in summary
    assert "delete mode" not in summary
