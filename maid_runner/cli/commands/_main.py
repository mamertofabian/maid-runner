"""MAID Runner v2 CLI entry point and argument parser."""

from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maid",
        description="MAID Runner - Manifest-driven AI Development validator",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_get_version()}"
    )
    sub = parser.add_subparsers(dest="command")

    # maid validate
    p = sub.add_parser("validate", help="Validate manifests against code")
    p.add_argument("manifest_path", nargs="?", default=None)
    p.add_argument(
        "--mode",
        default="implementation",
        choices=["behavioral", "implementation"],
    )
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--no-chain", action="store_true")
    p.add_argument(
        "--use-manifest-chain", action="store_true", help=argparse.SUPPRESS
    )  # v1 compat alias (chain is default)
    p.add_argument("--coherence", action="store_true")
    p.add_argument("--coherence-only", action="store_true")
    p.add_argument(
        "--json", "--json-output", action="store_true"
    )  # --json-output is v1 compat alias
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--watch-all", action="store_true")

    # maid test
    p = sub.add_parser("test", help="Run validation commands from manifests")
    p.add_argument("--manifest", default=None)
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--fail-fast", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--watch-all", action="store_true")
    batch_group = p.add_mutually_exclusive_group()
    batch_group.add_argument(
        "--batch", action="store_const", const=True, default=None, dest="batch"
    )
    batch_group.add_argument(
        "--no-batch", action="store_const", const=False, dest="batch"
    )

    # maid snapshot
    p = sub.add_parser("snapshot", help="Generate manifest from existing code")
    p.add_argument("file_path")
    p.add_argument("--output-dir", default="manifests/")
    p.add_argument("--output", default=None)
    p.add_argument("--with-tests", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")

    # maid snapshot-system
    p = sub.add_parser("snapshot-system", help="Generate system-wide manifest")
    p.add_argument("--output", default=None)
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--json", action="store_true")

    # maid bootstrap
    p = sub.add_parser("bootstrap", help="Bootstrap MAID for an existing project")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--output-dir", default="manifests/")
    p.add_argument("--exclude", action="append", default=None)
    p.add_argument("--no-gitignore", action="store_true")
    p.add_argument("--include-private", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--verbose", action="store_true")

    # maid manifest create
    p = sub.add_parser("manifest", help="Manifest operations")
    msub = p.add_subparsers(dest="manifest_command")
    cp = msub.add_parser("create", help="Create a new manifest")
    cp.add_argument("file_path")
    cp.add_argument("--goal", required=True)
    cp.add_argument("--type", default="feature", dest="task_type")
    cp.add_argument("--artifacts", default=None)
    cp.add_argument("--output-dir", default="manifests/")
    cp.add_argument("--dry-run", action="store_true")
    cp.add_argument("--json", action="store_true")
    cp.add_argument("--delete", action="store_true")
    cp.add_argument("--rename-to", default=None)

    # maid manifests (list manifests for a file)
    p = sub.add_parser("manifests", help="List manifests referencing a file")
    p.add_argument("file_path")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")

    # maid files
    p = sub.add_parser("files", help="Show file tracking status")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--hide-private", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")

    # maid init
    p = sub.add_parser("init", help="Initialize MAID in a project")
    p.add_argument(
        "--tool",
        default="auto",
        choices=["claude", "cursor", "windsurf", "generic", "auto"],
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")

    # maid graph
    p = sub.add_parser("graph", help="Knowledge graph operations")
    gsub = p.add_subparsers(dest="graph_command")
    gq = gsub.add_parser("query", help="Query the knowledge graph")
    gq.add_argument("question")
    gq.add_argument("--json", action="store_true")
    ge = gsub.add_parser("export", help="Export knowledge graph")
    ge.add_argument("--format", default="json", choices=["json", "dot", "graphml"])
    ge.add_argument("--output", default=None)
    ga = gsub.add_parser("analyze", help="Analyze file dependencies")
    ga.add_argument("file_path")
    ga.add_argument("--json", action="store_true")
    p.add_argument("--manifest-dir", default="manifests/")

    # maid coherence
    p = sub.add_parser("coherence", help="Run coherence checks")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--checks", default=None)
    p.add_argument("--exclude", default=None)
    p.add_argument("--json", action="store_true")

    # maid schema
    p = sub.add_parser("schema", help="Display manifest JSON Schema")
    p.add_argument("--version", default="2", dest="version")

    # maid howto
    p = sub.add_parser("howto", help="Show MAID workflow guidance")
    p.add_argument("--section", dest="topic")
    p.add_argument("topic", nargs="?", default=argparse.SUPPRESS)

    # maid chain
    p = sub.add_parser("chain", help="Manifest chain operations")
    csub = p.add_subparsers(dest="chain_command")
    clp = csub.add_parser("log", help="Show manifest event log")
    clp.add_argument("--manifest-dir", default="manifests/")
    clp.add_argument("--json", action="store_true")
    clp.add_argument("--active", action="store_true")
    clp.add_argument("--until-seq", type=int, default=None, dest="until_seq")
    clp.add_argument("--version-tag", type=str, default=None, dest="version_tag")

    rp = csub.add_parser(
        "replay", help="Preview effective artifacts at a point in time"
    )
    rp.add_argument("--manifest-dir", default="manifests/")
    rp.add_argument("--json", action="store_true")
    rp.add_argument("--until-seq", type=int, default=None, dest="until_seq")
    rp.add_argument("--version-tag", type=str, default=None, dest="version_tag")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    dispatch = {
        "validate": "_cmd_validate",
        "test": "_cmd_test",
        "snapshot": "_cmd_snapshot",
        "snapshot-system": "_cmd_snapshot_system",
        "bootstrap": "_cmd_bootstrap",
        "manifest": "_cmd_manifest",
        "manifests": "_cmd_manifests",
        "files": "_cmd_files",
        "init": "_cmd_init",
        "graph": "_cmd_graph",
        "coherence": "_cmd_coherence",
        "schema": "_cmd_schema",
        "howto": "_cmd_howto",
        "chain": "_cmd_chain",
    }

    handler_name = dispatch.get(args.command)
    if handler_name is None:
        parser.print_help()
        return 2

    # Lazy import command handlers
    from maid_runner.cli.commands import (
        validate as validate_mod,
        test as test_mod,
        snapshot as snapshot_mod,
        bootstrap as bootstrap_mod,
        init as init_mod,
        manifest as manifest_mod,
        files as files_mod,
        graph as graph_mod,
        coherence as coherence_mod,
        schema as schema_mod,
        howto as howto_mod,
        chain as chain_mod,
    )

    handlers = {
        "_cmd_validate": validate_mod.cmd_validate,
        "_cmd_test": test_mod.cmd_test,
        "_cmd_snapshot": snapshot_mod.cmd_snapshot,
        "_cmd_snapshot_system": snapshot_mod.cmd_snapshot_system,
        "_cmd_bootstrap": bootstrap_mod.cmd_bootstrap,
        "_cmd_manifest": manifest_mod.cmd_manifest,
        "_cmd_manifests": files_mod.cmd_manifests,
        "_cmd_files": files_mod.cmd_files,
        "_cmd_init": init_mod.cmd_init,
        "_cmd_graph": graph_mod.cmd_graph,
        "_cmd_coherence": coherence_mod.cmd_coherence,
        "_cmd_schema": schema_mod.cmd_schema,
        "_cmd_howto": howto_mod.cmd_howto,
        "_cmd_chain": chain_mod.cmd_chain,
    }

    handler = handlers[handler_name]
    try:
        return handler(args)
    except Exception as e:
        if getattr(args, "json", False):
            import json

            print(json.dumps({"error": f"Internal error: {e}"}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 2


def _get_version() -> str:
    try:
        from maid_runner.__version__ import __version__

        return __version__
    except Exception:
        return "unknown"
