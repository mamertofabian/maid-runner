"""Artifact-level evidence equivalence for chain-merge test consolidation."""

from __future__ import annotations

from dataclasses import dataclass

from maid_runner.core.chain_merge import ChainMergeAcceptanceSpec
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError


@dataclass(frozen=True)
class MergeEquivalenceResult:
    """Deterministic comparison of baseline and candidate acceptance evidence."""

    file_path: str
    success: bool
    detection_regressions: tuple[str, ...]
    coverage_regressions: tuple[str, ...]
    evidence_regressions: tuple[str, ...]
    errors: tuple[ValidationError, ...]


def check_merge_equivalence(
    file_path: str,
    acceptance_bar: ChainMergeAcceptanceSpec,
    candidate: ChainMergeAcceptanceSpec,
    baseline_blocked: bool = False,
) -> MergeEquivalenceResult:
    """Require current evidence to preserve the complete recorded baseline bar."""
    baseline_required = set(acceptance_bar.required_artifacts)
    candidate_required = set(candidate.required_artifacts)

    evidence = _spec_evidence_regressions(
        "baseline", acceptance_bar, require_artifacts=True
    )
    evidence.update(
        _spec_evidence_regressions("candidate", candidate, require_artifacts=False)
    )
    if baseline_blocked and baseline_required:
        evidence.add("baseline:verdict")
    if not acceptance_bar.detection_available:
        evidence.add("baseline:detection")
    if not acceptance_bar.coverage_available:
        evidence.add("baseline:coverage")
    if not candidate.detection_available:
        evidence.add("candidate:detection")
    if not candidate.coverage_available:
        evidence.add("candidate:coverage")

    for artifact in acceptance_bar.unknown_detection_artifacts:
        evidence.add(f"baseline:detection:{artifact}")
    for artifact in acceptance_bar.unknown_coverage_artifacts:
        evidence.add(f"baseline:coverage:{artifact}")
    for artifact in acceptance_bar.uncovered_coverage_artifacts:
        evidence.add(f"baseline:coverage:{artifact}")
    for artifact in candidate.unknown_detection_artifacts:
        if artifact in baseline_required:
            evidence.add(f"candidate:detection:{artifact}")
    for artifact in candidate.unknown_coverage_artifacts:
        if artifact in baseline_required:
            evidence.add(f"candidate:coverage:{artifact}")
    for artifact in sorted(baseline_required - candidate_required):
        evidence.add(f"candidate:contract:{artifact}")

    baseline_detected = set()
    for artifact in acceptance_bar.required_artifacts:
        nodeids = acceptance_bar.required_detecting_nodeids.get(artifact)
        if nodeids:
            baseline_detected.add(artifact)
        elif acceptance_bar.detection_available:
            evidence.add(f"baseline:detection:{artifact}")

    baseline_covered = set(acceptance_bar.required_covered_artifacts)
    baseline_coverage_status = (
        baseline_covered
        | set(acceptance_bar.uncovered_coverage_artifacts)
        | set(acceptance_bar.unknown_coverage_artifacts)
    )
    if acceptance_bar.coverage_available:
        for artifact in baseline_required - baseline_coverage_status:
            evidence.add(f"baseline:coverage:{artifact}")

    candidate_detection_unknown = set(candidate.unknown_detection_artifacts)
    detection_regressions = tuple(
        sorted(
            artifact
            for artifact in baseline_detected
            if candidate.detection_available
            and artifact in candidate_required
            and artifact not in candidate_detection_unknown
            and not candidate.required_detecting_nodeids.get(artifact)
        )
    )

    candidate_coverage_unknown = set(candidate.unknown_coverage_artifacts)
    candidate_covered = set(candidate.required_covered_artifacts)
    coverage_regressions = tuple(
        sorted(
            artifact
            for artifact in baseline_covered
            if candidate.coverage_available
            and artifact in candidate_required
            and artifact not in candidate_coverage_unknown
            and artifact not in candidate_covered
        )
    )
    evidence_regressions = tuple(sorted(evidence))

    errors = tuple(
        [
            _equivalence_error(
                file_path,
                f"Equivalence evidence is incomplete: {marker}.",
            )
            for marker in evidence_regressions
        ]
        + [
            _equivalence_error(
                file_path,
                f"Candidate tests no longer detect the knockout for {artifact}.",
            )
            for artifact in detection_regressions
        ]
        + [
            _equivalence_error(
                file_path,
                f"Candidate test coverage no longer covers {artifact}.",
            )
            for artifact in coverage_regressions
        ]
    )
    return MergeEquivalenceResult(
        file_path=file_path,
        success=not errors,
        detection_regressions=detection_regressions,
        coverage_regressions=coverage_regressions,
        evidence_regressions=evidence_regressions,
        errors=errors,
    )


def _equivalence_error(file_path: str, message: str) -> ValidationError:
    return ValidationError(
        code=ErrorCode.CHAIN_MERGE_EQUIVALENCE_REGRESSION,
        message=message,
        severity=Severity.ERROR,
        location=Location(file=file_path),
        suggestion=(
            "Restore candidate test coverage/detection or regenerate complete "
            "baseline and candidate evidence before retiring tests."
        ),
    )


def _spec_evidence_regressions(
    role: str,
    spec: ChainMergeAcceptanceSpec,
    *,
    require_artifacts: bool,
) -> set[str]:
    evidence: set[str] = set()
    required = spec.required_artifacts
    required_set = set(required)
    if (
        (require_artifacts and not required)
        or not _valid_identity_tuple(required)
        or len(required_set) != len(required)
    ):
        evidence.add(f"{role}:contract")

    detection_keys = set(spec.required_detecting_nodeids)
    detection_unknown = set(spec.unknown_detection_artifacts)
    if (
        not _valid_identity_tuple(spec.unknown_detection_artifacts)
        or not detection_keys <= required_set
        or not detection_unknown <= required_set
        or detection_keys & detection_unknown
        or detection_keys | detection_unknown != required_set
        or (
            not spec.detection_available
            and (detection_keys or detection_unknown != required_set)
        )
    ):
        evidence.add(f"{role}:contract")
    for artifact, nodeids in spec.required_detecting_nodeids.items():
        if (
            not isinstance(artifact, str)
            or not artifact.strip()
            or artifact not in required_set
        ):
            evidence.add(f"{role}:contract")
            continue
        if not _valid_identity_tuple(nodeids):
            evidence.add(f"{role}:detection:{artifact}")

    coverage_groups = (
        spec.required_covered_artifacts,
        spec.uncovered_coverage_artifacts,
        spec.unknown_coverage_artifacts,
    )
    coverage_sets = tuple(set(group) for group in coverage_groups)
    if (
        any(not _valid_identity_tuple(group) for group in coverage_groups)
        or any(not group <= required_set for group in coverage_sets)
        or any(
            left & right
            for index, left in enumerate(coverage_sets)
            for right in coverage_sets[index + 1 :]
        )
        or set().union(*coverage_sets) != required_set
        or (
            not spec.coverage_available
            and (
                bool(spec.required_covered_artifacts)
                or bool(spec.uncovered_coverage_artifacts)
                or coverage_sets[2] != required_set
            )
        )
    ):
        evidence.add(f"{role}:contract")
    return evidence


def _valid_identity_tuple(values: object) -> bool:
    return (
        isinstance(values, tuple)
        and all(isinstance(value, str) and value.strip() for value in values)
        and len(set(values)) == len(values)
    )
