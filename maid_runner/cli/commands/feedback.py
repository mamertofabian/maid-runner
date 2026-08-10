"""CLI handler for local-only MAID Runner feedback export."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from maid_runner.__version__ import __version__
from maid_runner.core.feedback import build_feedback_bundle, write_feedback_bundle
from maid_runner.core.feedback_intake import (
    aggregate_feedback_bundles,
    read_feedback_bundle,
    write_feedback_intake_report,
)
from maid_runner.core.outcomes import outcome_index_is_stale, read_outcome_index


def cmd_feedback(args: argparse.Namespace) -> int:
    """Handle privacy-bounded local feedback export."""

    if getattr(args, "feedback_command", None) == "aggregate":
        return cmd_feedback_aggregate(args)
    if getattr(args, "feedback_command", None) != "export":
        return _error(
            "Usage: maid feedback export --output <path> or "
            "maid feedback aggregate <bundle>... --output <path>",
            args,
        )

    index_path = Path(args.index)
    if not index_path.exists():
        return _error(f"Outcome index not found: {index_path}", args)

    try:
        index = read_outcome_index(index_path)
        project_root = (
            args.project_root if args.project_root is not None else index.project_root
        )
        manifest_dir = (
            args.manifest_dir
            if args.manifest_dir is not None
            else _index_manifest_dir(index.manifest_dir, project_root)
        )
        if not getattr(args, "allow_stale_index", False) and outcome_index_is_stale(
            index_path,
            manifest_dir,
            project_root,
        ):
            return _error(
                "Outcome index is stale; run `maid learn` or pass "
                "--allow-stale-index",
                args,
            )

        bundle = build_feedback_bundle(index, __version__)
        write_feedback_bundle(
            bundle,
            args.output,
            overwrite=getattr(args, "force", False),
        )
    except FileExistsError:
        return _error(
            f"Output already exists: {args.output}; pass --force to replace it",
            args,
        )
    except Exception as exc:
        return _error(str(exc), args)

    payload = {
        "exported": len(bundle.records),
        "notice": _REVIEW_NOTICE,
        "output": str(args.output),
        "review_required": True,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"Exported {len(bundle.records)} MAID Runner feedback record(s) "
            f"to {args.output}"
        )
        print(f"Review required: {_REVIEW_NOTICE}", file=sys.stderr)
    return 0


def cmd_feedback_aggregate(args: argparse.Namespace) -> int:
    """Validate local bundles and write one advisory intake report."""

    try:
        bundles = tuple(read_feedback_bundle(path) for path in args.inputs)
        report = aggregate_feedback_bundles(bundles)
        write_feedback_intake_report(
            report,
            args.output,
            overwrite=getattr(args, "force", False),
        )
    except FileExistsError:
        return _error(
            f"Output already exists: {args.output}; pass --force to replace it",
            args,
        )
    except Exception as exc:
        return _error(str(exc), args)

    payload = {
        "bundles_received": report.bundles_received,
        "notice": _AGGREGATE_NOTICE,
        "output": str(args.output),
        "records": len(report.records),
        "review_required": True,
        "unique_bundles": report.unique_bundles,
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            f"Aggregated {report.unique_bundles} unique feedback bundle(s) "
            f"into {args.output}"
        )
        print(f"Review required: {_AGGREGATE_NOTICE}", file=sys.stderr)
    return 0


_REVIEW_NOTICE = (
    "Feedback summaries are user-authored text; inspect the local bundle "
    "before sharing it. Export does not submit or upload data."
)
_AGGREGATE_NOTICE = (
    "Aggregation is advisory; inspect authored summaries before use. "
    "Aggregate does not submit data or create MAID changes."
)


def _index_manifest_dir(manifest_dir: str, project_root: str) -> str:
    path = Path(manifest_dir)
    if path.is_absolute():
        return str(path)
    return str(Path(project_root) / path)


def _error(message: str, args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        print(json.dumps({"error": message}, sort_keys=True))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return 2
