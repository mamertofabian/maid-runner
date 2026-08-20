"""Behavioral tests for maid_runner.core.chain_merge_evidence (chain-merge child 2).

SUT imported inside each test body. The round-trip test stores a real 121-22
cache entry and reads it back through the public accessor — no knockout run.
"""

from __future__ import annotations

from pathlib import Path


def test_returns_recorded_nodeids_for_known_merge_key():
    from maid_runner.core.chain_merge_evidence import RecordedDetectionEvidenceSource

    source = RecordedDetectionEvidenceSource(
        {"function:alpha": ("tests/test_x.py::test_a",)}
    )

    assert source.detecting_nodeids_for("function:alpha") == (
        "tests/test_x.py::test_a",
    )


def test_returns_none_for_unrecorded_artifact():
    from maid_runner.core.chain_merge_evidence import RecordedDetectionEvidenceSource

    source = RecordedDetectionEvidenceSource({"function:alpha": ("t::a",)})

    assert source.detecting_nodeids_for("function:missing") is None


def test_exact_contract_key_maps_to_merge_key():
    from maid_runner.core.chain_merge_evidence import RecordedDetectionEvidenceSource

    # merge_key "function:alpha" is 14 chars; contract_key wraps it with signature.
    source = RecordedDetectionEvidenceSource({"function:alpha": ("t::a",)})

    assert source.detecting_nodeids_for("exact:14:function:alpha3:str") == ("t::a",)


def test_satisfies_detection_evidence_source_protocol():
    from maid_runner.core.chain_merge import DetectionEvidenceSource
    from maid_runner.core.chain_merge_evidence import RecordedDetectionEvidenceSource

    source: DetectionEvidenceSource = RecordedDetectionEvidenceSource({})

    assert isinstance(source, DetectionEvidenceSource)


def test_from_cache_cold_cache_is_all_unknown(tmp_path):
    from maid_runner.core.chain_merge_evidence import RecordedDetectionEvidenceSource
    from maid_runner.core.knockout import cached_detecting_nodeids

    manifests = (_target_manifest(tmp_path),)

    # No cache written yet: the accessor yields an empty map and the source is
    # UNKNOWN for every artifact.
    assert cached_detecting_nodeids(manifests, tmp_path) == {}
    source = RecordedDetectionEvidenceSource.from_cache(manifests, str(tmp_path))
    assert source.detecting_nodeids_for("function:target") is None


def test_from_cache_reads_recorded_detecting_nodeids(tmp_path):
    from maid_runner.core._knockout_worker import KnockoutWorkerResult
    from maid_runner.core.chain_merge_evidence import RecordedDetectionEvidenceSource
    from maid_runner.core.knockout import (
        KnockoutDifferentialProof,
        KnockoutReport,
        KnockoutResult,
        _store_knockout_spec_cache,
        build_knockout_mutation_specs,
    )

    manifests = (_target_manifest(tmp_path),)
    (spec,) = build_knockout_mutation_specs(manifests, tmp_path)

    nodeids = ("tests/test_target.py::test_target",)
    proof = KnockoutDifferentialProof(
        identity=spec.identity,
        command=("pytest",),
        baseline_exit_code=0,
        mutant_exit_code=1,
        restored_exit_code=0,
        detecting_nodeids=nodeids,
        used_exact_fallback=False,
        diagnostics=(),
    )
    result = KnockoutResult(
        artifact_name=spec.identity.artifact_name,
        artifact_kind=spec.identity.artifact_kind,
        parent_class=spec.identity.parent_class,
        file_path=spec.identity.file_path,
        detected=True,
        duration_ms=1.0,
        proof=proof,
    )
    worker = KnockoutWorkerResult(
        identity=spec.identity,
        reports={"cmd": KnockoutReport(results=(result,), errors=())},
        process_cost=1,
        errors=(),
    )
    _store_knockout_spec_cache(tmp_path, spec, worker)

    source = RecordedDetectionEvidenceSource.from_cache(manifests, str(tmp_path))

    assert source.detecting_nodeids_for("function:target") == nodeids


def _target_manifest(root: Path):
    from maid_runner.core.manifest import load_manifest

    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "manifests").mkdir(exist_ok=True)
    (root / "src" / "target.py").write_text("def target() -> str:\n    return 'ok'\n")
    (root / "tests" / "test_target.py").write_text(
        "from src.target import target\n\n\ndef test_target():\n    assert target() == 'ok'\n"
    )
    path = root / "manifests" / "target.manifest.yaml"
    path.write_text(
        'schema: "2"\n'
        'goal: "target"\n'
        "type: feature\n"
        'created: "2026-08-13T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/target.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: target\n"
        "          args: []\n"
        "          returns: str\n"
        "  read:\n"
        "    - tests/test_target.py\n"
        "validate:\n"
        "  - python -m pytest -q tests/test_target.py\n"
    )
    return load_manifest(path)
