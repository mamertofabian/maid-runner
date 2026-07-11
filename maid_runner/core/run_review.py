"""Deterministic request, validation, and rendering for run reviews."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Optional

from maid_runner.core.run_evaluation import RunEvaluation
from maid_runner.core.types import Manifest


@dataclass(frozen=True)
class ReviewEvidenceItem:
    """One citable fact in a run-review request."""

    evidence_id: str
    kind: str
    text: str


@dataclass(frozen=True)
class ReviewRequest:
    """Complete deterministic prompt packet for one advisory run review."""

    schema_version: str
    manifest_slug: str
    evaluation: dict
    evidence_items: tuple[ReviewEvidenceItem, ...]
    instructions: str


def build_review_request(
    evaluation: RunEvaluation,
    manifest: Manifest,
    lock_payload: Optional[dict],
    diff_text: Optional[str],
) -> ReviewRequest:
    """Build a bounded, evidence-itemized request for model-assisted review."""
    evidence_items: list[ReviewEvidenceItem] = []

    for index, revision in enumerate(_lock_revisions(lock_payload), start=1):
        evidence_items.append(
            ReviewEvidenceItem(
                evidence_id=f"revision-{index}",
                kind="revision",
                text=_revision_text(index, revision),
            )
        )

    if manifest.outcome is not None:
        for index, lesson in enumerate(manifest.outcome.lessons, start=1):
            paths = f" Paths: {', '.join(lesson.paths)}." if lesson.paths else ""
            evidence_items.append(
                ReviewEvidenceItem(
                    evidence_id=f"outcome-lesson-{index}",
                    kind="outcome-lesson",
                    text=(
                        f"Outcome lesson {index}: {lesson.lesson_type}: "
                        f"{lesson.summary}.{paths}"
                    ),
                )
            )
        for index, note in enumerate(manifest.outcome.review_notes, start=1):
            evidence_items.append(
                ReviewEvidenceItem(
                    evidence_id=f"outcome-review-note-{index}",
                    kind="review-note",
                    text=(
                        f"Outcome review note {index}: {note.source} "
                        f"[{note.severity}] {note.summary}"
                    ),
                )
            )

    for index, finding in enumerate(evaluation.findings, start=1):
        evidence_items.append(
            ReviewEvidenceItem(
                evidence_id=f"finding-{index}",
                kind="finding",
                text=(
                    f"Evaluation finding {index}: {finding.severity} "
                    f"[{finding.category}] {finding.summary} "
                    f"(evidence: {', '.join(finding.evidence)})"
                ),
            )
        )

    diff_absence = "No diff evidence was supplied."
    if diff_text is not None:
        evidence_items.append(
            ReviewEvidenceItem(
                evidence_id="diff",
                kind="diff",
                text=diff_text,
            )
        )
        diff_absence = "A diff evidence item was supplied as evidence id 'diff'."

    return ReviewRequest(
        schema_version=_REQUEST_SCHEMA_VERSION,
        manifest_slug=evaluation.manifest_slug,
        evaluation=asdict(evaluation),
        evidence_items=tuple(evidence_items),
        instructions=_instructions(diff_absence),
    )


def validate_run_review(review_data: dict, request: ReviewRequest) -> list[str]:
    """Return exhaustive anti-fabrication errors for a run-review artifact."""
    errors: list[str] = []
    if not isinstance(review_data, dict):
        return ["review must be a JSON object"]

    for key in sorted(set(review_data) - _ALLOWED_TOP_LEVEL_KEYS):
        errors.append(f"unknown top-level key: {key}")

    confidence = review_data.get("confidence")
    if confidence not in _ALLOWED_CONFIDENCES:
        errors.append(f"invalid confidence: {confidence!r}")

    summary = review_data.get("summary")
    if summary is not None:
        if not isinstance(summary, str):
            errors.append("top-level summary must be a string")
        else:
            errors.extend(
                _unevidenced_path_errors(
                    summary,
                    evidence_text="\n".join(
                        item.text for item in request.evidence_items
                    ),
                    prefix="top-level summary",
                )
            )

    findings = review_data.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        return errors

    known_ids = {item.evidence_id for item in request.evidence_items}
    evidence_text = "\n".join(item.text for item in request.evidence_items)
    for index, finding in enumerate(findings, start=1):
        if not isinstance(finding, dict):
            errors.append(f"finding {index} must be an object")
            continue
        for key in sorted(set(finding) - _ALLOWED_FINDING_KEYS):
            errors.append(f"finding {index} unknown key: {key}")
        severity = finding.get("severity")
        if severity not in _ALLOWED_SEVERITIES:
            errors.append(f"finding {index} invalid severity: {severity!r}")
        citations = finding.get("citations")
        if not _valid_citations(citations):
            errors.append(f"finding {index} missing evidence citations")
            citations = []
        for citation in citations:
            if citation not in known_ids:
                errors.append(f"finding {index} unknown evidence id: {citation}")
        summary = finding.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            errors.append(f"finding {index} missing summary")
            continue
        errors.extend(
            _unevidenced_path_errors(
                summary,
                evidence_text=evidence_text,
                prefix=f"finding {index}",
            )
        )
    return errors


def render_run_review(review_data: dict, request: ReviewRequest) -> str:
    """Render a validated run review as labeled advisory markdown."""
    errors = validate_run_review(review_data, request)
    if errors:
        raise ValueError("Invalid run review: " + "; ".join(errors))

    lines = [
        "# LLM-Generated Advisory Run Review",
        "",
        (
            "This markdown is an LLM-generated advisory review. It is "
            "model-attributed review content, not an authoritative MAID gate."
        ),
        "",
        f"Manifest: {request.manifest_slug}",
        f"Confidence: {review_data['confidence']}",
    ]
    summary = review_data.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.extend(["", "## Summary", "", summary.strip()])

    lines.extend(["", "## Deterministic Counts", ""])
    for key in _COUNT_KEYS:
        lines.append(f"- {key}: {request.evaluation.get(key)}")

    lines.extend(["", "## Findings", ""])
    findings = review_data.get("findings", [])
    if not findings:
        lines.append("No advisory findings were provided.")
    evidence_by_id = {item.evidence_id: item for item in request.evidence_items}
    for index, finding in enumerate(findings, start=1):
        lines.append(
            f"### {index}. {finding['severity'].title()}: {finding['summary']}"
        )
        lines.append("")
        lines.append("Cited evidence:")
        for citation in finding["citations"]:
            item = evidence_by_id[citation]
            lines.append(f"- `{item.evidence_id}` ({item.kind}): {item.text}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _instructions(diff_sentence: str) -> str:
    return (
        "Produce exactly one JSON object with top-level keys confidence, summary, "
        "and findings. confidence is required and must be one of low, medium, "
        "or high. findings must be a list of objects with severity, summary, "
        "and citations. Allowed severities are info, warning, and attention. "
        "Every finding must cite evidence ids from evidence_items; unknown ids "
        "are invalid. Do not cite or imply facts outside evidence_items. If "
        "evidence is absent, state the absence as absence. Do not mention file "
        f"paths unless they appear in supplied evidence text. {diff_sentence}"
    )


def _lock_revisions(lock_payload: Optional[dict]) -> tuple[dict, ...]:
    if not isinstance(lock_payload, dict):
        return ()
    revisions = lock_payload.get("revisions", [])
    if not isinstance(revisions, list):
        return ()
    return tuple(item for item in revisions if isinstance(item, dict))


def _revision_text(index: int, revision: dict) -> str:
    reason = revision.get("reason") or "(no reason recorded)"
    delta = revision.get("contract_delta")
    parts = [f"Plan-lock revision {index}: reason: {reason}."]
    if isinstance(delta, dict):
        changes = []
        for key in _DELTA_KEYS:
            values = delta.get(key) or []
            if isinstance(values, list) and values:
                changes.append(f"{key}: {', '.join(str(value) for value in values)}")
        if changes:
            parts.append("Contract delta: " + "; ".join(changes) + ".")
        else:
            parts.append("Contract delta recorded no changes.")
    else:
        parts.append("Contract delta was not recorded.")
    return " ".join(parts)


def _valid_citations(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _mentioned_file_paths(text: str) -> tuple[str, ...]:
    return tuple(sorted(set(_FILE_PATH_RE.findall(text))))


def _unevidenced_path_errors(
    text: str,
    *,
    evidence_text: str,
    prefix: str,
) -> list[str]:
    return [
        f"{prefix} unevidenced file path: {path}"
        for path in _mentioned_file_paths(text)
        if path not in evidence_text
    ]


_REQUEST_SCHEMA_VERSION = "1"
_ALLOWED_TOP_LEVEL_KEYS = frozenset({"confidence", "summary", "findings"})
_ALLOWED_FINDING_KEYS = frozenset({"severity", "summary", "citations"})
_ALLOWED_CONFIDENCES = frozenset({"low", "medium", "high"})
_ALLOWED_SEVERITIES = frozenset({"info", "warning", "attention"})
_COUNT_KEYS = (
    "outcome_status",
    "lock_present",
    "red_evidence_status",
    "revisions_total",
    "revisions_strengthening",
    "revisions_neutral",
    "revisions_narrowing",
    "revisions_unclassified",
    "incidents_total",
)
_DELTA_KEYS = (
    "artifacts_added",
    "artifacts_removed",
    "files_added",
    "files_removed",
    "validate_commands_added",
    "validate_commands_removed",
)
_FILE_PATH_RE = re.compile(
    r"(?<![\w/.-])"
    r"(?:"
    r"(?:[\w.-]+/)+[\w.-]+(?:\.[A-Za-z0-9]+)?"
    r"|"
    r"\.[A-Za-z0-9][\w.-]*"
    r"|"
    r"[\w.-]+\.[A-Za-z0-9]+"
    r"|"
    r"(?:Makefile|Dockerfile|Procfile|LICENSE|README)"
    r")"
    r"(?![\w/.-])"
)
