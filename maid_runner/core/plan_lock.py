"""Tamper-evident plan locks.

A plan lock freezes the approved planning contract for one manifest: the
manifest content hash plus per-file content hashes of its behavioral test
files. Editing a locked behavioral test or the manifest after approval is
machine-detectable as a hash mismatch instead of relying on convention.

Locks are stored as one JSON file per manifest at
`.maid/plan-locks/<manifest-slug>.lock.json`, mirroring the file-backed
GrandfatherLock pattern in `maid_runner/core/supersession_audit.py`: a missing
lock file is fine, but a present-and-broken lock file fails closed.

Re-locking requires an explicit revision with a non-empty reason; the prior
hashes are appended to an immutable `revisions` history. The `red_evidence`
slot stores bounded red-phase runtime evidence captured from the manifest's
validate commands when a plan is locked or revised.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maid_runner.core._test_command_execution import _run_test_command
from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import _is_test_file, load_manifest, slug_from_path
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.supersession_audit import compute_manifest_hash
from maid_runner.core.types import Manifest


class _PlanLockLoadError(Exception):
    """Raised when a plan lock file exists but cannot be parsed.

    Private to the package. A missing lock file simply means the plan is not
    locked. A file that exists but is corrupt, unreadable, or malformed is a
    trust failure: the lock cannot be honored in good faith, so callers must
    fail closed rather than silently treat the plan as unlocked.
    """

    def __init__(self, path: Path, reason: str) -> None:
        self._path = Path(path)
        self._reason = reason
        super().__init__(f"Failed to load plan lock at {self._path}: {reason}")

    @property
    def lock_path(self) -> Path:
        return self._path

    @property
    def detail(self) -> str:
        return self._reason


@dataclass(frozen=True)
class PlanLockRevision:
    """One immutable revision history entry."""

    prior_manifest_hash: str
    prior_test_hashes: dict[str, str]
    revised_at: str
    reason: str


@dataclass(frozen=True)
class RedPhaseCommandEvidence:
    """Per-command red-phase record."""

    command: str
    exit_code: int
    output_tail: str
    classification: str


@dataclass(frozen=True)
class RedPhaseEvidence:
    """Aggregate red-phase evidence captured by maid plan lock/revise."""

    red: bool
    commands: tuple[RedPhaseCommandEvidence, ...]
    captured_at: str

    def to_payload(self) -> dict:
        """Serialize the evidence into the JSON payload stored in a plan lock."""
        return {
            "red": self.red,
            "captured_at": self.captured_at,
            "commands": [
                {
                    "command": command.command,
                    "exit_code": command.exit_code,
                    "output_tail": command.output_tail,
                    "classification": command.classification,
                }
                for command in self.commands
            ],
        }


@dataclass(frozen=True)
class PlanLock:
    """Tamper-evident per-manifest plan lock record."""

    manifest_path: str
    manifest_hash: str
    test_hashes: dict[str, str]
    created_at: str
    revision: int = 1
    revisions: tuple[PlanLockRevision, ...] = ()
    red_evidence: Optional[dict] = None

    @classmethod
    def load(cls, path: Path) -> "PlanLock":
        """Load a lock file; fail closed when it exists but is broken."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Plan lock not found: {p}")
        try:
            text = p.read_text()
        except OSError as exc:
            raise _PlanLockLoadError(p, f"unreadable ({exc})") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise _PlanLockLoadError(p, f"invalid JSON ({exc})") from exc
        if not isinstance(data, dict):
            raise _PlanLockLoadError(p, "top-level value is not a JSON object")
        raw_revisions = data.get("revisions", [])
        if not isinstance(raw_revisions, list):
            raise _PlanLockLoadError(p, "'revisions' must be an array")
        try:
            revisions = tuple(
                PlanLockRevision(
                    prior_manifest_hash=item["prior_manifest_hash"],
                    prior_test_hashes=dict(item["prior_test_hashes"]),
                    revised_at=item["revised_at"],
                    reason=item["reason"],
                )
                for item in raw_revisions
            )
            return cls(
                manifest_path=data["manifest_path"],
                manifest_hash=data["manifest_hash"],
                test_hashes=dict(data["test_hashes"]),
                created_at=data["created_at"],
                revision=int(data["revision"]),
                revisions=revisions,
                red_evidence=data.get("red_evidence"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _PlanLockLoadError(p, f"malformed lock record ({exc})") from exc

    def save(self, path: Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "manifest_path": self.manifest_path,
            "manifest_hash": self.manifest_hash,
            "test_hashes": dict(self.test_hashes),
            "created_at": self.created_at,
            "revision": self.revision,
            "revisions": [
                {
                    "prior_manifest_hash": r.prior_manifest_hash,
                    "prior_test_hashes": dict(r.prior_test_hashes),
                    "revised_at": r.revised_at,
                    "reason": r.reason,
                }
                for r in self.revisions
            ],
            "red_evidence": self.red_evidence,
        }
        contract = _load_manifest_contract_for_lock(self, p)
        if contract is not None:
            payload["_manifest_contract"] = contract
        p.write_text(json.dumps(payload, indent=2))


def default_plan_lock_path(project_root: Path, manifest_slug: str) -> Path:
    """Return `.maid/plan-locks/<manifest-slug>.lock.json` under the root."""
    return Path(project_root) / ".maid" / "plan-locks" / f"{manifest_slug}.lock.json"


def create_plan_lock(manifest_path: Path, project_root: Path) -> PlanLock:
    """Build a revision-1 lock over the manifest and its behavioral tests."""
    manifest = load_manifest(manifest_path)
    root = Path(project_root)
    return PlanLock(
        manifest_path=_project_relative_path(manifest_path, root),
        manifest_hash=compute_manifest_hash(Path(manifest_path)),
        test_hashes=_hash_test_files(root, _behavioral_test_paths(manifest)),
        created_at=_utc_now(),
    )


def revise_plan_lock(
    existing: PlanLock,
    manifest_path: Path,
    project_root: Path,
    reason: str,
) -> PlanLock:
    """Re-lock with current hashes, appending the prior hashes to history."""
    if not reason or not reason.strip():
        raise ValueError("Plan-lock revision requires a non-empty reason")
    fresh = create_plan_lock(manifest_path, project_root)
    entry = PlanLockRevision(
        prior_manifest_hash=existing.manifest_hash,
        prior_test_hashes=dict(existing.test_hashes),
        revised_at=_utc_now(),
        reason=reason,
    )
    return PlanLock(
        manifest_path=fresh.manifest_path,
        manifest_hash=fresh.manifest_hash,
        test_hashes=fresh.test_hashes,
        created_at=existing.created_at,
        revision=existing.revision + 1,
        revisions=existing.revisions + (entry,),
        red_evidence=None,
    )


def classify_red_exit_code(exit_code: int) -> str:
    """Classify red-phase evidence by process exit code only."""
    if exit_code == 1:
        return "red"
    if exit_code == 0:
        return "not_red"
    return "invalid"


def capture_red_phase_evidence(
    manifest_path: Path, project_root: Path
) -> RedPhaseEvidence:
    """Run the manifest's validate commands and record red-phase evidence."""
    manifest = load_manifest(manifest_path)
    root = Path(project_root)
    slug = slug_from_path(manifest_path)
    commands: list[RedPhaseCommandEvidence] = []
    for command in manifest.validate_commands:
        result = _run_test_command(command, cwd=root, manifest_slug=slug)
        commands.append(
            RedPhaseCommandEvidence(
                command=shlex.join(command),
                exit_code=result.exit_code,
                output_tail=_combined_output_tail(result.stdout, result.stderr),
                classification=classify_red_exit_code(result.exit_code),
            )
        )
    command_tuple = tuple(commands)
    return RedPhaseEvidence(
        red=_has_valid_red_evidence(command_tuple),
        commands=command_tuple,
        captured_at=_utc_now(),
    )


def enforce_plan_locks(
    chain: ManifestChain,
    project_root: Path,
    require_plan_lock: bool,
    require_red_evidence: bool,
    *,
    changed_paths: Collection[str] | None = None,
) -> "tuple[ValidationError, ...]":
    """Evaluate active manifests against their plan locks."""
    if not require_plan_lock and not require_red_evidence:
        return ()

    root = Path(project_root)
    changed_path_set = _normalize_changed_paths(changed_paths)
    errors: list[ValidationError] = []
    loaded_lock_paths: set[Path] = set()

    for manifest in chain.active_manifests():
        lock_path = default_plan_lock_path(root, manifest.slug)
        loaded_lock_paths.add(lock_path)
        in_scope = _manifest_in_changed_paths(manifest, root, changed_path_set)
        if not lock_path.exists():
            if in_scope and require_plan_lock:
                errors.append(
                    _lock_error(
                        ErrorCode.PLAN_LOCK_MISSING,
                        manifest,
                        root,
                        detail=f"missing lock: {_project_relative_path(lock_path, root)}",
                    )
                )
            if in_scope and require_red_evidence:
                errors.append(
                    _lock_error(
                        ErrorCode.RED_PHASE_EVIDENCE_MISSING,
                        manifest,
                        root,
                        detail=f"no plan lock at {_project_relative_path(lock_path, root)}",
                    )
                )
            continue

        lock = _load_lock_or_error(lock_path, root)
        if isinstance(lock, ValidationError):
            errors.append(lock)
            continue

        recorded_manifest = root / lock.manifest_path
        if not recorded_manifest.exists():
            errors.append(
                ValidationError(
                    code=ErrorCode.PLAN_LOCK_STALE,
                    message="PLAN_LOCK_STALE: lock references a missing manifest",
                    location=Location(file=lock.manifest_path),
                )
            )
            continue

        errors.extend(_test_hash_errors(lock, manifest, root))
        weakening_detail = _contract_weakening_detail(lock_path, lock, manifest)
        if weakening_detail is not None:
            errors.append(
                _lock_error(
                    ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK,
                    manifest,
                    root,
                    detail=weakening_detail,
                )
            )

        if in_scope and require_red_evidence:
            if lock.red_evidence is None:
                errors.append(
                    _lock_error(ErrorCode.RED_PHASE_EVIDENCE_MISSING, manifest, root)
                )
            elif not _red_evidence_is_valid(lock.red_evidence):
                errors.append(
                    _lock_error(ErrorCode.RED_PHASE_EVIDENCE_INVALID, manifest, root)
                )

    for lock_path in _plan_lock_files(root):
        if lock_path in loaded_lock_paths:
            continue
        lock = _load_lock_or_error(lock_path, root)
        if isinstance(lock, ValidationError):
            errors.append(lock)
            continue
        if not (root / lock.manifest_path).exists():
            errors.append(
                ValidationError(
                    code=ErrorCode.PLAN_LOCK_STALE,
                    message="PLAN_LOCK_STALE: lock references a missing manifest",
                    location=Location(file=lock.manifest_path),
                )
            )

    return tuple(errors)


def _normalize_changed_paths(
    changed_paths: Collection[str] | None,
) -> set[str] | None:
    if changed_paths is None:
        return None
    return {str(path).replace("\\", "/") for path in changed_paths}


def _manifest_in_changed_paths(
    manifest: Manifest,
    project_root: Path,
    changed_paths: set[str] | None,
) -> bool:
    if changed_paths is None:
        return True
    return _manifest_location(manifest, project_root) in changed_paths


def _behavioral_test_paths(manifest: Manifest) -> list[str]:
    """Collect the manifest's behavioral test files.

    Test files come from `files.read` entries that look like test files plus
    test files declared under `files.create`/`files.edit`/`files.snapshot`.
    """
    paths: list[str] = []
    for path in manifest.files_read:
        if _is_test_file(path) and path not in paths:
            paths.append(path)
    for fs in manifest.all_file_specs:
        if _is_test_file(fs.path) and fs.path not in paths:
            paths.append(fs.path)
    return paths


def _hash_test_files(project_root: Path, paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for rel in paths:
        full = project_root / rel
        if not full.exists():
            raise FileNotFoundError(f"Behavioral test file not found: {full}")
        hashes[rel] = compute_manifest_hash(full)
    return hashes


def _project_relative_path(manifest_path: Path, project_root: Path) -> str:
    full = Path(manifest_path).resolve()
    try:
        return full.relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        return str(manifest_path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_valid_red_evidence(commands: tuple[RedPhaseCommandEvidence, ...]) -> bool:
    return any(command.classification == "red" for command in commands) and not any(
        command.classification == "invalid" for command in commands
    )


def _combined_output_tail(stdout: str, stderr: str, max_lines: int = 20) -> str:
    combined = "\n".join(part for part in (stdout, stderr) if part)
    return "\n".join(combined.splitlines()[-max_lines:])


def _load_manifest_contract_for_lock(lock: PlanLock, lock_path: Path) -> dict | None:
    manifest_path = _project_root_from_lock_path(lock_path) / lock.manifest_path
    if not manifest_path.exists():
        return None
    return _manifest_contract(load_manifest(manifest_path))


def _project_root_from_lock_path(lock_path: Path) -> Path:
    try:
        return lock_path.parents[2]
    except IndexError:
        return Path(".")


def _manifest_contract(manifest: Manifest) -> dict:
    return {
        "artifacts": sorted(_artifact_declarations(manifest)),
        "test_files": sorted(_behavioral_test_paths(manifest)),
    }


def _artifact_declarations(manifest: Manifest) -> set[str]:
    declarations: set[str] = set()
    for file_spec in manifest.all_file_specs:
        for artifact in file_spec.artifacts:
            prefix = f"{file_spec.path}:{artifact.merge_key()}"
            declarations.add(prefix)
            declarations.add(f"{prefix}:kind={artifact.kind.value}")
            if artifact.of is not None:
                declarations.add(f"{prefix}:of={artifact.of}")
            if artifact.returns is not None:
                declarations.add(f"{prefix}:returns={artifact.returns}")
            if artifact.type_annotation is not None:
                declarations.add(f"{prefix}:type={artifact.type_annotation}")
            if artifact.is_async:
                declarations.add(f"{prefix}:async=true")
            for arg in artifact.args:
                declarations.add(
                    f"{prefix}:arg={arg.name}:type={arg.type}:default={arg.default}"
                )
            for raised in artifact.raises:
                declarations.add(f"{prefix}:raises={raised}")
            for base in artifact.bases:
                declarations.add(f"{prefix}:base={base}")
            for type_parameter in artifact.type_parameters:
                declarations.add(f"{prefix}:type_parameter={type_parameter}")
    return declarations


def _load_lock_or_error(
    lock_path: Path, project_root: Path
) -> PlanLock | ValidationError:
    try:
        return PlanLock.load(lock_path)
    except (FileNotFoundError, _PlanLockLoadError) as exc:
        return ValidationError(
            code=ErrorCode.PLAN_LOCK_UNREADABLE,
            message=f"PLAN_LOCK_UNREADABLE: lock cannot be loaded: {exc}",
            location=Location(file=_project_relative_path(lock_path, project_root)),
        )


def _test_hash_errors(
    lock: PlanLock,
    manifest: Manifest,
    project_root: Path,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    current_test_paths = set(_behavioral_test_paths(manifest))
    if set(lock.test_hashes) - current_test_paths:
        return []

    for rel, locked_hash in lock.test_hashes.items():
        full = project_root / rel
        current_hash = compute_manifest_hash(full) if full.exists() else None
        if current_hash != locked_hash:
            errors.append(
                _lock_error(
                    ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK,
                    manifest,
                    project_root,
                    detail=f"behavioral test changed after lock: {rel}",
                )
            )
    return errors


def _contract_weakening_detail(
    lock_path: Path,
    lock: PlanLock,
    manifest: Manifest,
) -> str | None:
    locked_tests = set(lock.test_hashes)
    current_contract = _manifest_contract(manifest)
    if locked_tests - set(current_contract["test_files"]):
        return "behavioral test entries shrank"

    locked_contract = _load_locked_contract(lock_path)
    if not locked_contract:
        current_hash = compute_manifest_hash(Path(manifest.source_path))
        if current_hash == lock.manifest_hash:
            return None
        return (
            "legacy plan lock lacks a manifest contract snapshot; "
            "revise the lock after reviewing the manifest change"
        )
    locked_artifacts = set(locked_contract.get("artifacts", ()))
    current_artifacts = set(current_contract["artifacts"])
    if locked_artifacts - current_artifacts:
        return "declared artifacts shrank"
    return None


def _load_locked_contract(lock_path: Path) -> dict | None:
    try:
        data = json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    contract = data.get("_manifest_contract")
    return contract if isinstance(contract, dict) else None


def _red_evidence_is_valid(evidence: dict) -> bool:
    if not isinstance(evidence, dict) or evidence.get("red") is not True:
        return False
    commands = evidence.get("commands")
    if not isinstance(commands, list):
        return False
    classifications = [
        command.get("classification")
        for command in commands
        if isinstance(command, dict)
    ]
    return "red" in classifications and "invalid" not in classifications


def _plan_lock_files(project_root: Path) -> tuple[Path, ...]:
    lock_dir = project_root / ".maid" / "plan-locks"
    if not lock_dir.exists():
        return ()
    return tuple(sorted(lock_dir.glob("*.lock.json")))


def _lock_error(
    code: ErrorCode,
    manifest: Manifest,
    project_root: Path,
    *,
    detail: str | None = None,
) -> ValidationError:
    messages = {
        ErrorCode.PLAN_LOCK_MISSING: "PLAN_LOCK_MISSING: manifest has no plan lock",
        ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK: (
            "BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK: behavioral test hash changed"
        ),
        ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK: (
            "MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK: manifest contract shrank"
        ),
        ErrorCode.PLAN_LOCK_STALE: "PLAN_LOCK_STALE: lock references a missing manifest",
        ErrorCode.RED_PHASE_EVIDENCE_MISSING: (
            "RED_PHASE_EVIDENCE_MISSING: plan lock has no red-phase evidence"
        ),
        ErrorCode.RED_PHASE_EVIDENCE_INVALID: (
            "RED_PHASE_EVIDENCE_INVALID: red-phase evidence is not valid red"
        ),
        ErrorCode.PLAN_LOCK_UNREADABLE: (
            "PLAN_LOCK_UNREADABLE: lock exists but cannot be loaded"
        ),
    }
    message = messages[code]
    if detail:
        message = f"{message} ({detail})"
    return ValidationError(
        code=code,
        message=message,
        location=Location(file=_manifest_location(manifest, project_root)),
    )


def _manifest_location(manifest: Manifest, project_root: Path) -> str:
    path = Path(manifest.source_path)
    return _project_relative_path(path, project_root)
