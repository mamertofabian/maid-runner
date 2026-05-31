"""CLI handler for deterministic Outcome insight aggregation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from maid_runner.core.outcome_insights import (
    OutcomeInsightGroup,
    aggregate_outcome_insights,
)
from maid_runner.core.outcomes import outcome_index_is_stale, read_outcome_index


def cmd_insights(args: argparse.Namespace) -> int:
    index_path = Path(args.index)
    if not index_path.exists():
        return _error(f"Outcome index not found: {index_path}", args)

    try:
        index = read_outcome_index(index_path)
    except Exception as exc:
        return _error(str(exc), args)

    project_root = (
        args.project_root if args.project_root is not None else index.project_root
    )
    manifest_dir = (
        args.manifest_dir
        if args.manifest_dir is not None
        else _index_manifest_dir(index.manifest_dir, project_root)
    )
    if not getattr(args, "allow_stale_index", False):
        try:
            if outcome_index_is_stale(index_path, manifest_dir, project_root):
                return _error(
                    "Outcome index is stale; run `maid learn` or pass "
                    "--allow-stale-index",
                    args,
                )
        except Exception as exc:
            return _error(f"Outcome index staleness check failed: {exc}", args)

    try:
        report = aggregate_outcome_insights(
            index,
            limit_per_group=getattr(args, "limit", 10),
        )
    except Exception as exc:
        return _error(str(exc), args)

    if getattr(args, "json", False):
        print(json.dumps(_report_to_dict(report), sort_keys=True))
        return 0

    print(f"total_records: {report.total_records}")
    for label, groups in _report_groups(report):
        print(f"{label}:")
        for group in groups:
            print(
                f"  {group.key}: count={group.count} "
                f"sources={','.join(group.source_manifests)}"
            )
    return 0


def _report_to_dict(report) -> dict:
    return {
        "total_records": report.total_records,
        **{
            label: [_group_to_dict(group) for group in groups]
            for label, groups in _report_groups(report)
        },
    }


def _group_to_dict(group: OutcomeInsightGroup) -> dict:
    return asdict(group)


def _report_groups(report) -> tuple[tuple[str, tuple[OutcomeInsightGroup, ...]], ...]:
    return (
        ("by_tag", report.by_tag),
        ("by_path", report.by_path),
        ("by_artifact", report.by_artifact),
        ("by_change_type", report.by_change_type),
        ("by_lesson_type", report.by_lesson_type),
        ("by_review_severity", report.by_review_severity),
        ("by_validation_status", report.by_validation_status),
        ("by_completion_month", report.by_completion_month),
    )


def _error(message: str, args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"error": message}, sort_keys=True))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return 2


def _index_manifest_dir(manifest_dir: str, project_root: str) -> str:
    path = Path(manifest_dir)
    if path.is_absolute():
        return str(path)
    return str(Path(project_root) / path)
