"""Behavioral contract for the public chain-merge CLI formatters."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_chain_merge_formatters_render_text_and_json():
    from maid_runner.cli.commands._format import (
        format_chain_merge_apply_result,
        format_chain_merge_report,
        format_chain_merge_summary,
    )
    from maid_runner.core.chain_merge import (
        ChainMergeAcceptanceSpec,
        ChainMergeReport,
        ChainMergeVerdict,
    )
    from maid_runner.core.chain_merge_apply import ChainMergeApplyResult
    from maid_runner.core.chain_merge_sweep import ChainMergeSweepSummary

    report = ChainMergeReport(
        file_path="src/example.py",
        verdict=ChainMergeVerdict.DEFRAG,
        active_manifest_count=2,
        superseded_manifest_count=1,
        distinct_artifact_count=1,
        total_declaration_count=2,
        redundant_declaration_count=1,
        blocking_reasons=(),
        acceptance=ChainMergeAcceptanceSpec(
            required_artifacts=("function:example",),
            detection_available=False,
            required_detecting_nodeids={},
            unknown_detection_artifacts=("function:example",),
        ),
    )
    summary = ChainMergeSweepSummary(
        defrag_count=1,
        lean_count=2,
        blocked_count=0,
        swept_file_count=3,
        worst_offenders=("src/example.py",),
    )
    apply_result = ChainMergeApplyResult(
        applied=False,
        snapshot_path=None,
        superseded_slugs=(),
        refused_reason="already lean",
        missing_artifacts=(),
    )

    assert "src/example.py: DEFRAG" in format_chain_merge_report(report)
    assert (
        json.loads(format_chain_merge_report(report, json_mode=True))["verdict"]
        == "defrag"
    )
    assert "1 DEFRAG, 2 LEAN, 0 BLOCKED" in format_chain_merge_summary(summary)
    assert (
        json.loads(format_chain_merge_summary(summary, json_mode=True))[
            "swept_file_count"
        ]
        == 3
    )
    assert format_chain_merge_apply_result(apply_result) == "refused: already lean"
    assert (
        json.loads(format_chain_merge_apply_result(apply_result, json_mode=True))[
            "applied"
        ]
        is False
    )


def test_chain_merge_formatters_are_accepted_by_all_active_contracts():
    from maid_runner.cli.commands._format import (
        format_chain_merge_apply_result,
        format_chain_merge_report,
        format_chain_merge_summary,
    )
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    # Exact symbol references keep the additive formatter contract visible to
    # behavioral validation; chain-aware implementation validation proves every
    # active file contract accepts those public names.
    assert all(
        callable(formatter)
        for formatter in (
            format_chain_merge_report,
            format_chain_merge_summary,
            format_chain_merge_apply_result,
        )
    )

    result = ValidationEngine(project_root=REPO_ROOT).validate(
        REPO_ROOT / "manifests/fix-chain-merge-formatter-contract.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        use_chain=True,
        manifest_dir="manifests",
    )

    assert result.success, [error.to_dict() for error in result.errors]
