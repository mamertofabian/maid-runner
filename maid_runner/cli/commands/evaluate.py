"""CLI handler for deterministic run evaluation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

from maid_runner.core.run_evaluation import RunEvaluation, RunFinding, evaluate_run
from maid_runner.core.types import AgentProvenance


def cmd_evaluate(args: argparse.Namespace) -> int:
    subcommand = getattr(args, "evaluate_command", None)
    if subcommand != "run":
        return _error("maid evaluate requires subcommand: run", args)

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


def _error(message: str, args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"error": message}, sort_keys=True))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return 2
