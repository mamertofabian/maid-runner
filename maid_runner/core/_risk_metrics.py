"""Built-in source metrics for the risk-v1 recommendation model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection

from maid_runner.validators.registry import ValidatorRegistry


@dataclass(frozen=True)
class _RiskMetrics:
    logical_lines: int | None
    decision_points: int | None
    largest_definition_lines: int | None
    public_artifacts: int | None
    parse_uncertain: bool
    evidence: tuple[str, ...] = ()


def _collect_risk_metrics(
    project_root: Path,
    paths: Collection[str],
    registry: ValidatorRegistry | None = None,
) -> dict[str, _RiskMetrics]:
    registry = registry or ValidatorRegistry.with_builtin_validators()
    return {
        path: _metrics_for_path(project_root / path, path, registry) for path in paths
    }


def _metrics_for_path(
    file_path: Path,
    relative_path: str,
    registry: ValidatorRegistry,
) -> _RiskMetrics:
    try:
        source = file_path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
        return _unknown_metrics(f"Source could not be read: {exc}")

    if not registry.has_validator(file_path):
        return _RiskMetrics(
            logical_lines=None,
            decision_points=None,
            largest_definition_lines=None,
            public_artifacts=None,
            parse_uncertain=True,
            evidence=("No registered validator for source language",),
        )

    try:
        validator = registry.get(file_path)
        result = validator.collect_complexity(source, file_path)
    except Exception as exc:
        return _RiskMetrics(
            logical_lines=None,
            decision_points=None,
            largest_definition_lines=None,
            public_artifacts=None,
            parse_uncertain=True,
            evidence=(f"Validator construction or collection failed: {exc}",),
        )
    if result.errors or not result.supported:
        return _RiskMetrics(
            logical_lines=result.logical_lines,
            decision_points=None,
            largest_definition_lines=None,
            public_artifacts=None,
            parse_uncertain=True,
            evidence=(
                tuple(str(error) for error in result.errors)
                or ("Validator does not support complexity collection",)
            ),
        )
    return _RiskMetrics(
        logical_lines=result.logical_lines,
        decision_points=result.decision_points,
        largest_definition_lines=result.largest_definition_lines,
        public_artifacts=result.public_artifacts,
        parse_uncertain=False,
    )


def _unknown_metrics(message: str) -> _RiskMetrics:
    return _RiskMetrics(
        logical_lines=None,
        decision_points=None,
        largest_definition_lines=None,
        public_artifacts=None,
        parse_uncertain=True,
        evidence=(message,),
    )
