"""Main CLI entry point for CC MAID Agent."""

import argparse
import sys
from pathlib import Path

from maid_agents.agents.refactorer import Refactorer
from maid_agents.claude.cli_wrapper import ClaudeWrapper
from maid_agents.core.orchestrator import MAIDOrchestrator


def main() -> None:
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

    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock mode instead of real Claude CLI",
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
    plan_parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum planning iterations (default: 10)",
    )

    # Implement subcommand
    implement_parser = subparsers.add_parser(
        "implement",
        help="Implement from manifest (Phase 3)",
    )
    implement_parser.add_argument("manifest_path", help="Path to manifest file")
    implement_parser.add_argument(
        "--max-iterations",
        type=int,
        default=20,
        help="Maximum implementation iterations (default: 20)",
    )

    # Refactor subcommand
    refactor_parser = subparsers.add_parser(
        "refactor",
        help="Refactor code to improve quality (Phase 3.5)",
    )
    refactor_parser.add_argument("manifest_path", help="Path to manifest file")

    # Refine subcommand
    refine_parser = subparsers.add_parser(
        "refine",
        help="Refine manifest and tests with validation loop (Phase 2 quality gate)",
    )
    refine_parser.add_argument("manifest_path", help="Path to manifest file")
    refine_parser.add_argument(
        "--goal",
        required=True,
        help="Refinement goals/objectives",
    )
    refine_parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum refinement iterations (default: 5)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Create Claude wrapper and orchestrator
    # Default to REAL Claude (mock_mode=False) unless --mock flag is used
    claude = ClaudeWrapper(mock_mode=getattr(args, "mock", False))
    orchestrator = MAIDOrchestrator(claude=claude)

    if args.command == "run":
        print(f"🚀 Running full MAID workflow for: {args.goal}")
        result = orchestrator.run_full_workflow(args.goal)
        if result.success:
            print(f"✅ {result.message}")
            print(f"📄 Manifest: {result.manifest_path}")
            sys.exit(0)
        else:
            print(f"❌ {result.message}")
            sys.exit(1)

    elif args.command == "plan":
        print(f"📋 Planning: {args.goal}")
        result = orchestrator.run_planning_loop(
            goal=args.goal, max_iterations=args.max_iterations
        )
        if result["success"]:
            print(f"✅ Planning complete in {result['iterations']} iteration(s)")
            print(f"📄 Manifest: {result['manifest_path']}")
            print(f"🧪 Tests: {', '.join(result['test_paths'])}")
            sys.exit(0)
        else:
            print(f"❌ Planning failed after {result['iterations']} iteration(s)")
            print(f"Error: {result['error']}")
            sys.exit(1)

    elif args.command == "implement":
        manifest_path = args.manifest_path
        if not Path(manifest_path).exists():
            print(f"❌ Manifest not found: {manifest_path}")
            sys.exit(1)

        print(f"⚙️ Implementing: {manifest_path}")
        result = orchestrator.run_implementation_loop(
            manifest_path=manifest_path, max_iterations=args.max_iterations
        )
        if result["success"]:
            print(f"✅ Implementation complete in {result['iterations']} iteration(s)")
            print(f"📝 Files modified: {', '.join(result['files_modified'])}")
            sys.exit(0)
        else:
            print(f"❌ Implementation failed after {result['iterations']} iteration(s)")
            print(f"Error: {result['error']}")
            sys.exit(1)

    elif args.command == "refactor":
        manifest_path = args.manifest_path
        if not Path(manifest_path).exists():
            print(f"❌ Manifest not found: {manifest_path}")
            sys.exit(1)

        print(f"✨ Refactoring: {manifest_path}")
        refactorer = Refactorer(claude)
        result = refactorer.refactor(manifest_path=manifest_path)

        if result["success"]:
            print("✅ Refactoring complete!")
            print(f"📝 Files affected: {', '.join(result['files_affected'])}")
            print(f"💡 Improvements ({len(result['improvements'])}):")
            for i, improvement in enumerate(result["improvements"], 1):
                print(f"   {i}. {improvement}")
            sys.exit(0)
        else:
            print("❌ Refactoring failed")
            print(f"Error: {result['error']}")
            sys.exit(1)

    elif args.command == "refine":
        manifest_path = args.manifest_path
        if not Path(manifest_path).exists():
            print(f"❌ Manifest not found: {manifest_path}")
            sys.exit(1)

        print(f"🔍 Refining: {manifest_path}")
        print(f"🎯 Goal: {args.goal}")
        result = orchestrator.run_refinement_loop(
            manifest_path=manifest_path,
            refinement_goal=args.goal,
            max_iterations=args.max_iterations,
        )

        if result["success"]:
            print(f"✅ Refinement complete in {result['iterations']} iteration(s)!")
            print(f"💡 Improvements ({len(result.get('improvements', []))}):")
            for i, improvement in enumerate(result.get("improvements", []), 1):
                print(f"   {i}. {improvement}")
            sys.exit(0)
        else:
            print(f"❌ Refinement failed after {result['iterations']} iteration(s)")
            print(f"Error: {result['error']}")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
