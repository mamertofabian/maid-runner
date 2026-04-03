"""Tests for maid_runner.core.chain - ManifestChain resolution and merge."""

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.types import ArtifactKind, FileMode


@pytest.fixture()
def chain_dir(tmp_path):
    """Create a temporary manifest directory with fixtures."""
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    return manifests


def _write_manifest(path, content):
    path.write_text(content)


class TestManifestChainBasic:
    def test_empty_directory(self, chain_dir):
        chain = ManifestChain(chain_dir)
        assert chain.active_manifests() == []
        assert chain.all_manifests == []

    def test_nonexistent_directory(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ManifestChain(tmp_path / "nonexistent")

    def test_single_manifest(self, chain_dir):
        _write_manifest(
            chain_dir / "add-greet.manifest.yaml",
            """schema: "2"
goal: "Add greet"
type: feature
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
validate:
  - pytest tests/ -v
created: "2025-06-01T00:00:00Z"
""",
        )
        chain = ManifestChain(chain_dir)
        assert len(chain.active_manifests()) == 1
        assert chain.active_manifests()[0].slug == "add-greet"


class TestSupersession:
    def test_basic_supersession(self, chain_dir):
        """Golden test 3.1: Basic supersession."""
        _write_manifest(
            chain_dir / "old-feature.manifest.yaml",
            """schema: "2"
goal: "Old feature"
type: feature
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: old_func
validate:
  - pytest tests/ -v
created: "2025-06-01T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "new-feature.manifest.yaml",
            """schema: "2"
goal: "New feature"
type: feature
supersedes:
  - old-feature
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: new_func
validate:
  - pytest tests/ -v
created: "2025-06-15T00:00:00Z"
""",
        )
        chain = ManifestChain(chain_dir)

        active = chain.active_manifests()
        assert len(active) == 1
        assert active[0].slug == "new-feature"

        superseded = chain.superseded_manifests()
        assert len(superseded) == 1
        assert superseded[0].slug == "old-feature"

        assert chain.is_superseded("old-feature") is True
        assert chain.is_superseded("new-feature") is False
        assert chain.superseded_by("old-feature") == "new-feature"
        assert chain.superseded_by("new-feature") is None

    def test_transitive_supersession(self, chain_dir):
        """A supersedes B, B supersedes C -> only A active."""
        _write_manifest(
            chain_dir / "c.manifest.yaml",
            """schema: "2"
goal: "C"
files:
  create:
    - path: src/c.py
      artifacts:
        - kind: function
          name: c
validate:
  - pytest
created: "2025-01-01T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "b.manifest.yaml",
            """schema: "2"
goal: "B"
supersedes: [c]
files:
  create:
    - path: src/c.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest
created: "2025-02-01T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
supersedes: [b]
files:
  create:
    - path: src/c.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
created: "2025-03-01T00:00:00Z"
""",
        )
        chain = ManifestChain(chain_dir)
        active = chain.active_manifests()
        assert len(active) == 1
        assert active[0].slug == "a"

    def test_circular_supersession_detected(self, chain_dir):
        """Golden test 3.4: Circular supersession."""
        _write_manifest(
            chain_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
supersedes: [b]
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
""",
        )
        _write_manifest(
            chain_dir / "b.manifest.yaml",
            """schema: "2"
goal: "B"
supersedes: [a]
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest
""",
        )
        chain = ManifestChain(chain_dir)
        errors = chain.validate_supersession_integrity()
        assert len(errors) > 0
        assert any("circular" in e.lower() for e in errors)

    def test_nonexistent_superseded_manifest(self, chain_dir):
        """Superseding a non-existent manifest is a warning, not an error."""
        _write_manifest(
            chain_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
supersedes: [nonexistent]
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
""",
        )
        chain = ManifestChain(chain_dir)
        errors = chain.validate_supersession_integrity()
        assert any("nonexistent" in e.lower() for e in errors)
        # But manifest is still active
        assert len(chain.active_manifests()) == 1


class TestArtifactMerge:
    def test_merge_across_manifests(self, chain_dir):
        """Golden test 3.2: Artifact merge from multiple manifests."""
        _write_manifest(
            chain_dir / "add-base.manifest.yaml",
            """schema: "2"
goal: "Add base"
files:
  create:
    - path: src/service.py
      artifacts:
        - kind: class
          name: Service
        - kind: method
          name: start
          of: Service
validate:
  - pytest
created: "2025-06-01T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "add-stop.manifest.yaml",
            """schema: "2"
goal: "Add stop"
files:
  edit:
    - path: src/service.py
      artifacts:
        - kind: method
          name: stop
          of: Service
validate:
  - pytest
created: "2025-06-15T00:00:00Z"
""",
        )
        chain = ManifestChain(chain_dir)
        merged = chain.merged_artifacts_for("src/service.py")
        names = [(a.name, a.kind) for a in merged]
        assert ("Service", ArtifactKind.CLASS) in names
        assert ("start", ArtifactKind.METHOD) in names
        assert ("stop", ArtifactKind.METHOD) in names
        assert len(merged) == 3

    def test_later_manifest_overrides_same_key(self, chain_dir):
        """Later manifest wins for same merge_key."""
        _write_manifest(
            chain_dir / "v1.manifest.yaml",
            """schema: "2"
goal: "V1"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: greet
          args:
            - name: name
              type: str
          returns: str
validate:
  - pytest
created: "2025-06-01T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "v2.manifest.yaml",
            """schema: "2"
goal: "V2"
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: greet
          args:
            - name: name
              type: str
            - name: formal
              type: bool
          returns: str
validate:
  - pytest
created: "2025-06-15T00:00:00Z"
""",
        )
        chain = ManifestChain(chain_dir)
        merged = chain.merged_artifacts_for("src/app.py")
        assert len(merged) == 1
        greet = merged[0]
        assert len(greet.args) == 2  # V2 version wins

    def test_merged_artifacts_for_nonexistent_file(self, chain_dir):
        chain = ManifestChain(chain_dir)
        assert chain.merged_artifacts_for("nonexistent.py") == []


class TestFileMode:
    def test_create_mode_is_strictest(self, chain_dir):
        """Golden test 3.3: CREATE wins over EDIT."""
        _write_manifest(
            chain_dir / "create-app.manifest.yaml",
            """schema: "2"
goal: "Create app"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: main
validate:
  - pytest
created: "2025-06-01T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "edit-app.manifest.yaml",
            """schema: "2"
goal: "Edit app"
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: helper
validate:
  - pytest
created: "2025-06-15T00:00:00Z"
""",
        )
        chain = ManifestChain(chain_dir)
        mode = chain.file_mode_for("src/app.py")
        assert mode == FileMode.CREATE

    def test_file_mode_edit_only(self, chain_dir):
        _write_manifest(
            chain_dir / "edit-app.manifest.yaml",
            """schema: "2"
goal: "Edit"
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: helper
validate:
  - pytest
""",
        )
        chain = ManifestChain(chain_dir)
        assert chain.file_mode_for("src/app.py") == FileMode.EDIT

    def test_file_mode_nonexistent(self, chain_dir):
        chain = ManifestChain(chain_dir)
        assert chain.file_mode_for("nonexistent.py") is None


class TestTrackedPaths:
    def test_all_tracked_paths(self, chain_dir):
        _write_manifest(
            chain_dir / "feature.manifest.yaml",
            """schema: "2"
goal: "Feature"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
  edit:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
  read:
    - src/c.py
validate:
  - pytest
""",
        )
        chain = ManifestChain(chain_dir)
        paths = chain.all_tracked_paths()
        assert "src/a.py" in paths
        assert "src/b.py" in paths
        assert "src/c.py" in paths  # read-only files are tracked too


class TestManifestsForFile:
    def test_manifests_for_file(self, chain_dir):
        _write_manifest(
            chain_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/shared.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
created: "2025-06-01T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "b.manifest.yaml",
            """schema: "2"
goal: "B"
files:
  edit:
    - path: src/shared.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest
created: "2025-06-15T00:00:00Z"
""",
        )
        chain = ManifestChain(chain_dir)
        manifests = chain.manifests_for_file("src/shared.py")
        assert len(manifests) == 2


class TestSortingOrder:
    def test_sorted_by_created_timestamp(self, chain_dir):
        _write_manifest(
            chain_dir / "z-later.manifest.yaml",
            """schema: "2"
goal: "Later"
files:
  create:
    - path: src/z.py
      artifacts:
        - kind: function
          name: z
validate:
  - pytest
created: "2025-06-15T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "a-earlier.manifest.yaml",
            """schema: "2"
goal: "Earlier"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
created: "2025-06-01T00:00:00Z"
""",
        )
        chain = ManifestChain(chain_dir)
        active = chain.active_manifests()
        assert active[0].slug == "a-earlier"
        assert active[1].slug == "z-later"

    def test_no_timestamp_sorts_last(self, chain_dir):
        _write_manifest(
            chain_dir / "with-time.manifest.yaml",
            """schema: "2"
goal: "With time"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
created: "2025-06-01T00:00:00Z"
""",
        )
        _write_manifest(
            chain_dir / "no-time.manifest.yaml",
            """schema: "2"
goal: "No time"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest
""",
        )
        chain = ManifestChain(chain_dir)
        active = chain.active_manifests()
        assert active[0].slug == "with-time"
        assert active[1].slug == "no-time"


class TestChainCaching:
    def test_active_manifests_cached(self, chain_dir):
        """Repeated calls to active_manifests return same result without re-filtering."""
        _write_manifest(
            chain_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
""",
        )
        chain = ManifestChain(chain_dir)
        first = chain.active_manifests()
        second = chain.active_manifests()
        assert first == second

    def test_reload_invalidates_cache(self, chain_dir):
        """reload() should clear the active_manifests cache."""
        _write_manifest(
            chain_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
""",
        )
        chain = ManifestChain(chain_dir)
        assert len(chain.active_manifests()) == 1

        _write_manifest(
            chain_dir / "b.manifest.yaml",
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest
""",
        )
        chain.reload()
        assert len(chain.active_manifests()) == 2


class TestReload:
    def test_reload_picks_up_changes(self, chain_dir):
        _write_manifest(
            chain_dir / "a.manifest.yaml",
            """schema: "2"
goal: "A"
files:
  create:
    - path: src/a.py
      artifacts:
        - kind: function
          name: a
validate:
  - pytest
""",
        )
        chain = ManifestChain(chain_dir)
        assert len(chain.active_manifests()) == 1

        _write_manifest(
            chain_dir / "b.manifest.yaml",
            """schema: "2"
goal: "B"
files:
  create:
    - path: src/b.py
      artifacts:
        - kind: function
          name: b
validate:
  - pytest
""",
        )
        chain.reload()
        assert len(chain.active_manifests()) == 2
