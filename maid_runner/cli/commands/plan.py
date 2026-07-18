"""CLI handler for `maid plan` subcommands."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import uuid
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
        capture_legacy_baseline_evidence,
        capture_red_phase_evidence,
        create_plan_lock,
        _PlanLockLoadError,
    )

    ctx = _PlanContext.from_args(args)
    legacy_baseline = bool(getattr(args, "legacy_baseline", False))
    reason = getattr(args, "reason", None)

    if legacy_baseline and getattr(args, "no_run", False):
        print_error(
            "--legacy-baseline cannot be combined with --no-run.",
            json_mode=ctx.json_mode,
        )
        return 2
    if legacy_baseline and (reason is None or not reason.strip()):
        print_error(
            "--legacy-baseline requires a non-empty --reason.",
            json_mode=ctx.json_mode,
        )
        return 2

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
        provenance = _resolve_agent_provenance_from_args(args)
        _print_provenance_warning(provenance.warning)
        lock = create_plan_lock(
            ctx.manifest_path, ctx.project_root, agent=provenance.provenance
        )
        if legacy_baseline:
            lock = replace(
                lock,
                legacy_baseline=capture_legacy_baseline_evidence(
                    ctx.manifest_path, ctx.project_root, reason
                ).to_payload(),
            )
        elif not getattr(args, "no_run", False):
            lock = replace(
                lock,
                red_evidence=capture_red_phase_evidence(
                    ctx.manifest_path, ctx.project_root
                ).to_payload(),
            )
        temporary_lock_path = ctx.lock_path.with_name(
            f".{ctx.lock_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            lock.save(temporary_lock_path)
            try:
                os.link(temporary_lock_path, ctx.lock_path)
            except FileExistsError as exc:
                raise ValueError(
                    f"Plan lock appeared while evidence was being captured at "
                    f"{ctx.lock_path}; refusing to overwrite it"
                ) from exc
        finally:
            temporary_lock_path.unlink(missing_ok=True)
    except _plan_input_errors() as exc:
        print_error(str(exc), json_mode=ctx.json_mode)
        return 2
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
        revision_preserves_red_evidence,
        _load_locked_contract,
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
    stash_implementation = bool(getattr(args, "stash_implementation", False))
    allow_sibling_dirty = bool(getattr(args, "allow_sibling_dirty", False))
    if allow_sibling_dirty and not stash_implementation:
        print_error(
            "--allow-sibling-dirty requires --stash-implementation.",
            json_mode=ctx.json_mode,
        )
        return 2
    if stash_implementation and getattr(args, "no_run", False):
        print_error(
            "--stash-implementation cannot be combined with --no-run.",
            json_mode=ctx.json_mode,
        )
        return 2
    if stash_implementation and preserve_red_evidence:
        print_error(
            "--stash-implementation cannot be combined with --preserve-red-evidence.",
            json_mode=ctx.json_mode,
        )
        return 2
    test_only_green = bool(getattr(args, "test_only_green", False))
    if test_only_green and stash_implementation:
        print_error(
            "--test-only-green cannot be combined with --stash-implementation.",
            json_mode=ctx.json_mode,
        )
        return 2
    if test_only_green and preserve_red_evidence:
        print_error(
            "--test-only-green cannot be combined with --preserve-red-evidence.",
            json_mode=ctx.json_mode,
        )
        return 2
    if test_only_green and getattr(args, "no_run", False):
        print_error(
            "--test-only-green cannot be combined with --no-run.",
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

    preserved_evidence_class = _preservable_evidence_class(existing.red_evidence)
    if preserve_red_evidence and preserved_evidence_class is None:
        print_error(
            "--preserve-red-evidence requires existing valid red or "
            "test-only-green evidence.",
            json_mode=ctx.json_mode,
        )
        return 2

    provenance = _resolve_agent_provenance_from_args(args)
    _print_provenance_warning(provenance.warning)

    if stash_implementation:
        return _cmd_plan_revise_with_stashed_implementation(
            ctx=ctx,
            existing=existing,
            reason=reason,
            agent=provenance.provenance,
            allow_sibling_dirty=allow_sibling_dirty,
        )
    if test_only_green:
        return _cmd_plan_revise_test_only_green(
            ctx=ctx,
            existing=existing,
            reason=reason,
            agent=provenance.provenance,
        )

    prior_contract = _load_locked_contract(ctx.lock_path)
    auto_preserve = False
    if not preserve_red_evidence and not getattr(args, "no_run", False):
        auto_preserve = revision_preserves_red_evidence(
            existing,
            ctx.manifest_path,
            ctx.project_root,
            prior_contract,
        )

    try:
        revised = revise_plan_lock(
            existing,
            ctx.manifest_path,
            ctx.project_root,
            reason,
            agent=provenance.provenance,
            prior_contract=prior_contract,
        )
        if preserve_red_evidence or auto_preserve:
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
    if preserve_red_evidence or auto_preserve:
        evidence_class = preserved_evidence_class or "red"
        reason_text = (
            " because the revision is contract-preserving"
            if auto_preserve
            else " by explicit request"
        )
        print(f"{evidence_class} evidence preserved{reason_text}.")
    return 0


def cmd_plan_status(args: argparse.Namespace) -> int:
    """Report lock state, hash matches and mismatches, and red evidence."""
    from maid_runner.core.plan_lock import (
        PlanLock,
        _PlanLockLoadError,
        manifest_hash_matches,
    )
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

    manifest_error: str | None = None
    try:
        manifest_match = manifest_hash_matches(lock.manifest_hash, ctx.manifest_path)
    except _manifest_status_errors() as exc:
        from yaml import YAMLError

        manifest_match = False
        manifest_error = (
            f"YAML parse error: {exc}" if isinstance(exc, YAMLError) else str(exc)
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
            **(
                {"manifest_error": manifest_error} if manifest_error is not None else {}
            ),
            "test_files": test_files,
            "red_evidence": lock.red_evidence,
            "legacy_baseline": lock.legacy_baseline,
            "agent": _agent_to_payload(lock.agent),
            "revisions": [
                {
                    "revised_at": r.revised_at,
                    "reason": r.reason,
                    "agent": _agent_to_payload(r.agent),
                    "contract_delta": _contract_delta_to_payload(r.contract_delta),
                }
                for r in lock.revisions
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        state = "TAMPERED" if has_mismatch else "OK"
        print(f"Plan '{ctx.slug}' locked at revision {lock.revision}: {state}")
        print(f"  Manifest: {'match' if manifest_match else 'MISMATCH'}")
        if manifest_error is not None:
            print(f"  Manifest error: {manifest_error}")
        for rel, entry in test_files.items():
            print(f"  {rel}: {'match' if entry['match'] else 'MISMATCH'}")
        print(f"  Red evidence: {'recorded' if lock.red_evidence else 'none'}")
        print(f"  Legacy baseline: {'recorded' if lock.legacy_baseline else 'none'}")
        if lock.agent is not None:
            print(f"  Agent: {_format_agent(lock.agent)}")
        for r in lock.revisions:
            print(f"  Revision at {r.revised_at}: {r.reason}")
            if r.agent is not None:
                print(f"    Revision agent: {_format_agent(r.agent)}")
            if r.contract_delta is not None:
                print(f"    {_format_contract_delta_summary(r.contract_delta)}")

    return 1 if has_mismatch else 0


def _plan_input_errors() -> tuple[type[Exception], ...]:
    """Expected failures when reading a manifest and hashing its test files."""
    from maid_runner.core.manifest import ManifestLoadError, ManifestSchemaError

    return (ManifestLoadError, ManifestSchemaError, OSError, ValueError)


def _manifest_status_errors() -> tuple[type[Exception], ...]:
    """Failures that make only the current manifest hash unreadable."""
    from yaml import YAMLError

    return (YAMLError, OSError, ValueError)


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


def _test_only_green_payload_is_valid(evidence: object) -> bool:
    if not isinstance(evidence, dict):
        return False
    if evidence.get("red") is not False or evidence.get("mode") != "test_only_green":
        return False
    commands = evidence.get("commands")
    return (
        bool(commands)
        and isinstance(commands, list)
        and all(
            isinstance(command, dict)
            and command.get("classification") == "not_red"
            and command.get("exit_code") == 0
            for command in commands
        )
    )


def _preservable_evidence_class(evidence: object) -> str | None:
    if _red_evidence_payload_is_valid(evidence if isinstance(evidence, dict) else None):
        return "red"
    if _test_only_green_payload_is_valid(evidence):
        return "test-only-green"
    return None


def _resolve_agent_provenance_from_args(args: argparse.Namespace):
    from maid_runner.core.agent_provenance import resolve_agent_provenance

    env = {
        key: os.environ[key]
        for key in (
            "MAID_AGENT_MODEL",
            "MAID_AGENT_PROVIDER",
            "MAID_AGENT_CLIENT",
            "MAID_AGENT_SKILLS",
            "MAID_AGENT_INSTRUCTIONS_FINGERPRINT",
        )
        if key in os.environ
    }
    return resolve_agent_provenance(
        {
            "model": getattr(args, "agent_model", None),
            "provider": getattr(args, "agent_provider", None),
            "client": getattr(args, "agent_client", None),
            "skills": getattr(args, "agent_skill", None),
            "instructions_fingerprint": getattr(
                args, "agent_instructions_fingerprint", None
            ),
        },
        env,
    )


def _print_provenance_warning(warning: str | None) -> None:
    if warning is not None:
        print(warning, file=sys.stderr)


def _agent_to_payload(agent) -> dict | None:
    if agent is None:
        return None
    payload = {"model": agent.model}
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


def _contract_delta_to_payload(delta) -> dict | None:
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


def _format_contract_delta_summary(delta) -> str:
    parts = []
    parts.extend(_delta_count_parts("+", len(delta.artifacts_added), "artifact"))
    parts.extend(_delta_count_parts("-", len(delta.artifacts_removed), "artifact"))
    parts.extend(_delta_count_parts("+", len(delta.files_added), "file"))
    parts.extend(_delta_count_parts("-", len(delta.files_removed), "file"))
    parts.extend(
        _delta_count_parts("+", len(delta.validate_commands_added), "validate command")
    )
    parts.extend(
        _delta_count_parts(
            "-", len(delta.validate_commands_removed), "validate command"
        )
    )
    if not parts:
        return "Delta: no contract changes"
    return "Delta: " + ", ".join(parts)


def _delta_count_parts(sign: str, count: int, singular: str) -> list[str]:
    if count == 0:
        return []
    noun = singular if count == 1 else f"{singular}s"
    return [f"{sign}{count} {noun}"]


def _format_agent(agent) -> str:
    details = []
    if agent.provider:
        details.append(f"provider={agent.provider}")
    if agent.client:
        details.append(f"client={agent.client}")
    if agent.skills:
        details.append(f"skills={','.join(agent.skills)}")
    if agent.instructions_fingerprint:
        details.append(f"instructions={agent.instructions_fingerprint}")
    if agent.source:
        details.append(f"source={agent.source}")
    suffix = f" ({'; '.join(details)})" if details else ""
    return f"{agent.model}{suffix}"


def _cmd_plan_revise_test_only_green(
    *,
    ctx,
    existing,
    reason: str,
    agent,
) -> int:
    """Revise with honest green evidence for test-only writable contracts."""
    from maid_runner.core._file_discovery import is_test_file
    from maid_runner.core.manifest import load_manifest
    from maid_runner.core.plan_lock import (
        capture_red_phase_evidence,
        revise_plan_lock,
        _load_locked_contract,
    )

    try:
        manifest = load_manifest(ctx.manifest_path)
        non_test_writable = sorted(
            normalized_path
            for path in manifest.all_writable_paths
            for normalized_path in [path.replace("\\", "/")]
            if not is_test_file(normalized_path)
        )
        if non_test_writable:
            print_error(
                "--test-only-green requires every writable path to be a test file. "
                "Use --stash-implementation or --preserve-red-evidence for contracts "
                "with implementation files. Non-test writable path(s): "
                + ", ".join(non_test_writable),
                json_mode=ctx.json_mode,
            )
            return 2

        revised = revise_plan_lock(
            existing,
            ctx.manifest_path,
            ctx.project_root,
            reason,
            agent=agent,
            prior_contract=_load_locked_contract(ctx.lock_path),
        )
        captured = capture_red_phase_evidence(ctx.manifest_path, ctx.project_root)
        failing = [
            command
            for command in captured.commands
            if command.classification != "not_red"
        ]
        if failing:
            tails = "\n".join(
                f"{command.command}: exit {command.exit_code}\n{command.output_tail}"
                for command in failing
            )
            print_error(
                "--test-only-green requires all validate commands to pass.\n" + tails,
                json_mode=ctx.json_mode,
            )
            return 1

        evidence = captured.to_payload()
        evidence["red"] = False
        evidence["mode"] = "test_only_green"
        revised = replace(revised, red_evidence=evidence)
        revised.save(ctx.lock_path)
        print(
            f"Revised plan lock for '{ctx.slug}' to revision {revised.revision} "
            f"({ctx.lock_path})"
        )
        print("Recorded test-only-green evidence for a test-only contract.")
        return 0
    except _plan_input_errors() as exc:
        print_error(str(exc), json_mode=ctx.json_mode)
        return 2


def _cmd_plan_revise_with_stashed_implementation(
    *,
    ctx: "_PlanContext",
    existing,
    reason: str,
    agent,
    allow_sibling_dirty: bool,
) -> int:
    """Revise a lock after temporarily stashing declared implementation files."""
    from maid_runner.core.manifest import load_manifest
    from maid_runner.core.plan_lock import (
        capture_red_phase_evidence,
        revise_plan_lock,
        _load_locked_contract,
    )

    try:
        manifest = load_manifest(ctx.manifest_path)
        manifest_rel = _project_relative(ctx.manifest_path, ctx.project_root)
        lock_rel = _project_relative(ctx.lock_path, ctx.project_root)
        behavioral_test_paths = _behavioral_test_paths_for_revise(manifest)
        contracted_writable_paths = {
            normalized_path
            for path in (
                [fs.path for fs in manifest.files_create]
                + [fs.path for fs in manifest.files_edit]
                + [ds.path for ds in manifest.files_delete]
                + [fs.path for fs in manifest.files_snapshot]
            )
            for normalized_path in [path.replace("\\", "/")]
            if normalized_path not in behavioral_test_paths
        }
        read_stash_paths = (
            {
                normalized_path
                for path in manifest.files_read
                for normalized_path in [path.replace("\\", "/")]
                if normalized_path not in behavioral_test_paths
            }
            if contracted_writable_paths
            else set()
        )
        read_stash_paths.discard(manifest_rel)
        read_stash_paths.discard(lock_rel)
        target_paths = tuple(
            sorted(
                normalized_path
                for path in manifest.all_writable_paths | read_stash_paths
                for normalized_path in [path.replace("\\", "/")]
                if normalized_path not in behavioral_test_paths
            )
        )
        if not target_paths:
            print_error(
                "--stash-implementation requires at least one declared non-test "
                "implementation file. For test-only contracts, use --test-only-green.",
                json_mode=ctx.json_mode,
            )
            return 2

        dirty_entries = _git_dirty_entries(ctx.project_root)
        allowed_dirty_paths = set(target_paths)
        allowed_dirty_paths.add(manifest_rel)
        allowed_dirty_paths.add(lock_rel)
        allowed_dirty_paths.update(behavioral_test_paths)
        allowed_dirty_paths.update(
            _same_task_lifecycle_dirty_paths(
                ctx.project_root, ctx.manifest_path, dirty_entries
            )
        )
        declared_surface_paths = {
            path.replace("\\", "/")
            for path in manifest.all_writable_paths | set(manifest.files_read)
        }
        declared_surface_paths.add(manifest_rel)
        declared_surface_paths.add(lock_rel)
        declared_surface_paths.update(behavioral_test_paths)
        own_surface_conflicts = sorted(
            entry.path
            for entry in dirty_entries
            if entry.path not in allowed_dirty_paths
            and entry.path in declared_surface_paths
        )
        sibling_dirty_paths = sorted(
            entry.path
            for entry in dirty_entries
            if entry.path not in allowed_dirty_paths
            and entry.path not in declared_surface_paths
        )
        refused_dirty_paths = own_surface_conflicts + (
            sibling_dirty_paths if not allow_sibling_dirty else []
        )
        if refused_dirty_paths:
            own_surface_detail = (
                " --allow-sibling-dirty applies only outside the manifest's own "
                "declared surface."
                if own_surface_conflicts
                else ""
            )
            print_error(
                "--stash-implementation refuses unrelated dirty path(s): "
                + ", ".join(sorted(refused_dirty_paths))
                + ". Declare narrow wiring files under files.read to include "
                "them in the targeted stash, or use --allow-sibling-dirty to "
                "tolerate and audit sibling-manifest work." + own_surface_detail,
                json_mode=ctx.json_mode,
            )
            return 2

        dirty_target_entries = [
            entry for entry in dirty_entries if entry.path in set(target_paths)
        ]
        if not dirty_target_entries:
            print_error(
                "--stash-implementation found no dirty declared implementation "
                "paths to stash.",
                json_mode=ctx.json_mode,
            )
            return 2
        staged_targets = [
            entry.path
            for entry in dirty_target_entries
            if entry.index_status not in (" ", "?")
        ]
        intent_to_add_targets = [
            entry.path
            for entry in dirty_target_entries
            if entry.index_status == " " and entry.worktree_status == "A"
        ]
        if intent_to_add_targets:
            reset_command = shlex.join(
                ["git", "reset", "--", *sorted(intent_to_add_targets)]
            )
            print_error(
                "--stash-implementation refuses intent-to-add implementation "
                "path(s): "
                + ", ".join(sorted(intent_to_add_targets))
                + f". Return them to plain untracked state with `{reset_command}` "
                "and retry.",
                json_mode=ctx.json_mode,
            )
            return 2
        if staged_targets:
            restore_command = shlex.join(
                ["git", "restore", "--staged", *sorted(staged_targets)]
            )
            print_error(
                "--stash-implementation refuses staged implementation path(s): "
                + ", ".join(sorted(staged_targets))
                + f". Unstage them with `{restore_command}` and retry.",
                json_mode=ctx.json_mode,
            )
            return 2

        before_stash_hashes = {
            entry.commit_hash for entry in _git_stash_entries(ctx.project_root)
        }
        dirty_target_paths = tuple(
            entry.path
            for entry in dirty_target_entries
            if entry.path in set(target_paths)
        )
        stash_message = f"maid plan revise --stash-implementation {uuid.uuid4().hex}"
        _git(
            ctx.project_root,
            "stash",
            "push",
            "--include-untracked",
            "--message",
            stash_message,
            "--",
            *dirty_target_paths,
        )
        created_stash = _created_stash_entry(
            ctx.project_root, stash_message, before_stash_hashes
        )
        if created_stash is None:
            print_error(
                "--stash-implementation could not create a targeted stash.",
                json_mode=ctx.json_mode,
            )
            return 2

        contract_hashes = _contract_hashes_for_stash_revise(
            ctx.project_root, ctx.manifest_path, manifest
        )
        stash_hash = created_stash.commit_hash
        restored = False
        try:
            revised = revise_plan_lock(
                existing,
                ctx.manifest_path,
                ctx.project_root,
                reason,
                agent=agent,
                prior_contract=_load_locked_contract(ctx.lock_path),
            )
            evidence = capture_red_phase_evidence(
                ctx.manifest_path, ctx.project_root
            ).to_payload()
            if (
                _contract_hashes_for_stash_revise(
                    ctx.project_root, ctx.manifest_path, manifest
                )
                != contract_hashes
            ):
                print_error(
                    "--stash-implementation refuses to save because validation "
                    "changed the manifest or behavioral tests.",
                    json_mode=ctx.json_mode,
                )
                return 2
            if not _red_evidence_payload_is_valid(evidence):
                if _includes_dependency_lockfile(dirty_target_paths):
                    print_error(
                        "--stash-implementation did not capture valid red evidence "
                        "because materialized dependency state (node_modules, .venv, "
                        "or vendor) is not stashed with dependency lockfiles. "
                        "Temporarily install the prior dependency state and use plain "
                        "plan revise, or record a reasoned legacy baseline.",
                        json_mode=ctx.json_mode,
                    )
                else:
                    print_error(
                        "--stash-implementation did not capture valid red evidence.",
                        json_mode=ctx.json_mode,
                    )
                return 1
            if allow_sibling_dirty:
                evidence["sibling_dirty_paths"] = list(sibling_dirty_paths)
            _restore_stash_entry(ctx.project_root, stash_hash, target_paths)
            restored = True
            revised = replace(revised, red_evidence=evidence)
            revised.save(ctx.lock_path)
            print(
                f"Revised plan lock for '{ctx.slug}' to revision {revised.revision} "
                f"({ctx.lock_path})"
            )
            if allow_sibling_dirty:
                print(
                    "Tolerated sibling dirty paths: "
                    + (
                        ", ".join(sibling_dirty_paths)
                        if sibling_dirty_paths
                        else "none"
                    )
                )
            return 0
        finally:
            if not restored:
                _restore_stash_entry(ctx.project_root, stash_hash, target_paths)
    except _plan_input_errors() as exc:
        print_error(str(exc), json_mode=ctx.json_mode)
        return 2
    except _GitCommandError as exc:
        print_error(str(exc), json_mode=ctx.json_mode)
        return 2


class _GitCommandError(Exception):
    """Expected git command failure for stash-backed plan revise."""


_DEPENDENCY_LOCKFILE_BASENAMES = {
    "package.json",
    "package-lock.json",
    "bun.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    "uv.lock",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
}


def _includes_dependency_lockfile(paths: tuple[str, ...]) -> bool:
    return any(Path(path).name in _DEPENDENCY_LOCKFILE_BASENAMES for path in paths)


class _DirtyEntry:
    """One parsed porcelain status entry."""

    def __init__(self, index_status: str, worktree_status: str, path: str) -> None:
        self.index_status = index_status
        self.worktree_status = worktree_status
        self.path = path


class _StashEntry:
    """One parsed stash list entry."""

    def __init__(self, commit_hash: str, ref: str, subject: str) -> None:
        self.commit_hash = commit_hash
        self.ref = ref
        self.subject = subject


def _git(project_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise _GitCommandError(
            "--stash-implementation requires available Git metadata."
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise _GitCommandError(
            "--stash-implementation git command failed"
            + (f": {detail}" if detail else ".")
        )
    return result.stdout


def _git_dirty_entries(project_root: Path) -> tuple[_DirtyEntry, ...]:
    _git(project_root, "rev-parse", "--is-inside-work-tree")
    output = _git(
        project_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    parts = [part for part in output.split("\0") if part]
    entries: list[_DirtyEntry] = []
    i = 0
    while i < len(parts):
        item = parts[i]
        if len(item) < 4:
            i += 1
            continue
        index_status = item[0]
        worktree_status = item[1]
        path = item[3:].replace("\\", "/")
        entries.append(_DirtyEntry(index_status, worktree_status, path))
        if index_status in ("R", "C"):
            i += 2
        else:
            i += 1
    return tuple(entries)


def _git_stash_list(project_root: Path) -> tuple[str, ...]:
    output = _git(project_root, "stash", "list")
    return tuple(line for line in output.splitlines() if line.strip())


def _git_stash_entries(project_root: Path) -> tuple[_StashEntry, ...]:
    output = _git(project_root, "stash", "list", "--format=%H%x09%gd%x09%gs")
    entries: list[_StashEntry] = []
    for line in output.splitlines():
        parts = line.split("\t", maxsplit=2)
        if len(parts) == 3:
            entries.append(_StashEntry(parts[0], parts[1], parts[2]))
    return tuple(entries)


def _created_stash_entry(
    project_root: Path, message: str, before_hashes: set[str]
) -> _StashEntry | None:
    matches = [
        entry
        for entry in _git_stash_entries(project_root)
        if message in entry.subject and entry.commit_hash not in before_hashes
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _stash_ref_for_hash(project_root: Path, commit_hash: str) -> str | None:
    for entry in _git_stash_entries(project_root):
        if entry.commit_hash == commit_hash:
            return entry.ref
    return None


def _restore_stash_entry(
    project_root: Path, stash_hash: str, target_paths: tuple[str, ...]
) -> None:
    dirty_target_paths = sorted(
        entry.path
        for entry in _git_dirty_entries(project_root)
        if entry.path in set(target_paths)
    )
    if dirty_target_paths:
        raise _GitCommandError(
            "--stash-implementation cannot restore because validation dirtied "
            "target path(s): " + ", ".join(dirty_target_paths)
        )
    _git(project_root, "stash", "apply", "--quiet", stash_hash)
    stash_ref = _stash_ref_for_hash(project_root, stash_hash)
    if stash_ref is None:
        raise _GitCommandError(
            "--stash-implementation restored changes but could not find the "
            "created stash entry to drop."
        )
    _git(project_root, "stash", "drop", "--quiet", stash_ref)


def _project_relative(path: Path, project_root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(project_root).resolve()).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")


def _behavioral_test_paths_for_revise(manifest) -> set[str]:
    from maid_runner.core.manifest import _is_test_file
    from maid_runner.core.types import ArtifactKind

    paths = {
        normalized_path
        for path in set(manifest.files_read) | manifest.all_writable_paths
        for normalized_path in [path.replace("\\", "/")]
        if _is_test_file(normalized_path)
    }
    paths.update(
        normalized_path
        for fs in manifest.all_file_specs
        for normalized_path in [fs.path.replace("\\", "/")]
        if any(artifact.kind == ArtifactKind.TEST_FUNCTION for artifact in fs.artifacts)
    )
    return paths


def _same_task_lifecycle_dirty_paths(
    project_root: Path, manifest_path: Path, dirty_entries: tuple[_DirtyEntry, ...]
) -> set[str]:
    manifest_rel = _project_relative(manifest_path, project_root)
    paths: set[str] = set()
    for entry in dirty_entries:
        if _is_matching_active_manifest_marker(project_root, manifest_rel, entry):
            paths.add(entry.path)
        if _is_matching_promoted_draft_deletion(project_root, manifest_rel, entry):
            paths.add(entry.path)
    return paths


def _is_matching_active_manifest_marker(
    project_root: Path, manifest_rel: str, entry: _DirtyEntry
) -> bool:
    if entry.path != ".maid/active-manifest":
        return False
    if entry.index_status not in (" ", "?"):
        return False
    marker_path = project_root / entry.path
    if not marker_path.is_file():
        return False
    try:
        first_line = marker_path.read_text().splitlines()[0].strip()
    except (IndexError, OSError, UnicodeDecodeError):
        return False
    return first_line == manifest_rel


def _is_matching_promoted_draft_deletion(
    project_root: Path, manifest_rel: str, entry: _DirtyEntry
) -> bool:
    manifest_parts = Path(manifest_rel).parts
    if len(manifest_parts) != 2 or manifest_parts[0] != "manifests":
        return False
    expected_draft = f"manifests/drafts/{manifest_parts[1]}"
    if entry.path != expected_draft:
        return False
    if entry.index_status != " " or entry.worktree_status != "D":
        return False
    return (project_root / manifest_rel).is_file() and not (
        project_root / entry.path
    ).exists()


def _contract_hashes_for_stash_revise(
    project_root: Path, manifest_path: Path, manifest
) -> dict[str, str | None]:
    from maid_runner.core.supersession_audit import compute_manifest_hash

    paths = {_project_relative(manifest_path, project_root)}
    paths.update(_behavioral_test_paths_for_revise(manifest))
    hashes: dict[str, str | None] = {}
    for rel_path in sorted(paths):
        full_path = project_root / rel_path
        hashes[rel_path] = (
            compute_manifest_hash(full_path) if full_path.exists() else None
        )
    return hashes


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
