"""CLI handler for deterministic run evaluation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

from maid_runner.core.manifest import load_manifest, slug_from_path
from maid_runner.core.plan_lock import default_plan_lock_path
from maid_runner.core.run_evaluation import (
    RunComparisonRow,
    RunEvaluation,
    RunFinding,
    compare_runs,
    evaluate_run,
)
from maid_runner.core.types import AgentProvenance, Manifest


def cmd_evaluate(args: argparse.Namespace) -> int:
    subcommand = getattr(args, "evaluate_command", None)
    if subcommand == "compare":
        return _cmd_compare(args)
    if subcommand != "run":
        return _error("maid evaluate requires subcommand: run or compare", args)

    manifest_path = Path(args.manifest_path)
    project_root = Path(args.project_root)
    try:
        evaluation = evaluate_run(manifest_path, project_root)
    except Exception as exc:
        return _error(f"{manifest_path}: {exc}", args)

    if getattr(args, "json", False):
        print(json.dumps(_evaluation_to_dict(evaluation), indent=2, sort_keys=True))
    else:
        print(_render_text(evaluation, quiet=getattr(args, "quiet", False)))
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    manifest_dir = _resolve_manifest_dir(Path(args.manifest_dir), project_root)
    if not manifest_dir.exists():
        return _error(f"Manifest directory not found: {manifest_dir}", args)
    if not manifest_dir.is_dir():
        return _error(f"Manifest directory is not a directory: {manifest_dir}", args)

    evaluations: list[RunEvaluation] = []
    skipped = 0
    for path in _manifest_paths(manifest_dir):
        try:
            manifest = load_manifest(path)
        except Exception as exc:
            print(f"Skipped {path}: {exc}", file=sys.stderr)
            skipped += 1
            continue
        if _inactive_lifecycle(manifest):
            continue
        if not _has_run_evidence(manifest, project_root):
            skipped += 1
            continue
        try:
            evaluations.append(evaluate_run(path.resolve(), project_root))
        except Exception as exc:
            print(f"Skipped {path}: {exc}", file=sys.stderr)
            skipped += 1

    rows = compare_runs(tuple(evaluations))
    if getattr(args, "json", False):
        print(json.dumps(_comparison_to_dict(rows, skipped), indent=2, sort_keys=True))
    else:
        print(_render_compare_text(rows, skipped))
    return 0


def _resolve_manifest_dir(manifest_dir: Path, project_root: Path) -> Path:
    if manifest_dir.is_absolute():
        return manifest_dir
    return project_root / manifest_dir


def _render_text(evaluation: RunEvaluation, *, quiet: bool) -> str:
    lines = [
        f"Manifest: {evaluation.manifest_path}",
        f"Slug: {evaluation.manifest_slug}",
        f"Provenance: {_provenance_text(evaluation)}",
        f"Outcome: {evaluation.outcome_status or 'missing'}",
        f"Plan lock: {'present' if evaluation.lock_present else 'missing'}",
        f"Red evidence: {evaluation.red_evidence_status}",
        (
            "Revisions: "
            f"total={evaluation.revisions_total}, "
            f"strengthening={evaluation.revisions_strengthening}, "
            f"neutral={evaluation.revisions_neutral}, "
            f"narrowing={evaluation.revisions_narrowing}, "
            f"unclassified={evaluation.revisions_unclassified}"
        ),
        f"Incidents: {evaluation.incidents_total}",
        "Findings:",
    ]
    findings = (
        tuple(f for f in evaluation.findings if f.severity != "info")
        if quiet
        else evaluation.findings
    )
    if not findings:
        lines.append("  none")
    for finding in findings:
        evidence = ", ".join(finding.evidence)
        lines.append(
            f"  - {finding.severity} [{finding.category}] {finding.summary} ({evidence})"
        )
    return "\n".join(lines)


def _render_compare_text(rows: tuple[RunComparisonRow, ...], skipped: int) -> str:
    headers = (
        "runs",
        "agent",
        "provider",
        "model",
        "client",
        "completed",
        "other",
        "narrowing",
        "unclassified",
        "red-valid",
        "incidents",
    )
    data = [
        (
            str(row.runs),
            _comparison_agent_label(row),
            row.provider or "-",
            row.model or "-",
            row.client or "-",
            str(row.outcomes_completed),
            str(row.outcomes_other),
            str(row.revisions_narrowing_total),
            str(row.revisions_unclassified_total),
            str(row.red_evidence_valid),
            str(row.incidents_total),
        )
        for row in rows
    ]
    widths = [
        (
            max(len(headers[index]), *(len(item[index]) for item in data))
            if data
            else len(headers[index])
        )
        for index in range(len(headers))
    ]
    lines = [_format_table_row(headers, widths)]
    lines.append(_format_table_row(tuple("-" * width for width in widths), widths))
    lines.extend(_format_table_row(item, widths) for item in data)
    lines.append(f"skipped: {skipped}")
    return "\n".join(lines)


def _format_table_row(values: tuple[str, ...], widths: list[int]) -> str:
    return " ".join(value.ljust(widths[index]) for index, value in enumerate(values))


def _comparison_agent_label(row: RunComparisonRow) -> str:
    if row.provider is None and row.model is None and row.client is None:
        return "(unknown agent)"
    parts = [part for part in (row.provider, row.model, row.client) if part]
    return " / ".join(parts)


def _provenance_text(evaluation: RunEvaluation) -> str:
    if evaluation.provenance is None:
        return "anonymous"
    agent = evaluation.provenance
    source = evaluation.provenance_source or "unknown"
    parts = [agent.model]
    if agent.provider:
        parts.append(agent.provider)
    if agent.client:
        parts.append(agent.client)
    return f"{' / '.join(parts)} from {source}"


def _evaluation_to_dict(evaluation: RunEvaluation) -> dict:
    payload = asdict(evaluation)
    payload["provenance"] = _agent_to_dict(evaluation.provenance)
    payload["findings"] = [_finding_to_dict(finding) for finding in evaluation.findings]
    return payload


def _comparison_to_dict(
    rows: tuple[RunComparisonRow, ...], skipped: int
) -> dict[str, object]:
    return {
        "rows": [_comparison_row_to_dict(row) for row in rows],
        "skipped": skipped,
    }


def _comparison_row_to_dict(row: RunComparisonRow) -> dict[str, object]:
    return {
        "provider": row.provider,
        "model": row.model,
        "client": row.client,
        "runs": row.runs,
        "outcomes_completed": row.outcomes_completed,
        "outcomes_other": row.outcomes_other,
        "revisions_narrowing_total": row.revisions_narrowing_total,
        "revisions_unclassified_total": row.revisions_unclassified_total,
        "red_evidence_valid": row.red_evidence_valid,
        "incidents_total": row.incidents_total,
    }


def _finding_to_dict(finding: RunFinding) -> dict:
    return {
        "severity": finding.severity,
        "category": finding.category,
        "summary": finding.summary,
        "evidence": list(finding.evidence),
    }


def _agent_to_dict(agent: AgentProvenance | None) -> dict | None:
    if agent is None:
        return None
    data = {"model": agent.model}
    if agent.provider is not None:
        data["provider"] = agent.provider
    if agent.client is not None:
        data["client"] = agent.client
    if agent.skills:
        data["skills"] = list(agent.skills)
    if agent.instructions_fingerprint is not None:
        data["instructions_fingerprint"] = agent.instructions_fingerprint
    if agent.source is not None:
        data["source"] = agent.source
    return data


_MANIFEST_SUFFIXES = (".manifest.yaml", ".manifest.yml", ".manifest.json")
_INACTIVE_MANIFEST_DIR_NAMES = frozenset({"drafts", "v1-archive"})
_INACTIVE_LIFECYCLE_STATUSES = frozenset(
    {"archive", "archived", "draft", "epic", "legacy", "planning"}
)


def _manifest_paths(manifest_dir: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in manifest_dir.rglob("*")
                if path.is_file()
                and any(path.name.endswith(suffix) for suffix in _MANIFEST_SUFFIXES)
                and not _is_in_inactive_child_dir(path, manifest_dir)
            ),
            key=lambda path: (slug_from_path(path), str(path)),
        )
    )


def _is_in_inactive_child_dir(path: Path, manifest_dir: Path) -> bool:
    try:
        relative = path.relative_to(manifest_dir)
    except ValueError:
        return False
    return any(part in _INACTIVE_MANIFEST_DIR_NAMES for part in relative.parts[:-1])


def _inactive_lifecycle(manifest: Manifest) -> bool:
    metadata = manifest.metadata if isinstance(manifest.metadata, dict) else {}
    status = str(metadata.get("status", "")).strip().lower()
    return status in _INACTIVE_LIFECYCLE_STATUSES


def _has_run_evidence(manifest: Manifest, project_root: Path) -> bool:
    if manifest.outcome is not None:
        return True
    return default_plan_lock_path(project_root, manifest.slug).exists()


def _error(message: str, args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"error": message}, sort_keys=True))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return 2
