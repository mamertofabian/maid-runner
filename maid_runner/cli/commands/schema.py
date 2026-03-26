"""CLI handler for 'maid schema' command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def cmd_schema(args: argparse.Namespace) -> int:
    schema_dir = Path(__file__).parent.parent.parent / "schemas"
    schema_file = schema_dir / f"manifest.v{args.version}.schema.json"

    if not schema_file.exists():
        print(f"Error: Schema v{args.version} not found at {schema_file}")
        return 2

    print(json.dumps(json.loads(schema_file.read_text()), indent=2))
    return 0
