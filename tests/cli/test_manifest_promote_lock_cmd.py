"""Tests for plan-lock migration in 'maid manifest promote'."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from maid_runner.cli.commands.manifest import cmd_manifest
from maid_runner.core.plan_lock import PlanLock, default_plan_lock_path
from maid_runner.core.supersession_audit import compute_manifest_hash


DRAFT_NAME = "add-example.manifest.yaml"
SLUG = "add-example"


def _write_draft(
    project_root: Path,
    validate_commands: list[str],
    read_paths: list[str] | None = None,
) -> Path:
    draft_dir = project_root / "manifests" / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft_path = draft_dir / DRAFT_NAME
    files: dict = {
        "create": [
            {
                "path": "src/example.py",
                "artifacts": [{"kind": "function", "name": "example_func"}],
            }
        ]
    }
    if read_paths:
        files["read"] = read_paths
    data = {
        "schema": "2",
        "goal": "Add example",
        "type": "feature",
        "created": "2026-06-02",
        "files": files,
        "validate": validate_commands,
    }
    draft_path.write_text(yaml.safe_dump(data, sort_keys=False))
    return draft_path


def _lock_draft(project_root: Path, draft_path: Path) -> Path:
    from maid_runner.core.plan_lock import create_plan_lock

    lock = create_plan_lock(draft_path, project_root)
    lock_path = default_plan_lock_path(project_root, SLUG)
    lock.save(lock_path)
    return lock_path


def _promote_args(
    project_root: Path, draft_path: Path, **overrides
) -> argparse.Namespace:
    values = {
        "manifest_command": "promote",
        "manifest_path": str(draft_path),
        "output_dir": str(project_root / "manifests"),
        "project_root": str(project_root),
        "no_run": False,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class TestPromoteLockMigration:
    def test_promote_migrates_lock_to_promoted_path(self, tmp_path):
        draft_path = _write_draft(tmp_path, ['python -c "raise SystemExit(1)"'])
        lock_path = _lock_draft(tmp_path, draft_path)
        prior_hash = PlanLock.load(lock_path).manifest_hash

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path, no_run=True))

        assert exit_code == 0
        promoted = tmp_path / "manifests" / DRAFT_NAME
        lock = PlanLock.load(lock_path)
        assert lock.manifest_path == f"manifests/{DRAFT_NAME}"
        assert lock.manifest_hash == compute_manifest_hash(promoted)
        assert lock.revision == 2
        assert lock.revisions[-1].prior_manifest_hash == prior_hash
        assert "promote" in lock.revisions[-1].reason.lower()

    def test_promote_rewrites_self_referencing_validate_paths(self, tmp_path):
        draft_rel = f"manifests/drafts/{DRAFT_NAME}"
        draft_path = _write_draft(
            tmp_path,
            [f"maid validate {draft_rel} --mode schema --quiet"],
        )

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))

        assert exit_code == 0
        promoted = tmp_path / "manifests" / DRAFT_NAME
        data = yaml.safe_load(promoted.read_text())
        assert data["validate"] == [
            f"maid validate manifests/{DRAFT_NAME} --mode schema --quiet"
        ]
        assert all("manifests/drafts" not in command for command in data["validate"])

    def test_promote_recaptures_red_evidence_by_default(self, tmp_path):
        draft_path = _write_draft(tmp_path, ['python -c "raise SystemExit(1)"'])
        lock_path = _lock_draft(tmp_path, draft_path)

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))

        assert exit_code == 0
        lock = PlanLock.load(lock_path)
        assert lock.red_evidence is not None
        assert lock.red_evidence["red"] is True
        assert lock.red_evidence["commands"][0]["exit_code"] == 1

    def test_promote_no_run_records_null_red_evidence(self, tmp_path):
        draft_path = _write_draft(tmp_path, ['python -c "raise SystemExit(1)"'])
        lock_path = _lock_draft(tmp_path, draft_path)

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path, no_run=True))

        assert exit_code == 0
        lock = PlanLock.load(lock_path)
        assert lock.red_evidence is None
        assert lock.manifest_path == f"manifests/{DRAFT_NAME}"
        assert lock.revision == 2

    def test_promote_refuses_mismatched_lock(self, tmp_path, capsys):
        draft_path = _write_draft(tmp_path, ['python -c "raise SystemExit(1)"'])
        lock_path = _lock_draft(tmp_path, draft_path)
        original = json.loads(lock_path.read_text())
        original["manifest_path"] = "manifests/drafts/other.manifest.yaml"
        lock_path.write_text(json.dumps(original, indent=2))
        before = lock_path.read_text()

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path, no_run=True))

        assert exit_code == 2
        assert draft_path.exists()
        assert not (tmp_path / "manifests" / DRAFT_NAME).exists()
        assert lock_path.read_text() == before
        assert "lock" in capsys.readouterr().err.lower()

    def test_promote_refuses_unreadable_lock(self, tmp_path, capsys):
        draft_path = _write_draft(tmp_path, ['python -c "raise SystemExit(1)"'])
        lock_path = default_plan_lock_path(tmp_path, SLUG)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text("{not json")

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path, no_run=True))

        assert exit_code == 2
        assert draft_path.exists()
        assert not (tmp_path / "manifests" / DRAFT_NAME).exists()
        assert lock_path.read_text() == "{not json"
        assert "lock" in capsys.readouterr().err.lower()

    def test_promote_rolls_back_when_lock_migration_fails(self, tmp_path, capsys):
        test_file = tmp_path / "tests" / "test_example.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("def test_example():\n    assert True\n")
        draft_path = _write_draft(
            tmp_path,
            ["pytest tests/test_example.py -v"],
            read_paths=["tests/test_example.py"],
        )
        lock_path = _lock_draft(tmp_path, draft_path)
        before = lock_path.read_text()
        test_file.unlink()

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path, no_run=True))

        assert exit_code == 2
        assert draft_path.exists()
        assert not (tmp_path / "manifests" / DRAFT_NAME).exists()
        assert lock_path.read_text() == before
        assert capsys.readouterr().err != ""

    def test_promote_without_lock_keeps_existing_behavior(self, tmp_path):
        draft_path = _write_draft(tmp_path, ["pytest tests/test_example.py -v"])

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path, no_run=True))

        assert exit_code == 0
        assert (tmp_path / "manifests" / DRAFT_NAME).exists()
        assert not draft_path.exists()
        assert not default_plan_lock_path(tmp_path, SLUG).exists()

    def test_promote_warns_about_other_manifests_referencing_draft_path(
        self, tmp_path, capsys
    ):
        draft_rel = f"manifests/drafts/{DRAFT_NAME}"
        draft_path = _write_draft(tmp_path, ["pytest tests/test_example.py -v"])
        referencing = tmp_path / "manifests" / "uses-example.manifest.yaml"
        referencing.parent.mkdir(parents=True, exist_ok=True)
        referencing.write_text(
            yaml.safe_dump(
                {
                    "schema": "2",
                    "goal": "Use example",
                    "type": "feature",
                    "created": "2026-06-02T00:00:00Z",
                    "files": {"read": [draft_rel]},
                    "validate": ["pytest tests/test_use.py -v"],
                },
                sort_keys=False,
            )
        )

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path, no_run=True))

        assert exit_code == 0
        output = capsys.readouterr()
        combined = output.out + output.err
        assert "uses-example.manifest.yaml" in combined
        assert "maid plan revise" in combined


class TestPromoteParserOptions:
    def test_promote_parser_accepts_no_run_and_project_root(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()

        args = parser.parse_args(
            [
                "manifest",
                "promote",
                "manifests/drafts/x.manifest.yaml",
                "--no-run",
                "--project-root",
                "subdir",
            ]
        )
        defaults = parser.parse_args(
            ["manifest", "promote", "manifests/drafts/x.manifest.yaml"]
        )

        assert args.no_run is True
        assert args.project_root == "subdir"
        assert defaults.no_run is False
        assert defaults.project_root == "."


class TestPromotionLockMigrationDocs:
    def test_promotion_lock_migration_docs_are_discoverable(self):
        root = Path(__file__).resolve().parents[2]
        workflow_doc = (root / "docs/draft-manifest-workflow.md").read_text(
            encoding="utf-8"
        )
        claude_md = (root / "CLAUDE.md").read_text(encoding="utf-8")

        assert "Plan Locks at Promotion" in workflow_doc
        assert "maid plan revise" in workflow_doc
        assert "migrates the promoted manifest's plan lock" in claude_md
