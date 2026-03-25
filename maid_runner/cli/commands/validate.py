"""CLI handler for 'maid validate' command."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._format import (
    format_batch_result,
    format_validation_result,
    print_error,
)


def cmd_validate(args: argparse.Namespace) -> int:
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")

    try:
        if args.manifest_path:
            result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
            )
            print(
                format_validation_result(result, json_mode=args.json, quiet=args.quiet)
            )
            return 0 if result.success else 1
        else:
            batch = engine.validate_all(args.manifest_dir, mode=mode)
            print(format_batch_result(batch, json_mode=args.json, quiet=args.quiet))
            return 0 if batch.success else 1
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2
