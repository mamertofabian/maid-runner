"""CLI handler for deterministic Outcome recall."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes
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

    try:
        matches = recall_outcomes(
            index,
            OutcomeRecallQuery(
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
            ),
            limit=getattr(args, "limit", 10),
        )
    except Exception as exc:
        return _error(str(exc), args)

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "count": len(matches),
                    "matches": [_match_to_dict(match) for match in matches],
                },
                sort_keys=True,
            )
        )
        return 0

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
