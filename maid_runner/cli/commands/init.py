"""CLI handler for 'maid init' command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def cmd_init(args: argparse.Namespace) -> int:
    manifest_dir = Path("manifests")
    config_file = Path(".maidrc.yaml")

    if not args.force:
        if manifest_dir.exists() and config_file.exists():
            print(
                "MAID already initialized. Use --force to reinitialize.",
                file=sys.stderr,
            )
            return 2

    if args.dry_run:
        print(f"Would create: {manifest_dir}/")
        print(f"Would create: {config_file}")
        return 0

    manifest_dir.mkdir(exist_ok=True)

    config_content = (
        "# MAID Runner configuration\n"
        "manifest_dir: manifests/\n"
        "schema_version: 2\n"
        "default_validation_mode: implementation\n"
    )

    config_file.write_text(config_content)
    print(f"Initialized MAID in {Path.cwd()}")
    print(f"  Created: {manifest_dir}/")
    print(f"  Created: {config_file}")
    return 0
