"""CLI handler for deterministic Outcome learning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from maid_runner.core.outcomes import (
    _build_outcome_index_with_stats,
    read_outcome_index,
    write_outcome_index,
)


def cmd_learn(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    try:
        if output_path.exists():
            read_outcome_index(output_path)
        index, skipped = _build_outcome_index_with_stats(
            args.manifest_dir,
            project_root=".",
            include_statuses=getattr(args, "include_status", None) or None,
        )
        write_outcome_index(index, output_path)
    except Exception as exc:
        if getattr(args, "json", False):
            print(json.dumps({"error": str(exc)}))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 2

    indexed = len(index.records)
    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "generated_from": index.generated_from,
                    "indexed": indexed,
                    "output": str(output_path),
                    "skipped": skipped,
                },
                sort_keys=True,
            )
        )
    elif not getattr(args, "quiet", False):
        print(
            f"Outcome index refreshed: indexed {indexed}, skipped {skipped}, "
            f"output {output_path}"
        )
    return 0
