"""Deterministic, advisory verify-profile recommendations for a change."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

import yaml

from maid_runner.core.chain import _INACTIVE_MANIFEST_DIR_NAMES
from maid_runner.core.coverage_recommendation import recommend_coverage
from maid_runner.core.diff_scope import DiffScopeBaseline, collect_diff_scope


class AssessmentTier(str, Enum):
    """Monotonic ceremony tier derived from collected change signals."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ChangeSignalSummary:
    """Deterministic inputs to verify-profile recommendation policy."""

    changed_paths: tuple[str, ...]
    sensitive_paths: tuple[str, ...]
    public_artifact_changes: int
    risk_priorities: tuple[str, ...]


@dataclass(frozen=True)
class VerifyProfileRecommendation:
    """Advisory profile selection and its human-readable evidence."""

    tier: AssessmentTier
    profile: str
    rationale: tuple[str, ...]
    human_gate_expected: bool


def recommend_verify_profile(
    signals: ChangeSignalSummary,
) -> VerifyProfileRecommendation:
    """Map deterministic change signals to an existing verify profile."""
    changed_count = len(signals.changed_paths)
    risk_priority = _highest_risk_priority(signals.risk_priorities)
    has_human_gate_path = any(
        _sensitive_category(path) == "human-gate" for path in signals.sensitive_paths
    )
    has_high_risk_signal = bool(
        signals.sensitive_paths
        or signals.public_artifact_changes
        or risk_priority in {"high", "critical"}
    )

    if changed_count >= 8 and has_human_gate_path:
        tier = AssessmentTier.CRITICAL
    elif changed_count >= 8 or has_high_risk_signal:
        tier = AssessmentTier.HIGH
    elif changed_count >= 3 or risk_priority == "medium":
        tier = AssessmentTier.MEDIUM
    else:
        tier = AssessmentTier.LOW

    rationale = [f"{changed_count} changed path(s)"]
    if signals.sensitive_paths:
        rationale.append("sensitive path(s): " + ", ".join(signals.sensitive_paths))
    if signals.public_artifact_changes:
        rationale.append(f"{signals.public_artifact_changes} public artifact change(s)")
    if risk_priority is not None:
        rationale.append(f"highest risk-v1 priority: {risk_priority}")
    if len(rationale) == 1:
        rationale.append("no elevated deterministic blast-radius signal")

    return VerifyProfileRecommendation(
        tier=tier,
        profile=(
            "deep"
            if tier in {AssessmentTier.HIGH, AssessmentTier.CRITICAL}
            else "handoff"
        ),
        rationale=tuple(rationale),
        human_gate_expected=tier is AssessmentTier.CRITICAL,
    )


def assess_change_signals(
    project_root: Path,
    baseline: DiffScopeBaseline,
    manifest_dir: str = "manifests/",
) -> ChangeSignalSummary:
    """Collect diff-scope and risk-v1 evidence for an explicit baseline."""
    root = project_root.resolve()
    diff = collect_diff_scope(root, baseline)
    all_changed_paths = tuple(sorted({*diff.created, *diff.edited, *diff.deleted}))
    non_generated_paths = tuple(
        path for path in all_changed_paths if not _is_generated_cache_path(path)
    )
    manifest_root = _manifest_root(root, manifest_dir)
    material_paths = tuple(
        path
        for path in non_generated_paths
        if not _is_lifecycle_path(path, manifest_root)
    )
    routine_lifecycle_paths = _routine_lifecycle_paths(
        root,
        non_generated_paths,
        material_paths,
        manifest_root,
    )
    changed_paths = tuple(
        path for path in non_generated_paths if path not in routine_lifecycle_paths
    )
    changed_set = set(changed_paths)
    public_artifact_changes = sum(
        len(delta.added) + len(delta.signature_changed) + len(delta.removed)
        for delta in diff.deltas
        if delta.path in changed_set
    )

    # risk-v1 is repository-wide by design. Run it once, then retain only
    # candidates in this change; fully tracked/deleted paths may be absent and
    # are represented by the other explicit signals rather than a fake zero.
    risk_report = recommend_coverage(
        root,
        manifest_dir=manifest_dir,
        limit=2**31 - 1,
        use_cache=False,
    )
    risk_priorities = tuple(
        candidate.priority.value
        for candidate in sorted(risk_report.candidates, key=lambda item: item.path)
        if candidate.path in changed_set
    )

    return ChangeSignalSummary(
        changed_paths=changed_paths,
        sensitive_paths=tuple(
            path for path in changed_paths if _is_sensitive_path(path)
        ),
        public_artifact_changes=public_artifact_changes,
        risk_priorities=risk_priorities,
    )


def _highest_risk_priority(priorities: tuple[str, ...]) -> str | None:
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    known = [priority for priority in priorities if priority in order]
    return max(known, key=order.__getitem__) if known else None


def _is_sensitive_path(path: str) -> bool:
    return _sensitive_category(path) is not None


def _is_generated_cache_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized == ".maid/cache" or normalized.startswith(".maid/cache/")


def _manifest_root(root: Path, manifest_dir: str) -> str | None:
    configured = Path(manifest_dir)
    if configured.is_absolute():
        try:
            configured = configured.resolve().relative_to(root)
        except ValueError:
            return None
    normalized = configured.as_posix().strip("/")
    return normalized or "."


def _is_lifecycle_path(path: str, manifest_root: str | None) -> bool:
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if _is_plan_lock_path(normalized):
        return True
    if manifest_root is None:
        return False
    if manifest_root == ".":
        relative = normalized
    elif normalized.startswith(f"{manifest_root}/"):
        relative = normalized[len(manifest_root) + 1 :]
    else:
        return False
    parts = relative.split("/")
    return bool(
        parts[-1].endswith((".manifest.yaml", ".manifest.yml"))
        and not _INACTIVE_MANIFEST_DIR_NAMES.intersection(parts[:-1])
    )


def _is_plan_lock_path(path: str) -> bool:
    return path.startswith(".maid/plan-locks/") and path.endswith(".lock.json")


def _routine_lifecycle_paths(
    root: Path,
    changed_paths: tuple[str, ...],
    material_paths: tuple[str, ...],
    manifest_root: str | None,
) -> set[str]:
    if not material_paths or manifest_root is None:
        return set()

    changed_set = set(changed_paths)
    material_set = set(material_paths)
    routine: set[str] = set()
    for path in changed_paths:
        if not _is_manifest_path(path, manifest_root):
            continue
        declared_paths = _declared_writable_paths(root / path)
        if not material_set.intersection(declared_paths):
            continue
        routine.add(path)
        lock_path = f".maid/plan-locks/{_manifest_slug(path)}.lock.json"
        if lock_path in changed_set:
            routine.add(lock_path)
    return routine


def _is_manifest_path(path: str, manifest_root: str) -> bool:
    return _is_lifecycle_path(path, manifest_root) and not _is_plan_lock_path(path)


def _manifest_slug(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    for suffix in (".manifest.yaml", ".manifest.yml"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _declared_writable_paths(manifest_path: Path) -> set[str]:
    try:
        payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return set()
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        return set()

    declared: set[str] = set()
    files = payload["files"]
    for section in ("create", "edit", "delete", "scope"):
        entries = files.get(section, ())
        if not isinstance(entries, list):
            continue
        for entry in entries:
            candidate = (
                entry
                if isinstance(entry, str)
                else entry.get("path") if isinstance(entry, dict) else None
            )
            if isinstance(candidate, str):
                declared.add(candidate.replace("\\", "/").removeprefix("./"))
    return declared


def _sensitive_category(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    lowered = normalized.lower()
    parts = tuple(part for part in lowered.split("/") if part)
    name = parts[-1] if parts else ""
    tokens = _path_tokens(normalized)
    if _is_plan_lock_path(normalized):
        return "human-gate"
    human_gate_tokens = {
        "auth",
        "authz",
        "authentication",
        "authorization",
        "acl",
        "oauth",
        "oidc",
        "rbac",
        "saml",
        "security",
        "permission",
        "permissions",
        "schema",
        "schemas",
        "migration",
        "migrations",
        "manifest",
        "manifests",
    }
    build_names = {
        ".travis.yml",
        ".gitlab-ci.yml",
        "azure-pipelines.yml",
        "bitbucket-pipelines.yml",
        "build.bash",
        "build.gradle",
        "build.gradle.kts",
        "build.ps1",
        "build.py",
        "build.sh",
        "cargo.toml",
        "ci.yaml",
        "ci.yml",
        "cmakelists.txt",
        "dockerfile",
        "go.mod",
        "jenkinsfile",
        "makefile",
        "package.json",
        "pom.xml",
        "pyproject.toml",
        "tox.ini",
    }
    if (
        parts[:2] == (".github", "workflows")
        or (parts and parts[0] == ".circleci")
        or "ci" in parts
        or "build" in parts
        or name in build_names
    ):
        return "build"
    if lowered.endswith((".md", ".mdx", ".rst", ".txt")):
        return None
    if human_gate_tokens.intersection(tokens) or lowered.endswith(
        (".manifest.yaml", ".manifest.yml")
    ):
        return "human-gate"
    return None


def _path_tokens(path: str) -> set[str]:
    tokens: set[str] = set()
    for chunk in re.split(r"[^A-Za-z0-9]+", path):
        if not chunk:
            continue
        words = re.findall(
            r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|[0-9]+",
            chunk,
        )
        tokens.update(word.lower() for word in (words or [chunk]))
    return tokens
