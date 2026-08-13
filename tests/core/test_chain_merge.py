"""Behavioral tests for maid_runner.core.chain_merge (chain-merge child 1: report).

Imports of the system under test live inside each test body so that a missing
module fails the test with an in-body ImportError (exit 1) rather than a
collection error (exit 2), keeping red evidence valid.
"""

from __future__ import annotations


def _manifests_dir(tmp_path):
    d = tmp_path / "manifests"
    d.mkdir()
    return d


_MANIFEST_A = """schema: "2"
goal: "A creates foo"
type: feature
files:
  create:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
        - kind: function
          name: beta
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""

# Edits foo, re-declaring `beta` (redundant) and adding `gamma`.
_MANIFEST_B = """schema: "2"
goal: "B edits foo"
type: feature
files:
  edit:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: beta
        - kind: function
          name: gamma
validate:
  - pytest
created: "2026-02-01T00:00:00Z"
"""

_MANIFEST_SINGLE = """schema: "2"
goal: "Single foo"
type: feature
files:
  create:
    - path: src/foo.py
      artifacts:
        - kind: function
          name: alpha
        - kind: function
          name: beta
validate:
  - pytest
created: "2026-01-01T00:00:00Z"
"""


def test_fragmented_chain_reports_defrag_with_counts(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import (
        ChainMergeAcceptanceSpec,
        ChainMergeReport,
        ChainMergeVerdict,
        build_chain_merge_report,
    )

    d = _manifests_dir(tmp_path)
    (d / "a.manifest.yaml").write_text(_MANIFEST_A)
    (d / "b.manifest.yaml").write_text(_MANIFEST_B)
    chain = ManifestChain(d)

    report = build_chain_merge_report("src/foo.py", chain, None)

    assert isinstance(report, ChainMergeReport)
    assert isinstance(report.acceptance, ChainMergeAcceptanceSpec)
    assert report.file_path == "src/foo.py"
    assert report.verdict is ChainMergeVerdict.DEFRAG
    assert report.active_manifest_count == 2
    assert report.superseded_manifest_count == 0
    assert report.distinct_artifact_count == 3
    assert report.total_declaration_count == 4
    assert report.redundant_declaration_count == 1


def test_single_manifest_no_redundancy_reports_lean(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import (
        ChainMergeVerdict,
        build_chain_merge_report,
    )

    d = _manifests_dir(tmp_path)
    (d / "single.manifest.yaml").write_text(_MANIFEST_SINGLE)
    chain = ManifestChain(d)

    report = build_chain_merge_report("src/foo.py", chain, None)

    assert report.verdict is ChainMergeVerdict.LEAN
    assert report.active_manifest_count == 1
    assert report.redundant_declaration_count == 0


def test_file_without_active_writable_manifest_reports_blocked(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import (
        ChainMergeVerdict,
        build_chain_merge_report,
    )

    d = _manifests_dir(tmp_path)
    (d / "single.manifest.yaml").write_text(_MANIFEST_SINGLE)
    chain = ManifestChain(d)

    report = build_chain_merge_report("src/does_not_exist.py", chain, None)

    assert report.verdict is ChainMergeVerdict.BLOCKED
    assert report.blocking_reasons


def test_required_artifacts_equals_merged_artifacts_for(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import build_chain_merge_report

    d = _manifests_dir(tmp_path)
    (d / "a.manifest.yaml").write_text(_MANIFEST_A)
    (d / "b.manifest.yaml").write_text(_MANIFEST_B)
    chain = ManifestChain(d)

    report = build_chain_merge_report("src/foo.py", chain, None)

    expected = tuple(
        sorted(a.contract_key() for a in chain.merged_artifacts_for("src/foo.py"))
    )
    assert report.acceptance.required_artifacts == expected


def test_redundant_count_equals_total_minus_distinct(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import build_chain_merge_report

    d = _manifests_dir(tmp_path)
    (d / "a.manifest.yaml").write_text(_MANIFEST_A)
    (d / "b.manifest.yaml").write_text(_MANIFEST_B)
    chain = ManifestChain(d)

    report = build_chain_merge_report("src/foo.py", chain, None)

    assert (
        report.redundant_declaration_count
        == report.total_declaration_count - report.distinct_artifact_count
    )


def test_absent_detection_source_marks_all_unknown(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import build_chain_merge_report

    d = _manifests_dir(tmp_path)
    (d / "a.manifest.yaml").write_text(_MANIFEST_A)
    chain = ManifestChain(d)

    report = build_chain_merge_report("src/foo.py", chain, None)

    assert report.acceptance.detection_available is False
    assert set(report.acceptance.unknown_detection_artifacts) == set(
        report.acceptance.required_artifacts
    )
    assert report.acceptance.required_detecting_nodeids == {}


def test_detection_source_populates_required_nodeids(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import (
        DetectionEvidenceSource,
        build_chain_merge_report,
    )

    class _FakeSource:
        def detecting_nodeids_for(self, artifact_key: str):
            return ("tests/test_foo.py::test_alpha",)

    d = _manifests_dir(tmp_path)
    (d / "a.manifest.yaml").write_text(_MANIFEST_A)
    chain = ManifestChain(d)

    source: DetectionEvidenceSource = _FakeSource()
    assert isinstance(source, DetectionEvidenceSource)
    assert source.detecting_nodeids_for("any") == ("tests/test_foo.py::test_alpha",)

    report = build_chain_merge_report("src/foo.py", chain, source)

    assert report.acceptance.detection_available is True
    assert report.acceptance.unknown_detection_artifacts == ()
    assert report.acceptance.required_artifacts  # non-empty
    for key in report.acceptance.required_artifacts:
        assert report.acceptance.required_detecting_nodeids[key] == (
            "tests/test_foo.py::test_alpha",
        )


def test_report_is_deterministic(tmp_path):
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.chain_merge import build_chain_merge_report

    d = _manifests_dir(tmp_path)
    (d / "a.manifest.yaml").write_text(_MANIFEST_A)
    (d / "b.manifest.yaml").write_text(_MANIFEST_B)
    chain = ManifestChain(d)

    r1 = build_chain_merge_report("src/foo.py", chain, None)
    r2 = build_chain_merge_report("src/foo.py", chain, None)
    assert r1 == r2
