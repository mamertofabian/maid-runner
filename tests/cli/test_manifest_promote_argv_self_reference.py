"""Regression coverage for argv-form self references during promotion."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from maid_runner.cli.commands.manifest import cmd_manifest


def test_promote_rewrites_argv_form_self_referencing_validate_path(
    tmp_path: Path,
) -> None:
    draft_dir = tmp_path / "manifests" / "drafts"
    draft_dir.mkdir(parents=True)
    draft_path = draft_dir / "argv-self-reference.manifest.yaml"
    draft_relative = "manifests/drafts/argv-self-reference.manifest.yaml"
    active_relative = "manifests/argv-self-reference.manifest.yaml"
    draft_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Exercise argv-form promotion",
                "type": "fix",
                "created": "2026-07-11T00:00:00Z",
                "files": {"scope": [{"path": "src/example.py", "reason": "fixture"}]},
                "validate": [
                    [
                        "./scripts/maid",
                        "validate",
                        draft_relative,
                        "--mode",
                        "implementation",
                    ]
                ],
            },
            sort_keys=False,
        )
    )

    exit_code = cmd_manifest(
        SimpleNamespace(
            manifest_command="promote",
            manifest_path=str(draft_path),
            output_dir=str(tmp_path / "manifests"),
            project_root=str(tmp_path),
            no_run=True,
            json=False,
        )
    )

    assert exit_code == 0
    promoted = yaml.safe_load((tmp_path / active_relative).read_text())
    assert promoted["validate"] == [
        [
            "./scripts/maid",
            "validate",
            active_relative,
            "--mode",
            "implementation",
        ]
    ]
    assert not draft_path.exists()


def test_promote_preserves_argv_values_that_only_contain_draft_path_substring(
    tmp_path: Path,
) -> None:
    draft_dir = tmp_path / "manifests" / "drafts"
    draft_dir.mkdir(parents=True)
    draft_path = draft_dir / "argv-substring.manifest.yaml"
    draft_relative = "manifests/drafts/argv-substring.manifest.yaml"
    embedded_value = f"--report={draft_relative}.json"
    draft_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Preserve non-self-reference argv values",
                "type": "fix",
                "created": "2026-07-11T00:00:00Z",
                "files": {"scope": [{"path": "src/example.py", "reason": "fixture"}]},
                "validate": [["tool", embedded_value]],
            },
            sort_keys=False,
        )
    )

    exit_code = cmd_manifest(
        SimpleNamespace(
            manifest_command="promote",
            manifest_path=str(draft_path),
            output_dir=str(tmp_path / "manifests"),
            project_root=str(tmp_path),
            no_run=True,
            json=False,
        )
    )

    assert exit_code == 0
    promoted = yaml.safe_load(
        (tmp_path / "manifests" / "argv-substring.manifest.yaml").read_text()
    )
    assert promoted["validate"] == [["tool", embedded_value]]
