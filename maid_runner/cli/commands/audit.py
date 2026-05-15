"""CLI handler for `maid audit` subcommands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from maid_runner.cli.commands._format import (
    format_supersession_audit,
    print_error,
)


def cmd_audit(args: argparse.Namespace) -> int:
    """Dispatch `maid audit <subcommand>`."""
    sub = getattr(args, "audit_command", None)
    if sub == "supersessions":
        return cmd_audit_supersessions(args)
    print_error(
        f"Unknown audit subcommand: {sub}",
        json_mode=getattr(args, "json", False),
    )
    return 2


def cmd_audit_supersessions(args: argparse.Namespace) -> int:
    """Audit supersession artifact preservation; optionally seal the lock."""
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.supersession_audit import (
        GrandfatherEntry,
        GrandfatherLock,
        _GrandfatherLockLoadError,
        SupersessionAuditor,
        _violation_lock_key,
        compute_manifest_hash,
        default_lock_path,
    )

    project_root = Path(getattr(args, "project_root", "."))
    manifest_dir_raw = Path(args.manifest_dir)
    manifest_dir = (
        manifest_dir_raw
        if manifest_dir_raw.is_absolute()
        else project_root / manifest_dir_raw
    )
    lock_path_arg = getattr(args, "lock", None)
    lock_path = (
        Path(lock_path_arg) if lock_path_arg else default_lock_path(project_root)
    )
    seal = bool(getattr(args, "seal", False))
    unseal = bool(getattr(args, "unseal", False))
    json_mode = bool(getattr(args, "json", False))
    quiet = bool(getattr(args, "quiet", False))

    try:
        chain = ManifestChain(manifest_dir, project_root=project_root)
    except FileNotFoundError:
        print_error(
            f"Manifest directory not found: {manifest_dir}",
            json_mode=json_mode,
        )
        return 2

    if chain.load_errors:
        if json_mode:
            import json as _json

            print(
                _json.dumps(
                    {
                        "error": "chain has load errors; refusing to audit",
                        "load_errors": [e.to_dict() for e in chain.load_errors],
                    },
                    indent=2,
                )
            )
        else:
            print_error(
                f"Refusing to audit: manifest chain has "
                f"{len(chain.load_errors)} load error(s). "
                f"Fix or remove malformed manifests before sealing.",
                json_mode=False,
            )
            for err in chain.load_errors:
                print(f"  {err.code.value} {err.message}")
        return 2

    auditor = SupersessionAuditor(project_root=project_root)
    violations = list(auditor.find_violations(chain))
    existing_lock: Optional[GrandfatherLock]
    try:
        existing_lock = (
            GrandfatherLock.load(lock_path)
            if lock_path.exists()
            else GrandfatherLock.empty()
        )
    except _GrandfatherLockLoadError as exc:
        if seal and unseal:
            existing_lock = GrandfatherLock.empty()
        else:
            print_error(
                f"Grandfather lock at {lock_path} is invalid: {exc.detail}. "
                "Re-run with --seal --unseal to overwrite.",
                json_mode=json_mode,
            )
            return 2

    if seal:
        if existing_lock is not None and existing_lock.is_sealed() and not unseal:
            print_error(
                f"Lock file already sealed at {existing_lock.sealed_at}. "
                "Re-run with --unseal to overwrite.",
                json_mode=json_mode,
            )
            return 2

        from datetime import datetime, timezone

        sealed_at = datetime.now(timezone.utc).isoformat()
        entries_by_slug: dict[str, list[str]] = {}
        path_by_slug: dict[str, str] = {}
        for v in violations:
            lock_key = _violation_lock_key(
                v.superseded_slug, v.file_path, v.artifact_key
            )
            entries_by_slug.setdefault(v.superseding_slug, []).append(lock_key)
            path_by_slug[v.superseding_slug] = v.superseding_manifest_path

        sealed_entries = tuple(
            GrandfatherEntry(
                superseding_slug=slug,
                content_hash=compute_manifest_hash(Path(path_by_slug[slug])),
                dropped_artifact_keys=tuple(keys),
                reason="Legacy migration: grandfathered at seal time",
            )
            for slug, keys in entries_by_slug.items()
        )
        new_lock = GrandfatherLock.empty().with_seal(
            sealed_at=sealed_at, entries=sealed_entries
        )
        new_lock.save(lock_path)
        output = format_supersession_audit(
            violations=[],
            grandfathered_count=sum(
                len(e.dropped_artifact_keys) for e in sealed_entries
            ),
            sealed_at=sealed_at,
            json_mode=json_mode,
        )
        if json_mode or not quiet:
            print(output)
        return 0

    grandfathered_count = 0
    non_grandfathered: list = []
    for v in violations:
        if existing_lock is not None and existing_lock.is_sealed():
            content_hash = compute_manifest_hash(Path(v.superseding_manifest_path))
            lock_key = _violation_lock_key(
                v.superseded_slug, v.file_path, v.artifact_key
            )
            if existing_lock.is_grandfathered(
                v.superseding_slug, content_hash, lock_key
            ):
                grandfathered_count += 1
                continue
        non_grandfathered.append(v)

    from maid_runner.core.validate import ValidationEngine

    engine = ValidationEngine(project_root=project_root)
    removed_artifact_errors = []
    for m in chain.active_manifests():
        if not m.removed_artifacts:
            continue
        removed_artifact_errors.extend(engine.validate_removed_artifacts(m))

    sealed_at = existing_lock.sealed_at if existing_lock else None
    if json_mode:
        import json as _json

        payload = {
            "violations": [
                {
                    "superseding_slug": v.superseding_slug,
                    "superseded_slug": v.superseded_slug,
                    "superseding_manifest_path": v.superseding_manifest_path,
                    "file_path": v.file_path,
                    "artifact_key": v.artifact_key,
                    "artifact_name": v.artifact_name,
                    "artifact_kind": v.artifact_kind,
                }
                for v in non_grandfathered
            ],
            "grandfathered_count": grandfathered_count,
            "sealed_at": sealed_at,
            "removed_artifact_errors": [e.to_dict() for e in removed_artifact_errors],
        }
        print(_json.dumps(payload, indent=2))
    else:
        should_print_summary = not quiet or bool(
            non_grandfathered or removed_artifact_errors
        )
        if should_print_summary:
            output = format_supersession_audit(
                violations=non_grandfathered,
                grandfathered_count=grandfathered_count,
                sealed_at=sealed_at,
                json_mode=False,
            )
            print(output)
        if removed_artifact_errors:
            if should_print_summary:
                print("")
            print(f"Unverifiable removed_artifacts ({len(removed_artifact_errors)}):")
            for err in removed_artifact_errors:
                print(f"  {err.code.value} {err.message}")

    if non_grandfathered or removed_artifact_errors:
        return 1
    return 0
