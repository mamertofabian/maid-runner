"""Main CLI entry point for CC MAID Agent."""

import argparse
import sys


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="ccmaid",
        description="Claude Code MAID Agent - Automates MAID workflow",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="ccmaid 0.1.0",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Run full MAID workflow from goal",
    )
    run_parser.add_argument("goal", help="High-level goal description")

    # Plan subcommand
    plan_parser = subparsers.add_parser(
        "plan",
        help="Create manifest and tests (Phases 1-2)",
    )
    plan_parser.add_argument("goal", help="High-level goal description")

    # Implement subcommand
    implement_parser = subparsers.add_parser(
        "implement",
        help="Implement from manifest (Phase 3)",
    )
    implement_parser.add_argument("manifest_path", help="Path to manifest file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        print(f"Would run full workflow for: {args.goal}")
        print("Not yet implemented")
    elif args.command == "plan":
        print(f"Would create plan for: {args.goal}")
        print("Not yet implemented")
    elif args.command == "implement":
        print(f"Would implement: {args.manifest_path}")
        print("Not yet implemented")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
