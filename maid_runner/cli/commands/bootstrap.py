"""CLI command handler for maid bootstrap."""

from __future__ import annotations

import argparse
import json

from maid_runner.cli.commands._format import format_bootstrap_report, print_error
from maid_runner.core.bootstrap import (
    BootstrapRankReport,
    bootstrap_project,
    rank_bootstrap_candidates,
)
from maid_runner.core.coverage_recommendation import (
    CoverageExplanation,
    CoverageRecommendation,
    CoverageRecommendationReport,
    explain_coverage,
    recommend_coverage,
)


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Bootstrap MAID for an existing project."""
    json_mode = getattr(args, "json", False)
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)

    exclude = set(args.exclude) if args.exclude else None
    respect_gitignore = not getattr(args, "no_gitignore", False)
    rank_requested = getattr(args, "rank", False)
    model = getattr(args, "model", "legacy-v1")

    if not rank_requested and model == "risk-v1":
        print_error("--model risk-v1 requires --rank", json_mode=json_mode)
        return 2
    if not rank_requested and getattr(args, "explain", None):
        print_error("--explain requires --rank --model risk-v1", json_mode=json_mode)
        return 2
    if not rank_requested and getattr(args, "deep", False):
        print_error("--deep requires --rank --model risk-v1", json_mode=json_mode)
        return 2

    try:
        if rank_requested and model == "risk-v1":
            explain_path = getattr(args, "explain", None)
            if explain_path:
                explanation = explain_coverage(
                    args.directory,
                    explain_path,
                    manifest_dir=args.output_dir,
                    deep=getattr(args, "deep", False),
                )
                output = _format_coverage_explanation(
                    explanation,
                    json_mode=json_mode,
                )
            else:
                report = recommend_coverage(
                    args.directory,
                    manifest_dir=args.output_dir,
                    limit=getattr(args, "limit", 20),
                    exclude_patterns=exclude,
                    respect_gitignore=respect_gitignore,
                    deep=getattr(args, "deep", False),
                )
                output = _format_coverage_recommendations(
                    report,
                    json_mode=json_mode,
                )
            if output:
                print(output)
            return 0

        if rank_requested:
            if getattr(args, "explain", None) or getattr(args, "deep", False):
                raise ValueError("--explain and --deep require --model risk-v1")
            report = rank_bootstrap_candidates(
                args.directory,
                manifest_dir=args.output_dir,
                limit=getattr(args, "limit", 20),
                exclude_patterns=exclude,
                respect_gitignore=respect_gitignore,
            )
            output = _format_rank_report(report, json_mode=json_mode)
            if output:
                print(output)
            return 0

        report = bootstrap_project(
            args.directory,
            manifest_dir=args.output_dir,
            exclude_patterns=exclude,
            respect_gitignore=respect_gitignore,
            include_private=getattr(args, "include_private", False),
            dry_run=getattr(args, "dry_run", False),
        )
    except Exception as e:
        print_error(str(e), json_mode=json_mode)
        return 2

    output = format_bootstrap_report(
        report,
        json_mode=json_mode,
        quiet=quiet,
        verbose=verbose,
    )
    if output:
        print(output)

    return 0


def _format_rank_report(
    report: BootstrapRankReport,
    *,
    json_mode: bool = False,
) -> str:
    if json_mode:
        return json.dumps(
            {
                "total_candidates": report.total_candidates,
                "limit": report.limit,
                "candidates": [
                    {
                        "rank": index,
                        "path": candidate.path,
                        "churn": candidate.churn,
                        "inbound_refs": candidate.inbound_refs,
                        "public_artifacts": candidate.public_artifacts,
                    }
                    for index, candidate in enumerate(report.candidates, start=1)
                ],
            },
            indent=2,
        )

    lines = [
        "Ranked bootstrap candidates: "
        f"{len(report.candidates)} of {report.total_candidates}"
    ]
    for index, candidate in enumerate(report.candidates, start=1):
        lines.append(
            f"{index}. {candidate.path} "
            f"(churn={candidate.churn}, "
            f"inbound_refs={candidate.inbound_refs}, "
            f"public_artifacts={candidate.public_artifacts})"
        )
    return "\n".join(lines)


def _format_coverage_recommendations(
    report: CoverageRecommendationReport,
    *,
    json_mode: bool = False,
) -> str:
    if json_mode:
        return json.dumps(
            {
                "model": report.model,
                "repository_head": report.repository_head,
                "total_candidates": report.total_candidates,
                "limit": report.limit,
                "warnings": list(report.warnings),
                "cache_status": report.cache_status,
                "candidates": [
                    {
                        "rank": index,
                        **_coverage_candidate_dict(candidate),
                    }
                    for index, candidate in enumerate(report.candidates, start=1)
                ],
            },
            indent=2,
        )

    lines = [
        "Coverage recommendations: "
        f"{len(report.candidates)} of {report.total_candidates} "
        f"(cache: {report.cache_status})"
    ]
    for index, candidate in enumerate(report.candidates, start=1):
        lines.append(
            f"{index}. {candidate.priority.value.upper():8} "
            f"{candidate.score:5.1f}  {candidate.path}"
        )
        for signal in candidate.signals:
            raw = str(signal.raw_value)
            if len(raw) > 72:
                raw = f"{raw[:69]}..."
            lines.append(
                f"   {_signal_label(signal.name):24} "
                f"+{signal.contribution:.1f}  {raw} "
                f"[{signal.confidence.value}]"
            )
            lines.extend(f"      {item}" for item in signal.evidence)
        lines.append(f"   Confidence: {candidate.confidence.value}")
        lines.append(f"   Recommended action: {candidate.recommended_action}")
    if report.warnings:
        lines.append("")
        lines.extend(f"Warning: {warning}" for warning in report.warnings)
    return "\n".join(lines)


def _format_coverage_explanation(
    explanation: CoverageExplanation,
    *,
    json_mode: bool = False,
) -> str:
    payload = {
        "model": "risk-v1",
        "path": explanation.path,
        "eligible": explanation.eligible,
        "coverage_status": explanation.coverage_status.value,
        "exclusion_reason": explanation.exclusion_reason,
        "recommendation": (
            _coverage_candidate_dict(explanation.recommendation)
            if explanation.recommendation is not None
            else None
        ),
    }
    if json_mode:
        return json.dumps(payload, indent=2)
    if not explanation.eligible:
        return (
            f"{explanation.path}: not eligible "
            f"({explanation.exclusion_reason or explanation.coverage_status.value})"
        )
    assert explanation.recommendation is not None
    candidate = explanation.recommendation
    return _format_coverage_recommendations(
        CoverageRecommendationReport(
            model="risk-v1",
            repository_head=None,
            candidates=(candidate,),
            total_candidates=1,
            limit=1,
        )
    )


def _coverage_candidate_dict(
    candidate: CoverageRecommendation,
) -> dict:
    return {
        "path": candidate.path,
        "coverage_status": candidate.coverage_status.value,
        "score": candidate.score,
        "priority": candidate.priority.value,
        "confidence": candidate.confidence.value,
        "signals": {
            signal.name: {
                "raw_value": signal.raw_value,
                "normalized_value": signal.normalized_value,
                "contribution": signal.contribution,
                "confidence": signal.confidence.value,
                "evidence": list(signal.evidence),
            }
            for signal in candidate.signals
        },
        "reasons": list(candidate.reasons),
        "recommended_action": candidate.recommended_action,
    }


def _signal_label(name: str) -> str:
    return {
        "coverage_gap": "Coverage gap",
        "direct_dependents": "Direct dependents",
        "transitive_dependents": "Transitive dependents",
        "entrypoint_reachability": "Entrypoint reachability",
        "public_artifacts": "Public artifacts",
        "change_pressure": "Change pressure",
        "complexity": "Complexity",
        "test_reference_gap": "Test reference gap",
        "acceptance_evidence_gap": "Acceptance evidence gap",
        "validation_command_gap": "Validation command gap",
    }.get(name, name.replace("_", " ").title())
