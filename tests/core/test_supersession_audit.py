"""Behavioral tests for supersession artifact-preservation defense."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode, Severity
from maid_runner.core.supersession_audit import (
    GrandfatherEntry,
    GrandfatherLock,
    SupersessionAuditor,
    SupersessionViolation,
    compute_manifest_hash,
    default_lock_path,
)


@pytest.fixture()
def manifests_dir(tmp_path: Path) -> Path:
    d = tmp_path / "manifests"
    d.mkdir()
    return d


def _write_manifest(path: Path, content: str) -> None:
    path.write_text(content)


def _write_pair(
    manifests_dir: Path,
    *,
    b_artifact: str,
    a_artifact: str,
    a_deletes: str = "",
    a_path: str = "src/b.py",
) -> None:
    _write_manifest(
        manifests_dir / "b.manifest.yaml",
        f"""schema: "2"
goal: "B"
type: feature
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: {b_artifact}
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
    )
    delete_block = ""
    if a_deletes:
        delete_block = f'  delete:\n    - path: {a_deletes}\n      reason: "moved"\n'
    _write_manifest(
        manifests_dir / "a.manifest.yaml",
        f"""schema: "2"
goal: "A"
type: feature
supersedes: [b]
files:
  create:
    - path: {a_path}
      artifacts:
        - kind: function
          name: {a_artifact}
{delete_block}validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
    )


class TestComputeManifestHash:
    def test_returns_sha256_prefixed_string(self, tmp_path: Path) -> None:
        path = tmp_path / "m.manifest.yaml"
        path.write_text("schema: '2'\ngoal: x\n")
        result = compute_manifest_hash(path)
        assert result.startswith("sha256:")
        assert len(result) > len("sha256:") + 10

    def test_stable_for_identical_content(self, tmp_path: Path) -> None:
        p1 = tmp_path / "a.yaml"
        p2 = tmp_path / "b.yaml"
        p1.write_text("same")
        p2.write_text("same")
        assert compute_manifest_hash(p1) == compute_manifest_hash(p2)

    def test_changes_with_content(self, tmp_path: Path) -> None:
        p = tmp_path / "m.yaml"
        p.write_text("first")
        h1 = compute_manifest_hash(p)
        p.write_text("second")
        h2 = compute_manifest_hash(p)
        assert h1 != h2


class TestDefaultLockPath:
    def test_resolves_under_dot_maid(self, tmp_path: Path) -> None:
        path = default_lock_path(tmp_path)
        assert path == tmp_path / ".maid" / "legacy-grandfathered.lock"


class TestSupersessionViolation:
    def test_carries_artifact_identity_fields(self) -> None:
        v = SupersessionViolation(
            superseding_slug="a",
            superseded_slug="b",
            superseding_manifest_path="manifests/a.manifest.yaml",
            file_path="src/a.py",
            artifact_key="function:foo",
            artifact_name="foo",
            artifact_kind="function",
        )
        assert v.superseding_slug == "a"
        assert v.superseded_slug == "b"
        assert v.superseding_manifest_path == "manifests/a.manifest.yaml"
        assert v.file_path == "src/a.py"
        assert v.artifact_key == "function:foo"
        assert v.artifact_name == "foo"
        assert v.artifact_kind == "function"


class TestGrandfatherEntry:
    def test_records_drop_set_and_reason(self) -> None:
        entry = GrandfatherEntry(
            superseding_slug="a",
            content_hash="sha256:abc",
            dropped_artifact_keys=("function:foo", "class:Bar"),
            reason="legacy migration",
        )
        assert entry.superseding_slug == "a"
        assert entry.content_hash == "sha256:abc"
        assert "function:foo" in entry.dropped_artifact_keys
        assert "class:Bar" in entry.dropped_artifact_keys
        assert entry.reason == "legacy migration"


class TestGrandfatherLockEmpty:
    def test_empty_has_no_entries_or_seal(self) -> None:
        lock = GrandfatherLock.empty()
        assert lock.entries == ()
        assert lock.sealed_at is None
        assert lock.is_sealed() is False
        assert lock.version == "2"


class TestGrandfatherLockLoadMissingFile:
    def test_load_returns_empty_for_missing_path(self, tmp_path: Path) -> None:
        lock = GrandfatherLock.load(tmp_path / "missing.lock")
        assert lock.entries == ()
        assert lock.is_sealed() is False


class TestGrandfatherLockLoadInvalid:
    def test_load_raises_on_malformed_json(self, tmp_path: Path) -> None:
        from maid_runner.core.supersession_audit import (
            _GrandfatherLockLoadError as GrandfatherLockLoadError,
        )

        path = tmp_path / "bad.lock"
        path.write_text("not valid json {{{")
        with pytest.raises(GrandfatherLockLoadError):
            GrandfatherLock.load(path)

    def test_load_raises_on_non_object_top_level(self, tmp_path: Path) -> None:
        from maid_runner.core.supersession_audit import (
            _GrandfatherLockLoadError as GrandfatherLockLoadError,
        )

        path = tmp_path / "bad.lock"
        path.write_text('"a string at top level"')
        with pytest.raises(GrandfatherLockLoadError):
            GrandfatherLock.load(path)

    def test_load_raises_on_malformed_entry(self, tmp_path: Path) -> None:
        from maid_runner.core.supersession_audit import (
            _GrandfatherLockLoadError as GrandfatherLockLoadError,
        )

        path = tmp_path / "bad.lock"
        path.write_text(
            '{"version": "1", "sealed_at": "2026-01-01", "entries": [{"foo": "bar"}]}'
        )
        with pytest.raises(GrandfatherLockLoadError):
            GrandfatherLock.load(path)


class TestManifestChainAuditInvalidLock:
    def test_chain_audit_emits_error_when_lock_corrupt(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        lock_dir = tmp_path / ".maid"
        lock_dir.mkdir()
        (lock_dir / "legacy-grandfathered.lock").write_text("not json")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        errors = chain.audit_supersession_artifacts()
        lock_errors = [
            e
            for e in errors
            if e.severity == Severity.ERROR and "Grandfather lock" in e.message
        ]
        assert len(lock_errors) == 1


class TestGrandfatherLockSaveAndLoad:
    def test_save_then_load_round_trip(self, tmp_path: Path) -> None:
        entry = GrandfatherEntry(
            superseding_slug="a",
            content_hash="sha256:abc",
            dropped_artifact_keys=("function:foo",),
            reason="legacy",
        )
        lock = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15T18:00:00",
            entries=(entry,),
        )
        path = tmp_path / "lock.json"
        lock.save(path)
        assert path.exists()

        loaded = GrandfatherLock.load(path)
        assert loaded.is_sealed() is True
        assert loaded.sealed_at == "2026-05-15T18:00:00"
        assert len(loaded.entries) == 1
        assert loaded.entries[0].superseding_slug == "a"
        assert loaded.entries[0].content_hash == "sha256:abc"

    def test_save_writes_json(self, tmp_path: Path) -> None:
        lock = GrandfatherLock.empty().with_seal(sealed_at="2026-05-15", entries=())
        path = tmp_path / "lock.json"
        lock.save(path)
        data = json.loads(path.read_text())
        assert data["sealed_at"] == "2026-05-15"


class TestGrandfatherLockWithSeal:
    def test_with_seal_returns_new_sealed_instance(self) -> None:
        original = GrandfatherLock.empty()
        sealed = original.with_seal(sealed_at="2026-05-15", entries=())
        assert original.is_sealed() is False
        assert sealed.is_sealed() is True
        assert sealed.sealed_at == "2026-05-15"


class TestGrandfatherLockIsGrandfathered:
    def test_matches_on_slug_hash_and_artifact_key(self) -> None:
        entry = GrandfatherEntry(
            superseding_slug="a",
            content_hash="sha256:abc",
            dropped_artifact_keys=("function:foo",),
            reason="legacy",
        )
        lock = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15", entries=(entry,)
        )
        assert lock.is_grandfathered("a", "sha256:abc", "function:foo") is True

    def test_rejects_when_content_hash_differs(self) -> None:
        entry = GrandfatherEntry(
            superseding_slug="a",
            content_hash="sha256:abc",
            dropped_artifact_keys=("function:foo",),
            reason="legacy",
        )
        lock = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15", entries=(entry,)
        )
        assert lock.is_grandfathered("a", "sha256:tampered", "function:foo") is False

    def test_rejects_when_artifact_key_not_listed(self) -> None:
        entry = GrandfatherEntry(
            superseding_slug="a",
            content_hash="sha256:abc",
            dropped_artifact_keys=("function:foo",),
            reason="legacy",
        )
        lock = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15", entries=(entry,)
        )
        assert lock.is_grandfathered("a", "sha256:abc", "class:Other") is False

    def test_rejects_when_slug_does_not_match(self) -> None:
        entry = GrandfatherEntry(
            superseding_slug="a",
            content_hash="sha256:abc",
            dropped_artifact_keys=("function:foo",),
            reason="legacy",
        )
        lock = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15", entries=(entry,)
        )
        assert lock.is_grandfathered("other", "sha256:abc", "function:foo") is False


class TestSupersessionAuditorNoSupersession:
    def test_returns_empty_when_no_supersedes_links(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_manifest(
            manifests_dir / "one.manifest.yaml",
            """schema: "2"
goal: "single"
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
""",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert violations == ()


class TestSupersessionAuditorDroppedArtifact:
    def test_flags_artifact_present_in_b_but_missing_in_a(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert len(violations) == 1
        assert violations[0].superseding_slug == "a"
        assert violations[0].superseded_slug == "b"
        assert violations[0].artifact_name == "foo"


class TestSupersessionAuditorPreserved:
    def test_no_violation_when_replacement_redeclares_artifact_in_same_file(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(
            manifests_dir,
            b_artifact="foo",
            a_artifact="foo",
            a_path="src/a.py",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert violations == ()

    def test_same_name_in_different_file_does_not_preserve(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(
            manifests_dir,
            b_artifact="foo",
            a_artifact="foo",
            a_path="src/b.py",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert len(violations) == 1
        assert violations[0].artifact_name == "foo"
        assert violations[0].file_path == "src/a.py"


class TestSupersessionAuditorFileDeleted:
    def test_no_violation_when_path_listed_in_files_delete(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(
            manifests_dir, b_artifact="foo", a_artifact="bar", a_deletes="src/a.py"
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert violations == ()


class TestSupersessionAuditorPrivateArtifactExcluded:
    def test_private_underscore_artifact_not_flagged(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="_private_func", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert violations == ()


class TestSupersessionAuditorRemovedArtifactBypass:
    def test_removed_artifacts_pointing_at_different_file_does_not_exempt(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_manifest(
            manifests_dir / "b.manifest.yaml",
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
""",
        )
        _write_manifest(
            manifests_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
type: feature
supersedes: [b]
removed_artifacts:
  - kind: function
    name: foo
    file: src/unrelated.py
    reason: "bypass attempt"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert len(violations) == 1
        assert violations[0].artifact_name == "foo"
        assert violations[0].file_path == "src/a.py"


class TestSupersessionAuditorRemovedArtifact:
    def test_no_violation_when_replacement_lists_artifact_as_removed(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("def kept_helper() -> None:\n    return\n")
        _write_manifest(
            manifests_dir / "b.manifest.yaml",
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
""",
        )
        _write_manifest(
            manifests_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
type: feature
supersedes: [b]
removed_artifacts:
  - kind: function
    name: foo
    file: src/a.py
    reason: "deprecated"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert violations == ()


class TestSupersessionAuditorAuditWithoutLock:
    def test_unsealed_violations_surface_as_warnings_for_migration(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        errors = auditor.audit(chain, lock=None)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION
        assert errors[0].severity == Severity.WARNING

    def test_empty_lock_treated_as_unsealed(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        errors = auditor.audit(chain, lock=GrandfatherLock.empty())
        assert len(errors) == 1
        assert errors[0].severity == Severity.WARNING


class TestSupersessionAuditorAuditWithSealedLock:
    def test_sealed_lock_promotes_non_grandfathered_drops_to_error(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        sealed = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15T00:00:00", entries=()
        )
        errors = auditor.audit(chain, lock=sealed)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION
        assert errors[0].severity == Severity.ERROR


class TestSupersessionAuditorRemovedArtifactsVerifiedAtAuditTime:
    def test_bogus_removed_artifacts_claim_does_not_exempt(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("def foo() -> None:\n    return\n")
        _write_manifest(
            manifests_dir / "b.manifest.yaml",
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
""",
        )
        _write_manifest(
            manifests_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
type: feature
supersedes: [b]
removed_artifacts:
  - kind: function
    name: foo
    file: src/a.py
    reason: "claimed removed but the symbol is still in source"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert len(violations) == 1
        assert violations[0].artifact_name == "foo"

    def test_verified_removed_artifacts_claim_does_exempt(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("def keep_me() -> None:\n    return\n")
        _write_manifest(
            manifests_dir / "b.manifest.yaml",
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
""",
        )
        _write_manifest(
            manifests_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
type: feature
supersedes: [b]
removed_artifacts:
  - kind: function
    name: foo
    file: src/a.py
    reason: "actually removed"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert violations == ()


class TestSupersessionAuditorGrandfatherCompositeKey:
    def test_seal_for_one_supersession_does_not_exempt_a_different_supersession(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_manifest(
            manifests_dir / "b1.manifest.yaml",
            """schema: "2"
goal: "B1"
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
""",
        )
        _write_manifest(
            manifests_dir / "b2.manifest.yaml",
            """schema: "2"
goal: "B2"
type: feature
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-01-02T00:00:00Z"
""",
        )
        _write_manifest(
            manifests_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A drops both"
type: feature
supersedes: [b1, b2]
files:
  create:
    - path: src/c.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )

        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert len(violations) == 2

        b1_violation = next(v for v in violations if v.superseded_slug == "b1")

        # Seal only the b1 drop; b2 drop should still surface.
        entry = GrandfatherEntry(
            superseding_slug=b1_violation.superseding_slug,
            content_hash=compute_manifest_hash(
                Path(b1_violation.superseding_manifest_path)
            ),
            dropped_artifact_keys=(
                f"{b1_violation.superseded_slug}|"
                f"{b1_violation.file_path}|{b1_violation.artifact_key}",
            ),
            reason="legacy migration, b1 only",
        )
        lock = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15", entries=(entry,)
        )

        errors = auditor.audit(chain, lock=lock)
        codes = [e.code for e in errors]
        severities = [e.severity for e in errors]
        assert ErrorCode.GRANDFATHERED_SUPERSESSION in codes
        assert ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION in codes
        assert Severity.INFO in severities
        assert Severity.ERROR in severities


class TestSupersessionAuditorFilesDeleteVerifiedAtAuditTime:
    def test_files_delete_claim_for_still_present_file_does_not_exempt(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("def foo() -> None:\n    return\n")
        _write_manifest(
            manifests_dir / "b.manifest.yaml",
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
""",
        )
        _write_manifest(
            manifests_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
type: feature
supersedes: [b]
files:
  create:
    - path: src/c.py
      artifacts:
        - kind: function
          name: bar
  delete:
    - path: src/a.py
      reason: "claimed deleted but file still exists"
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert len(violations) == 1
        assert violations[0].artifact_name == "foo"


class TestSupersessionAuditorExcludesTestFunctions:
    def test_test_function_drops_do_not_surface_as_violations(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_manifest(
            manifests_dir / "b.manifest.yaml",
            """schema: "2"
goal: "B"
type: feature
files:
  create:
    - path: tests/test_x.py
      artifacts:
        - kind: test_function
          name: test_legacy_coverage
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
        )
        _write_manifest(
            manifests_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
type: feature
supersedes: [b]
files:
  create:
    - path: tests/test_y.py
      artifacts:
        - kind: test_function
          name: test_replacement
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        assert violations == ()


class TestSupersessionAuditorRemovedArtifactPathContainment:
    def test_parent_relative_removed_path_does_not_exempt(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        m_dir = project_root / "manifests"
        m_dir.mkdir()
        (tmp_path / "escaped.py").write_text("def other() -> None:\n    return\n")
        _write_manifest(
            m_dir / "b.manifest.yaml",
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
""",
        )
        _write_manifest(
            m_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
type: feature
supersedes: [b]
removed_artifacts:
  - kind: function
    name: foo
    file: ../escaped.py
    reason: "bypass via parent-relative path"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        chain = ManifestChain(m_dir, project_root=project_root)
        auditor = SupersessionAuditor(project_root=project_root)
        violations = auditor.find_violations(chain)
        assert len(violations) == 1
        assert violations[0].artifact_name == "foo"

    def test_absolute_removed_path_does_not_exempt(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        m_dir = project_root / "manifests"
        m_dir.mkdir()
        outside = tmp_path / "escaped.py"
        outside.write_text("def other() -> None:\n    return\n")
        _write_manifest(
            m_dir / "b.manifest.yaml",
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
""",
        )
        _write_manifest(
            m_dir / "a.manifest.yaml",
            f"""schema: "2"
goal: "A"
type: feature
supersedes: [b]
removed_artifacts:
  - kind: function
    name: foo
    file: {outside}
    reason: "bypass via absolute path"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        chain = ManifestChain(m_dir, project_root=project_root)
        auditor = SupersessionAuditor(project_root=project_root)
        violations = auditor.find_violations(chain)
        assert len(violations) == 1
        assert violations[0].artifact_name == "foo"


class TestSupersessionAuditorEveryEdge:
    def test_audits_each_superseder_when_duplicates_target_same_slug(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_manifest(
            manifests_dir / "b.manifest.yaml",
            """schema: "2"
goal: "B"
type: feature
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: foo
        - kind: function
          name: qux
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
""",
        )
        _write_manifest(
            manifests_dir / "a1.manifest.yaml",
            """schema: "2"
goal: "A1 supersedes B and keeps foo"
type: feature
supersedes: [b]
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: foo
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
""",
        )
        _write_manifest(
            manifests_dir / "a2.manifest.yaml",
            """schema: "2"
goal: "A2 also supersedes B and drops both"
type: feature
supersedes: [b]
files:
  create:
    - path: src/c.py
      artifacts:
        - kind: function
          name: bar
validate:
  - pytest
created: "2026-03-01T00:00:00Z"
""",
        )
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)
        violations = auditor.find_violations(chain)
        culprits = {(v.superseding_slug, v.artifact_name) for v in violations}
        assert ("a1", "qux") in culprits
        assert ("a2", "foo") in culprits
        assert ("a2", "qux") in culprits


class TestSupersessionAuditorAuditWithLock:
    def test_grandfathered_violation_is_info_not_warning(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)

        violations = auditor.find_violations(chain)
        assert len(violations) == 1
        v = violations[0]

        composite_key = f"{v.superseded_slug}|{v.file_path}|{v.artifact_key}"
        entry = GrandfatherEntry(
            superseding_slug=v.superseding_slug,
            content_hash=compute_manifest_hash(Path(v.superseding_manifest_path)),
            dropped_artifact_keys=(composite_key,),
            reason="legacy migration",
        )
        lock = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15", entries=(entry,)
        )

        errors = auditor.audit(chain, lock=lock)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.GRANDFATHERED_SUPERSESSION
        assert errors[0].severity == Severity.INFO

    def test_lock_with_wrong_hash_does_not_grandfather(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        auditor = SupersessionAuditor(project_root=tmp_path)

        violations = auditor.find_violations(chain)
        v = violations[0]
        composite_key = f"{v.superseded_slug}|{v.file_path}|{v.artifact_key}"
        stale_entry = GrandfatherEntry(
            superseding_slug=v.superseding_slug,
            content_hash="sha256:stale_hash_from_before_edit",
            dropped_artifact_keys=(composite_key,),
            reason="legacy",
        )
        lock = GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15", entries=(stale_entry,)
        )

        errors = auditor.audit(chain, lock=lock)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION
        assert errors[0].severity == Severity.ERROR


class TestManifestChainAuditMethod:
    def test_chain_audit_returns_validation_errors(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        errors = chain.audit_supersession_artifacts(lock=None)
        assert isinstance(errors, list)
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION

    def test_chain_audit_auto_loads_lock_from_dot_maid(
        self, manifests_dir: Path, tmp_path: Path
    ) -> None:
        _write_pair(manifests_dir, b_artifact="foo", a_artifact="bar")
        chain = ManifestChain(manifests_dir, project_root=tmp_path)
        violations = SupersessionAuditor(project_root=tmp_path).find_violations(chain)
        v = violations[0]

        lock_dir = tmp_path / ".maid"
        lock_dir.mkdir()
        lock_path = lock_dir / "legacy-grandfathered.lock"
        composite_key = f"{v.superseded_slug}|{v.file_path}|{v.artifact_key}"
        entry = GrandfatherEntry(
            superseding_slug=v.superseding_slug,
            content_hash=compute_manifest_hash(Path(v.superseding_manifest_path)),
            dropped_artifact_keys=(composite_key,),
            reason="legacy",
        )
        GrandfatherLock.empty().with_seal(
            sealed_at="2026-05-15", entries=(entry,)
        ).save(lock_path)

        errors = chain.audit_supersession_artifacts()
        assert len(errors) == 1
        assert errors[0].code == ErrorCode.GRANDFATHERED_SUPERSESSION


class TestErrorCodeAdditions:
    def test_dropped_by_supersession_code_defined(self) -> None:
        assert ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION.value.startswith("E")

    def test_grandfathered_supersession_code_defined(self) -> None:
        assert ErrorCode.GRANDFATHERED_SUPERSESSION.value.startswith("E")
