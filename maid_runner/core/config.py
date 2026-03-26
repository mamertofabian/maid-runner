"""Project-level configuration for MAID Runner v2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import yaml

from maid_runner.core.types import ValidationMode


@dataclass(frozen=True)
class MaidConfig:
    manifest_dir: str = "manifests/"
    schema_version: str = "2"
    default_validation_mode: ValidationMode = ValidationMode.IMPLEMENTATION
    languages: tuple[str, ...] = ("python", "typescript")
    coherence_enabled: bool = False
    coherence_checks: tuple[str, ...] = ()


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

    return MaidConfig(
        manifest_dir=data.get("manifest_dir", "manifests/"),
        schema_version=str(data.get("schema_version", "2")),
        default_validation_mode=ValidationMode(
            data.get("default_validation_mode", "implementation")
        ),
        languages=tuple(data.get("languages", ("python", "typescript"))),
        coherence_enabled=bool(coherence.get("enabled", False)),
        coherence_checks=tuple(coherence.get("checks", ())),
    )
