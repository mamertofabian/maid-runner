"""Behavioral tests for manifest sequence_number, version_tag, and chain event-log.

Verifies:
    - Manifest dataclass carries sequence_number and version_tag
    - Parser reads sequence_number and version_tag from YAML
    - Parser is backward-compatible (manifests without new fields still load)
    - ManifestChain.event_log returns all manifests in event order
    - Chain ordering uses sequence_number first, falling back to created -> slug
    - Mixed ordering (some with, some without sequence_number) emits diagnostics
    - version_tag round-trips through save/load
    - Superseded manifests appear in event_log
"""

from __future__ import annotations

from pathlib import Path

import yaml

from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest, save_manifest, slug_from_path
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import (
    ArtifactKind,
    ArtifactSpec,
    FileMode,
    FileSpec,
    Manifest,
)


# ---------------------------------------------------------------------------
# Manifest dataclass: sequence_number and version_tag attributes
# ---------------------------------------------------------------------------


class TestManifestEventLogFields:
    def test_sequence_number_defaults_to_none(self) -> None:
        m = Manifest(
            slug="test",
            source_path="/tmp/test.manifest.yaml",
            goal="test goal",
            validate_commands=(),
        )
        assert m.sequence_number is None

    def test_version_tag_defaults_to_none(self) -> None:
        m = Manifest(
            slug="test",
            source_path="/tmp/test.manifest.yaml",
            goal="test goal",
            validate_commands=(),
        )
        assert m.version_tag is None

    def test_sequence_number_can_be_set(self) -> None:
        m = Manifest(
            slug="test",
            source_path="/tmp/test.manifest.yaml",
            goal="test goal",
            validate_commands=(),
            sequence_number=7,
        )
        assert m.sequence_number == 7

    def test_version_tag_can_be_set(self) -> None:
        m = Manifest(
            slug="test",
            source_path="/tmp/test.manifest.yaml",
            goal="test goal",
            validate_commands=(),
            version_tag="v2.4.0",
        )
        assert m.version_tag == "v2.4.0"


# ---------------------------------------------------------------------------
# Parser: reading sequence_number and version_tag from YAML
# ---------------------------------------------------------------------------


class TestManifestParserEventLogFields:
    def test_parses_sequence_number_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """schema: "2"
goal: "test sequence_number"
type: feature
created: "2026-04-26"
sequence_number: 42
files:
  create:
    - path: dummy.py
      artifacts:
        - kind: function
          name: _placeholder
validate:
  - pytest tests/ -v
"""
        manifest_path = tmp_path / "test.manifest.yaml"
        manifest_path.write_text(yaml_content)

        m = load_manifest(manifest_path)
        assert m.sequence_number == 42

    def test_parses_version_tag_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """schema: "2"
goal: "test version_tag"
type: feature
created: "2026-04-26"
version_tag: "release-1.0"
files:
  create:
    - path: dummy.py
      artifacts:
        - kind: function
          name: _placeholder
validate:
  - pytest tests/ -v
"""
        manifest_path = tmp_path / "test.manifest.yaml"
        manifest_path.write_text(yaml_content)

        m = load_manifest(manifest_path)
        assert m.version_tag == "release-1.0"

    def test_backward_compatible_missing_fields(self, tmp_path: Path) -> None:
        yaml_content = """schema: "2"
goal: "legacy manifest without new fields"
type: fix
created: "2025-01-01"
files:
  create:
    - path: old.py
      artifacts:
        - kind: function
          name: _placeholder
validate:
  - pytest tests/ -v
"""
        manifest_path = tmp_path / "legacy.manifest.yaml"
        manifest_path.write_text(yaml_content)

        m = load_manifest(manifest_path)
        assert m.sequence_number is None
        assert m.version_tag is None


# ---------------------------------------------------------------------------
# Save/load round-trip
# ---------------------------------------------------------------------------


class TestManifestSaveLoadRoundTrip:
    def test_sequence_number_round_trips(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "roundtrip.manifest.yaml"
        original = Manifest(
            slug=slug_from_path(manifest_path),
            source_path=str(manifest_path),
            goal="round-trip test",
            validate_commands=(("pytest", "tests/", "-v"),),
            task_type=None,
            sequence_number=99,
            version_tag="v3.0.0-beta",
            files_create=(
                FileSpec(
                    path="dummy.py",
                    artifacts=(
                        ArtifactSpec(kind=ArtifactKind.FUNCTION, name="_placeholder"),
                    ),
                    mode=FileMode.CREATE,
                ),
            ),
        )
        save_manifest(original, manifest_path)

        reloaded = load_manifest(manifest_path)
        assert reloaded.sequence_number == 99
        assert reloaded.version_tag == "v3.0.0-beta"


# ---------------------------------------------------------------------------
# ManifestChain event_log: all manifests in event order
# ---------------------------------------------------------------------------


class TestChainEventLog:
    def test_event_log_includes_all_manifests(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a-first.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b-second.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )
        _write_manifest(
            manifest_dir,
            "c-third.manifest.yaml",
            goal="third",
            created="2026-03-01",
            sequence_number=3,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        log = chain.event_log()

        assert len(log) == 3
        assert [m.slug for m in log] == [
            "a-first",
            "b-second",
            "c-third",
        ]

    def test_event_log_uses_sequence_number_over_created(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Deliberately reverse creation order — sequence_number must win
        _write_manifest(
            manifest_dir,
            "b-second.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )
        _write_manifest(
            manifest_dir,
            "a-first.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "c-third.manifest.yaml",
            goal="third",
            created="2026-03-01",
            sequence_number=3,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        log = chain.event_log()

        assert [m.slug for m in log] == [
            "a-first",
            "b-second",
            "c-third",
        ]

    def test_event_log_falls_back_to_created_when_sequence_missing(
        self, tmp_path: Path
    ) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # No sequence_number — should sort by created
        _write_manifest(
            manifest_dir,
            "c.manifest.yaml",
            goal="latest",
            created="2026-03-01",
        )
        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="earliest",
            created="2026-01-01",
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="middle",
            created="2026-02-01",
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        log = chain.event_log()

        assert [m.slug for m in log] == ["a", "b", "c"]

    def test_event_log_includes_superseded_manifests(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "original.manifest.yaml",
            goal="original",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "replacement.manifest.yaml",
            goal="replacement",
            created="2026-02-01",
            sequence_number=2,
            supersedes=["original"],
        )

        chain = ManifestChain(manifest_dir, tmp_path)

        # Active manifests exclude superseded
        active = chain.active_manifests()
        assert len(active) == 1
        assert active[0].slug == "replacement"

        # event_log includes superseded
        log = chain.event_log()
        assert len(log) == 2
        assert {m.slug for m in log} == {"original", "replacement"}

    def test_mixed_ordering_does_not_crash(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "sequenced.manifest.yaml",
            goal="sequenced",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "legacy.manifest.yaml",
            goal="legacy",
            created="2026-02-01",
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        # Must not crash — mixed ordering should degrade gracefully
        log = chain.event_log()
        assert len(log) == 2

        # Mixed ordering emits a diagnostic warning
        diags = chain.diagnostics()
        mixed = [d for d in diags if d.code == ErrorCode.MIXED_SEQUENCE_NUMBERING]
        assert len(mixed) == 1, (
            f"Expected one MIXED_SEQUENCE_NUMBERING diagnostic, got: {diags}"
        )


# ---------------------------------------------------------------------------
# Duplicate sequence_number diagnostic
# ---------------------------------------------------------------------------


class TestDuplicateSequenceNumber:
    def test_duplicate_sequence_emits_error(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=5,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=5,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        diags = chain.diagnostics()
        dupes = [d for d in diags if d.code == ErrorCode.DUPLICATE_SEQUENCE_NUMBER]
        assert len(dupes) >= 1, (
            f"Expected DUPLICATE_SEQUENCE_NUMBER diagnostic, got: {diags}"
        )

    def test_unique_sequence_numbers_emit_no_duplicate_error(
        self, tmp_path: Path
    ) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        diags = chain.diagnostics()
        dupes = [d for d in diags if d.code == ErrorCode.DUPLICATE_SEQUENCE_NUMBER]
        assert len(dupes) == 0, f"Unexpected DUPLICATE_SEQUENCE_NUMBER: {diags}"


# ---------------------------------------------------------------------------
# Non-monotonic sequence_number diagnostic
# ---------------------------------------------------------------------------


class TestNonMonotonicSequenceOrder:
    def test_non_monotonic_emits_warning(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # seq 3 has earlier created than seq 2 — non-monotonic
        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="later seq, earlier created",
            created="2026-01-01",
            sequence_number=3,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="earlier seq, later created",
            created="2026-02-01",
            sequence_number=2,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        diags = chain.diagnostics()
        nonmono = [d for d in diags if d.code == ErrorCode.NON_MONOTONIC_SEQUENCE_ORDER]
        assert len(nonmono) >= 1, (
            f"Expected NON_MONOTONIC_SEQUENCE_ORDER diagnostic, got: {diags}"
        )

    def test_monotonic_sequence_emits_no_warning(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        diags = chain.diagnostics()
        nonmono = [d for d in diags if d.code == ErrorCode.NON_MONOTONIC_SEQUENCE_ORDER]
        assert len(nonmono) == 0, f"Unexpected NON_MONOTONIC_SEQUENCE_ORDER: {diags}"


# ---------------------------------------------------------------------------
# event_log_until: point-in-time query API
# ---------------------------------------------------------------------------


class TestEventLogUntil:
    def test_sequence_cutoff_returns_up_to_and_including(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )
        _write_manifest(
            manifest_dir,
            "c.manifest.yaml",
            goal="third",
            created="2026-03-01",
            sequence_number=3,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.event_log_until(sequence_number=2)

        assert len(result) == 2
        assert [m.slug for m in result] == ["a", "b"]

    def test_sequence_before_first_returns_empty(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=10,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.event_log_until(sequence_number=5)

        assert result == []

    def test_sequence_between_existing_returns_earlier(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "c.manifest.yaml",
            goal="third",
            created="2026-03-01",
            sequence_number=5,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.event_log_until(sequence_number=2)

        assert len(result) == 1
        assert result[0].slug == "a"

    def test_sequence_after_last_returns_all_sequenced(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.event_log_until(sequence_number=99)

        assert len(result) == 2

    def test_version_tag_cutoff_returns_through_first_match(
        self, tmp_path: Path
    ) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            version_tag="release-1",
        )
        _write_manifest(
            manifest_dir,
            "c.manifest.yaml",
            goal="third",
            created="2026-03-01",
            sequence_number=3,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.event_log_until(version_tag="release-1")

        assert len(result) == 2
        assert [m.slug for m in result] == ["a", "b"]

    def test_version_tag_not_found_returns_empty(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.event_log_until(version_tag="nonexistent")

        assert result == []

    def test_sequence_number_takes_precedence_over_version_tag(
        self, tmp_path: Path
    ) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            version_tag="v1",
        )
        _write_manifest(
            manifest_dir,
            "c.manifest.yaml",
            goal="third",
            created="2026-03-01",
            sequence_number=3,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        # seq=1 would only return [a], but version_tag="v1" would return [a,b].
        # sequence_number takes precedence.
        result = chain.event_log_until(sequence_number=1, version_tag="v1")
        assert [m.slug for m in result] == ["a"]

    def test_neither_arg_returns_all(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.event_log_until()

        assert len(result) == 2

    def test_includes_superseded_manifests(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "original.manifest.yaml",
            goal="original",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "replacement.manifest.yaml",
            goal="replacement",
            created="2026-02-01",
            sequence_number=2,
            supersedes=["original"],
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.event_log_until(sequence_number=2)

        assert len(result) == 2
        assert {m.slug for m in result} == {"original", "replacement"}

    def test_invalid_sequence_number_raises_value_error(self, tmp_path: Path) -> None:
        import pytest as pt

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        with pt.raises(ValueError, match="sequence_number must be >= 1"):
            chain.event_log_until(sequence_number=0)

    def test_empty_version_tag_raises_value_error(self, tmp_path: Path) -> None:
        import pytest as pt

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        with pt.raises(ValueError, match="version_tag must not be empty"):
            chain.event_log_until(version_tag="")


# ---------------------------------------------------------------------------
# replay_until: effective artifacts at a point in time
# ---------------------------------------------------------------------------


class TestReplayUntil:
    def test_full_replay_returns_effective_artifacts(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest_with_artifacts(
            manifest_dir,
            "first.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
            artifacts=[{"kind": "function", "name": "greet"}],
        )
        _write_manifest_with_artifacts(
            manifest_dir,
            "second.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            artifacts=[{"kind": "function", "name": "farewell"}],
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.replay_until()

        specs = result.get("mod.py", [])
        names = {s.name for s in specs}
        assert names == {"greet", "farewell"}

    def test_sequence_cutoff_excludes_later_artifacts(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest_with_artifacts(
            manifest_dir,
            "first.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
            artifacts=[{"kind": "function", "name": "greet"}],
        )
        _write_manifest_with_artifacts(
            manifest_dir,
            "second.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            artifacts=[{"kind": "function", "name": "farewell"}],
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.replay_until(sequence_number=1)

        specs = result.get("mod.py", [])
        names = {s.name for s in specs}
        assert names == {"greet"}

    def test_superseded_artifacts_are_replaced(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest_with_artifacts(
            manifest_dir,
            "original.manifest.yaml",
            goal="original",
            created="2026-01-01",
            sequence_number=1,
            artifacts=[{"kind": "function", "name": "old_handler"}],
        )
        _write_manifest_with_artifacts(
            manifest_dir,
            "replacement.manifest.yaml",
            goal="replacement",
            created="2026-02-01",
            sequence_number=2,
            artifacts=[{"kind": "function", "name": "new_handler"}],
            supersedes=["original"],
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.replay_until()

        specs = result.get("mod.py", [])
        names = {s.name for s in specs}
        assert "new_handler" in names
        assert "old_handler" not in names  # superseded → excluded

    def test_deleted_file_excluded_from_result(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest_with_artifacts(
            manifest_dir,
            "create.manifest.yaml",
            goal="create",
            created="2026-01-01",
            sequence_number=1,
            artifacts=[{"kind": "function", "name": "greet"}],
        )
        # Second manifest deletes the file
        _write_manifest_with_delete(
            manifest_dir,
            "delete.manifest.yaml",
            goal="delete",
            created="2026-02-01",
            sequence_number=2,
            delete_path="mod.py",
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.replay_until()

        assert "mod.py" not in result

    def test_version_tag_cutoff(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest_with_artifacts(
            manifest_dir,
            "first.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
            artifacts=[{"kind": "function", "name": "greet"}],
        )
        _write_manifest_with_artifacts(
            manifest_dir,
            "second.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            artifacts=[{"kind": "function", "name": "farewell"}],
            version_tag="release-1",
        )
        _write_manifest_with_artifacts(
            manifest_dir,
            "third.manifest.yaml",
            goal="third",
            created="2026-03-01",
            sequence_number=3,
            artifacts=[{"kind": "function", "name": "bonus"}],
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.replay_until(version_tag="release-1")

        specs = result.get("mod.py", [])
        names = {s.name for s in specs}
        assert names == {"greet", "farewell"}
        assert "bonus" not in names

    def test_both_args_sequence_wins(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest_with_artifacts(
            manifest_dir,
            "first.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
            artifacts=[{"kind": "function", "name": "greet"}],
        )
        _write_manifest_with_artifacts(
            manifest_dir,
            "second.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            artifacts=[{"kind": "function", "name": "farewell"}],
            version_tag="v1",
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        # seq=1 would give just {greet}, tag="v1" would give {greet, farewell}
        result = chain.replay_until(sequence_number=1, version_tag="v1")
        names = {s.name for s in result.get("mod.py", [])}
        assert names == {"greet"}

    def test_superseder_after_cutoff_preserves_original(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest_with_artifacts(
            manifest_dir,
            "original.manifest.yaml",
            goal="original",
            created="2026-01-01",
            sequence_number=1,
            artifacts=[{"kind": "function", "name": "handler"}],
        )
        _write_manifest_with_artifacts(
            manifest_dir,
            "replacement.manifest.yaml",
            goal="replacement",
            created="2026-02-01",
            sequence_number=3,
            artifacts=[{"kind": "function", "name": "handler_v2"}],
            supersedes=["original"],
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        # Cutoff at seq=2: replacement (seq=3) is after, so original
        # should still appear.
        result = chain.replay_until(sequence_number=2)

        specs = result.get("mod.py", [])
        names = {s.name for s in specs}
        assert names == {"handler"}

    def test_empty_prefix_returns_empty_dict(self, tmp_path: Path) -> None:
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest_with_artifacts(
            manifest_dir,
            "only.manifest.yaml",
            goal="only",
            created="2026-01-01",
            sequence_number=5,
            artifacts=[{"kind": "function", "name": "greet"}],
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        result = chain.replay_until(sequence_number=2)
        assert result == {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(
    manifest_dir: Path,
    filename: str,
    goal: str,
    created: str,
    sequence_number: int | None = None,
    version_tag: str | None = None,
    supersedes: list[str] | None = None,
) -> None:
    data: dict = {
        "schema": "2",
        "goal": goal,
        "type": "feature",
        "created": created,
        "files": {
            "create": [
                {
                    "path": "dummy.py",
                    "artifacts": [{"kind": "function", "name": "_placeholder"}],
                }
            ]
        },
        "validate": ["pytest tests/ -v"],
    }
    if sequence_number is not None:
        data["sequence_number"] = sequence_number
    if version_tag is not None:
        data["version_tag"] = version_tag
    if supersedes:
        data["supersedes"] = supersedes

    path = manifest_dir / filename
    path.write_text(yaml.dump(data))


def _write_manifest_with_artifacts(
    manifest_dir: Path,
    filename: str,
    goal: str,
    created: str,
    sequence_number: int | None = None,
    version_tag: str | None = None,
    supersedes: list[str] | None = None,
    artifacts: list[dict] | None = None,
) -> None:
    data: dict = {
        "schema": "2",
        "goal": goal,
        "type": "feature",
        "created": created,
        "files": {
            "create": [
                {
                    "path": "mod.py",
                    "artifacts": artifacts or [],
                }
            ]
        },
        "validate": ["pytest tests/ -v"],
    }
    if sequence_number is not None:
        data["sequence_number"] = sequence_number
    if version_tag is not None:
        data["version_tag"] = version_tag
    if supersedes:
        data["supersedes"] = supersedes

    path = manifest_dir / filename
    path.write_text(yaml.dump(data))


def _write_manifest_with_delete(
    manifest_dir: Path,
    filename: str,
    goal: str,
    created: str,
    sequence_number: int | None = None,
    delete_path: str = "mod.py",
) -> None:
    data: dict = {
        "schema": "2",
        "goal": goal,
        "type": "refactor",
        "created": created,
        "files": {"delete": [{"path": delete_path, "reason": "no longer needed"}]},
        "validate": ["pytest tests/ -v"],
    }
    if sequence_number is not None:
        data["sequence_number"] = sequence_number

    path = manifest_dir / filename
    path.write_text(yaml.dump(data))
