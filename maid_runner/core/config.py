"""Project-level configuration for MAID Runner v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml

from maid_runner.core.types import ValidationMode


@dataclass(frozen=True)
class CriticalPathRule:
    pattern: str
    minimum_priority: str


@dataclass(frozen=True)
class CoverageRecommendationConfig:
    critical_paths: tuple[CriticalPathRule, ...] = ()
    entrypoints: tuple[str, ...] = ()
    cache_enabled: bool = True
    deep_command: tuple[str, ...] | None = None


@dataclass(frozen=True)
class MaidConfig:
    manifest_dir: str = "manifests/"
    schema_version: str = "2"
    default_validation_mode: ValidationMode = ValidationMode.IMPLEMENTATION
    languages: tuple[str, ...] = ("python", "typescript")
    coherence_enabled: bool = False
    coherence_checks: tuple[str, ...] = ()
    coverage_recommendation: CoverageRecommendationConfig = (
        CoverageRecommendationConfig()
    )


def load_config(project_root: Union[str, Path]) -> MaidConfig:
    config_path = Path(project_root) / ".maidrc.yaml"
    if not config_path.exists():
        return MaidConfig()

    text = config_path.read_text()
    if not text or not text.strip():
        return MaidConfig()

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return MaidConfig()

    coherence = data.get("coherence", {}) or {}
    recommendation = data.get("coverage_recommendation", {}) or {}
    if not isinstance(recommendation, dict):
        raise ValueError("coverage_recommendation must be a mapping")
    raw_rules = recommendation.get("critical_paths", []) or []
    if not isinstance(raw_rules, list):
        raise ValueError("coverage_recommendation.critical_paths must be a list")
    rules: list[CriticalPathRule] = []
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise ValueError("critical_paths entries must be mappings")
        pattern = raw_rule.get("pattern")
        minimum = raw_rule.get("minimum_priority")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("critical path pattern must be a non-empty string")
        if minimum not in {"low", "medium", "high", "critical"}:
            raise ValueError(
                "critical path minimum_priority must be low, medium, high, or critical"
            )
        rules.append(CriticalPathRule(pattern, minimum))
    raw_entrypoints = recommendation.get("entrypoints", []) or []
    if not isinstance(raw_entrypoints, list) or not all(
        isinstance(item, str) for item in raw_entrypoints
    ):
        raise ValueError("coverage_recommendation.entrypoints must be a string list")
    deep = recommendation.get("deep", {}) or {}
    if not isinstance(deep, dict):
        raise ValueError("coverage_recommendation.deep must be a mapping")
    raw_command = deep.get("command")
    if raw_command is not None and (
        not isinstance(raw_command, list)
        or not raw_command
        or not all(isinstance(item, str) and item for item in raw_command)
    ):
        raise ValueError(
            "coverage_recommendation.deep.command must be a non-empty string list"
        )

    return MaidConfig(
        manifest_dir=data.get("manifest_dir", "manifests/"),
        schema_version=str(data.get("schema_version", "2")),
        default_validation_mode=ValidationMode(
            data.get("default_validation_mode", "implementation")
        ),
        languages=tuple(data.get("languages", ("python", "typescript"))),
        coherence_enabled=bool(coherence.get("enabled", False)),
        coherence_checks=tuple(coherence.get("checks", ())),
        coverage_recommendation=CoverageRecommendationConfig(
            critical_paths=tuple(rules),
            entrypoints=tuple(raw_entrypoints),
            cache_enabled=bool(recommendation.get("cache", True)),
            deep_command=tuple(raw_command) if raw_command is not None else None,
        ),
    )
