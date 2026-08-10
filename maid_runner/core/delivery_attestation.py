"""Portable provenance for plan-locked commits delivered through Git refs."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from collections.abc import Collection
from pathlib import Path

from maid_runner.core.manifest import (
    ManifestLoadError,
    ManifestSchemaError,
    load_manifest,
    slug_from_path,
)
from maid_runner.core.plan_lock import (
    PlanLock,
    compute_manifest_contract_hash,
    default_plan_lock_path,
)

_SCHEMA = "maid-delivery-provenance/v1"
_INVALID_ATTESTATION_CODE = "E713"
_DELIVERY_MISMATCH_CODE = "E714"


def compute_delivery_attestation(
    project_root: Path,
    manifest_paths: Collection[Path],
    validated_ref: str,
) -> dict:
    """Derive covered committed-byte hashes for explicit plan-locked manifests."""
    root = Path(project_root).resolve()
    validated_commit = _resolve_commit(root, validated_ref)
    normalized_paths = sorted(
        {_project_relative(root, Path(path)) for path in manifest_paths}
    )
    if not normalized_paths:
        raise ValueError("delivery attestation requires at least one manifest")

    contracts: list[dict] = []
    for manifest_path in normalized_paths:
        manifest_bytes = _git_blob(root, validated_commit, manifest_path)
        if manifest_bytes is None:
            raise ValueError(
                f"manifest is missing at validated commit: {manifest_path}"
            )
        manifest = _load_manifest_bytes(manifest_bytes)
        slug = slug_from_path(Path(manifest_path))
        lock_path = default_plan_lock_path(root, slug)
        try:
            lock = PlanLock.load(lock_path)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise ValueError(
                f"plan lock is missing or unreadable for {manifest_path}: {exc}"
            ) from exc
        if Path(lock.manifest_path).as_posix() != manifest_path:
            raise ValueError(
                "plan lock manifest path does not match attested manifest: "
                f"{lock.manifest_path!r} != {manifest_path!r}"
            )
        manifest_hash = _manifest_hash_from_bytes(manifest_bytes)
        if lock.manifest_hash != manifest_hash:
            raise ValueError(
                f"plan lock contract hash does not match {manifest_path} at "
                f"{validated_commit}"
            )
        covered_files = {
            path: _blob_hash(root, validated_commit, path)
            for path in sorted(manifest.all_writable_paths)
        }
        contracts.append(
            {
                "manifest_path": manifest_path,
                "manifest_hash": manifest_hash,
                "covered_files": covered_files,
            }
        )

    return {
        "schema": _SCHEMA,
        "validated_commit": validated_commit,
        "contracts": contracts,
    }


def verify_delivered_attestation(
    attestation: dict,
    project_root: Path,
    delivered_ref: str,
) -> dict:
    """Compare attested bytes with a named local or remote delivered branch."""
    root = Path(project_root).resolve()
    invalid_reason = _attestation_error(attestation)
    if invalid_reason is not None:
        return _failure(
            _INVALID_ATTESTATION_CODE,
            invalid_reason,
            delivered_ref=delivered_ref,
        )

    validated_reason = _validated_commit_error(attestation, root)
    if validated_reason is not None:
        return _failure(
            _INVALID_ATTESTATION_CODE,
            validated_reason,
            delivered_ref=delivered_ref,
        )

    symbolic_ref = _symbolic_delivery_ref(root, delivered_ref)
    if symbolic_ref is None:
        return _failure(
            _DELIVERY_MISMATCH_CODE,
            "delivered target must resolve to refs/heads/... or refs/remotes/...",
            delivered_ref=delivered_ref,
        )
    try:
        delivered_commit = _resolve_commit(root, symbolic_ref)
    except ValueError as exc:
        return _failure(
            _DELIVERY_MISMATCH_CODE,
            str(exc),
            delivered_ref=symbolic_ref,
        )

    expected_by_path: dict[str, str | None] = {}
    for contract in attestation["contracts"]:
        manifest_path = contract["manifest_path"]
        manifest_bytes = _git_blob(root, delivered_commit, manifest_path)
        if manifest_bytes is None:
            return _failure(
                _INVALID_ATTESTATION_CODE,
                f"attested manifest is missing at delivered ref: {manifest_path}",
                delivered_ref=symbolic_ref,
                delivered_commit=delivered_commit,
            )
        try:
            _load_manifest_bytes(manifest_bytes)
            delivered_hash = _manifest_hash_from_bytes(manifest_bytes)
        except (ManifestLoadError, ManifestSchemaError, OSError, ValueError) as exc:
            return _failure(
                _INVALID_ATTESTATION_CODE,
                f"attested manifest is unreadable at delivered ref: {exc}",
                delivered_ref=symbolic_ref,
                delivered_commit=delivered_commit,
            )
        if delivered_hash != contract["manifest_hash"]:
            return _failure(
                _INVALID_ATTESTATION_CODE,
                f"attested manifest contract does not match delivered ref: {manifest_path}",
                delivered_ref=symbolic_ref,
                delivered_commit=delivered_commit,
            )
        for path, expected in contract["covered_files"].items():
            prior = expected_by_path.get(path, expected)
            if path in expected_by_path and prior != expected:
                return _failure(
                    _INVALID_ATTESTATION_CODE,
                    f"conflicting expected hashes for covered path: {path}",
                    delivered_ref=symbolic_ref,
                    delivered_commit=delivered_commit,
                )
            expected_by_path[path] = expected

    mismatches = []
    for path, expected in sorted(expected_by_path.items()):
        actual = _blob_hash(root, delivered_commit, path)
        if actual != expected:
            mismatches.append({"path": path, "expected": expected, "actual": actual})

    if mismatches:
        return _failure(
            _DELIVERY_MISMATCH_CODE,
            "delivered ref changed or omitted covered committed bytes",
            delivered_ref=symbolic_ref,
            delivered_commit=delivered_commit,
            mismatches=mismatches,
        )
    return {
        "success": True,
        "delivered_ref": symbolic_ref,
        "delivered_commit": delivered_commit,
        "mismatches": [],
        "errors": [],
    }


def render_provenance_record(
    attestation: dict,
    verification: dict | None = None,
) -> str:
    """Serialize an attestation and optional delivery result deterministically."""
    invalid_reason = _attestation_error(attestation)
    if invalid_reason is not None:
        raise ValueError(invalid_reason)
    record = {
        "schema": attestation["schema"],
        "validated_commit": attestation["validated_commit"],
        "contracts": attestation["contracts"],
    }
    if verification is not None:
        record["validation"] = verification
    return json.dumps(record, indent=2, sort_keys=True, allow_nan=False)


def _attestation_error(attestation: object) -> str | None:
    if not isinstance(attestation, dict):
        return "delivery attestation must be a JSON object"
    if attestation.get("schema") != _SCHEMA:
        return f"delivery attestation schema must be {_SCHEMA!r}"
    validated_commit = attestation.get("validated_commit")
    if not _is_object_id(validated_commit):
        return "delivery attestation validated_commit must be a Git object ID"
    contracts = attestation.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        return "delivery attestation contracts must be a non-empty array"
    seen_manifests: set[str] = set()
    for contract in contracts:
        if not isinstance(contract, dict):
            return "each delivery attestation contract must be an object"
        manifest_path = contract.get("manifest_path")
        if not _is_safe_relative_path(manifest_path):
            return "delivery attestation manifest_path must be project-relative"
        if manifest_path in seen_manifests:
            return f"duplicate attested manifest path: {manifest_path}"
        seen_manifests.add(manifest_path)
        manifest_hash = contract.get("manifest_hash")
        if not (
            isinstance(manifest_hash, str)
            and manifest_hash.startswith("sha256-contract:")
            and _is_hex(manifest_hash.removeprefix("sha256-contract:"), 64)
        ):
            return f"invalid manifest contract hash for {manifest_path}"
        covered_files = contract.get("covered_files")
        if not isinstance(covered_files, dict) or not covered_files:
            return f"covered_files must be a non-empty object for {manifest_path}"
        for path, digest in covered_files.items():
            if not _is_safe_relative_path(path):
                return f"covered path must be project-relative: {path!r}"
            if digest is not None and not (
                isinstance(digest, str)
                and digest.startswith("sha256:")
                and _is_hex(digest.removeprefix("sha256:"), 64)
            ):
                return f"invalid covered-file hash for {path}"
    return None


def _validated_commit_error(attestation: dict, root: Path) -> str | None:
    validated_commit = attestation["validated_commit"]
    try:
        resolved_commit = _resolve_commit(root, validated_commit)
    except ValueError as exc:
        return f"validated commit cannot be resolved: {exc}"
    if resolved_commit != validated_commit:
        return "validated_commit does not resolve to its recorded object ID"

    for contract in attestation["contracts"]:
        manifest_path = contract["manifest_path"]
        manifest_bytes = _git_blob(root, validated_commit, manifest_path)
        if manifest_bytes is None:
            return f"attested manifest is missing at validated commit: {manifest_path}"
        try:
            manifest_hash = _manifest_hash_from_bytes(manifest_bytes)
            manifest = _load_manifest_bytes(manifest_bytes)
        except (ManifestLoadError, ManifestSchemaError, OSError, ValueError) as exc:
            return f"attested manifest is unreadable at validated commit: {exc}"
        if manifest_hash != contract["manifest_hash"]:
            return (
                "attested manifest contract does not match validated commit: "
                f"{manifest_path}"
            )
        expected_paths = set(manifest.all_writable_paths)
        recorded_paths = set(contract["covered_files"])
        if recorded_paths != expected_paths:
            missing = sorted(expected_paths - recorded_paths)
            extra = sorted(recorded_paths - expected_paths)
            return (
                f"attested covered set does not match {manifest_path} writable "
                f"scope (missing={missing}, extra={extra})"
            )
        for path, expected_hash in contract["covered_files"].items():
            if _blob_hash(root, validated_commit, path) != expected_hash:
                return f"attested hash does not match validated commit: {path}"
    return None


def _failure(
    code: str,
    message: str,
    *,
    delivered_ref: str,
    delivered_commit: str | None = None,
    mismatches: list[dict] | None = None,
) -> dict:
    return {
        "success": False,
        "delivered_ref": delivered_ref,
        "delivered_commit": delivered_commit,
        "mismatches": mismatches or [],
        "errors": [{"code": code, "message": message}],
    }


def _project_relative(root: Path, path: Path) -> str:
    candidate = path if path.is_absolute() else root / path
    try:
        return candidate.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"manifest path is outside project root: {path}") from exc


def _resolve_commit(root: Path, ref: str) -> str:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("Git ref must be a non-empty string")
    result = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if result.returncode != 0:
        raise ValueError(f"Git ref does not resolve to a commit: {ref}")
    return result.stdout.decode("ascii").strip()


def _symbolic_delivery_ref(root: Path, ref: str) -> str | None:
    if not isinstance(ref, str) or not ref.strip():
        return None
    result = _git(root, "rev-parse", "--symbolic-full-name", ref)
    if result.returncode != 0:
        return None
    symbolic = result.stdout.decode("utf-8", errors="replace").strip()
    if symbolic.startswith(("refs/heads/", "refs/remotes/")):
        return symbolic
    return None


def _blob_hash(root: Path, commit: str, path: str) -> str | None:
    content = _git_blob(root, commit, path)
    if content is None:
        return None
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _git_blob(root: Path, commit: str, path: str) -> bytes | None:
    result = _git(root, "show", f"{commit}:{path}")
    if result.returncode == 0:
        return result.stdout
    missing = _git(root, "cat-file", "-e", f"{commit}:{path}")
    if missing.returncode != 0:
        return None
    raise ValueError(f"Git could not read committed blob: {commit}:{path}")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Git command failed: git {' '.join(args)} ({exc})") from exc


def _load_manifest_bytes(content: bytes):
    with tempfile.NamedTemporaryFile(suffix=".manifest.yaml", delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    try:
        return load_manifest(temporary)
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_hash_from_bytes(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".manifest.yaml", delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    try:
        return compute_manifest_contract_hash(temporary)
    finally:
        temporary.unlink(missing_ok=True)


def _is_object_id(value: object) -> bool:
    return isinstance(value, str) and (_is_hex(value, 40) or _is_hex(value, 64))


def _is_hex(value: str, length: int) -> bool:
    if len(value) != length:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _is_safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts
