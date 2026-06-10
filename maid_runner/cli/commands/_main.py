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

    _register_validate_parser(sub)
    _register_test_parser(sub)
    _register_verify_parser(sub)
    _register_plan_parser(sub)
    _register_snapshot_parser(sub)
    _register_snapshot_system_parser(sub)
    _register_bootstrap_parser(sub)
    _register_learn_parser(sub)
    _register_recall_parser(sub)
    _register_insights_parser(sub)
    _register_benchmark_parser(sub)
    _register_manifest_graph_chain_audit_parsers(sub)

    return parser


def _register_validate_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("validate", help="Validate manifests against code")
    p.add_argument("manifest_path", nargs="?", default=None)
    p.add_argument(
        "--mode",
        default="implementation",
        choices=["schema", "behavioral", "implementation"],
    )
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow directory-wide validation to succeed when no active manifests are found",
    )
    p.add_argument("--no-chain", action="store_true")
    p.add_argument(
        "--use-manifest-chain", action="store_true", help=argparse.SUPPRESS
    )  # v1 compat alias (chain is default)
    p.add_argument("--coherence", action="store_true")
    p.add_argument("--coherence-only", action="store_true")
    p.add_argument(
        "--check-assertions",
        action="store_true",
        help="Warn when behavioral tests exercise artifacts without assertions",
    )
    p.add_argument(
        "--check-stubs",
        action="store_true",
        help="Warn when implementation validation finds stubbed artifacts",
    )
    p.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return failure when validation warnings are present",
    )
    p.add_argument(
        "--run-tests",
        action="store_true",
        help="Run manifest validate commands after structural validation succeeds",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Enable assertion checks, stub checks, and warning failure",
    )
    p.add_argument(
        "--file-tracking",
        action="store_true",
        help="Fail validation when undeclared or weakly registered production files exist",
    )
    p.add_argument(
        "--worktree-scope",
        action="store_true",
        help="Fail validation when changed production files are outside writable manifest scope",
    )
    p.add_argument(
        "--changed-scope",
        action="store_true",
        help="Fail validation when files changed since a task baseline are outside writable manifest scope",
    )
    p.add_argument(
        "--since",
        default=None,
        help="Commit-ish to use as the explicit --changed-scope baseline",
    )
    p.add_argument(
        "--base-ref",
        default=None,
        help="Ref whose merge-base with HEAD is used as the --changed-scope baseline",
    )
    p.add_argument(
        "--include-tests",
        action="store_true",
        help="Include changed test files in scope checks",
    )
    p.add_argument(
        "--json", "--json-output", action="store_true"
    )  # --json-output is v1 compat alias
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--watch-all", action="store_true")


def _register_test_parser(sub: argparse._SubParsersAction) -> None:
    from maid_runner.core.test_runner import _positive_jobs_arg

    p = sub.add_parser("test", help="Run validation commands from manifests")
    p.add_argument("--manifest", default=None)
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--fail-fast", action="store_true")
    p.add_argument(
        "--jobs",
        type=_positive_jobs_arg,
        default=1,
        help="Run independent implementation command groups with this many workers",
    )
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


def _register_verify_parser(sub: argparse._SubParsersAction) -> None:
    from maid_runner.core.test_runner import _positive_jobs_arg

    p = sub.add_parser("verify", help="Run the full MAID verification gate")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--allow-empty", action="store_true")
    verify_fast = p.add_mutually_exclusive_group()
    verify_fast.add_argument(
        "--fail-fast",
        action="store_true",
        dest="fail_fast",
        default=True,
        help="Stop after the first failing verification stage",
    )
    verify_fast.add_argument(
        "--keep-going",
        action="store_false",
        dest="fail_fast",
        help="Run remaining verification stages after a failure",
    )
    p.add_argument("--check-assertions", action="store_true")
    p.add_argument("--check-stubs", action="store_true")
    p.add_argument("--fail-on-warnings", action="store_true")
    p.add_argument(
        "--strict",
        action="store_true",
        help="Enable assertion checks, stub checks, and warning failure",
    )
    p.add_argument(
        "--advisory",
        action="store_true",
        help="Report verify strictness warnings without failing on warnings",
    )
    p.add_argument(
        "--worktree-scope",
        action="store_true",
        help="Require the git worktree-scope gate",
    )
    verify_changed_scope = p.add_mutually_exclusive_group()
    verify_changed_scope.add_argument(
        "--changed-scope",
        action="store_const",
        const=True,
        default=True,
        dest="changed_scope",
        help="Require the git changed-scope gate from an explicit task baseline (default)",
    )
    verify_changed_scope.add_argument(
        "--no-changed-scope",
        action="store_const",
        const=False,
        dest="changed_scope",
        help="Disable the default changed-scope handoff gate",
    )
    p.add_argument(
        "--since",
        default=None,
        help="Commit-ish to use as the explicit --changed-scope baseline",
    )
    p.add_argument(
        "--base-ref",
        default=None,
        help="Ref whose merge-base with HEAD is used as the --changed-scope baseline",
    )
    p.add_argument(
        "--include-tests",
        action="store_true",
        help="Include changed test files in scope gates",
    )
    p.add_argument(
        "--test-jobs",
        type=_positive_jobs_arg,
        default=1,
        help="Run the verify tests stage with this many test command workers",
    )
    p.add_argument("--json", action="store_true")


def _register_plan_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("plan", help="Tamper-evident plan lock operations")
    psub = p.add_subparsers(dest="plan_command")
    lp = psub.add_parser("lock", help="Create a plan lock for a manifest")
    lp.add_argument("manifest_path")
    lp.add_argument("--no-run", action="store_true", dest="no_run")
    lp.add_argument("--project-root", default=".", dest="project_root")
    rp = psub.add_parser("revise", help="Re-lock a manifest with a revision reason")
    rp.add_argument("manifest_path")
    rp.add_argument("--reason", default=None)
    rp.add_argument("--no-run", action="store_true", dest="no_run")
    rp.add_argument("--project-root", default=".", dest="project_root")
    sp = psub.add_parser("status", help="Report plan lock state and hash matches")
    sp.add_argument("manifest_path")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--project-root", default=".", dest="project_root")


def _register_snapshot_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("snapshot", help="Generate manifest from existing code")
    p.add_argument("file_path")
    p.add_argument("--output-dir", default="manifests/")
    p.add_argument("--output", default=None)
    p.add_argument("--with-tests", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")


def _register_snapshot_system_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("snapshot-system", help="Generate system-wide manifest")
    p.add_argument("--output", default=None)
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--json", action="store_true")


def _register_bootstrap_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("bootstrap", help="Bootstrap MAID for an existing project")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument("--output-dir", default="manifests/")
    p.add_argument("--exclude", action="append", default=None)
    p.add_argument("--no-gitignore", action="store_true")
    p.add_argument("--rank", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--include-private", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--verbose", action="store_true")


def _register_learn_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("learn", help="Refresh the deterministic Outcome index")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--output", default=".maid/outcomes.json")
    p.add_argument(
        "--include-status",
        action="append",
        default=None,
        dest="include_status",
        help="Outcome status to index; replaces the completed-only default",
    )
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")


def _register_recall_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("recall", help="Search the deterministic Outcome index")
    p.add_argument("--index", default=".maid/outcomes.json")
    p.add_argument("--text", default=None)
    p.add_argument("--tag", action="append", default=None)
    p.add_argument("--path", action="append", default=None)
    p.add_argument("--artifact", action="append", default=None)
    p.add_argument("--validation-command", action="append", default=None)
    p.add_argument("--review-text", default=None)
    p.add_argument("--manifest-slug", action="append", default=None)
    p.add_argument("--manifest-dir", default=None)
    p.add_argument("--project-root", default=None)
    p.add_argument("--allow-stale-index", action="store_true")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")


def _register_insights_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("insights", help="Aggregate deterministic Outcome insights")
    p.add_argument("--index", default=".maid/outcomes.json")
    p.add_argument("--manifest-dir", default=None)
    p.add_argument("--project-root", default=None)
    p.add_argument("--allow-stale-index", action="store_true")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")


def _register_benchmark_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "benchmark",
        help="Run local benchmark timings for MAID validation gates",
    )
    p.add_argument("projects", nargs="*", help="Project paths to benchmark")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument(
        "--command-prefix",
        action="append",
        default=[],
        help="Prefix each measured command, repeat for multiple words",
    )
    p.add_argument(
        "--repeat",
        type=_positive_repeat_arg,
        default=1,
        help="Run the full benchmark matrix this many times per project",
    )
    p.add_argument("--json-output", default=None)
    p.add_argument("--markdown-output", default=None)
    p.add_argument("--json", action="store_true")


def _positive_repeat_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("repeat must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("repeat must be a positive integer")
    return parsed


def _register_manifest_graph_chain_audit_parsers(
    sub: argparse._SubParsersAction,
) -> None:
    _register_manifest_parser(sub)
    _register_manifests_parser(sub)
    _register_files_parser(sub)
    _register_init_parser(sub)
    _register_graph_parser(sub)
    _register_coherence_parser(sub)
    _register_schema_parser(sub)
    _register_howto_parser(sub)
    _register_chain_parser(sub)
    _register_serve_parser(sub)
    _register_audit_parser(sub)


def _register_manifest_parser(sub: argparse._SubParsersAction) -> None:
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
    cp.add_argument(
        "--temptation",
        dest="temptations",
        action="append",
        default=None,
        help="Add task-specific anti-gaming guidance as 'risk::instead'.",
    )
    pp = msub.add_parser("promote", help="Promote a draft manifest")
    pp.add_argument("manifest_path")
    pp.add_argument("--output-dir", default="manifests/")
    pp.add_argument("--json", action="store_true")
    fdp = msub.add_parser(
        "from-diff", help="Generate a draft manifest from git diff scope"
    )
    fdp.add_argument("--since", default=None)
    fdp.add_argument("--base-ref", default=None, dest="base_ref")
    fdp.add_argument("--worktree", action="store_true")
    fdp.add_argument("--slug", default=None)
    fdp.add_argument("--output", default=None)
    fdp.add_argument("--force", action="store_true")
    fdp.add_argument("--dry-run", action="store_true")
    fdp.add_argument("--json", action="store_true")


def _register_manifests_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("manifests", help="List manifests referencing a file")
    p.add_argument("file_path")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")


def _register_files_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("files", help="Show file tracking status")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--hide-private", action="store_true")
    p.add_argument(
        "--fail-on",
        action="append",
        choices=["undeclared", "registered", "any"],
        default=None,
        help="Return 1 when the selected file-tracking status is present",
    )
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")


def _register_init_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("init", help="Initialize MAID in a project")
    p.add_argument(
        "--tool",
        default="auto",
        choices=["claude", "codex", "cursor", "windsurf", "generic", "auto"],
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")


def _register_graph_parser(sub: argparse._SubParsersAction) -> None:
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


def _register_coherence_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("coherence", help="Run coherence checks")
    p.add_argument("--manifest-dir", default="manifests/")
    p.add_argument("--checks", default=None)
    p.add_argument("--exclude", default=None)
    p.add_argument("--json", action="store_true")


def _register_schema_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("schema", help="Display manifest JSON Schema")
    p.add_argument("--version", default="2", dest="version")


def _register_howto_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("howto", help="Show MAID workflow guidance")
    p.add_argument("--section", dest="topic")
    p.add_argument("topic", nargs="?", default=argparse.SUPPRESS)


def _register_chain_parser(sub: argparse._SubParsersAction) -> None:
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


def _register_serve_parser(sub: argparse._SubParsersAction) -> None:
    from maid_runner.cli.commands.serve import register_serve_subparser

    register_serve_subparser(sub)


def _register_audit_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("audit", help="Audit MAID manifests for systemic issues")
    asub = p.add_subparsers(dest="audit_command")
    aup = asub.add_parser(
        "supersessions",
        help="Audit supersession artifact preservation",
    )
    aup.add_argument("--manifest-dir", default="manifests/")
    aup.add_argument("--lock", default=None)
    aup.add_argument("--seal", action="store_true")
    aup.add_argument("--unseal", action="store_true")
    aup.add_argument("--json", action="store_true")
    aup.add_argument("--quiet", action="store_true")
    aup.add_argument("--project-root", default=".", dest="project_root")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    dispatch = {
        "validate": "_cmd_validate",
        "test": "_cmd_test",
        "verify": "_cmd_verify",
        "plan": "_cmd_plan",
        "snapshot": "_cmd_snapshot",
        "snapshot-system": "_cmd_snapshot_system",
        "bootstrap": "_cmd_bootstrap",
        "learn": "_cmd_learn",
        "recall": "_cmd_recall",
        "insights": "_cmd_insights",
        "benchmark": "_cmd_benchmark",
        "manifest": "_cmd_manifest",
        "manifests": "_cmd_manifests",
        "files": "_cmd_files",
        "init": "_cmd_init",
        "graph": "_cmd_graph",
        "coherence": "_cmd_coherence",
        "schema": "_cmd_schema",
        "howto": "_cmd_howto",
        "chain": "_cmd_chain",
        "audit": "_cmd_audit",
        "serve": "_cmd_serve",
    }

    handler_name = dispatch.get(args.command)
    if handler_name is None:
        parser.print_help()
        return 2

    # Lazy import command handlers
    from maid_runner.cli.commands import (
        validate as validate_mod,
        test as test_mod,
        verify as verify_mod,
        plan as plan_mod,
        snapshot as snapshot_mod,
        bootstrap as bootstrap_mod,
        learn as learn_mod,
        recall as recall_mod,
        insights as insights_mod,
        benchmark as benchmark_mod,
        init as init_mod,
        manifest as manifest_mod,
        files as files_mod,
        graph as graph_mod,
        coherence as coherence_mod,
        schema as schema_mod,
        howto as howto_mod,
        chain as chain_mod,
        audit as audit_mod,
        serve as serve_mod,
    )

    handlers = {
        "_cmd_validate": validate_mod.cmd_validate,
        "_cmd_test": test_mod.cmd_test,
        "_cmd_verify": verify_mod.cmd_verify,
        "_cmd_plan": plan_mod.cmd_plan,
        "_cmd_snapshot": snapshot_mod.cmd_snapshot,
        "_cmd_snapshot_system": snapshot_mod.cmd_snapshot_system,
        "_cmd_bootstrap": bootstrap_mod.cmd_bootstrap,
        "_cmd_learn": learn_mod.cmd_learn,
        "_cmd_recall": recall_mod.cmd_recall,
        "_cmd_insights": insights_mod.cmd_insights,
        "_cmd_benchmark": benchmark_mod.cmd_benchmark,
        "_cmd_manifest": manifest_mod.cmd_manifest,
        "_cmd_manifests": files_mod.cmd_manifests,
        "_cmd_files": files_mod.cmd_files,
        "_cmd_init": init_mod.cmd_init,
        "_cmd_graph": graph_mod.cmd_graph,
        "_cmd_coherence": coherence_mod.cmd_coherence,
        "_cmd_schema": schema_mod.cmd_schema,
        "_cmd_howto": howto_mod.cmd_howto,
        "_cmd_chain": chain_mod.cmd_chain,
        "_cmd_audit": audit_mod.cmd_audit,
        "_cmd_serve": serve_mod.cmd_serve,
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
