"""Deterministic coverage-risk recommendations for brownfield repositories."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import fnmatch
import math
from pathlib import Path
from statistics import mean
from typing import Union

from maid_runner.core._dependency_index import (
    _DependencyIndex,
    _build_dependency_index,
    _is_test_evidence_file,
)
from maid_runner.core._coverage_cache import (
    coverage_cache_key,
    load_cached_coverage_report,
    write_cached_coverage_report,
)
from maid_runner.core._coverage_history_evidence import (
    collect_coverage_history_evidence,
)
from maid_runner.core._deep_coverage import collect_deep_coverage
from maid_runner.core._file_discovery import discover_source_files
from maid_runner.core._file_tracking import _run_file_tracking
from maid_runner.core._repository_history import (
    _HistoryMetrics,
    _build_repository_history,
    _git_text,
)
from maid_runner.core._risk_metrics import _RiskMetrics, _collect_risk_metrics
from maid_runner.core.chain import ManifestChain
from maid_runner.core.config import CriticalPathRule, load_config
from maid_runner.core.result import FileTrackingStatus
from maid_runner.validators.registry import ValidatorRegistry


class CoverageStatus(str, Enum):
    UNDECLARED: str = "undeclared"
    WRITABLE_NO_ARTIFACTS: str = "writable-no-artifacts"
    READ_ONLY: str = "read-only"
    TRACKED: str = "tracked"


class CoveragePriority(str, Enum):
    CRITICAL: str = "critical"
    HIGH: str = "high"
    MEDIUM: str = "medium"
    LOW: str = "low"


class CoverageConfidence(str, Enum):
    HIGH: str = "high"
    MEDIUM: str = "medium"
    LOW: str = "low"


_RawValue = str | int | float | bool | tuple[str, ...] | None


@dataclass(frozen=True)
class CoverageSignal:
    name: str
    raw_value: _RawValue
    normalized_value: float | None
    contribution: float
    confidence: CoverageConfidence
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverageRecommendation:
    path: str
    coverage_status: CoverageStatus
    score: float
    priority: CoveragePriority
    confidence: CoverageConfidence
    signals: tuple[CoverageSignal, ...]
    reasons: tuple[str, ...]
    recommended_action: str


@dataclass(frozen=True)
class CoverageRecommendationReport:
    model: str
    repository_head: str | None
    candidates: tuple[CoverageRecommendation, ...]
    total_candidates: int
    limit: int
    warnings: tuple[str, ...] = ()
    cache_status: str = "disabled"


@dataclass(frozen=True)
class CoverageExplanation:
    path: str
    eligible: bool
    coverage_status: CoverageStatus
    exclusion_reason: str | None
    recommendation: CoverageRecommendation | None


def recommend_coverage(
    project_root: Union[str, Path],
    *,
    manifest_dir: str = "manifests/",
    limit: int = 20,
    exclude_patterns: set[str] | None = None,
    respect_gitignore: bool = True,
    deep: bool = False,
) -> CoverageRecommendationReport:
    """Rank incompletely tracked production files with the risk-v1 model."""
    root = Path(project_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project directory not found: {root}")
    config = load_config(root)
    policy = config.coverage_recommendation
    if deep and policy.deep_command is None:
        raise ValueError(
            "--deep requires coverage_recommendation.deep.command in .maidrc.yaml"
        )

    registry = ValidatorRegistry.with_builtin_validators()
    all_files = discover_source_files(
        root,
        extensions=registry.supported_extensions(),
        exclude_patterns=exclude_patterns,
        respect_gitignore=respect_gitignore,
    )
    production_files = [path for path in all_files if not _is_test_evidence_file(path)]
    chain, statuses = _coverage_statuses(root, manifest_dir, production_files)
    candidate_paths = [
        path
        for path in production_files
        if statuses.get(path, CoverageStatus.UNDECLARED) is not CoverageStatus.TRACKED
    ]
    repository_head = _git_text(root, ("rev-parse", "HEAD")) or None
    cache_key = coverage_cache_key(
        root,
        repository_head=repository_head,
        paths=all_files,
        manifest_dir=manifest_dir,
        config_payload=asdict(policy),
        options={
            "exclude_patterns": sorted(exclude_patterns or ()),
            "respect_gitignore": respect_gitignore,
            "history_date": datetime.now(timezone.utc).date().isoformat(),
            "validators": [
                {
                    "name": record.name,
                    "extensions": record.extensions,
                    "source": record.source,
                    "status": record.status,
                    "detail": record.detail,
                }
                for record in registry.validator_records()
            ],
        },
    )
    if policy.cache_enabled and not deep:
        cached = load_cached_coverage_report(root, cache_key)
        if cached is not None:
            return _report_from_cache(cached, limit=limit)

    history = _build_repository_history(root, candidate_paths)
    dependencies = _build_dependency_index(
        root,
        all_files,
        policy.entrypoints,
        registry,
    )
    metrics = _collect_risk_metrics(root, production_files, registry)
    percentiles = _metric_percentiles(metrics)
    historical = collect_coverage_history_evidence(root, candidate_paths)
    deep_result = (
        collect_deep_coverage(root, policy.deep_command, candidate_paths)
        if deep and policy.deep_command is not None
        else None
    )

    candidates = [
        _recommend_file(
            path=path,
            status=statuses.get(path, CoverageStatus.UNDECLARED),
            history=history.metrics.get(path, _HistoryMetrics(confidence="low")),
            dependencies=dependencies,
            metrics=metrics[path],
            percentiles=percentiles,
            chain=chain,
            critical_paths=policy.critical_paths,
            historical_evidence=historical.get(path, ()),
            deep_percent=(
                deep_result.percentages.get(path) if deep_result is not None else None
            ),
            deep_enabled=deep_result is not None,
        )
        for path in candidate_paths
    ]
    candidates.sort(
        key=lambda candidate: (
            _priority_order(candidate.priority),
            -candidate.score,
            candidate.path,
        )
    )
    warnings = history.warnings + (
        deep_result.warnings if deep_result is not None else ()
    )
    full_report = CoverageRecommendationReport(
        model="risk-v1",
        repository_head=history.repository_head,
        candidates=tuple(candidates),
        total_candidates=len(candidates),
        limit=len(candidates),
        warnings=warnings,
        cache_status="bypassed-deep" if deep else "disabled",
    )
    if policy.cache_enabled and not deep:
        write_cached_coverage_report(root, cache_key, _report_to_cache(full_report))
        cache_status = "miss"
    elif deep:
        cache_status = "bypassed-deep"
    else:
        cache_status = "disabled"
    return _slice_report(full_report, limit=limit, cache_status=cache_status)


def explain_coverage(
    project_root: Union[str, Path],
    path: Union[str, Path],
    *,
    manifest_dir: str = "manifests/",
    deep: bool = False,
) -> CoverageExplanation:
    """Explain recommendation eligibility and evidence for one source path."""
    root = Path(project_root).resolve()
    target = Path(path)
    absolute = target if target.is_absolute() else root / target
    try:
        relative = absolute.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Explain path is outside project root: {path}") from exc
    if not absolute.is_file():
        raise FileNotFoundError(f"Explain path not found: {relative}")

    all_files = discover_source_files(root, respect_gitignore=True)
    if relative not in all_files:
        return CoverageExplanation(
            path=relative,
            eligible=False,
            coverage_status=CoverageStatus.UNDECLARED,
            exclusion_reason="not a discovered source file",
            recommendation=None,
        )
    if _is_test_evidence_file(relative):
        return CoverageExplanation(
            path=relative,
            eligible=False,
            coverage_status=CoverageStatus.UNDECLARED,
            exclusion_reason="test files are evidence, not candidates",
            recommendation=None,
        )

    _chain, statuses = _coverage_statuses(root, manifest_dir, [relative])
    status = statuses.get(relative, CoverageStatus.UNDECLARED)
    if status is CoverageStatus.TRACKED:
        return CoverageExplanation(
            path=relative,
            eligible=False,
            coverage_status=status,
            exclusion_reason="fully tracked",
            recommendation=None,
        )

    report = recommend_coverage(
        root,
        manifest_dir=manifest_dir,
        limit=max(len(all_files), 1),
        deep=deep,
    )
    recommendation = next(
        (candidate for candidate in report.candidates if candidate.path == relative),
        None,
    )
    if recommendation is None:
        raise ValueError(f"Explain path was not eligible after discovery: {relative}")
    return CoverageExplanation(
        path=relative,
        eligible=True,
        coverage_status=status,
        exclusion_reason=None,
        recommendation=recommendation,
    )


def _coverage_statuses(
    root: Path,
    manifest_dir: str,
    production_files: list[str],
) -> tuple[ManifestChain | None, dict[str, CoverageStatus]]:
    manifest_root = Path(manifest_dir)
    if not manifest_root.is_absolute():
        manifest_root = root / manifest_root
    if not manifest_root.exists():
        return None, {path: CoverageStatus.UNDECLARED for path in production_files}

    chain = ManifestChain(manifest_root, project_root=root)
    report = _run_file_tracking(root, chain)
    read_only = chain.all_read_only_paths()
    statuses: dict[str, CoverageStatus] = {}
    for entry in report.entries:
        if entry.path not in production_files:
            continue
        if entry.status is FileTrackingStatus.UNDECLARED:
            statuses[entry.path] = CoverageStatus.UNDECLARED
        elif entry.status is FileTrackingStatus.TRACKED:
            statuses[entry.path] = CoverageStatus.TRACKED
        elif entry.path in read_only:
            statuses[entry.path] = CoverageStatus.READ_ONLY
        else:
            statuses[entry.path] = CoverageStatus.WRITABLE_NO_ARTIFACTS
    for path in production_files:
        statuses.setdefault(path, CoverageStatus.UNDECLARED)
    return chain, statuses


def _recommend_file(
    *,
    path: str,
    status: CoverageStatus,
    history: _HistoryMetrics,
    dependencies: _DependencyIndex,
    metrics: _RiskMetrics,
    percentiles: dict[str, dict[str, float]],
    chain: ManifestChain | None,
    critical_paths: tuple[CriticalPathRule, ...],
    historical_evidence: tuple[str, ...],
    deep_percent: float | None,
    deep_enabled: bool,
) -> CoverageRecommendation:
    signals: list[CoverageSignal] = []

    coverage_points = {
        CoverageStatus.UNDECLARED: 30.0,
        CoverageStatus.WRITABLE_NO_ARTIFACTS: 22.0,
        CoverageStatus.READ_ONLY: 14.0,
    }[status]
    signals.append(
        CoverageSignal(
            "coverage_gap",
            status.value,
            coverage_points / 30.0,
            coverage_points,
            CoverageConfidence.HIGH,
            (_coverage_reason(status),),
        )
    )

    dependency_confidence = _confidence(dependencies.confidence_for(path))
    direct = len(dependencies.direct_dependents(path))
    transitive = len(dependencies.transitive_dependents(path, 3))
    entrypoint = dependencies.reachable_from_entrypoint(path, 3)
    signals.extend(
        (
            _bounded_signal(
                "direct_dependents",
                direct,
                cap=20,
                weight=9,
                confidence=dependency_confidence,
            ),
            _bounded_signal(
                "transitive_dependents",
                transitive,
                cap=100,
                weight=6,
                confidence=dependency_confidence,
            ),
            _boolean_signal(
                "entrypoint_reachability",
                entrypoint,
                weight=4,
                confidence=dependency_confidence,
            ),
        )
    )

    if metrics.public_artifacts is None:
        public_surface = CoverageSignal(
            "public_artifacts",
            None,
            None,
            3.0,
            CoverageConfidence.LOW,
            metrics.evidence or ("Public artifact collection unavailable",),
        )
    else:
        public_surface = _bounded_signal(
            "public_artifacts",
            metrics.public_artifacts,
            cap=20,
            weight=6,
            confidence=CoverageConfidence.HIGH,
        )
    signals.append(public_surface)

    signals.append(_change_pressure_signal(history))
    signals.append(_complexity_signal(path, metrics, percentiles))

    has_test_reference = bool(dependencies.test_dependents(path))
    if deep_enabled:
        if deep_percent is None:
            signals.append(
                CoverageSignal(
                    "test_reference_gap",
                    None,
                    None,
                    2.0,
                    CoverageConfidence.LOW,
                    ("Deep coverage produced no measurement for this file",),
                )
            )
        else:
            gap = max(0.0, min(1.0, 1 - deep_percent / 100))
            signals.append(
                CoverageSignal(
                    "test_reference_gap",
                    f"coverage_percent={deep_percent:.1f}",
                    gap,
                    round(4 * gap, 3),
                    CoverageConfidence.HIGH,
                    ("Executed Python coverage evidence",),
                )
            )
    else:
        signals.append(
            _boolean_gap_signal(
                "test_reference_gap",
                not has_test_reference,
                4,
                confidence=dependency_confidence,
                evidence=dependencies.test_dependents(path),
            )
        )
    referenced_manifests = _manifests_referencing(chain, path)
    has_acceptance = bool(
        has_test_reference
        and any(
            manifest.acceptance and manifest.acceptance.tests
            for manifest in referenced_manifests
        )
    )
    signals.append(
        _boolean_gap_signal(
            "acceptance_evidence_gap",
            not has_acceptance,
            3,
            confidence=CoverageConfidence.HIGH,
        )
    )
    has_validation = any(
        manifest.validate_commands for manifest in referenced_manifests
    )
    signals.append(
        _boolean_gap_signal(
            "validation_command_gap",
            not has_validation,
            3,
            confidence=CoverageConfidence.HIGH,
        )
    )
    signals.append(
        CoverageSignal(
            "historical_context",
            len(historical_evidence),
            None,
            0.0,
            CoverageConfidence.HIGH,
            historical_evidence,
        )
    )

    score = round(sum(signal.contribution for signal in signals), 1)
    priority = _priority(score)
    confidence = _aggregate_confidence(signals)
    reasons = [_coverage_reason(status)]
    if direct:
        reasons.append(f"{direct} direct production dependent(s)")
    if transitive:
        reasons.append(f"{transitive} transitive dependent(s) within three levels")
    if not has_test_reference:
        reasons.append("No static test dependency/reference found")
    if confidence is CoverageConfidence.LOW:
        reasons.append("One or more measurements are incomplete")
    matched_rule = _matching_critical_rule(path, critical_paths)
    if matched_rule is not None:
        floor = CoveragePriority(matched_rule.minimum_priority)
        if _priority_order(floor) < _priority_order(priority):
            priority = floor
        reasons.append(
            "Critical path policy "
            f"{matched_rule.pattern} sets minimum priority {floor.value}"
        )
    return CoverageRecommendation(
        path=path,
        coverage_status=status,
        score=score,
        priority=priority,
        confidence=confidence,
        signals=tuple(signals),
        reasons=tuple(reasons),
        recommended_action=_recommended_action(status, priority),
    )


def _bounded_signal(
    name: str,
    raw: int,
    *,
    cap: int,
    weight: float,
    confidence: CoverageConfidence,
) -> CoverageSignal:
    normalized = min(1.0, math.log1p(max(raw, 0)) / math.log1p(cap))
    contribution = normalized * weight
    if confidence is CoverageConfidence.LOW:
        contribution = max(contribution, weight / 2)
        normalized = None
    return CoverageSignal(
        name,
        raw,
        normalized,
        round(contribution, 3),
        confidence,
    )


def _boolean_signal(
    name: str,
    raw: bool,
    *,
    weight: float,
    confidence: CoverageConfidence,
) -> CoverageSignal:
    contribution = weight if raw else 0.0
    if confidence is CoverageConfidence.LOW:
        contribution = max(contribution, weight / 2)
        normalized = None
    else:
        normalized = 1.0 if raw else 0.0
    return CoverageSignal(name, raw, normalized, contribution, confidence)


def _boolean_gap_signal(
    name: str,
    gap: bool,
    weight: float,
    *,
    confidence: CoverageConfidence,
    evidence: tuple[str, ...] = (),
) -> CoverageSignal:
    contribution = weight if gap else 0.0
    normalized: float | None = 1.0 if gap else 0.0
    if confidence is CoverageConfidence.LOW:
        contribution = max(contribution, weight / 2)
        normalized = None
    return CoverageSignal(
        name,
        gap,
        normalized,
        contribution,
        confidence,
        evidence,
    )


def _change_pressure_signal(history: _HistoryMetrics) -> CoverageSignal:
    commits_90 = 5 * _saturating(history.commits_90, 12)
    commits_365 = 3 * _saturating(history.commits_365, 30)
    lines = 6 * _saturating(history.lines_365, 2000)
    months = 3 * min(history.active_months / 12, 1)
    recency = (
        3 * (2 ** (-history.days_since_change / 90))
        if history.days_since_change is not None
        else 0
    )
    contribution = commits_90 + commits_365 + lines + months + recency
    confidence = _confidence(history.confidence)
    normalized: float | None = contribution / 20
    if confidence is CoverageConfidence.LOW:
        contribution = max(contribution, 10)
        normalized = None
    raw = (
        f"{history.commits_90} commits/90d; {history.commits_365} commits/365d; "
        f"{history.lines_365} lines/365d; {history.active_months} active months"
    )
    return CoverageSignal(
        "change_pressure",
        raw,
        normalized,
        round(contribution, 3),
        confidence,
        history.evidence,
    )


def _complexity_signal(
    path: str,
    metrics: _RiskMetrics,
    percentiles: dict[str, dict[str, float]],
) -> CoverageSignal:
    pieces = (
        ("logical_lines", metrics.logical_lines, 4.0),
        ("decision_points", metrics.decision_points, 4.0),
        ("largest_definition_lines", metrics.largest_definition_lines, 3.0),
        ("public_artifacts", metrics.public_artifacts, 2.0),
    )
    contribution = 0.0
    normalized_values: list[float] = []
    unknown = False
    raw_parts: list[str] = []
    for name, raw, weight in pieces:
        raw_parts.append(f"{name}={raw if raw is not None else 'unknown'}")
        percentile = percentiles[name].get(path) if raw is not None else None
        if percentile is None:
            contribution += weight / 2
            unknown = True
        else:
            contribution += weight * percentile
            normalized_values.append(percentile)
    if metrics.parse_uncertain:
        contribution += 2
        unknown = True
    confidence = CoverageConfidence.LOW if unknown else CoverageConfidence.HIGH
    normalized = None if unknown else mean(normalized_values)
    return CoverageSignal(
        "complexity",
        "; ".join(raw_parts),
        normalized,
        round(contribution, 3),
        confidence,
        metrics.evidence,
    )


def _metric_percentiles(
    metrics: dict[str, _RiskMetrics],
) -> dict[str, dict[str, float]]:
    fields = (
        "logical_lines",
        "decision_points",
        "largest_definition_lines",
        "public_artifacts",
    )
    return {
        field: _percentile_map(
            {
                path: value
                for path, item in metrics.items()
                if (value := getattr(item, field)) is not None
            }
        )
        for field in fields
    }


def _percentile_map(values: dict[str, int]) -> dict[str, float]:
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 0.5}
    grouped: dict[int, list[str]] = {}
    for path, value in values.items():
        grouped.setdefault(value, []).append(path)
    result: dict[str, float] = {}
    position = 0
    denominator = len(values) - 1
    for value in sorted(grouped):
        paths = grouped[value]
        average_rank = position + (len(paths) - 1) / 2
        percentile = average_rank / denominator
        for path in paths:
            result[path] = percentile
        position += len(paths)
    return result


def _manifests_referencing(
    chain: ManifestChain | None,
    path: str,
):
    if chain is None:
        return ()
    return tuple(
        manifest
        for manifest in chain.active_manifests()
        if path in manifest.all_referenced_paths
    )


def _saturating(value: int, cap: int) -> float:
    return min(1.0, math.log1p(max(value, 0)) / math.log1p(cap))


def _confidence(value: str) -> CoverageConfidence:
    try:
        return CoverageConfidence(value)
    except ValueError:
        return CoverageConfidence.LOW


def _aggregate_confidence(
    signals: list[CoverageSignal],
) -> CoverageConfidence:
    levels = {signal.confidence for signal in signals}
    if CoverageConfidence.LOW in levels:
        return CoverageConfidence.LOW
    if CoverageConfidence.MEDIUM in levels:
        return CoverageConfidence.MEDIUM
    return CoverageConfidence.HIGH


def _priority(score: float) -> CoveragePriority:
    if score >= 80:
        return CoveragePriority.CRITICAL
    if score >= 60:
        return CoveragePriority.HIGH
    if score >= 35:
        return CoveragePriority.MEDIUM
    return CoveragePriority.LOW


def _priority_order(priority: CoveragePriority) -> int:
    return {
        CoveragePriority.CRITICAL: 0,
        CoveragePriority.HIGH: 1,
        CoveragePriority.MEDIUM: 2,
        CoveragePriority.LOW: 3,
    }[priority]


def _matching_critical_rule(
    path: str,
    rules: tuple[CriticalPathRule, ...],
) -> CriticalPathRule | None:
    matches = [rule for rule in rules if fnmatch.fnmatchcase(path, rule.pattern)]
    if not matches:
        return None
    return min(
        matches,
        key=lambda rule: _priority_order(CoveragePriority(rule.minimum_priority)),
    )


def _slice_report(
    report: CoverageRecommendationReport,
    *,
    limit: int,
    cache_status: str,
) -> CoverageRecommendationReport:
    bounded_limit = max(limit, 0)
    return CoverageRecommendationReport(
        model=report.model,
        repository_head=report.repository_head,
        candidates=report.candidates[:bounded_limit],
        total_candidates=report.total_candidates,
        limit=bounded_limit,
        warnings=report.warnings,
        cache_status=cache_status,
    )


def _report_to_cache(report: CoverageRecommendationReport) -> dict:
    return {
        "model": report.model,
        "repository_head": report.repository_head,
        "total_candidates": report.total_candidates,
        "warnings": list(report.warnings),
        "candidates": [
            {
                "path": item.path,
                "coverage_status": item.coverage_status.value,
                "score": item.score,
                "priority": item.priority.value,
                "confidence": item.confidence.value,
                "signals": [
                    {
                        "name": signal.name,
                        "raw_value": signal.raw_value,
                        "normalized_value": signal.normalized_value,
                        "contribution": signal.contribution,
                        "confidence": signal.confidence.value,
                        "evidence": list(signal.evidence),
                    }
                    for signal in item.signals
                ],
                "reasons": list(item.reasons),
                "recommended_action": item.recommended_action,
            }
            for item in report.candidates
        ],
    }


def _report_from_cache(payload: dict, *, limit: int) -> CoverageRecommendationReport:
    candidates = tuple(
        CoverageRecommendation(
            path=str(item["path"]),
            coverage_status=CoverageStatus(item["coverage_status"]),
            score=float(item["score"]),
            priority=CoveragePriority(item["priority"]),
            confidence=CoverageConfidence(item["confidence"]),
            signals=tuple(
                CoverageSignal(
                    name=str(signal["name"]),
                    raw_value=signal.get("raw_value"),
                    normalized_value=signal.get("normalized_value"),
                    contribution=float(signal["contribution"]),
                    confidence=CoverageConfidence(signal["confidence"]),
                    evidence=tuple(signal.get("evidence", ())),
                )
                for signal in item.get("signals", ())
            ),
            reasons=tuple(item.get("reasons", ())),
            recommended_action=str(item["recommended_action"]),
        )
        for item in payload.get("candidates", ())
    )
    full = CoverageRecommendationReport(
        model=str(payload.get("model", "risk-v1")),
        repository_head=payload.get("repository_head"),
        candidates=candidates,
        total_candidates=int(payload.get("total_candidates", len(candidates))),
        limit=len(candidates),
        warnings=tuple(payload.get("warnings", ())),
        cache_status="hit",
    )
    return _slice_report(full, limit=limit, cache_status="hit")


def _coverage_reason(status: CoverageStatus) -> str:
    return {
        CoverageStatus.UNDECLARED: "File has no active MAID declaration",
        CoverageStatus.WRITABLE_NO_ARTIFACTS: (
            "Writable manifest registration has no declared artifacts"
        ),
        CoverageStatus.READ_ONLY: "File is registered only as read-only context",
        CoverageStatus.TRACKED: "File is fully tracked",
    }[status]


def _recommended_action(
    status: CoverageStatus,
    priority: CoveragePriority,
) -> str:
    if status is CoverageStatus.WRITABLE_NO_ARTIFACTS:
        return "complete-behavioral-contract"
    if status is CoverageStatus.READ_ONLY:
        return "promote-read-only-contract"
    if priority in {CoveragePriority.CRITICAL, CoveragePriority.HIGH}:
        return "baseline-now"
    return "baseline-next"
