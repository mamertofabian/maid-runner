"""CLI handler for deterministic Outcome recall."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from maid_runner.core.outcome_recall import (
    ManifestQuerySignal,
    OutcomeRecallQuery,
    derive_recall_query,
    recall_outcomes,
)
from maid_runner.core.outcomes import outcome_index_is_stale, read_outcome_index


def cmd_recall(args: argparse.Namespace) -> int:
    index_path = Path(args.index)
    if not index_path.exists():
        return _error(f"Outcome index not found: {index_path}", args)

    try:
        index = read_outcome_index(index_path)
    except Exception as exc:
        return _error(str(exc), args)

    project_root = (
        args.project_root if args.project_root is not None else index.project_root
    )
    manifest_dir = (
        args.manifest_dir
        if args.manifest_dir is not None
        else _index_manifest_dir(index.manifest_dir, project_root)
    )
    if not getattr(args, "allow_stale_index", False):
        try:
            if outcome_index_is_stale(index_path, manifest_dir, project_root):
                return _error(
                    "Outcome index is stale; run `maid learn` or pass "
                    "--allow-stale-index",
                    args,
                )
        except Exception as exc:
            return _error(f"Outcome index staleness check failed: {exc}", args)

    derivation = None
    try:
        if getattr(args, "for_manifest", None):
            manual_flags = _manual_query_filter_flags(args)
            if manual_flags:
                raise ValueError(
                    "--for-manifest cannot be combined with manual recall "
                    f"filters: {', '.join(manual_flags)}"
                )
            derivation = derive_recall_query(args.for_manifest, project_root)
            query = derivation.query
        else:
            query = OutcomeRecallQuery(
                text=getattr(args, "text", None),
                tags=tuple(getattr(args, "tag", ()) or ()),
                paths=tuple(getattr(args, "path", ()) or ()),
                artifacts=tuple(getattr(args, "artifact", ()) or ()),
                validation_commands=tuple(
                    getattr(args, "validation_command", ()) or ()
                ),
                review_text=getattr(args, "review_text", None),
                manifest_slugs=tuple(getattr(args, "manifest_slug", ()) or ()),
                project_root=project_root,
            )
        matches = recall_outcomes(
            index,
            query,
            limit=getattr(args, "limit", 10),
        )
    except Exception as exc:
        return _error(str(exc), args)

    if getattr(args, "json", False):
        payload = {
            "count": len(matches),
            "matches": [_match_to_dict(match) for match in matches],
        }
        if derivation is not None:
            payload["derived_signals"] = [
                _signal_to_dict(signal) for signal in derivation.signals
            ]
            payload["manifest_path"] = derivation.manifest_path
        print(json.dumps(payload, sort_keys=True))
        return 0

    if derivation is not None:
        print(f"Derived query signals from {derivation.manifest_path}:")
        for signal in derivation.signals:
            print(
                f"  {signal.dimension}: {signal.value} "
                f"(source: {signal.source_field})"
            )

    for match in matches:
        print(f"{match.record.manifest_path} score={match.score}")
        for reason in match.reasons:
            print(f"  reason: {reason}")
        for lesson in match.record.lessons:
            print(f"  lesson: {lesson.summary}")
        for note in match.record.review_notes:
            print(f"  review: {note.source}/{note.severity}: {note.summary}")
    return 0


def _match_to_dict(match) -> dict:
    return {
        "lessons": [lesson.summary for lesson in match.record.lessons],
        "manifest_path": match.record.manifest_path,
        "manifest_slug": match.record.manifest_slug,
        "reasons": list(match.reasons),
        "review_notes": [
            f"{note.source}/{note.severity}: {note.summary}"
            for note in match.record.review_notes
        ],
        "score": match.score,
    }


def _signal_to_dict(signal: ManifestQuerySignal) -> dict:
    return {
        "dimension": signal.dimension,
        "source_field": signal.source_field,
        "value": signal.value,
    }


def _manual_query_filter_flags(args: argparse.Namespace) -> list[str]:
    flags: list[str] = []
    if getattr(args, "text", None):
        flags.append("--text")
    if getattr(args, "tag", None):
        flags.append("--tag")
    if getattr(args, "path", None):
        flags.append("--path")
    if getattr(args, "artifact", None):
        flags.append("--artifact")
    if getattr(args, "validation_command", None):
        flags.append("--validation-command")
    if getattr(args, "review_text", None):
        flags.append("--review-text")
    if getattr(args, "manifest_slug", None):
        flags.append("--manifest-slug")
    return flags


def _error(message: str, args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"error": message}, sort_keys=True))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return 2


def _index_manifest_dir(manifest_dir: str, project_root: str) -> str:
    path = Path(manifest_dir)
    if path.is_absolute():
        return str(path)
    return str(Path(project_root) / path)
