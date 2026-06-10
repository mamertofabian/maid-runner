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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maid_runner.core._test_command_execution import _run_test_command
from maid_runner.core.manifest import _is_test_file, load_manifest, slug_from_path
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
