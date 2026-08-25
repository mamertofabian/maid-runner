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

import ast
import hashlib
import json
import shlex
import subprocess
import tempfile
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from maid_runner.core._command_integrity_test_discovery import (
    find_command_integrity_test_files,
    is_command_integrity_test_file,
)
from maid_runner.core._test_command_execution import _run_test_command
from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import _manifest_to_dict, load_manifest, slug_from_path
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.supersession_audit import compute_manifest_hash
from maid_runner.core.types import AgentProvenance, Manifest

_CONTRACT_HASH_PREFIX = "sha256-contract:"
_PYAST_V2_HASH_PREFIX = "sha256-pyast:v2:"
_PYAST_HASH_PREFIX = "sha256-pyast:"
_BYTE_HASH_PREFIX = "sha256:"
_DELETED_FILE_FINGERPRINT = "<deleted>"
_CLEAN_FILE_FINGERPRINT = "<clean>"
_VALIDATE_AND_ACCEPTANCE_SOURCE = "validate_and_acceptance"


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
class ContractDelta:
    """Deterministic set-difference between two locked manifest contracts."""

    artifacts_added: tuple[str, ...] = ()
    artifacts_removed: tuple[str, ...] = ()
    files_added: tuple[str, ...] = ()
    files_removed: tuple[str, ...] = ()
    validate_commands_added: tuple[str, ...] = ()
    validate_commands_removed: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanLockDependent:
    """One active manifest lock that pins a queried behavioral test."""

    manifest_slug: str
    manifest_path: str
    lock_path: str
    test_path: str
    test_hash_matches: bool
    recovery_command: str


@dataclass(frozen=True)
class PlanLockRevision:
    """One immutable revision history entry."""

    prior_manifest_hash: str
    prior_test_hashes: dict[str, str]
    revised_at: str
    reason: str
    agent: Optional[AgentProvenance] = None
    contract_delta: Optional[ContractDelta] = None


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
    command_source: str | None = None

    def to_payload(self) -> dict:
        """Serialize the evidence into the JSON payload stored in a plan lock."""
        payload = {
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
        if self.command_source is not None:
            payload["command_source"] = self.command_source
        return payload


@dataclass(frozen=True)
class LegacyBaselineEvidence:
    """Audited green baseline for a manifest that predates plan locks."""

    reason: str
    baseline_commit: str
    baseline_manifest_hash: str
    contract_delta: ContractDelta
    commands: tuple[RedPhaseCommandEvidence, ...]
    captured_at: str
    baseline_manifest_source: str = "head"

    def to_payload(self) -> dict:
        """Serialize legacy provenance without claiming historical red evidence."""
        return {
            "kind": "legacy_baseline",
            "green": True,
            "reason": self.reason,
            "baseline_commit": self.baseline_commit,
            "baseline_manifest_hash": self.baseline_manifest_hash,
            "baseline_manifest_source": self.baseline_manifest_source,
            "contract_delta": _contract_delta_to_payload(self.contract_delta),
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
    agent: Optional[AgentProvenance] = None
    legacy_baseline: Optional[dict] = None

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
                    agent=_agent_from_payload(item.get("agent")),
                    contract_delta=_contract_delta_from_payload(
                        item.get("contract_delta")
                    ),
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
                legacy_baseline=data.get("legacy_baseline"),
                agent=_agent_from_payload(data.get("agent")),
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
                    "agent": _agent_to_payload(r.agent),
                    "contract_delta": _contract_delta_to_payload(r.contract_delta),
                }
                for r in self.revisions
            ],
            "red_evidence": self.red_evidence,
            "legacy_baseline": self.legacy_baseline,
            "agent": _agent_to_payload(self.agent),
        }
        contract = _load_manifest_contract_for_lock(self, p)
        if contract is not None:
            payload["_manifest_contract"] = contract
        p.write_text(json.dumps(payload, indent=2))


def default_plan_lock_path(project_root: Path, manifest_slug: str) -> Path:
    """Return `.maid/plan-locks/<manifest-slug>.lock.json` under the root."""
    return Path(project_root) / ".maid" / "plan-locks" / f"{manifest_slug}.lock.json"


def find_plan_lock_dependents(
    chain: ManifestChain,
    project_root: Path,
    test_path: str | Path,
) -> tuple[PlanLockDependent, ...]:
    """Return active readable locks that pin one in-project behavioral test."""
    root = Path(project_root).resolve()
    requested = Path(test_path)
    full_test_path = requested if requested.is_absolute() else root / requested
    try:
        relative_test_path = full_test_path.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"Plan-lock dependency path is outside project root: {test_path}"
        ) from exc

    dependents: list[PlanLockDependent] = []
    for manifest in chain.active_manifests():
        lock_path = default_plan_lock_path(root, manifest.slug)
        if not lock_path.exists():
            continue
        lock = PlanLock.load(lock_path)
        locked_hash = lock.test_hashes.get(relative_test_path)
        if locked_hash is None:
            continue
        manifest_path = _project_relative_path(Path(manifest.source_path), root)
        relative_lock_path = _project_relative_path(lock_path, root)
        project_root_option = ""
        recovery_manifest_path = manifest_path
        if root != Path.cwd().resolve():
            project_root_option = f"--project-root {shlex.quote(str(root))} "
            recovery_manifest_path = str(root / manifest_path)
        recovery_command = (
            f"maid plan revise {shlex.quote(recovery_manifest_path)} "
            f"{project_root_option}"
            '--reason "accept approved shared-test change" '
            "--preserve-red-evidence"
        )
        dependents.append(
            PlanLockDependent(
                manifest_slug=manifest.slug,
                manifest_path=manifest_path,
                lock_path=relative_lock_path,
                test_path=relative_test_path,
                test_hash_matches=test_hash_matches(locked_hash, full_test_path),
                recovery_command=recovery_command,
            )
        )
    return tuple(dependents)


def compute_manifest_contract_hash(manifest_path: Path) -> str:
    """Return a sha256-contract digest over the parsed manifest minus outcome.

    Parses the manifest YAML, drops only the top-level ``outcome`` key, and
    hashes the canonical JSON serialization of the remainder. Unparseable YAML
    raises (fail loud); there is no byte-hash fallback.
    """
    data = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(
            f"manifest must parse to a mapping for contract hashing: {manifest_path}"
        )
    contract = dict(data)
    contract.pop("outcome", None)
    normalized = _normalize_manifest_contract_value(
        contract,
        manifest_path=Path(manifest_path),
        location="<root>",
    )
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_CONTRACT_HASH_PREFIX}{digest}"


def _normalize_manifest_contract_value(
    value: object,
    *,
    manifest_path: Path,
    location: str,
) -> object:
    """Normalize the bounded YAML-native values accepted by contract hashing."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return [
            _normalize_manifest_contract_value(
                item,
                manifest_path=manifest_path,
                location=f"{location}[{index}]",
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            key = _normalize_manifest_contract_key(
                raw_key,
                manifest_path=manifest_path,
                location=location,
            )
            child_location = key if location == "<root>" else f"{location}.{key}"
            if key in normalized:
                raise ValueError(
                    f"Cannot hash manifest {manifest_path}: mapping keys collide "
                    f"after normalization at {child_location}"
                )
            normalized[key] = _normalize_manifest_contract_value(
                raw_value,
                manifest_path=manifest_path,
                location=child_location,
            )
        return normalized
    raise ValueError(
        f"Cannot hash manifest {manifest_path}: unsupported value at {location} "
        f"({type(value).__name__})"
    )


def _normalize_manifest_contract_key(
    key: object,
    *,
    manifest_path: Path,
    location: str,
) -> str:
    if isinstance(key, str):
        return key
    if isinstance(key, datetime):
        return key.isoformat()
    if isinstance(key, date):
        return key.isoformat()
    if key is None:
        return "null"
    if key is True:
        return "true"
    if key is False:
        return "false"
    if isinstance(key, (int, float)):
        return str(key)
    raise ValueError(
        f"Cannot hash manifest {manifest_path}: unsupported mapping key at "
        f"{location} ({type(key).__name__})"
    )


def manifest_hash_matches(lock_hash: str, manifest_path: Path) -> bool:
    """Compare a stored lock hash to the current manifest by prefix dispatch.

    ``sha256-contract:`` values use the contract-scoped hash; legacy ``sha256:``
    values use the raw byte hash. Unknown prefixes and missing files return
    False (fail closed).
    """
    path = Path(manifest_path)
    if not path.is_file():
        return False
    if lock_hash.startswith(_CONTRACT_HASH_PREFIX):
        return lock_hash == compute_manifest_contract_hash(path)
    if lock_hash.startswith(_BYTE_HASH_PREFIX):
        return lock_hash == compute_manifest_hash(path)
    return False


def compute_behavioral_test_hash(path: Path) -> str:
    """Return a formatting-aware hash for a behavioral test file.

    Python (``.py``) files use the versioned, cross-interpreter AST v2
    payload so whitespace- and comment-only edits stay digest-stable without
    inheriting version-added empty ``ast`` fields. Other suffixes keep the
    legacy byte hash. Syntax, decode, and canonicalization errors raise (fail
    loud); there is no silent byte-hash fallback for ``.py`` paths.
    """
    file_path = Path(path)
    if file_path.suffix == ".py":
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
        canonical = json.dumps(
            _canonical_python_ast(tree),
            ensure_ascii=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return f"{_PYAST_V2_HASH_PREFIX}{digest}"
    return compute_manifest_hash(file_path)


def _canonical_python_ast(value: object) -> object:
    """Return a stable semantic payload for a supported Python AST value."""
    if isinstance(value, ast.AST):
        fields: list[list[object]] = []
        for name, child in ast.iter_fields(value):
            normalized = _canonical_python_ast(child)
            if normalized is None or normalized == []:
                continue
            fields.append([name, normalized])
        return [type(value).__name__, fields]
    if isinstance(value, list):
        return [_canonical_python_ast(item) for item in value]
    if value is Ellipsis:
        return ["ellipsis"]
    if isinstance(value, str):
        return ["str", value.encode("utf-8", "surrogatepass").hex()]
    if isinstance(value, bytes):
        return ["bytes", value.hex()]
    if isinstance(value, complex):
        return ["complex", repr(value)]
    if isinstance(value, float):
        return ["float", repr(value)]
    if value is None or isinstance(value, (bool, int)):
        return value
    raise ValueError(
        f"Cannot hash Python behavioral test: unsupported AST value "
        f"{type(value).__name__}"
    )


def _compute_legacy_pyast_hash(file_path: Path) -> str:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    canonical = ast.dump(tree, annotate_fields=True, include_attributes=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_PYAST_HASH_PREFIX}{digest}"


def test_hash_matches(lock_hash: str, path: Path) -> bool:
    """Compare a stored behavioral-test hash to the current file by prefix.

    ``sha256-pyast:v2:`` uses the portable AST payload, historical
    ``sha256-pyast:`` uses the interpreter-shaped v1 AST dump, and legacy
    ``sha256:`` values use the raw byte hash. Unknown prefixes and missing
    files return False (fail closed).
    """
    file_path = Path(path)
    if not file_path.is_file():
        return False
    if lock_hash.startswith(_PYAST_V2_HASH_PREFIX):
        return lock_hash == compute_behavioral_test_hash(file_path)
    if lock_hash.startswith(_PYAST_HASH_PREFIX):
        return lock_hash == _compute_legacy_pyast_hash(file_path)
    if lock_hash.startswith(_BYTE_HASH_PREFIX):
        return lock_hash == compute_manifest_hash(file_path)
    return False


def create_plan_lock(
    manifest_path: Path,
    project_root: Path,
    agent: Optional[AgentProvenance] = None,
) -> PlanLock:
    """Build a revision-1 lock over the manifest and its behavioral tests."""
    manifest = load_manifest(manifest_path)
    root = Path(project_root)
    return PlanLock(
        manifest_path=_project_relative_path(manifest_path, root),
        manifest_hash=compute_manifest_contract_hash(Path(manifest_path)),
        test_hashes=_hash_test_files(root, _behavioral_test_paths(manifest, root)),
        created_at=_utc_now(),
        agent=agent,
    )


def revise_plan_lock(
    existing: PlanLock,
    manifest_path: Path,
    project_root: Path,
    reason: str,
    agent: Optional[AgentProvenance] = None,
    prior_contract: Optional[dict] = None,
    preserve_legacy_baseline: bool = True,
) -> PlanLock:
    """Re-lock with current hashes, appending the prior hashes to history."""
    if not reason or not reason.strip():
        raise ValueError("Plan-lock revision requires a non-empty reason")
    fresh = create_plan_lock(manifest_path, project_root, agent=existing.agent)
    new_contract = _manifest_contract(load_manifest(manifest_path), project_root)
    entry = PlanLockRevision(
        prior_manifest_hash=existing.manifest_hash,
        prior_test_hashes=dict(existing.test_hashes),
        revised_at=_utc_now(),
        reason=reason,
        agent=agent,
        contract_delta=(
            compute_contract_delta(prior_contract, new_contract)
            if prior_contract is not None
            else None
        ),
    )
    legacy_baseline = None
    if preserve_legacy_baseline and existing.legacy_baseline is not None:
        if existing.red_evidence is not None:
            raise ValueError(
                "Cannot preserve a legacy baseline from a lock that also contains "
                "red evidence"
            )
        lock_path = default_plan_lock_path(
            Path(project_root), load_manifest(manifest_path).slug
        )
        if not _legacy_baseline_is_valid(existing.legacy_baseline, lock_path):
            raise ValueError("Cannot preserve an invalid legacy baseline")
        evidence_commands = existing.legacy_baseline.get("commands")
        current_commands = new_contract.get("validate_commands")
        if not isinstance(evidence_commands, list) or not isinstance(
            current_commands, list
        ):
            raise ValueError("Cannot preserve a legacy baseline without command data")
        command_strings = [
            command.get("command")
            for command in evidence_commands
            if isinstance(command, dict)
        ]
        if Counter(command_strings) != Counter(current_commands):
            raise ValueError(
                "Cannot preserve legacy baseline because validate commands changed"
            )
        legacy_baseline = existing.legacy_baseline
    return PlanLock(
        manifest_path=fresh.manifest_path,
        manifest_hash=fresh.manifest_hash,
        test_hashes=fresh.test_hashes,
        created_at=existing.created_at,
        revision=existing.revision + 1,
        revisions=existing.revisions + (entry,),
        red_evidence=None,
        agent=existing.agent,
        legacy_baseline=legacy_baseline,
    )


def revision_preserves_red_evidence(
    existing: PlanLock,
    manifest_path: Path,
    project_root: Path,
    prior_contract: dict | None,
) -> bool:
    """Return whether plain revise may carry existing red evidence forward.

    All three parts of the contract-preserving rule must hold: empty contract
    delta, locked behavioral test bytes still match with no newly discovered
    test files, and the existing evidence payload remains valid. Pre-084 locks
    without a persisted contract snapshot fail closed.
    """
    if prior_contract is None:
        return False
    if existing.red_evidence is not None and existing.legacy_baseline is not None:
        return False
    root = Path(project_root)
    manifest = load_manifest(manifest_path)
    preserves_red = _red_evidence_dict_is_valid(existing.red_evidence)
    preserves_test_only_green = _test_only_green_payload_is_valid(existing.red_evidence)
    preserves_legacy_baseline = _legacy_baseline_is_valid(
        existing.legacy_baseline,
        default_plan_lock_path(root, manifest.slug),
    )
    if (
        not preserves_red
        and not preserves_test_only_green
        and not preserves_legacy_baseline
    ):
        return False
    if preserves_test_only_green:
        from maid_runner.core._file_discovery import is_test_file

        if any(
            not is_test_file(path.replace("\\", "/"))
            for path in manifest.all_writable_paths
        ):
            return False
    new_contract = _manifest_contract(manifest, root)
    if compute_contract_delta(prior_contract, new_contract) != ContractDelta():
        return False
    if preserves_red or preserves_test_only_green:
        evidence_commands = existing.red_evidence.get("commands")
        prior_command_groups = _red_evidence_contract_command_groups(
            prior_contract, existing.red_evidence
        )
        new_command_groups = _red_evidence_contract_command_groups(
            new_contract, existing.red_evidence
        )
        if (
            not isinstance(evidence_commands, list)
            or prior_command_groups is None
            or new_command_groups is None
        ):
            return False
        evidence_command_strings = [
            command.get("command")
            for command in evidence_commands
            if isinstance(command, dict)
        ]
        prior_validate, prior_acceptance = prior_command_groups
        new_validate, new_acceptance = new_command_groups
        validate_count = len(prior_validate)
        evidence_validate = evidence_command_strings[:validate_count]
        evidence_acceptance = evidence_command_strings[validate_count:]
        if (
            len(evidence_command_strings) != len(evidence_commands)
            or len(evidence_command_strings)
            != len(prior_validate) + len(prior_acceptance)
            or Counter(evidence_validate) != Counter(prior_validate)
            or Counter(prior_validate) != Counter(new_validate)
            or Counter(evidence_acceptance) != Counter(prior_acceptance)
            or Counter(prior_acceptance) != Counter(new_acceptance)
        ):
            return False

    current_tests = set(_behavioral_test_paths(manifest, root))
    locked_tests = set(existing.test_hashes)
    if current_tests - locked_tests:
        return False

    for rel, locked_hash in existing.test_hashes.items():
        full = root / rel
        if not full.is_file() or not test_hash_matches(locked_hash, full):
            return False
    return True


def compute_contract_delta(prior_contract: dict, new_contract: dict) -> ContractDelta:
    """Return sorted set differences between two persisted contract payloads."""
    prior_artifacts = _contract_string_set(prior_contract, "artifacts")
    new_artifacts = _contract_string_set(new_contract, "artifacts")
    prior_files = _contract_file_entries(prior_contract)
    new_files = _contract_file_entries(new_contract)
    prior_validate = _contract_string_set(prior_contract, "validate_commands")
    new_validate = _contract_string_set(new_contract, "validate_commands")
    return ContractDelta(
        artifacts_added=tuple(sorted(new_artifacts - prior_artifacts)),
        artifacts_removed=tuple(sorted(prior_artifacts - new_artifacts)),
        files_added=tuple(sorted(new_files - prior_files)),
        files_removed=tuple(sorted(prior_files - new_files)),
        validate_commands_added=tuple(sorted(new_validate - prior_validate)),
        validate_commands_removed=tuple(sorted(prior_validate - new_validate)),
    )


def _agent_to_payload(agent: AgentProvenance | None) -> dict | None:
    if agent is None:
        return None
    payload = {"model": agent.model}
    if agent.reasoning_effort is not None:
        payload["reasoning_effort"] = agent.reasoning_effort
    if agent.provider is not None:
        payload["provider"] = agent.provider
    if agent.client is not None:
        payload["client"] = agent.client
    if agent.skills:
        payload["skills"] = list(agent.skills)
    if agent.instructions_fingerprint is not None:
        payload["instructions_fingerprint"] = agent.instructions_fingerprint
    if agent.source is not None:
        payload["source"] = agent.source
    return payload


def _agent_from_payload(value: object) -> AgentProvenance | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("agent must be an object or null")
    model = value.get("model")
    if not isinstance(model, str) or not model.strip():
        raise TypeError("agent.model must be a non-empty string")
    provider = _optional_agent_string(value, "provider")
    reasoning_effort = _optional_agent_string(value, "reasoning_effort")
    if reasoning_effort is not None and not reasoning_effort.strip():
        raise TypeError("agent.reasoning_effort must be a non-empty string")
    client = _optional_agent_string(value, "client")
    instructions_fingerprint = _optional_agent_string(value, "instructions_fingerprint")
    source = _optional_agent_string(value, "source")
    raw_skills = value.get("skills", [])
    if not isinstance(raw_skills, list) or not all(
        isinstance(item, str) for item in raw_skills
    ):
        raise TypeError("agent.skills must be an array of strings")
    return AgentProvenance(
        model=model,
        reasoning_effort=reasoning_effort,
        provider=provider,
        client=client,
        skills=tuple(raw_skills),
        instructions_fingerprint=instructions_fingerprint,
        source=source,
    )


def _contract_delta_to_payload(delta: ContractDelta | None) -> dict | None:
    if delta is None:
        return None
    return {
        "artifacts_added": list(delta.artifacts_added),
        "artifacts_removed": list(delta.artifacts_removed),
        "files_added": list(delta.files_added),
        "files_removed": list(delta.files_removed),
        "validate_commands_added": list(delta.validate_commands_added),
        "validate_commands_removed": list(delta.validate_commands_removed),
    }


def _contract_delta_from_payload(value: object) -> ContractDelta | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError("contract_delta must be an object or null")
    return ContractDelta(
        artifacts_added=_contract_delta_tuple(value, "artifacts_added"),
        artifacts_removed=_contract_delta_tuple(value, "artifacts_removed"),
        files_added=_contract_delta_tuple(value, "files_added"),
        files_removed=_contract_delta_tuple(value, "files_removed"),
        validate_commands_added=_contract_delta_tuple(value, "validate_commands_added"),
        validate_commands_removed=_contract_delta_tuple(
            value, "validate_commands_removed"
        ),
    )


def _contract_delta_tuple(value: dict, key: str) -> tuple[str, ...]:
    raw = value.get(key)
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise TypeError(f"contract_delta.{key} must be an array of strings")
    return tuple(raw)


def _optional_agent_string(value: dict, key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"agent.{key} must be a string or null")
    return raw


def classify_red_exit_code(exit_code: int) -> str:
    """Classify red-phase evidence by process exit code only."""
    if exit_code == 1:
        return "red"
    if exit_code == 0:
        return "not_red"
    return "invalid"


def capture_red_phase_evidence(
    manifest_path: Path,
    project_root: Path,
    command_timeout_seconds: int = 300,
) -> RedPhaseEvidence:
    """Run fast validate commands, then acceptance commands when needed for red."""
    if command_timeout_seconds < 1:
        raise ValueError("Command timeout must be a positive integer")

    manifest = load_manifest(manifest_path)
    root = Path(project_root)
    slug = slug_from_path(manifest_path)
    commands: list[RedPhaseCommandEvidence] = []
    for command in manifest.validate_commands:
        result = _run_test_command(
            command,
            cwd=root,
            timeout=command_timeout_seconds,
            manifest_slug=slug,
        )
        commands.append(
            RedPhaseCommandEvidence(
                command=shlex.join(command),
                exit_code=result.exit_code,
                output_tail=_combined_output_tail(result.stdout, result.stderr),
                classification=classify_red_exit_code(result.exit_code),
            )
        )
    validate_command_tuple = tuple(commands)
    if (
        _has_valid_red_evidence(validate_command_tuple)
        or any(command.classification != "not_red" for command in commands)
        or manifest.acceptance is None
    ):
        return RedPhaseEvidence(
            red=_has_valid_red_evidence(validate_command_tuple),
            commands=validate_command_tuple,
            captured_at=_utc_now(),
        )

    for command in manifest.acceptance.tests:
        result = _run_test_command(
            command,
            cwd=root,
            timeout=command_timeout_seconds,
            manifest_slug=slug,
        )
        commands.append(
            RedPhaseCommandEvidence(
                command=shlex.join(command),
                exit_code=result.exit_code,
                output_tail=_combined_output_tail(result.stdout, result.stderr),
                classification=classify_red_exit_code(result.exit_code),
            )
        )
    return RedPhaseEvidence(
        red=_has_valid_red_evidence(tuple(commands)),
        commands=tuple(commands),
        captured_at=_utc_now(),
        command_source=_VALIDATE_AND_ACCEPTANCE_SOURCE,
    )


def capture_legacy_baseline_evidence(
    manifest_path: Path,
    project_root: Path,
    reason: str,
    command_timeout_seconds: int = 300,
) -> LegacyBaselineEvidence:
    """Capture a green, contract-stable baseline for a legacy manifest."""
    if command_timeout_seconds < 1:
        raise ValueError("Command timeout must be a positive integer")
    if not reason or not reason.strip():
        raise ValueError("Legacy-baseline migration requires a non-empty reason")

    root = Path(project_root).resolve()
    current_path = Path(manifest_path).resolve()
    manifest_rel = _project_relative_path(current_path, root)
    baseline_commit = _git_text(root, "rev-parse", "HEAD").strip()
    # git show resolves paths from the repository root regardless of cwd, so the
    # blob must be addressed by its repo-root path even though every comparison
    # below is project-relative.
    repository_manifest_path = f"{_git_prefix(root)}{manifest_rel}"
    head_manifest_spec = f"HEAD:{repository_manifest_path}"
    if _git_object_exists(root, head_manifest_spec):
        baseline_bytes = _git_bytes(root, "show", head_manifest_spec)
        baseline_manifest_source = "head"
    else:
        index_manifest_spec = f":{repository_manifest_path}"
        if not _git_object_exists(root, index_manifest_spec):
            raise ValueError(
                "A legacy-baseline manifest absent from HEAD must be staged in "
                "the Git index"
            )
        baseline_bytes = _git_bytes(root, "show", index_manifest_spec)
        if current_path.read_bytes() != baseline_bytes:
            raise ValueError(
                "A legacy-baseline manifest absent from HEAD must match the "
                "staged index blob exactly"
            )
        baseline_manifest_source = "index"
    dirty_paths = _git_changed_paths(root)
    if dirty_paths - {manifest_rel}:
        raise ValueError(
            "Legacy-baseline migration refuses dirty path(s) other than the "
            f"manifest: {', '.join(sorted(dirty_paths - {manifest_rel}))}"
        )

    current_manifest = load_manifest(current_path)
    current_contract = _manifest_contract(current_manifest, root)
    if baseline_manifest_source == "index":
        _require_first_commit_contract_at_head(current_manifest, current_contract, root)
    with tempfile.TemporaryDirectory(prefix="maid-legacy-baseline-") as temp_dir:
        baseline_path = Path(temp_dir) / current_path.name
        baseline_path.write_bytes(baseline_bytes)
        baseline_manifest = load_manifest(baseline_path)
        baseline_contract = _manifest_contract(baseline_manifest, root)
        baseline_hash = compute_manifest_hash(baseline_path).removeprefix("sha256:")

    delta = compute_contract_delta(baseline_contract, current_contract)
    file_contract_changed = baseline_contract.get(
        "file_contract"
    ) != current_contract.get("file_contract")
    if file_contract_changed or any(
        (
            delta.artifacts_added,
            delta.artifacts_removed,
            delta.files_added,
            delta.files_removed,
        )
    ):
        raise ValueError(
            "Legacy-baseline migration permits validation metadata changes only; "
            "declared artifacts and file sections must match HEAD"
        )

    baseline_tests = set(baseline_contract.get("test_files", ()))
    current_tests = set(current_contract.get("test_files", ()))
    if baseline_tests - current_tests:
        raise ValueError(
            "Legacy-baseline migration cannot remove behavioral-test coverage"
        )
    if not _validate_commands_are_retained_or_preserved_in_acceptance(
        baseline_contract.get("validate_commands"),
        current_contract.get("validate_commands"),
        current_tests,
        current_manifest,
    ):
        raise ValueError(
            "Legacy-baseline migration may only retain validate commands, append "
            "discovered behavioral-test targets to them, move exact commands to "
            "acceptance.tests, or add new commands"
        )

    before_hashes = _contract_file_hashes(current_path, current_manifest, root)
    before_dirty_fingerprints = _git_changed_path_fingerprints(root)
    commands: list[RedPhaseCommandEvidence] = []
    for command in current_manifest.validate_commands:
        result = _run_test_command(
            command,
            cwd=root,
            timeout=command_timeout_seconds,
            manifest_slug=current_manifest.slug,
        )
        evidence = RedPhaseCommandEvidence(
            command=shlex.join(command),
            exit_code=result.exit_code,
            output_tail=_combined_output_tail(result.stdout, result.stderr),
            classification=classify_red_exit_code(result.exit_code),
        )
        commands.append(evidence)
        if result.exit_code != 0:
            raise ValueError(
                "Legacy-baseline migration requires every validate command to "
                f"pass; {evidence.command!r} exited {result.exit_code}"
            )

    after_hashes = _contract_file_hashes(current_path, current_manifest, root)
    if after_hashes != before_hashes:
        changed = sorted(
            path
            for path in set(before_hashes) | set(after_hashes)
            if before_hashes.get(path) != after_hashes.get(path)
        )
        raise ValueError(
            "Legacy-baseline validation mutated contract file(s): " + ", ".join(changed)
        )
    post_run_dirty = _git_changed_paths(root)
    post_run_dirty_fingerprints = _git_changed_path_fingerprints(root)
    mutated_dirty_paths = sorted(
        path
        for path in set(before_dirty_fingerprints) | set(post_run_dirty_fingerprints)
        if before_dirty_fingerprints.get(path, _CLEAN_FILE_FINGERPRINT)
        != post_run_dirty_fingerprints.get(path, _CLEAN_FILE_FINGERPRINT)
    )
    if mutated_dirty_paths:
        raise ValueError(
            "Legacy-baseline validation created or changed unrelated path(s): "
            + ", ".join(mutated_dirty_paths)
        )
    if post_run_dirty - {manifest_rel}:
        raise ValueError(
            "Legacy-baseline validation created or changed unrelated path(s): "
            + ", ".join(sorted(post_run_dirty - {manifest_rel}))
        )

    return LegacyBaselineEvidence(
        reason=reason.strip(),
        baseline_commit=baseline_commit,
        baseline_manifest_hash=baseline_hash,
        contract_delta=delta,
        commands=tuple(commands),
        captured_at=_utc_now(),
        baseline_manifest_source=baseline_manifest_source,
    )


def enforce_plan_locks(
    chain: ManifestChain,
    project_root: Path,
    require_plan_lock: bool,
    require_red_evidence: bool,
    *,
    changed_paths: Collection[str] | None = None,
    plan_lock_scope: str = "repository",
) -> "tuple[ValidationError, ...]":
    """Evaluate active manifests against their plan locks."""
    if not require_plan_lock and not require_red_evidence:
        return ()
    if plan_lock_scope not in {"repository", "task"}:
        raise ValueError("plan_lock_scope must be either 'repository' or 'task'")

    root = Path(project_root)
    changed_path_set = _normalize_changed_paths(changed_paths)
    errors: list[ValidationError] = []
    loaded_lock_paths: set[Path] = set()

    for manifest in chain.active_manifests():
        lock_path = default_plan_lock_path(root, manifest.slug)
        loaded_lock_paths.add(lock_path)
        requirement_in_scope = _manifest_in_changed_paths(
            manifest, root, changed_path_set
        )
        if not lock_path.exists():
            if requirement_in_scope and require_plan_lock:
                errors.append(
                    _lock_error(
                        ErrorCode.PLAN_LOCK_MISSING,
                        manifest,
                        root,
                        detail=f"missing lock: {_project_relative_path(lock_path, root)}",
                    )
                )
            if requirement_in_scope and require_red_evidence:
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
            if (
                plan_lock_scope == "task"
                and changed_path_set is not None
                and not _manifest_in_task_paths(manifest, root, changed_path_set)
            ):
                continue
            errors.append(lock)
            continue

        if (
            plan_lock_scope == "task"
            and changed_path_set is not None
            and not _manifest_in_task_paths(
                manifest,
                root,
                changed_path_set,
                lock_path=lock_path,
                lock=lock,
            )
        ):
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

        errors.extend(_test_hash_errors(lock_path, lock, manifest, root))
        weakening_detail = _contract_weakening_detail(lock_path, lock, manifest, root)
        if weakening_detail is not None:
            errors.append(
                _lock_error(
                    ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK,
                    manifest,
                    root,
                    detail=weakening_detail,
                )
            )
        mismatch_detail = _red_evidence_command_mismatch_detail(lock_path, lock)
        if mismatch_detail is not None:
            errors.append(
                _lock_error(
                    ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH,
                    manifest,
                    root,
                    detail=mismatch_detail,
                )
            )

        if requirement_in_scope and require_red_evidence:
            if lock.red_evidence is None and lock.legacy_baseline is None:
                errors.append(
                    _lock_error(ErrorCode.RED_PHASE_EVIDENCE_MISSING, manifest, root)
                )
            elif (
                lock.red_evidence is not None
                and _red_evidence_is_valid(lock.red_evidence)
                and lock.legacy_baseline is None
            ):
                pass
            elif (
                lock.red_evidence is not None
                and _test_only_green_evidence_satisfies(lock.red_evidence, lock_path)
                and lock.legacy_baseline is None
            ):
                pass
            elif lock.red_evidence is None and _legacy_baseline_is_valid(
                lock.legacy_baseline, lock_path
            ):
                pass
            else:
                detail = (
                    _test_only_green_rejection_detail(lock.red_evidence, lock_path)
                    or "legacy baseline or red-phase evidence is invalid"
                )
                errors.append(
                    _lock_error(
                        ErrorCode.RED_PHASE_EVIDENCE_INVALID,
                        manifest,
                        root,
                        detail=detail,
                    )
                )

    if plan_lock_scope == "task" and changed_path_set is not None:
        return tuple(errors)

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


def _manifest_in_task_paths(
    manifest: Manifest,
    project_root: Path,
    changed_paths: set[str],
    *,
    lock_path: Path | None = None,
    lock: PlanLock | None = None,
) -> bool:
    task_contract_paths = {
        _manifest_location(manifest, project_root),
        *_behavioral_test_paths(manifest, project_root),
    }
    if lock_path is not None and lock is not None:
        historical_production_paths = _historical_production_test_paths(
            lock_path, lock, manifest, project_root
        )
        task_contract_paths.update(set(lock.test_hashes) - historical_production_paths)
    return not task_contract_paths.isdisjoint(changed_paths)


def _behavioral_test_paths(manifest: Manifest, project_root: Path) -> list[str]:
    """Collect semantically classified behavioral test files."""
    return find_command_integrity_test_files(manifest, Path(project_root))


def _hash_test_files(project_root: Path, paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for rel in paths:
        full = project_root / rel
        if not full.exists():
            raise FileNotFoundError(f"Behavioral test file not found: {full}")
        hashes[rel] = compute_behavioral_test_hash(full)
    return hashes


def _red_evidence_dict_is_valid(evidence: dict | None) -> bool:
    """Return whether a lock's red_evidence dict is valid red-phase evidence."""
    return isinstance(evidence, dict) and _red_evidence_is_valid(evidence)


def _current_test_hash_or_none(
    path: Path, *, lock_hash: str | None = None
) -> str | None:
    """Hash a regular file for status/display, returning None when unreadable."""
    try:
        if not path.is_file():
            return None
        if lock_hash is None or lock_hash.startswith(_PYAST_V2_HASH_PREFIX):
            return compute_behavioral_test_hash(path)
        if lock_hash.startswith(_PYAST_HASH_PREFIX):
            return _compute_legacy_pyast_hash(path)
        if lock_hash.startswith(_BYTE_HASH_PREFIX):
            return compute_manifest_hash(path)
        return compute_behavioral_test_hash(path)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _file_hash_or_none(path: Path) -> str | None:
    """Hash a regular file, returning None for missing or unreadable paths."""
    return _current_test_hash_or_none(path)


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
    project_root = _project_root_from_lock_path(lock_path)
    manifest_path = project_root / lock.manifest_path
    if not manifest_path.exists():
        return None
    return _manifest_contract(load_manifest(manifest_path), project_root)


def _project_root_from_lock_path(lock_path: Path) -> Path:
    try:
        return lock_path.parents[2]
    except IndexError:
        return Path(".")


def _manifest_contract(manifest: Manifest, project_root: Path) -> dict:
    serialized_manifest = _manifest_to_dict(manifest)
    return {
        "artifacts": sorted(_artifact_declarations(manifest)),
        "files": {
            "create": sorted(file_spec.path for file_spec in manifest.files_create),
            "edit": sorted(file_spec.path for file_spec in manifest.files_edit),
            "read": sorted(manifest.files_read),
            "scope": sorted(file_spec.path for file_spec in manifest.files_scope),
            "delete": sorted(file_spec.path for file_spec in manifest.files_delete),
            "snapshot": sorted(file_spec.path for file_spec in manifest.files_snapshot),
        },
        "file_contract": serialized_manifest.get("files", {}),
        "test_files": sorted(_behavioral_test_paths(manifest, project_root)),
        "validate_commands": [
            shlex.join(command) for command in manifest.validate_commands
        ],
        "acceptance_commands": (
            [shlex.join(command) for command in manifest.acceptance.tests]
            if manifest.acceptance is not None
            else []
        ),
    }


def _contract_string_set(contract: dict, key: str) -> set[str]:
    values = contract.get(key, ())
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {value for value in values if isinstance(value, str)}


def _contract_file_entries(contract: dict) -> set[str]:
    raw_files = contract.get("files", {})
    if not isinstance(raw_files, dict):
        return set()
    entries: set[str] = set()
    for section in ("create", "edit", "read", "scope", "delete", "snapshot"):
        values = raw_files.get(section, ())
        if not isinstance(values, (list, tuple, set)):
            continue
        entries.update(
            f"{section}:{value}" for value in values if isinstance(value, str)
        )
    return entries


def _validate_commands_are_strengthened(
    baseline_value: object,
    current_value: object,
    behavioral_test_paths: Collection[str],
) -> bool:
    """Match every baseline argv to an exact or test-target-only extension."""
    if not isinstance(baseline_value, list) or not all(
        isinstance(command, str) for command in baseline_value
    ):
        return False
    if not isinstance(current_value, list) or not all(
        isinstance(command, str) for command in current_value
    ):
        return False
    try:
        baseline_commands = [tuple(shlex.split(command)) for command in baseline_value]
        current_commands = [tuple(shlex.split(command)) for command in current_value]
    except ValueError:
        return False

    allowed_suffixes = {
        path.replace("\\", "/").removeprefix("./") for path in behavioral_test_paths
    }

    def is_compatible(baseline: tuple[str, ...], current: tuple[str, ...]) -> bool:
        if current[: len(baseline)] != baseline:
            return False
        suffix = current[len(baseline) :]
        if suffix and baseline and baseline[-1].startswith("-"):
            return False
        return all(
            token.replace("\\", "/").removeprefix("./") in allowed_suffixes
            for token in suffix
        )

    candidates = [
        [
            current_index
            for current_index, current in enumerate(current_commands)
            if is_compatible(baseline, current)
        ]
        for baseline in baseline_commands
    ]
    assigned: dict[int, int] = {}

    def assign(baseline_index: int, seen: set[int]) -> bool:
        for current_index in candidates[baseline_index]:
            if current_index in seen:
                continue
            seen.add(current_index)
            previous = assigned.get(current_index)
            if previous is None or assign(previous, seen):
                assigned[current_index] = baseline_index
                return True
        return False

    baseline_order = sorted(
        range(len(baseline_commands)),
        key=lambda index: (len(candidates[index]), -len(baseline_commands[index])),
    )
    return all(assign(index, set()) for index in baseline_order)


def _validate_commands_are_retained_or_preserved_in_acceptance(
    baseline_value: object,
    current_value: object,
    behavioral_test_paths: Collection[str],
    current_manifest: Manifest,
) -> bool:
    """Allow exact validate-to-acceptance moves before applying strengthen rules."""
    if not isinstance(baseline_value, list) or not all(
        isinstance(command, str) for command in baseline_value
    ):
        return False

    acceptance_counter: Counter[str] = Counter()
    if current_manifest.acceptance is not None:
        acceptance_counter.update(
            shlex.join(command) for command in current_manifest.acceptance.tests
        )

    remaining_baseline_commands: list[str] = []
    for command in baseline_value:
        if acceptance_counter[command] > 0:
            acceptance_counter[command] -= 1
        else:
            remaining_baseline_commands.append(command)

    return _validate_commands_are_strengthened(
        remaining_baseline_commands,
        current_value,
        behavioral_test_paths,
    )


def _contract_file_hashes(
    manifest_path: Path, manifest: Manifest, project_root: Path
) -> dict[str, str | None]:
    paths = {_project_relative_path(manifest_path, project_root)}
    paths.update(_behavioral_test_paths(manifest, project_root))
    return {
        path: (
            compute_behavioral_test_hash(project_root / path)
            if (project_root / path).is_file()
            else None
        )
        for path in sorted(paths)
    }


def _git_text(project_root: Path, *args: str) -> str:
    return _git_result(project_root, *args, text=True).stdout


def _git_bytes(project_root: Path, *args: str) -> bytes:
    return _git_result(project_root, *args, text=False).stdout


def _git_object_exists(project_root: Path, object_spec: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", object_spec],
        cwd=project_root,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _require_first_commit_contract_at_head(
    manifest: Manifest, contract: dict, project_root: Path
) -> None:
    """Reject index bootstrap when declared brownfield code is not at HEAD."""
    prefix = _git_prefix(project_root)
    absent_paths = {spec.path for spec in manifest.all_file_specs if spec.is_absent}
    absent_paths.update(spec.path for spec in manifest.files_delete)
    required_paths = set(manifest.all_referenced_paths)
    required_paths.update(_contract_string_set(contract, "test_files"))
    required_paths -= absent_paths

    missing = sorted(
        path
        for path in required_paths
        if not _git_object_exists(project_root, f"HEAD:{prefix}{path}")
    )
    if missing:
        raise ValueError(
            "First-commit legacy-baseline contract path(s) must already exist at "
            "HEAD: " + ", ".join(missing)
        )

    undeleted = sorted(
        path
        for path in absent_paths
        if _git_object_exists(project_root, f"HEAD:{prefix}{path}")
    )
    if undeleted:
        raise ValueError(
            "First-commit legacy-baseline deletion path(s) must already be absent "
            "at HEAD: " + ", ".join(undeleted)
        )


def _git_result(
    project_root: Path, *args: str, text: bool
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=text,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode(errors="replace")
        raise ValueError(
            f"Git command failed for legacy-baseline migration: git {' '.join(args)}"
            + (f" ({stderr.strip()})" if stderr.strip() else "")
        )
    return result


def _git_prefix(project_root: Path) -> str:
    """Return the project root's path within the repository, '' at the root.

    Mirrors the prefix resolution in core/worktree.py, but routed through this
    module's own git helper so failures keep the legacy-baseline error wording.
    """
    # splitlines() strips only the trailing newline. .strip() would also eat
    # leading or trailing whitespace that belongs to a directory name.
    lines = _git_text(project_root, "rev-parse", "--show-prefix").splitlines()
    return (lines[0] if lines else "").replace("\\", "/")


def _git_repository_root(project_root: Path) -> Path:
    """Return the containing git repository root for a MAID project root."""
    lines = _git_text(project_root, "rev-parse", "--show-toplevel").splitlines()
    if not lines:
        raise ValueError(
            "Git command failed for legacy-baseline migration: git rev-parse "
            "--show-toplevel returned no output"
        )
    return Path(lines[0]).resolve()


def _git_changed_path_fingerprints(project_root: Path) -> dict[str, str | None]:
    """Return repo-relative dirty paths and their current content fingerprints."""
    repository_root = _git_repository_root(project_root)
    tracked = _git_bytes(repository_root, "diff", "--name-only", "-z", "HEAD", "--")
    untracked = _git_bytes(
        repository_root, "ls-files", "--others", "--exclude-standard", "-z"
    )
    paths = {
        path.decode(errors="surrogateescape").replace("\\", "/")
        for path in tracked.split(b"\0") + untracked.split(b"\0")
        if path
    }
    return {
        path: _working_tree_file_fingerprint(repository_root / path)
        for path in sorted(paths)
    }


def _working_tree_file_fingerprint(path: Path) -> str | None:
    if not path.is_file():
        return _DELETED_FILE_FINGERPRINT
    return _BYTE_HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_changed_paths(project_root: Path) -> set[str]:
    # --relative makes git emit paths relative to project_root and drops paths
    # outside it. Without it, git diff reports repository-root-relative paths
    # while git ls-files --others reports project-relative ones, so the union
    # would mix two namespaces. ls-files is already project-relative and must
    # not be stripped.
    tracked = _git_bytes(
        project_root, "diff", "--name-only", "--relative", "-z", "HEAD", "--"
    )
    untracked = _git_bytes(
        project_root, "ls-files", "--others", "--exclude-standard", "-z"
    )
    return {
        path.decode(errors="surrogateescape").replace("\\", "/")
        for path in tracked.split(b"\0") + untracked.split(b"\0")
        if path
    }


def _historical_production_test_paths(
    lock_path: Path,
    lock: PlanLock,
    manifest: Manifest,
    project_root: Path,
) -> set[str]:
    """Identify immutable filename-only false positives in older lock snapshots.

    A path is safe to ignore only while the current manifest still declares
    it, its bytes match the locked hash, it remains semantically non-test, and
    the saved contract structure is valid. Every removed, changed, or
    ambiguous path stays fail-closed.
    """
    contract = _load_locked_contract(lock_path)
    if not contract:
        return set()

    validate_commands = contract.get("validate_commands")
    test_files = contract.get("test_files")
    if not isinstance(validate_commands, list) or not all(
        isinstance(command, str) for command in validate_commands
    ):
        return set()
    if not isinstance(test_files, list) or not all(
        isinstance(path, str) for path in test_files
    ):
        return set()
    if not validate_commands or not test_files:
        return set()

    current_validate_commands = Counter(
        _manifest_contract(manifest, project_root)["validate_commands"]
    )
    if Counter(validate_commands) - current_validate_commands:
        return set()

    declared_paths = manifest.all_referenced_paths

    production_paths: set[str] = set()
    for path in set(lock.test_hashes) & declared_paths & set(test_files):
        full_path = project_root / path
        locked_hash = lock.test_hashes[path]
        if test_hash_matches(
            locked_hash, full_path
        ) and not is_command_integrity_test_file(path, project_root):
            production_paths.add(path)
    return production_paths


def _artifact_declarations(manifest: Manifest) -> set[str]:
    declarations: set[str] = set()
    for file_spec in manifest.all_file_specs:
        for artifact in file_spec.artifacts:
            prefix = f"{file_spec.path}:{artifact.contract_key()}"
            declarations.add(prefix)
            declarations.add(f"{prefix}:kind={artifact.kind.value}")
            if artifact.of is not None:
                declarations.add(f"{prefix}:of={artifact.of}")
            if artifact.signature is not None:
                declarations.add(f"{prefix}:signature={artifact.signature}")
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
    lock_path: Path,
    lock: PlanLock,
    manifest: Manifest,
    project_root: Path,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    historical_production_paths = _historical_production_test_paths(
        lock_path, lock, manifest, project_root
    )
    locked_test_hashes = {
        path: locked_hash
        for path, locked_hash in lock.test_hashes.items()
        if path not in historical_production_paths
    }

    for rel, locked_hash in locked_test_hashes.items():
        full = project_root / rel
        if not test_hash_matches(locked_hash, full):
            errors.append(
                _lock_error(
                    ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK,
                    manifest,
                    project_root,
                    detail=f"behavioral test changed after lock: {rel}",
                    suggestion=(
                        f"Run `maid plan dependents {shlex.quote(rel)}` to inspect "
                        "every active lock that pins this behavioral test before "
                        "revising evidence."
                    ),
                )
            )
    return errors


def _contract_weakening_detail(
    lock_path: Path,
    lock: PlanLock,
    manifest: Manifest,
    project_root: Path,
) -> str | None:
    historical_production_paths = _historical_production_test_paths(
        lock_path, lock, manifest, project_root
    )
    locked_tests = set(lock.test_hashes) - historical_production_paths
    current_contract = _manifest_contract(manifest, project_root)
    if locked_tests - set(current_contract["test_files"]):
        return "behavioral test entries shrank"

    locked_contract = _load_locked_contract(lock_path)
    if not locked_contract:
        if manifest_hash_matches(lock.manifest_hash, Path(manifest.source_path)):
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


def _red_evidence_command_mismatch_detail(
    lock_path: Path, lock: PlanLock
) -> str | None:
    """Detect spliced red evidence by comparing command strings.

    Evidence is bound to the validate commands snapshotted into the lock at
    save time, not to the current manifest: post-lock additive validate edits
    stay legal. Locks without a snapshot field (created before the field
    existed) and locks without command evidence are skipped.
    """
    evidence = lock.red_evidence
    if not isinstance(evidence, dict):
        return None
    command_source = evidence.get("command_source")
    if command_source not in {None, _VALIDATE_AND_ACCEPTANCE_SOURCE}:
        return f"red evidence uses unsupported command source {command_source!r}"
    commands = evidence.get("commands")
    if not isinstance(commands, list):
        return None
    contract = _load_locked_contract(lock_path)
    if contract is None:
        if evidence.get("command_source") == _VALIDATE_AND_ACCEPTANCE_SOURCE:
            return (
                "acceptance-scoped red evidence lacks a locked manifest "
                "contract snapshot"
            )
        return None
    snapshot_groups = _red_evidence_contract_command_groups(contract, evidence)
    if snapshot_groups is None:
        if evidence.get("command_source") == _VALIDATE_AND_ACCEPTANCE_SOURCE:
            return (
                "acceptance-scoped red evidence lacks a locked acceptance "
                "command snapshot"
            )
        return None
    evidence_commands = [
        command.get("command") for command in commands if isinstance(command, dict)
    ]
    validate_snapshot, acceptance_snapshot = snapshot_groups
    validate_count = len(validate_snapshot)
    evidence_validate = evidence_commands[:validate_count]
    evidence_acceptance = evidence_commands[validate_count:]
    if (
        len(evidence_commands) != len(commands)
        or len(evidence_commands) != len(validate_snapshot) + len(acceptance_snapshot)
        or Counter(evidence_validate) != Counter(validate_snapshot)
        or Counter(evidence_acceptance) != Counter(acceptance_snapshot)
    ):
        expected = (
            "locked validate and acceptance command partitions"
            if evidence.get("command_source") == _VALIDATE_AND_ACCEPTANCE_SOURCE
            else "locked validate commands"
        )
        return f"red evidence commands do not match the {expected}"
    return None


def _red_evidence_contract_command_groups(
    contract: dict, evidence: dict
) -> tuple[list[str], list[str]] | None:
    validate_commands = contract.get("validate_commands")
    if not isinstance(validate_commands, list) or not all(
        isinstance(command, str) for command in validate_commands
    ):
        return None
    command_source = evidence.get("command_source")
    if command_source is None:
        return validate_commands, []
    if command_source != _VALIDATE_AND_ACCEPTANCE_SOURCE:
        return None
    acceptance_commands = contract.get("acceptance_commands")
    if not isinstance(acceptance_commands, list) or not all(
        isinstance(command, str) for command in acceptance_commands
    ):
        return None
    return validate_commands, acceptance_commands


def _red_evidence_is_valid(evidence: dict) -> bool:
    if not isinstance(evidence, dict) or evidence.get("red") is not True:
        return False
    if evidence.get("command_source") not in {
        None,
        _VALIDATE_AND_ACCEPTANCE_SOURCE,
    }:
        return False
    mode = evidence.get("mode")
    if mode == "stash_restoration":
        return _stash_restoration_red_evidence_is_valid(evidence)
    if mode is not None:
        return False
    commands = evidence.get("commands")
    if not isinstance(commands, list):
        return False
    if not all(_red_command_payload_is_consistent(command) for command in commands):
        return False
    classifications = [command["classification"] for command in commands]
    return "red" in classifications and "invalid" not in classifications


def _stash_restoration_red_evidence_is_valid(evidence: dict) -> bool:
    """Validate mixed red evidence proven by an exact-stash restoration run."""
    commands = evidence.get("commands")
    restored_commands = evidence.get("restored_commands")
    if not isinstance(commands, list) or not isinstance(restored_commands, list):
        return False
    if not commands or len(commands) != len(restored_commands):
        return False
    if not isinstance(evidence.get("restored_captured_at"), str):
        return False
    if not all(
        _red_command_payload_is_consistent(command)
        for command in (*commands, *restored_commands)
    ):
        return False

    classifications = [command["classification"] for command in commands]
    if "red" not in classifications or "invalid" not in classifications:
        return False
    if any(command["classification"] == "invalid" for command in restored_commands):
        return False
    return all(
        command["command"] == restored_command["command"]
        for command, restored_command in zip(commands, restored_commands)
    )


def _red_command_payload_is_consistent(command: object) -> bool:
    """Return whether serialized command evidence matches exit classification."""
    if not isinstance(command, dict):
        return False
    command_text = command.get("command")
    exit_code = command.get("exit_code")
    return (
        isinstance(command_text, str)
        and bool(command_text)
        and type(exit_code) is int
        and command.get("classification") == classify_red_exit_code(exit_code)
        and isinstance(command.get("output_tail"), str)
    )


def _contract_writable_paths(contract: dict) -> set[str]:
    raw_files = contract.get("files", {})
    if not isinstance(raw_files, dict):
        return set()
    entries: set[str] = set()
    for section in ("create", "edit", "scope", "delete", "snapshot"):
        values = raw_files.get(section, ())
        if not isinstance(values, (list, tuple, set)):
            continue
        entries.update(
            value.replace("\\", "/") for value in values if isinstance(value, str)
        )
    return entries


def _contract_writable_paths_are_all_tests(contract: dict) -> bool:
    from maid_runner.core._file_discovery import is_test_file

    return all(is_test_file(path) for path in _contract_writable_paths(contract))


def _test_only_green_commands_are_green(evidence: dict) -> bool:
    commands = evidence.get("commands")
    if not isinstance(commands, list) or not commands:
        return False
    for command in commands:
        if not _red_command_payload_is_consistent(command):
            return False
        if command["classification"] != "not_red":
            return False
    return True


def _test_only_green_payload_is_valid(evidence: object) -> bool:
    return (
        isinstance(evidence, dict)
        and evidence.get("red") is False
        and evidence.get("mode") == "test_only_green"
        and _test_only_green_commands_are_green(evidence)
    )


def _test_only_green_evidence_satisfies(evidence: dict, lock_path: Path) -> bool:
    if not _test_only_green_payload_is_valid(evidence):
        return False
    contract = _load_locked_contract(lock_path)
    if contract is None:
        return False
    return _contract_writable_paths_are_all_tests(contract)


def _test_only_green_rejection_detail(evidence: object, lock_path: Path) -> str | None:
    if not isinstance(evidence, dict) or evidence.get("mode") != "test_only_green":
        return None
    contract = _load_locked_contract(lock_path)
    if contract is None:
        return (
            "test_only_green evidence cannot satisfy --require-red-evidence "
            "without a persisted manifest contract snapshot"
        )
    if not _contract_writable_paths_are_all_tests(contract):
        return (
            "test_only_green/contract mismatch: persisted contract includes "
            "non-test writable path(s)"
        )
    return "test_only_green evidence is invalid"


def _legacy_baseline_is_valid(evidence: object, lock_path: Path) -> bool:
    if not isinstance(evidence, dict):
        return False
    if evidence.get("kind") != "legacy_baseline" or evidence.get("green") is not True:
        return False
    reason = evidence.get("reason")
    commit = evidence.get("baseline_commit")
    manifest_hash = evidence.get("baseline_manifest_hash")
    manifest_source = evidence.get("baseline_manifest_source", "head")
    captured_at = evidence.get("captured_at")
    if not isinstance(reason, str) or not reason.strip():
        return False
    if not _is_hex_digest(commit, lengths={40, 64}):
        return False
    if not _is_hex_digest(manifest_hash, lengths={64}):
        return False
    if manifest_source not in {"head", "index"}:
        return False
    if not isinstance(captured_at, str) or not captured_at.strip():
        return False

    try:
        delta = _contract_delta_from_payload(evidence.get("contract_delta"))
    except TypeError:
        return False
    if delta is None or any(
        (
            delta.artifacts_added,
            delta.artifacts_removed,
            delta.files_added,
            delta.files_removed,
        )
    ):
        return False

    commands = evidence.get("commands")
    if not isinstance(commands, list) or not commands:
        return False
    command_strings: list[str] = []
    for command in commands:
        if not isinstance(command, dict):
            return False
        command_string = command.get("command")
        if not isinstance(command_string, str) or not command_string:
            return False
        if command.get("exit_code") != 0:
            return False
        if command.get("classification") != "not_red":
            return False
        if not isinstance(command.get("output_tail"), str):
            return False
        command_strings.append(command_string)

    contract = _load_locked_contract(lock_path)
    if not isinstance(contract, dict):
        return False
    snapshot = contract.get("validate_commands")
    return isinstance(snapshot, list) and Counter(command_strings) == Counter(snapshot)


def _is_hex_digest(value: object, *, lengths: set[int]) -> bool:
    return (
        isinstance(value, str)
        and len(value) in lengths
        and all(character in "0123456789abcdef" for character in value.lower())
    )


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
    suggestion: str | None = None,
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
        ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH: (
            "RED_EVIDENCE_COMMAND_MISMATCH: red-phase evidence command strings "
            "do not match the locked validate commands"
        ),
    }
    message = messages[code]
    if detail:
        message = f"{message} ({detail})"
    return ValidationError(
        code=code,
        message=message,
        location=Location(file=_manifest_location(manifest, project_root)),
        suggestion=suggestion,
    )


def _manifest_location(manifest: Manifest, project_root: Path) -> str:
    path = Path(manifest.source_path)
    return _project_relative_path(path, project_root)
