"""CLI handler for deterministic run evaluation."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile

from maid_runner.core.manifest import load_manifest, slug_from_path
from maid_runner.core.plan_lock import default_plan_lock_path
from maid_runner.core.run_review import (
    ReviewEvidenceItem,
    ReviewRequest,
    build_review_request,
    render_run_review,
    validate_run_review,
)
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
    if subcommand == "prompt":
        return _cmd_prompt(args)
    if subcommand == "validate":
        return _cmd_validate_review(args)
    if subcommand == "render":
        return _cmd_render_review(args)
    if subcommand == "compare":
        return _cmd_compare(args)
    if subcommand != "run":
        return _error(
            "maid evaluate requires one of: run, compare, prompt, validate, render",
            args,
        )

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


def _cmd_prompt(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest_path)
    project_root = Path(getattr(args, "project_root", "."))
    try:
        evaluation = evaluate_run(manifest_path, project_root)
        manifest = load_manifest(_resolve_manifest_path(manifest_path, project_root))
        lock_payload = _read_lock_payload(project_root, evaluation.manifest_slug)
        diff_text = _read_diff_text(getattr(args, "diff_file", None))
        request = build_review_request(evaluation, manifest, lock_payload, diff_text)
        output_path = Path(args.output or ".maid/run-review-request.json")
        _write_text_atomic(
            output_path,
            json.dumps(_request_to_dict(request), indent=2, sort_keys=True) + "\n",
        )
    except Exception as exc:
        return _error(f"{manifest_path}: {exc}", args)

    print(f"Run review request written: {output_path}")
    return 0


def _cmd_validate_review(args: argparse.Namespace) -> int:
    try:
        review_data = _read_json_object(Path(args.review_path), "run review")
        request = _read_request(Path(args.request))
    except Exception as exc:
        return _error(str(exc), args)

    errors = validate_run_review(review_data, request)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2
    print(f"Run review valid: {Path(args.review_path)}")
    return 0


def _cmd_render_review(args: argparse.Namespace) -> int:
    try:
        review_data = _read_json_object(Path(args.review_path), "run review")
        request = _read_request(Path(args.request))
    except Exception as exc:
        return _error(str(exc), args)

    errors = validate_run_review(review_data, request)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 2

    output_path = Path(args.output or f".maid/run-reviews/{request.manifest_slug}.md")
    try:
        _write_text_atomic(output_path, render_run_review(review_data, request))
    except Exception as exc:
        return _error(str(exc), args)
    print(f"Run review rendered: {output_path}")
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


def _resolve_manifest_path(manifest_path: Path, project_root: Path) -> Path:
    if manifest_path.is_absolute():
        return manifest_path
    return project_root / manifest_path


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


def _read_lock_payload(project_root: Path, manifest_slug: str) -> dict | None:
    lock_path = default_plan_lock_path(project_root, manifest_slug)
    if not lock_path.exists():
        return None
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _read_diff_text(diff_file: str | None) -> str | None:
    if diff_file is None:
        return None
    return Path(diff_file).read_text(encoding="utf-8")


def _read_json_object(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Malformed {label} JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"Malformed {label} JSON at {path}: top-level value is not an object"
        )
    return data


def _read_request(path: Path) -> ReviewRequest:
    return _request_from_dict(_read_json_object(path, "run review request"))


def _request_to_dict(request: ReviewRequest) -> dict:
    return {
        "schema_version": request.schema_version,
        "manifest_slug": request.manifest_slug,
        "evaluation": request.evaluation,
        "evidence_items": [asdict(item) for item in request.evidence_items],
        "instructions": request.instructions,
    }


def _request_from_dict(data: dict) -> ReviewRequest:
    evidence_items = data.get("evidence_items")
    if not isinstance(evidence_items, list):
        raise ValueError("run review request evidence_items must be a list")
    try:
        items = tuple(_evidence_item_from_dict(item) for item in evidence_items)
        return ReviewRequest(
            schema_version=_request_string(data, "schema_version"),
            manifest_slug=_request_string(data, "manifest_slug"),
            evaluation=_request_dict(data, "evaluation"),
            evidence_items=items,
            instructions=_request_string(data, "instructions"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed run review request: {exc}") from exc


def _evidence_item_from_dict(item: object) -> ReviewEvidenceItem:
    if not isinstance(item, dict):
        raise ValueError("evidence_items entries must be objects")
    return ReviewEvidenceItem(
        evidence_id=_request_string(item, "evidence_id"),
        kind=_request_string(item, "kind"),
        text=_request_string(item, "text"),
    )


def _request_string(data: dict, key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _request_dict(data: dict, key: str) -> dict:
    value = data[key]
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(text)
            temp_file.flush()
        temp_path.replace(path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


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
