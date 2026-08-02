"""Deterministic static cache support for coverage recommendations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Collection


def coverage_cache_key(
    project_root: Path,
    *,
    repository_head: str | None,
    paths: Collection[str],
    manifest_dir: str,
    config_payload: dict,
    options: dict,
) -> str:
    digest = hashlib.sha256()
    digest.update(b"coverage-risk-v1-static-cache-v1\0")
    digest.update((repository_head or "").encode())
    digest.update(json.dumps(config_payload, sort_keys=True).encode())
    digest.update(json.dumps(options, sort_keys=True).encode())

    inputs = {project_root / path for path in paths}
    inputs.update(
        {
            project_root / ".maidrc.yaml",
            project_root / "pyproject.toml",
            project_root / "package.json",
            project_root / ".git" / "shallow",
        }
    )
    inputs.update(project_root.glob("tsconfig*.json"))
    manifest_root = Path(manifest_dir)
    if not manifest_root.is_absolute():
        manifest_root = project_root / manifest_root
    if manifest_root.exists():
        inputs.update(path for path in manifest_root.rglob("*") if path.is_file())
    outcomes = project_root / ".maid" / "outcomes.json"
    if outcomes.is_file():
        inputs.add(outcomes)
    incidents = project_root / ".maid" / "incidents"
    if incidents.exists():
        inputs.update(path for path in incidents.rglob("*") if path.is_file())

    for path in sorted(inputs, key=lambda item: str(item)):
        try:
            label = path.relative_to(project_root).as_posix()
        except ValueError:
            label = str(path.resolve())
        digest.update(label.encode())
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def load_cached_coverage_report(
    project_root: Path,
    cache_key: str,
) -> dict | None:
    path = project_root / ".maid" / "cache" / "coverage-risk-v1.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("cache_key") != cache_key:
        return None
    report = payload.get("report")
    return report if isinstance(report, dict) else None


def write_cached_coverage_report(
    project_root: Path,
    cache_key: str,
    report: dict,
) -> None:
    path = project_root / ".maid" / "cache" / "coverage-risk-v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cache_key": cache_key, "report": report}
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
