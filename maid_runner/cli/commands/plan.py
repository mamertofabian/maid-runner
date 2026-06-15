"""CLI handler for `maid plan` subcommands."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from maid_runner.cli.commands._format import print_error


def cmd_plan(args: argparse.Namespace) -> int:
    """Dispatch `maid plan <subcommand>`."""
    sub = getattr(args, "plan_command", None)
    if sub == "lock":
        return cmd_plan_lock(args)
    if sub == "revise":
        return cmd_plan_revise(args)
    if sub == "status":
        return cmd_plan_status(args)
    print_error(
        f"Unknown plan subcommand: {sub}",
        json_mode=getattr(args, "json", False),
    )
    return 2


def cmd_plan_lock(args: argparse.Namespace) -> int:
    """Create a plan lock; refuse to overwrite an existing lock."""
    from maid_runner.core.plan_lock import (
        PlanLock,
        capture_red_phase_evidence,
        create_plan_lock,
        _PlanLockLoadError,
    )

    ctx = _PlanContext.from_args(args)

    if ctx.lock_path.exists():
        try:
            PlanLock.load(ctx.lock_path)
        except _PlanLockLoadError as exc:
            print_error(
                f"Existing plan lock at {ctx.lock_path} is invalid: {exc.detail}. "
                "Refusing to overwrite a broken lock; remove it manually after "
                "investigating.",
                json_mode=ctx.json_mode,
            )
            return 2
        print_error(
            f"Plan lock already exists at {ctx.lock_path}. "
            'Use `maid plan revise <manifest> --reason "<text>"` to re-lock.',
            json_mode=ctx.json_mode,
        )
        return 1

    try:
        lock = create_plan_lock(ctx.manifest_path, ctx.project_root)
        if not getattr(args, "no_run", False):
            lock = replace(
                lock,
                red_evidence=capture_red_phase_evidence(
                    ctx.manifest_path, ctx.project_root
                ).to_payload(),
            )
    except _plan_input_errors() as exc:
        print_error(str(exc), json_mode=ctx.json_mode)
        return 2
    lock.save(ctx.lock_path)
    print(
        f"Locked plan '{ctx.slug}' at revision {lock.revision} "
        f"({len(lock.test_hashes)} behavioral test file(s), {ctx.lock_path})"
    )
    return 0


def cmd_plan_revise(args: argparse.Namespace) -> int:
    """Re-lock with current hashes; require a non-empty --reason."""
    from maid_runner.core.plan_lock import (
        PlanLock,
        capture_red_phase_evidence,
        revise_plan_lock,
        _PlanLockLoadError,
    )

    ctx = _PlanContext.from_args(args)
    reason = getattr(args, "reason", None)
    if reason is None or not reason.strip():
        print_error(
            "Plan-lock revision requires a non-empty --reason.",
            json_mode=ctx.json_mode,
        )
        return 2

    preserve_red_evidence = bool(getattr(args, "preserve_red_evidence", False))
    if preserve_red_evidence and getattr(args, "no_run", False):
        print_error(
            "--preserve-red-evidence cannot be combined with --no-run.",
            json_mode=ctx.json_mode,
        )
        return 2

    if not ctx.lock_path.exists():
        print_error(
            f"No plan lock to revise at {ctx.lock_path}. "
            "Use `maid plan lock <manifest>` first.",
            json_mode=ctx.json_mode,
        )
        return 1

    try:
        existing = PlanLock.load(ctx.lock_path)
    except _PlanLockLoadError as exc:
        print_error(
            f"Plan lock at {ctx.lock_path} is invalid: {exc.detail}",
            json_mode=ctx.json_mode,
        )
        return 2

    if preserve_red_evidence and not _red_evidence_payload_is_valid(
        existing.red_evidence
    ):
        print_error(
            "--preserve-red-evidence requires existing valid red evidence.",
            json_mode=ctx.json_mode,
        )
        return 2

    try:
        revised = revise_plan_lock(
            existing, ctx.manifest_path, ctx.project_root, reason
        )
        if preserve_red_evidence:
            revised = replace(revised, red_evidence=existing.red_evidence)
        elif not getattr(args, "no_run", False):
            revised = replace(
                revised,
                red_evidence=capture_red_phase_evidence(
                    ctx.manifest_path, ctx.project_root
                ).to_payload(),
            )
    except _plan_input_errors() as exc:
        print_error(str(exc), json_mode=ctx.json_mode)
        return 2
    revised.save(ctx.lock_path)
    print(
        f"Revised plan lock for '{ctx.slug}' to revision {revised.revision} "
        f"({ctx.lock_path})"
    )
    return 0


def cmd_plan_status(args: argparse.Namespace) -> int:
    """Report lock state, hash matches and mismatches, and red evidence."""
    from maid_runner.core.plan_lock import PlanLock, _PlanLockLoadError
    from maid_runner.core.supersession_audit import compute_manifest_hash

    ctx = _PlanContext.from_args(args)

    if not ctx.lock_path.exists():
        if ctx.json_mode:
            payload = {
                "manifest_path": str(ctx.manifest_path),
                "lock_path": str(ctx.lock_path),
                "locked": False,
            }
            print(json.dumps(payload, indent=2))
        else:
            print(f"Plan '{ctx.slug}' is not locked (no lock at {ctx.lock_path}).")
        return 0

    try:
        lock = PlanLock.load(ctx.lock_path)
    except _PlanLockLoadError as exc:
        print_error(
            f"Plan lock at {ctx.lock_path} is invalid: {exc.detail}",
            json_mode=ctx.json_mode,
        )
        return 2

    manifest_match = (
        ctx.manifest_path.exists()
        and compute_manifest_hash(ctx.manifest_path) == lock.manifest_hash
    )
    test_files: dict[str, dict] = {}
    for rel, locked_hash in lock.test_hashes.items():
        full = ctx.project_root / rel
        current_hash = compute_manifest_hash(full) if full.exists() else None
        test_files[rel] = {
            "locked_hash": locked_hash,
            "current_hash": current_hash,
            "match": current_hash == locked_hash,
        }
    has_mismatch = not manifest_match or any(
        not entry["match"] for entry in test_files.values()
    )

    if ctx.json_mode:
        payload = {
            "manifest_path": lock.manifest_path,
            "lock_path": str(ctx.lock_path),
            "locked": True,
            "revision": lock.revision,
            "created_at": lock.created_at,
            "manifest_match": manifest_match,
            "test_files": test_files,
            "red_evidence": lock.red_evidence,
            "revisions": [
                {"revised_at": r.revised_at, "reason": r.reason} for r in lock.revisions
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        state = "TAMPERED" if has_mismatch else "OK"
        print(f"Plan '{ctx.slug}' locked at revision {lock.revision}: {state}")
        print(f"  Manifest: {'match' if manifest_match else 'MISMATCH'}")
        for rel, entry in test_files.items():
            print(f"  {rel}: {'match' if entry['match'] else 'MISMATCH'}")
        print(f"  Red evidence: {'recorded' if lock.red_evidence else 'none'}")
        for r in lock.revisions:
            print(f"  Revision at {r.revised_at}: {r.reason}")

    return 1 if has_mismatch else 0


def _plan_input_errors() -> tuple[type[Exception], ...]:
    """Expected failures when reading a manifest and hashing its test files."""
    from maid_runner.core.manifest import ManifestLoadError, ManifestSchemaError

    return (ManifestLoadError, ManifestSchemaError, OSError, ValueError)


def _red_evidence_payload_is_valid(evidence: dict | None) -> bool:
    """Return whether an existing lock payload is valid red evidence."""
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


class _PlanContext:
    """Resolved paths shared by all plan subcommands."""

    def __init__(self, manifest_path: Path, project_root: Path, json_mode: bool):
        from maid_runner.core.manifest import slug_from_path
        from maid_runner.core.plan_lock import default_plan_lock_path

        self.manifest_path = manifest_path
        self.project_root = project_root
        self.json_mode = json_mode
        self.slug = slug_from_path(manifest_path)
        self.lock_path = default_plan_lock_path(project_root, self.slug)

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "_PlanContext":
        return cls(
            manifest_path=Path(args.manifest_path),
            project_root=Path(getattr(args, "project_root", ".")),
            json_mode=bool(getattr(args, "json", False)),
        )
