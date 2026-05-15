"""Behavioral tests for `maid audit supersessions` CLI command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands._format import format_supersession_audit
from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.audit import cmd_audit, cmd_audit_supersessions
from maid_runner.core.supersession_audit import (
    GrandfatherEntry,
    GrandfatherLock,
    SupersessionViolation,
    compute_manifest_hash,
    default_lock_path,
)


def _write_pair(manifests_dir: Path) -> None:
    (manifests_dir / "b.manifest.yaml").write_text(
        """schema: "2"
goal: "B"
type: feature
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""
    )
    (manifests_dir / "a.manifest.yaml").write_text(
        """schema: "2"
goal: "A"
type: feature
supersedes: [b]
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
"""
    )


class TestAuditSubparserRegistered:
    def test_build_parser_includes_audit_subcommand(self) -> None:
        parser = build_parser()
        subcommands: dict[str, argparse.ArgumentParser] = {}
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    subcommands[name] = sub
        assert "audit" in subcommands

    def test_audit_has_supersessions_subcommand(self) -> None:
        parser = build_parser()
        audit_parser: argparse.ArgumentParser | None = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                audit_parser = action.choices.get("audit")
                break
        assert audit_parser is not None
        audit_subs: dict[str, argparse.ArgumentParser] = {}
        for action in audit_parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    audit_subs[name] = sub
        assert "supersessions" in audit_subs


class TestCmdAuditDispatch:
    def test_cmd_audit_routes_to_supersessions(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(default_lock_path(tmp_path)),
            seal=False,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit(args)
        assert exit_code == 0


class TestCmdAuditSupersessionsClean:
    def test_exit_zero_when_no_violations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "only.manifest.yaml").write_text(
            """schema: "2"
goal: "only"
type: feature
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""
        )
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(default_lock_path(tmp_path)),
            seal=False,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 0


class TestCmdAuditSupersessionsViolations:
    def test_exit_nonzero_when_non_grandfathered_violations(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        _write_pair(manifests_dir)
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(default_lock_path(tmp_path)),
            seal=False,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 1

    def test_json_mode_emits_machine_readable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        _write_pair(manifests_dir)
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(default_lock_path(tmp_path)),
            seal=False,
            unseal=False,
            json=True,
            quiet=False,
            project_root=str(tmp_path),
        )
        cmd_audit_supersessions(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "violations" in parsed


class TestCmdAuditSupersessionsSeal:
    def test_seal_writes_lock_file(self, tmp_path: Path) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        _write_pair(manifests_dir)
        lock_path = tmp_path / ".maid" / "legacy-grandfathered.lock"
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=True,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 0
        assert lock_path.exists()
        loaded = GrandfatherLock.load(lock_path)
        assert loaded.is_sealed() is True
        assert len(loaded.entries) >= 1

    def test_seal_refuses_when_already_sealed_without_unseal(
        self, tmp_path: Path
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        _write_pair(manifests_dir)
        lock_path = tmp_path / ".maid" / "legacy-grandfathered.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        GrandfatherLock.empty().with_seal(sealed_at="2026-05-15", entries=()).save(
            lock_path
        )

        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=True,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 2

    def test_seal_allows_overwrite_with_unseal_flag(self, tmp_path: Path) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        _write_pair(manifests_dir)
        lock_path = tmp_path / ".maid" / "legacy-grandfathered.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        GrandfatherLock.empty().with_seal(sealed_at="2026-05-15", entries=()).save(
            lock_path
        )

        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=True,
            unseal=True,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 0
        loaded = GrandfatherLock.load(lock_path)
        assert len(loaded.entries) >= 1


class TestCmdAuditSupersessionsSealThenAudit:
    def test_seal_then_audit_exits_zero_with_grandfathered_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        _write_pair(manifests_dir)
        lock_path = tmp_path / ".maid" / "legacy-grandfathered.lock"
        seal_args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=True,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        assert cmd_audit_supersessions(seal_args) == 0
        capsys.readouterr()

        audit_args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=False,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(audit_args)
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "grandfathered" in out.lower()

    def test_quiet_suppresses_success_summary_after_seal(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        _write_pair(manifests_dir)
        lock_path = tmp_path / ".maid" / "legacy-grandfathered.lock"
        seal_args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=True,
            unseal=False,
            json=False,
            quiet=True,
            project_root=str(tmp_path),
        )
        assert cmd_audit_supersessions(seal_args) == 0
        assert capsys.readouterr().out == ""

        audit_args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=False,
            unseal=False,
            json=False,
            quiet=True,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(audit_args)
        assert exit_code == 0
        assert capsys.readouterr().out == ""


class TestCmdAuditSupersessionsChainLoadErrors:
    def test_audit_refuses_on_malformed_manifest(self, tmp_path: Path) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "valid.manifest.yaml").write_text(
            """schema: "2"
goal: "valid"
type: feature
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""
        )
        (manifests_dir / "broken.manifest.yaml").write_text(
            "this is not: [valid: yaml: at: all"
        )
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(default_lock_path(tmp_path)),
            seal=False,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 2

    def test_seal_refuses_on_malformed_manifest(self, tmp_path: Path) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "valid.manifest.yaml").write_text(
            """schema: "2"
goal: "valid"
type: feature
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""
        )
        (manifests_dir / "broken.manifest.yaml").write_text(
            "this is not: [valid: yaml: at: all"
        )
        lock_path = tmp_path / ".maid" / "legacy-grandfathered.lock"
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=True,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 2
        assert not lock_path.exists()


class TestCmdAuditSupersessionsRelativeManifestDir:
    def test_relative_manifest_dir_resolved_against_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        m_dir = project_root / "manifests"
        m_dir.mkdir()
        (m_dir / "only.manifest.yaml").write_text(
            """schema: "2"
goal: "only"
type: feature
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""
        )
        other_dir = tmp_path / "elsewhere"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)

        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir="manifests",
            lock=str(default_lock_path(project_root)),
            seal=False,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(project_root),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 0


class TestCmdAuditSupersessionsInvalidLock:
    def test_exit_nonzero_when_lock_file_corrupt(self, tmp_path: Path) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "only.manifest.yaml").write_text(
            """schema: "2"
goal: "x"
type: feature
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""
        )
        lock_dir = tmp_path / ".maid"
        lock_dir.mkdir()
        lock_path = lock_dir / "legacy-grandfathered.lock"
        lock_path.write_text("not json")
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(lock_path),
            seal=False,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 2


class TestCmdAuditSupersessionsJsonShape:
    def test_json_output_is_single_parseable_object_when_removed_errors_present(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "only.manifest.yaml").write_text(
            """schema: "2"
goal: "only"
type: feature
removed_artifacts:
  - kind: function
    name: ghost
    file: src/missing.py
    reason: "bypass attempt"
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""
        )
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(default_lock_path(tmp_path)),
            seal=False,
            unseal=False,
            json=True,
            quiet=False,
            project_root=str(tmp_path),
        )
        cmd_audit_supersessions(args)
        out = capsys.readouterr().out.strip()
        parsed = json.loads(out)
        assert "violations" in parsed
        assert "grandfathered_count" in parsed
        assert "removed_artifact_errors" in parsed
        assert len(parsed["removed_artifact_errors"]) >= 1


class TestCmdAuditSupersessionsVerifiesRemovedArtifacts:
    def test_exit_nonzero_when_removed_artifact_file_missing(
        self, tmp_path: Path
    ) -> None:
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "only.manifest.yaml").write_text(
            """schema: "2"
goal: "only"
type: feature
removed_artifacts:
  - kind: function
    name: ghost
    file: src/does_not_exist.py
    reason: "bypass attempt"
files:
  create:
    - path: src/x.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""
        )
        args = SimpleNamespace(
            audit_command="supersessions",
            manifest_dir=str(manifests_dir),
            lock=str(default_lock_path(tmp_path)),
            seal=False,
            unseal=False,
            json=False,
            quiet=False,
            project_root=str(tmp_path),
        )
        exit_code = cmd_audit_supersessions(args)
        assert exit_code == 1


class TestFormatSupersessionAuditText:
    def test_clean_shows_no_violations(self) -> None:
        out = format_supersession_audit(
            violations=[],
            grandfathered_count=0,
            sealed_at=None,
            json_mode=False,
        )
        assert "no" in out.lower() or "0" in out

    def test_shows_violation_details(self) -> None:
        v = SupersessionViolation(
            superseding_slug="a",
            superseded_slug="b",
            superseding_manifest_path="manifests/a.manifest.yaml",
            file_path="src/a.py",
            artifact_key="function:foo",
            artifact_name="foo",
            artifact_kind="function",
        )
        out = format_supersession_audit(
            violations=[v],
            grandfathered_count=0,
            sealed_at=None,
            json_mode=False,
        )
        assert "foo" in out
        assert "a" in out
        assert "b" in out

    def test_grandfathered_count_visible(self) -> None:
        out = format_supersession_audit(
            violations=[],
            grandfathered_count=7,
            sealed_at="2026-05-15",
            json_mode=False,
        )
        assert "7" in out
        assert "grandfathered" in out.lower()


class TestFormatSupersessionAuditJson:
    def test_json_includes_violations_and_grandfathered_count(self) -> None:
        v = SupersessionViolation(
            superseding_slug="a",
            superseded_slug="b",
            superseding_manifest_path="manifests/a.manifest.yaml",
            file_path="src/a.py",
            artifact_key="function:foo",
            artifact_name="foo",
            artifact_kind="function",
        )
        out = format_supersession_audit(
            violations=[v],
            grandfathered_count=2,
            sealed_at="2026-05-15",
            json_mode=True,
        )
        parsed = json.loads(out)
        assert parsed["grandfathered_count"] == 2
        assert parsed["sealed_at"] == "2026-05-15"
        assert isinstance(parsed["violations"], list)
        assert len(parsed["violations"]) == 1
        assert parsed["violations"][0]["artifact_name"] == "foo"


class TestComputeManifestHashIntegration:
    def test_hash_used_to_key_grandfather_entry(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "m.manifest.yaml"
        manifest_path.write_text("schema: '2'\ngoal: x\n")
        h = compute_manifest_hash(manifest_path)
        entry = GrandfatherEntry(
            superseding_slug="m",
            content_hash=h,
            dropped_artifact_keys=("function:foo",),
            reason="legacy",
        )
        assert entry.content_hash == h
