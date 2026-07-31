"""Advisory Outcome and incident context for coverage recommendations."""

from __future__ import annotations

from collections.abc import Collection
import json
from pathlib import Path

import yaml


def collect_coverage_history_evidence(
    project_root: Path,
    paths: Collection[str],
) -> dict[str, tuple[str, ...]]:
    evidence: dict[str, list[str]] = {path: [] for path in paths}
    _collect_outcomes(project_root, evidence)
    _collect_incidents(project_root, evidence)
    return {path: tuple(items) for path, items in evidence.items()}


def _collect_outcomes(project_root: Path, evidence: dict[str, list[str]]) -> None:
    path = project_root / ".maid" / "outcomes.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    records = payload.get("records", ()) if isinstance(payload, dict) else ()
    if not isinstance(records, list):
        return
    for record in records:
        if not isinstance(record, dict):
            continue
        declared = record.get("declared_paths", ())
        if not isinstance(declared, list):
            continue
        slug = str(record.get("manifest_slug", "unknown"))
        status = str(record.get("status", "unknown"))
        for target in set(declared) & evidence.keys():
            evidence[target].append(f"Prior Outcome {slug} ({status})")


def _collect_incidents(project_root: Path, evidence: dict[str, list[str]]) -> None:
    directory = project_root / ".maid" / "incidents"
    if not directory.exists():
        return
    for path in sorted(directory.glob("*.incident.y*ml")):
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(payload, dict):
            continue
        searchable = json.dumps(
            {
                "packet": payload.get("packet"),
                "rejected_diff": payload.get("rejected_diff"),
                "chosen_diff": payload.get("chosen_diff"),
                "notes": payload.get("notes"),
            },
            sort_keys=True,
        )
        tags = payload.get("pattern_tags", ())
        tag_text = ", ".join(tags) if isinstance(tags, list) else ""
        for target in evidence:
            if target in searchable:
                suffix = f" [{tag_text}]" if tag_text else ""
                evidence[target].append(f"Prior incident {path.name}{suffix}")
