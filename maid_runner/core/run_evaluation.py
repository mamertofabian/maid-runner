"""Deterministic after-action evaluation for completed MAID runs."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from maid_runner.core.incidents import StoredIncident, read_incident
from maid_runner.core.manifest import load_manifest
from maid_runner.core.plan_lock import (
    ContractDelta,
    PlanLock,
    _PlanLockLoadError,
    _red_evidence_is_valid,
    default_plan_lock_path,
)
from maid_runner.core.types import AgentProvenance, Manifest


@dataclass(frozen=True)
class RunFinding:
    """One evidence-cited run-evaluation finding."""

    severity: str
    category: str
    summary: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class RunEvaluation:
    """Complete deterministic after-action evaluation of one manifest run."""

    manifest_path: str
    manifest_slug: str
    provenance: Optional[AgentProvenance]
    provenance_source: Optional[str]
    outcome_status: Optional[str]
    outcome_uncorroborated_commands: tuple[str, ...]
    unevidenced_validate_commands: tuple[str, ...]
    lock_present: bool
    red_evidence_status: str
    revisions_total: int
    revisions_strengthening: int
    revisions_neutral: int
    revisions_narrowing: int
    revisions_unclassified: int
    incidents_total: int
    findings: tuple[RunFinding, ...]


def evaluate_run(manifest_path: Path, project_root: Path) -> RunEvaluation:
    """Evaluate stored run evidence without mutating state or rerunning commands."""
    root = Path(project_root)
    resolved_manifest_path = _resolve_manifest_path(Path(manifest_path), root)
    manifest = load_manifest(resolved_manifest_path)
    display_manifest_path = _project_relative_path(resolved_manifest_path, root)
    lock_state = _load_lock(root, manifest.slug)
    lock = lock_state.lock
    findings: list[RunFinding] = []

    provenance, provenance_source = _resolve_provenance(manifest, lock)
    if provenance is None:
        findings.append(
            RunFinding(
                severity="warning",
                category="provenance",
                summary="Run provenance is anonymous; no outcome, plan-lock, or revision agent was recorded.",
                evidence=(f"manifest:{manifest.slug}",),
            )
        )
    else:
        findings.append(
            RunFinding(
                severity="info",
                category="provenance",
                summary=f"Run provenance resolved from {provenance_source}.",
                evidence=(f"{provenance_source}:agent",),
            )
        )

    (
        revisions_strengthening,
        revisions_neutral,
        revisions_narrowing,
        revisions_unclassified,
        revision_findings,
    ) = _classify_revisions(lock)
    findings.extend(revision_findings)

    red_evidence_status = _red_evidence_status(lock_state)
    findings.append(
        _red_evidence_finding(manifest.slug, red_evidence_status, lock_state)
    )

    (
        outcome_uncorroborated_commands,
        unevidenced_validate_commands,
        outcome_findings,
    ) = _corroborate_outcome(manifest, lock_state)
    findings.extend(outcome_findings)

    incidents, incident_findings = _incident_findings(root, manifest)
    findings.extend(incident_findings)

    return RunEvaluation(
        manifest_path=display_manifest_path,
        manifest_slug=manifest.slug,
        provenance=provenance,
        provenance_source=provenance_source,
        outcome_status=manifest.outcome.status.value if manifest.outcome else None,
        outcome_uncorroborated_commands=outcome_uncorroborated_commands,
        unevidenced_validate_commands=unevidenced_validate_commands,
        lock_present=lock_state.present,
        red_evidence_status=red_evidence_status,
        revisions_total=len(lock.revisions) if lock else 0,
        revisions_strengthening=revisions_strengthening,
        revisions_neutral=revisions_neutral,
        revisions_narrowing=revisions_narrowing,
        revisions_unclassified=revisions_unclassified,
        incidents_total=incidents,
        findings=_sort_findings(findings),
    )


@dataclass(frozen=True)
class _LockState:
    present: bool
    lock: PlanLock | None = None
    load_error: str | None = None


def _load_lock(project_root: Path, manifest_slug: str) -> _LockState:
    lock_path = default_plan_lock_path(project_root, manifest_slug)
    if not lock_path.exists():
        return _LockState(present=False)
    try:
        return _LockState(present=True, lock=PlanLock.load(lock_path))
    except (FileNotFoundError, _PlanLockLoadError, OSError, ValueError) as exc:
        return _LockState(present=True, load_error=str(exc))


def _resolve_provenance(
    manifest: Manifest, lock: PlanLock | None
) -> tuple[AgentProvenance | None, str | None]:
    if manifest.outcome is not None and manifest.outcome.agent is not None:
        return manifest.outcome.agent, "outcome"
    if lock is not None:
        if lock.agent is not None:
            return lock.agent, "plan-lock"
        for revision in reversed(lock.revisions):
            if revision.agent is not None:
                return revision.agent, "plan-lock-revision"
    return None, None


def _classify_revisions(
    lock: PlanLock | None,
) -> tuple[int, int, int, int, tuple[RunFinding, ...]]:
    if lock is None:
        return 0, 0, 0, 0, ()

    strengthening = neutral = narrowing = unclassified = 0
    findings: list[RunFinding] = []
    for index, revision in enumerate(lock.revisions, start=1):
        evidence = (f"plan-lock:revision-{index}",)
        delta = revision.contract_delta
        if delta is None:
            unclassified += 1
            findings.append(
                RunFinding(
                    severity="info",
                    category="plan-discipline",
                    summary="Plan-lock revision is unclassified because stored contract-delta evidence is absent.",
                    evidence=evidence,
                )
            )
            continue
        classification = _classify_delta(delta)
        if classification == "narrowing":
            narrowing += 1
            findings.append(
                RunFinding(
                    severity="attention",
                    category="plan-discipline",
                    summary="Plan-lock revision is narrowing based on stored contract-delta removals.",
                    evidence=evidence,
                )
            )
        elif classification == "strengthening":
            strengthening += 1
            findings.append(
                RunFinding(
                    severity="info",
                    category="plan-discipline",
                    summary="Plan-lock revision is strengthening based on stored contract-delta additions.",
                    evidence=evidence,
                )
            )
        else:
            neutral += 1
            findings.append(
                RunFinding(
                    severity="info",
                    category="plan-discipline",
                    summary="Plan-lock revision is neutral based on stored contract-delta evidence.",
                    evidence=evidence,
                )
            )
    return strengthening, neutral, narrowing, unclassified, tuple(findings)


def _classify_delta(delta: ContractDelta) -> str:
    significant_file_removals = tuple(
        entry for entry in delta.files_removed if not entry.startswith("read:")
    )
    if (
        delta.artifacts_removed
        or significant_file_removals
        or delta.validate_commands_removed
    ):
        return "narrowing"
    if delta.artifacts_added or delta.files_added or delta.validate_commands_added:
        return "strengthening"
    return "neutral"


def _red_evidence_status(lock_state: _LockState) -> str:
    if not lock_state.present:
        return "no-lock"
    if lock_state.lock is None:
        return "invalid"
    if lock_state.lock.red_evidence is None:
        return "missing"
    return (
        "valid" if _red_evidence_is_valid(lock_state.lock.red_evidence) else "invalid"
    )


def _red_evidence_finding(
    manifest_slug: str, status: str, lock_state: _LockState
) -> RunFinding:
    if lock_state.load_error is not None:
        return RunFinding(
            severity="warning",
            category="red-evidence",
            summary=f"Plan lock is unreadable, so red evidence status is invalid: {lock_state.load_error}",
            evidence=(f"plan-lock:{manifest_slug}",),
        )
    if status == "valid":
        return RunFinding(
            severity="info",
            category="red-evidence",
            summary="Plan-lock red evidence is valid.",
            evidence=("plan-lock:red-evidence",),
        )
    if status == "no-lock":
        return RunFinding(
            severity="warning",
            category="red-evidence",
            summary="No plan lock exists, so red evidence status is no-lock.",
            evidence=(f"manifest:{manifest_slug}",),
        )
    if status == "missing":
        return RunFinding(
            severity="warning",
            category="red-evidence",
            summary="Plan lock exists but red evidence is missing.",
            evidence=("plan-lock:red-evidence",),
        )
    return RunFinding(
        severity="warning",
        category="red-evidence",
        summary="Plan lock red evidence is present but invalid.",
        evidence=("plan-lock:red-evidence",),
    )


def _corroborate_outcome(
    manifest: Manifest, lock_state: _LockState
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[RunFinding, ...]]:
    if manifest.outcome is None:
        if not lock_state.present:
            return (), (), ()
        return (
            (),
            (),
            (
                RunFinding(
                    severity="warning",
                    category="outcome-corroboration",
                    summary="Plan lock exists but the manifest has no outcome section to corroborate.",
                    evidence=(f"manifest:{manifest.slug}",),
                ),
            ),
        )

    manifest_commands = tuple(
        _command_text(command) for command in manifest.validate_commands
    )
    evidence_commands = tuple(
        _command_text(evidence.command) for evidence in manifest.outcome.validation
    )
    manifest_command_set = set(manifest_commands)
    evidence_command_set = set(evidence_commands)
    uncorroborated = tuple(
        command for command in evidence_commands if command not in manifest_command_set
    )
    unevidenced = (
        tuple(
            command
            for command in manifest_commands
            if command not in evidence_command_set
        )
        if manifest.outcome.status.value == "completed"
        else ()
    )

    findings: list[RunFinding] = []
    for index, command in enumerate(evidence_commands, start=1):
        if command not in manifest_command_set:
            findings.append(
                RunFinding(
                    severity="info",
                    category="outcome-corroboration",
                    summary=f"Outcome cites validation evidence outside this manifest's validate list: {command}",
                    evidence=(f"outcome:validation[{index}]",),
                )
            )
    for index, command in enumerate(manifest_commands, start=1):
        if (
            command not in evidence_command_set
            and manifest.outcome.status.value == "completed"
        ):
            findings.append(
                RunFinding(
                    severity="warning",
                    category="outcome-corroboration",
                    summary=f"Completed outcome lacks validation evidence for manifest command: {command}",
                    evidence=(f"manifest:validate[{index}]",),
                )
            )
    if not uncorroborated and not unevidenced:
        findings.append(
            RunFinding(
                severity="info",
                category="outcome-corroboration",
                summary="Outcome validation evidence corroborates the manifest validate commands.",
                evidence=("outcome:validation",),
            )
        )
    return uncorroborated, unevidenced, tuple(findings)


def _incident_findings(
    project_root: Path, manifest: Manifest
) -> tuple[int, tuple[RunFinding, ...]]:
    incidents: list[StoredIncident] = []
    findings: list[RunFinding] = []
    incidents_dir = project_root / ".maid" / "incidents"
    manifest_refs = {
        manifest.slug,
        manifest.source_path,
        _project_relative_path(Path(manifest.source_path), project_root),
    }
    for stored in _list_incidents_lenient(incidents_dir):
        if isinstance(stored, RunFinding):
            findings.append(stored)
            continue
        if stored.record.manifest in manifest_refs:
            incidents.append(stored)
            findings.append(
                RunFinding(
                    severity="warning",
                    category="integrity",
                    summary=f"Stored incident references this manifest: {Path(stored.path).name}",
                    evidence=(f"incident:{Path(stored.path).name}",),
                )
            )

    if not findings:
        return 0, (
            RunFinding(
                severity="info",
                category="integrity",
                summary="No stored incidents reference this manifest.",
                evidence=(f"manifest:{manifest.slug}",),
            ),
        )
    return len(incidents), tuple(findings)


def _list_incidents_lenient(
    incidents_dir: Path,
) -> tuple[StoredIncident | RunFinding, ...]:
    if not incidents_dir.exists():
        return ()
    if not incidents_dir.is_dir():
        return (
            RunFinding(
                severity="warning",
                category="integrity",
                summary=f"Incident storage is unreadable: {incidents_dir} is not a directory",
                evidence=("incident:storage",),
            ),
        )
    items: list[StoredIncident | RunFinding] = []
    for path in sorted(incidents_dir.glob("*.incident.yaml")):
        try:
            items.append(StoredIncident(path=str(path), record=read_incident(path)))
        except Exception as exc:
            items.append(
                RunFinding(
                    severity="warning",
                    category="integrity",
                    summary=f"Incident storage is unreadable: {exc}",
                    evidence=(f"incident:{path.name}",),
                )
            )
    return tuple(items)


def _command_text(command: tuple[str, ...]) -> str:
    return shlex.join(command)


def _resolve_manifest_path(manifest_path: Path, project_root: Path) -> Path:
    if manifest_path.is_absolute():
        return manifest_path
    return project_root / manifest_path


def _project_relative_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _sort_findings(findings: list[RunFinding]) -> tuple[RunFinding, ...]:
    severity_order = {"attention": 0, "warning": 1, "info": 2}
    return tuple(
        sorted(
            findings,
            key=lambda finding: (
                severity_order.get(finding.severity, 99),
                finding.category,
                finding.summary,
                finding.evidence,
            ),
        )
    )
