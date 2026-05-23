"""Supersession artifact-preservation defense.

When manifest A supersedes manifest B, every public artifact declared in B must
be accounted for by A:

    (a) re-declared in A's own artifact set, or
    (b) live in a file that A lists under files.delete, or
    (c) appear in A's removed_artifacts declarations.

Otherwise the artifact is "dropped by supersession". Dropped artifacts are the
gaming signal: supersession used to silently shrink the validation surface.

Backward compatibility is handled through a file-backed GrandfatherLock keyed
on (superseding_slug, content_hash, artifact_key). Editing a grandfathered
manifest invalidates its content_hash and revokes grandfathering.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from maid_runner.core import _artifact_collection_cache as artifact_cache
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError
from maid_runner.core.types import ArtifactKind, RemovedArtifactSpec

if TYPE_CHECKING:
    from maid_runner.core.chain import ManifestChain


class _GrandfatherLockLoadError(Exception):
    """Raised when a grandfather lock file exists but cannot be parsed.

    Private to the package. A missing lock file is fine (treated as unsealed
    migration grace). A file that exists but is corrupt, unreadable, or
    malformed is a trust failure: the protection layer cannot proceed in good
    faith, so the audit must fail closed rather than silently demote to
    unsealed.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self._path = Path(path)
        self._reason = reason
        super().__init__(f"Failed to load grandfather lock at {self._path}: {reason}")

    @property
    def lock_path(self) -> Path:
        return self._path

    @property
    def detail(self) -> str:
        return self._reason


def compute_manifest_hash(manifest_path: Path) -> str:
    """Return a stable sha256-prefixed hash of the manifest file bytes."""
    data = Path(manifest_path).read_bytes()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _path_is_within_project(project_root: Path, file_path: str) -> bool:
    """Return True iff `file_path` is a relative path that stays inside
    `project_root` after normalization.

    Absolute paths and parent-relative paths that resolve outside the project
    root are rejected. This is a trust-boundary check: removed_artifacts must
    refer to in-repo files, never to host filesystem locations.
    """
    candidate = Path(file_path)
    if candidate.is_absolute():
        return False
    try:
        project_abs = project_root.resolve()
        full = (project_root / candidate).resolve()
        full.relative_to(project_abs)
    except (ValueError, OSError):
        return False
    return True


def default_lock_path(project_root: Path) -> Path:
    """Return the default lock-file path under the project's `.maid` directory."""
    return Path(project_root) / ".maid" / "legacy-grandfathered.lock"


@dataclass(frozen=True)
class SupersessionViolation:
    superseding_slug: str
    superseded_slug: str
    superseding_manifest_path: str
    file_path: str
    artifact_key: str
    artifact_name: str
    artifact_kind: str


@dataclass(frozen=True)
class GrandfatherEntry:
    superseding_slug: str
    content_hash: str
    dropped_artifact_keys: tuple[str, ...]
    reason: str


def _violation_lock_key(superseded_slug: str, file_path: str, artifact_key: str) -> str:
    """Compose a composite lock key.

    The grandfather lock matches on (superseding_slug, content_hash, key). For
    the key to uniquely identify a single violation we encode the superseded
    slug and file path along with the artifact merge key, separated by `|`
    (which is invalid in slugs and file paths in practice).
    """
    return f"{superseded_slug}|{file_path}|{artifact_key}"


@dataclass(frozen=True)
class GrandfatherLock:
    version: str = "2"
    sealed_at: Optional[str] = None
    entries: tuple[GrandfatherEntry, ...] = field(default_factory=tuple)

    @classmethod
    def empty(cls) -> "GrandfatherLock":
        return cls()

    @classmethod
    def load(cls, path: Path) -> "GrandfatherLock":
        p = Path(path)
        if not p.exists():
            return cls.empty()
        try:
            text = p.read_text()
        except OSError as exc:
            raise _GrandfatherLockLoadError(p, f"unreadable ({exc})") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise _GrandfatherLockLoadError(p, f"invalid JSON ({exc})") from exc
        if not isinstance(data, dict):
            raise _GrandfatherLockLoadError(p, "top-level value is not a JSON object")
        raw_entries = data.get("entries", [])
        if not isinstance(raw_entries, list):
            raise _GrandfatherLockLoadError(p, "'entries' must be an array")
        try:
            entries = tuple(
                GrandfatherEntry(
                    superseding_slug=item["superseding_slug"],
                    content_hash=item["content_hash"],
                    dropped_artifact_keys=tuple(item.get("dropped_artifact_keys", ())),
                    reason=item.get("reason", ""),
                )
                for item in raw_entries
            )
        except (KeyError, TypeError) as exc:
            raise _GrandfatherLockLoadError(p, f"malformed entry ({exc})") from exc
        return cls(
            version=str(data.get("version", "2")),
            sealed_at=data.get("sealed_at"),
            entries=entries,
        )

    def save(self, path: Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "sealed_at": self.sealed_at,
            "entries": [
                {
                    "superseding_slug": e.superseding_slug,
                    "content_hash": e.content_hash,
                    "dropped_artifact_keys": list(e.dropped_artifact_keys),
                    "reason": e.reason,
                }
                for e in self.entries
            ],
        }
        p.write_text(json.dumps(payload, indent=2, sort_keys=False))

    def is_sealed(self) -> bool:
        return self.sealed_at is not None

    def is_grandfathered(
        self,
        superseding_slug: str,
        content_hash: str,
        artifact_key: str,
    ) -> bool:
        for entry in self.entries:
            if entry.superseding_slug != superseding_slug:
                continue
            if entry.content_hash != content_hash:
                continue
            if artifact_key in entry.dropped_artifact_keys:
                return True
        return False

    def with_seal(
        self,
        sealed_at: str,
        entries: "tuple[GrandfatherEntry, ...]",
    ) -> "GrandfatherLock":
        return replace(self, sealed_at=sealed_at, entries=tuple(entries))


class SupersessionAuditor:
    """Compute supersession artifact-preservation violations over a chain."""

    def __init__(self, project_root: Path = Path("."), registry=None) -> None:
        self._project_root = Path(project_root)
        if registry is None:
            from maid_runner.validators.registry import ValidatorRegistry

            registry = ValidatorRegistry.with_builtin_validators()
        self._registry = registry

    def _removal_is_verified_absent(self, spec: RemovedArtifactSpec) -> bool:
        """Return True iff the named symbol is provably absent from the file.

        Fails closed: missing file, unsupported file, unreadable file, parse
        errors, a still-present symbol, a path that escapes the project root,
        or a method/attribute spec missing its `of` owner all return False. A
        False result revokes the exemption that `removed_artifacts` would
        otherwise grant the supersession audit.
        """
        if spec.kind in (ArtifactKind.METHOD, ArtifactKind.ATTRIBUTE) and not spec.of:
            return False
        if not _path_is_within_project(self._project_root, spec.file):
            return False
        full_path = self._project_root / spec.file
        if not full_path.exists():
            return False
        if not self._registry.has_validator(spec.file):
            return False
        try:
            source = full_path.read_text()
        except OSError:
            return False
        try:
            validator = self._registry.get(spec.file)
            collection = artifact_cache.collect_cached_implementation_artifacts(
                validator, source, spec.file
            )
        except Exception:
            return False
        if collection.errors:
            return False
        target_key = _removed_spec_key(spec)
        for found in collection.artifacts:
            if found.merge_key() == target_key:
                return False
        return True

    def find_violations(
        self, chain: "ManifestChain"
    ) -> "tuple[SupersessionViolation, ...]":
        violations: list[SupersessionViolation] = []
        manifests_by_slug = {m.slug: m for m in chain.all_manifests}

        for replacement in chain.all_manifests:
            if not replacement.supersedes:
                continue

            replacement_keys_by_file = _collect_artifact_keys_by_file(replacement)
            deleted_paths = {
                ds.path
                for ds in replacement.files_delete
                if not (self._project_root / ds.path).exists()
            }
            removed_by_file: dict[str, set[str]] = {}
            for ra in replacement.removed_artifacts:
                if not self._removal_is_verified_absent(ra):
                    continue
                removed_by_file.setdefault(ra.file, set()).add(_removed_spec_key(ra))

            for superseded_slug in replacement.supersedes:
                superseded = manifests_by_slug.get(superseded_slug)
                if superseded is None:
                    continue
                for fs in superseded.all_file_specs:
                    if fs.path in deleted_paths:
                        continue
                    file_replacement_keys = replacement_keys_by_file.get(fs.path, set())
                    file_removed_keys = removed_by_file.get(fs.path, set())
                    for artifact in fs.artifacts:
                        if artifact.is_private:
                            continue
                        if artifact.kind == ArtifactKind.TEST_FUNCTION:
                            continue
                        key = artifact.merge_key()
                        if key in file_replacement_keys:
                            continue
                        if key in file_removed_keys:
                            continue
                        violations.append(
                            SupersessionViolation(
                                superseding_slug=replacement.slug,
                                superseded_slug=superseded.slug,
                                superseding_manifest_path=replacement.source_path,
                                file_path=fs.path,
                                artifact_key=key,
                                artifact_name=artifact.name,
                                artifact_kind=artifact.kind.value,
                            )
                        )

        return tuple(violations)

    def audit(
        self,
        chain: "ManifestChain",
        lock: Optional[GrandfatherLock] = None,
    ) -> "tuple[ValidationError, ...]":
        violations = self.find_violations(chain)
        if not violations:
            return ()

        errors: list[ValidationError] = []
        hash_cache: dict[str, str] = {}
        is_sealed = lock is not None and lock.is_sealed()
        drop_severity = Severity.ERROR if is_sealed else Severity.WARNING
        for v in violations:
            grandfathered = False
            if is_sealed:
                content_hash = hash_cache.get(v.superseding_manifest_path)
                if content_hash is None:
                    content_hash = compute_manifest_hash(
                        Path(v.superseding_manifest_path)
                    )
                    hash_cache[v.superseding_manifest_path] = content_hash
                lock_key = _violation_lock_key(
                    v.superseded_slug, v.file_path, v.artifact_key
                )
                grandfathered = lock.is_grandfathered(
                    v.superseding_slug, content_hash, lock_key
                )

            if grandfathered:
                errors.append(
                    ValidationError(
                        code=ErrorCode.GRANDFATHERED_SUPERSESSION,
                        message=(
                            f"Grandfathered drop: '{v.artifact_name}' ({v.artifact_kind}) "
                            f"in {v.file_path} from superseded '{v.superseded_slug}'"
                        ),
                        severity=Severity.INFO,
                        location=Location(file=v.superseding_manifest_path),
                    )
                )
            else:
                errors.append(
                    ValidationError(
                        code=ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION,
                        message=(
                            f"Manifest '{v.superseding_slug}' supersedes "
                            f"'{v.superseded_slug}' but drops artifact "
                            f"'{v.artifact_name}' ({v.artifact_kind}) at "
                            f"{v.file_path}"
                        ),
                        severity=drop_severity,
                        location=Location(file=v.superseding_manifest_path),
                        suggestion=(
                            "Re-declare the artifact in the replacement manifest, "
                            "list its file under files.delete, or list the symbol "
                            "under removed_artifacts."
                        ),
                    )
                )

        return tuple(errors)


def _collect_artifact_keys_by_file(manifest) -> dict[str, set[str]]:
    keys: dict[str, set[str]] = {}
    for fs in manifest.all_file_specs:
        bucket = keys.setdefault(fs.path, set())
        for a in fs.artifacts:
            bucket.add(a.merge_key())
    return keys


def _removed_spec_key(spec: RemovedArtifactSpec) -> str:
    if spec.kind in (ArtifactKind.METHOD, ArtifactKind.ATTRIBUTE) and spec.of:
        return f"{spec.kind.value}:{spec.of}.{spec.name}"
    return f"{spec.kind.value}:{spec.name}"
