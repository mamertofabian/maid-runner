"""Behavioral coverage for actionable inactive-manifest diagnostics."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode


_UNMARKED_MANIFEST = """schema: "2"
goal: "Hidden active-looking manifest"
type: fix
files:
  create:
    - path: src/example.py
      artifacts:
        - kind: function
          name: example
validate:
  - pytest tests/test_example.py -q
"""


def _write_unmarked_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(_UNMARKED_MANIFEST)


def test_draft_inventory_diagnostic_names_copyable_marker_choices(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_unmarked_manifest(manifest_dir / "drafts" / "hidden.manifest.yaml")

    diagnostics = ManifestChain(manifest_dir, tmp_path).inactive_manifest_diagnostics()

    assert [diagnostic.code for diagnostic in diagnostics] == [
        ErrorCode.INACTIVE_MANIFEST_NOT_MARKED
    ]
    suggestion = diagnostics[0].suggestion
    assert suggestion is not None
    assert "# draft-kind: implementation" in suggestion
    assert "# draft-kind: epic" in suggestion


def test_archive_inventory_diagnostic_names_copyable_archive_marker(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_unmarked_manifest(manifest_dir / "v1-archive" / "hidden.manifest.yaml")

    diagnostics = ManifestChain(manifest_dir, tmp_path).inactive_manifest_diagnostics()

    assert [diagnostic.code for diagnostic in diagnostics] == [
        ErrorCode.INACTIVE_MANIFEST_NOT_MARKED
    ]
    suggestion = diagnostics[0].suggestion
    assert suggestion is not None
    assert "# archive-kind:" in suggestion
