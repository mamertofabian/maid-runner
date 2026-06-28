"""MAID Runner v2 CLI entry point and argument parser."""

from __future__ import annotations

import argparse
import sys


class _NoAbbrevArgumentParser(argparse.ArgumentParser):
    """Parser that rejects long-option prefix abbreviations.

    Subparsers created via add_subparsers default to the parent's class
    (parser_class=type(self)), so using this class for the root parser
    disables abbreviation for every nested subcommand parser as well.
    Without this, `maid verify --manifest <file>` silently parsed as
    `--manifest-dir <file>` (incident 20260611-141146).
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]


def build_parser() -> argparse.ArgumentParser:
    parser = _NoAbbrevArgumentParser(
        prog="maid",
        description="MAID Runner - Manifest-driven AI Development validator",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_get_version()}"
    )
    sub = parser.add_subparsers(dest="command")

    _register_validate_parser(sub)
    _register_validators_parser(sub)
    _register_test_parser(sub)
    _register_verify_parser(sub)
    _register_plan_parser(sub)
    _register_task_parser(sub)
    _register_hook_parser(sub)
    _register_snapshot_parser(sub)
    _register_snapshot_system_parser(sub)
    _register_bootstrap_parser(sub)
    _register_learn_parser(sub)
    _register_recall_parser(sub)
    _register_insights_parser(sub)
    _register_enrich_parser(sub)
    _register_benchmark_parser(sub)
    _register_incident_parser(sub)
    _register_daemon_parser(sub)
    _register_skills_parser(sub)
    _register_manifest_graph_chain_audit_parsers(sub)

    return parser


def _register_skills_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("skills", help="Manage user-level MAID skills")
    ssub = p.add_subparsers(dest="skills_command")
    install = ssub.add_parser(
        "install", help="Install the user-level maid-onboard skill"
    )
    install.add_argument(
        "--user",
        action="store_true",
        default=True,
        help="Install into the user home (default)",
    )
    install.add_argument(
        "--link",
        action="store_true",
        help="Symlink to the packaged skill instead of copying (dev)",
    )
    install.add_argument(
        "--target-root",
        default=None,
        dest="target_root",
        help="Override the install base directory (default: user home)",
    )


def _register_validators_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("validators", help="List discovered validators")
    p.add_argument("--json", action="store_true", help="Print validator data as JSON")


def _register_validate_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("validate", help="Validate manifests against code")
    p.add_argument("manifest_path", nargs="?", default=None)
    p.add_argument(
        "--mode",
        default="implementation",
        choices=["schema", "behavioral", "implementation"],
        help="Validation mode to run",
    )
    p.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of active manifests"
    )
    p.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow directory-wide validation to succeed when no active manifests are found",
    )
    p.add_argument(
        "--no-chain",
        action="store_true",
        help="Validate the selected manifest without manifest-chain merging",
    )
    p.add_argument(
        "--use-manifest-chain", action="store_true", help=argparse.SUPPRESS
    )  # v1 compat alias (chain is default)
    p.add_argument(
        "--coherence",
        action="store_true",
        help="Run coherence checks after manifest validation",
    )
    p.add_argument(
        "--coherence-only",
        action="store_true",
        help="Run coherence checks without structural manifest validation",
    )
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
        "--artifact-coverage",
        action="store_true",
        help="Run validate commands under coverage and require declared artifacts to execute",
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
        "--json",
        "--json-output",
        action="store_true",
        help="Print validation results as JSON",
    )  # --json-output is v1 compat alias
    p.add_argument(
        "--packet",
        nargs="?",
        const=".maid/last-failure-packet.json",
        default=None,
        help="Write a failure packet JSON file on validation failure",
    )
    p.add_argument(
        "--sarif",
        default=None,
        help="Write a SARIF 2.1.0 report to the given path",
    )
    p.add_argument(
        "--quiet", action="store_true", help="Suppress non-error validation output"
    )
    p.add_argument(
        "--watch",
        action="store_true",
        help="Re-run validation when relevant files change",
    )
    p.add_argument(
        "--watch-all",
        action="store_true",
        help="Re-run validation when any project file changes",
    )


def _register_test_parser(sub: argparse._SubParsersAction) -> None:
    from maid_runner.core.test_runner import _positive_jobs_arg

    p = sub.add_parser("test", help="Run validation commands from manifests")
    p.add_argument(
        "--manifest", default=None, help="Run validate commands for one manifest"
    )
    p.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of active manifests"
    )
    p.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failing validate command",
    )
    p.add_argument(
        "--jobs",
        type=_positive_jobs_arg,
        default=1,
        help="Run independent implementation command groups with this many workers",
    )
    p.add_argument(
        "--verbose", action="store_true", help="Print command output while tests run"
    )
    p.add_argument("--json", action="store_true", help="Print test results as JSON")
    p.add_argument(
        "--watch",
        action="store_true",
        help="Re-run manifest tests when relevant files change",
    )
    p.add_argument(
        "--watch-all",
        action="store_true",
        help="Re-run manifest tests when any project file changes",
    )
    batch_group = p.add_mutually_exclusive_group()
    batch_group.add_argument(
        "--batch",
        action="store_const",
        const=True,
        default=None,
        dest="batch",
        help="Batch independent command groups when possible",
    )
    batch_group.add_argument(
        "--no-batch",
        action="store_const",
        const=False,
        dest="batch",
        help="Run validate commands without batching independent groups",
    )


def _register_verify_parser(sub: argparse._SubParsersAction) -> None:
    from maid_runner.core.test_runner import _positive_jobs_arg

    p = sub.add_parser("verify", help="Run the full MAID verification gate")
    p.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of active manifests"
    )
    p.add_argument(
        "--allow-empty",
        action="store_true",
        help="Allow verification when no active manifests are found",
    )
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
        help="Fail verification when warnings are present",
    )
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
    p.add_argument(
        "--require-plan-lock",
        action="store_true",
        help="Fail when active manifests are missing or violate plan locks",
    )
    p.add_argument(
        "--require-red-evidence",
        action="store_true",
        help="Fail when plan locks lack valid red-phase evidence",
    )
    p.add_argument(
        "--artifact-coverage",
        action="store_true",
        help="Run validate commands under coverage and require declared artifacts to execute",
    )
    p.add_argument(
        "--knockout",
        action="store_true",
        help="Knock out declared Python artifacts and require validate commands to fail",
    )
    p.add_argument(
        "--knockout-limit",
        type=_positive_jobs_arg,
        default=None,
        help="Limit the number of declared artifacts tested by --knockout",
    )
    p.add_argument(
        "--knockout-allow-dirty",
        action="store_true",
        help="Allow --knockout to rewrite dirty target files",
    )
    p.add_argument(
        "--packet",
        nargs="?",
        const=".maid/last-failure-packet.json",
        default=None,
        help="Write a failure packet JSON file on verification failure",
    )
    p.add_argument(
        "--sarif",
        default=None,
        help="Write a SARIF 2.1.0 report to the given path",
    )
    p.add_argument(
        "--json", action="store_true", help="Print verification results as JSON"
    )


def _register_plan_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("plan", help="Tamper-evident plan lock operations")
    psub = p.add_subparsers(dest="plan_command")
    lp = psub.add_parser("lock", help="Create a plan lock for a manifest")
    lp.add_argument("manifest_path")
    lp.add_argument(
        "--no-run",
        action="store_true",
        dest="no_run",
        help="Create the lock without capturing red-phase evidence",
    )
    lp.add_argument(
        "--project-root",
        default=".",
        dest="project_root",
        help="Project root containing the manifest",
    )
    rp = psub.add_parser("revise", help="Re-lock a manifest with a revision reason")
    rp.add_argument("manifest_path")
    rp.add_argument(
        "--reason",
        default=None,
        help="Human-readable reason for revising the plan lock",
    )
    rp.add_argument(
        "--no-run",
        action="store_true",
        dest="no_run",
        help="Revise the lock without recapturing red-phase evidence",
    )
    rp.add_argument(
        "--preserve-red-evidence",
        action="store_true",
        dest="preserve_red_evidence",
        help="Keep existing valid red evidence during metadata-only revisions",
    )
    rp.add_argument(
        "--stash-implementation",
        action="store_true",
        dest="stash_implementation",
        help="Temporarily stash declared implementation changes while recapturing red evidence",
    )
    rp.add_argument(
        "--project-root",
        default=".",
        dest="project_root",
        help="Project root containing the manifest",
    )
    sp = psub.add_parser("status", help="Report plan lock state and hash matches")
    sp.add_argument("manifest_path")
    sp.add_argument(
        "--json", action="store_true", help="Print plan-lock status as JSON"
    )
    sp.add_argument(
        "--project-root",
        default=".",
        dest="project_root",
        help="Project root containing the manifest",
    )


def _register_task_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("task", help="Manage the active MAID task manifest")
    tsub = p.add_subparsers(dest="task_command")
    start = tsub.add_parser("start", help="Set the active task manifest")
    start.add_argument("manifest_path")
    tsub.add_parser("stop", help="Clear the active task manifest")
    status = tsub.add_parser("status", help="Show the active task manifest")
    status.add_argument(
        "--json", action="store_true", help="Print active-task status as JSON"
    )


def _register_hook_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("hook", help="Run MAID agent hook helpers")
    hsub = p.add_subparsers(dest="hook_command")
    scope_check = hsub.add_parser("scope-check", help="Check active manifest scope")
    scope_check.add_argument(
        "--path",
        default=None,
        help="Candidate path to check against active manifest scope",
    )
    scope_check.add_argument(
        "--stdin", action="store_true", help="Read a hook payload from standard input"
    )
    scope_check.add_argument(
        "--strict",
        action="store_true",
        help="Fail when the candidate path is outside writable scope",
    )


def _register_snapshot_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("snapshot", help="Generate manifest from existing code")
    p.add_argument("file_path")
    p.add_argument(
        "--output-dir",
        default="manifests/",
        help="Directory where the snapshot manifest will be written",
    )
    p.add_argument("--output", default=None, help="Explicit manifest output path")
    p.add_argument(
        "--with-tests",
        action="store_true",
        help="Include discovered test files in the snapshot",
    )
    p.add_argument(
        "--force", action="store_true", help="Overwrite an existing output manifest"
    )
    p.add_argument("--json", action="store_true", help="Print snapshot result as JSON")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the snapshot without writing files",
    )


def _register_snapshot_system_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("snapshot-system", help="Generate system-wide manifest")
    p.add_argument(
        "--output", default=None, help="Explicit output path for the system manifest"
    )
    p.add_argument(
        "--manifest-dir",
        default="manifests/",
        help="Directory used when deriving default output paths",
    )
    p.add_argument(
        "--quiet", action="store_true", help="Suppress non-error snapshot output"
    )
    p.add_argument(
        "--json", action="store_true", help="Print system snapshot result as JSON"
    )


def _register_bootstrap_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("bootstrap", help="Bootstrap MAID for an existing project")
    p.add_argument("directory", nargs="?", default=".")
    p.add_argument(
        "--output-dir",
        default="manifests/",
        help="Directory where bootstrap manifests will be written",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=None,
        help="Exclude a path pattern from bootstrap discovery; may be repeated",
    )
    p.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Ignore .gitignore rules during bootstrap discovery",
    )
    p.add_argument(
        "--rank",
        action="store_true",
        help="Rank undeclared files into an adoption plan",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of ranked files to include",
    )
    p.add_argument(
        "--include-private",
        action="store_true",
        help="Include private or hidden files in bootstrap discovery",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview bootstrap output without writing files",
    )
    p.add_argument("--json", action="store_true", help="Print bootstrap result as JSON")
    p.add_argument(
        "--quiet", action="store_true", help="Suppress non-error bootstrap output"
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed bootstrap discovery output",
    )


def _register_learn_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("learn", help="Refresh the deterministic Outcome index")
    p.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of manifests to index"
    )
    p.add_argument(
        "--output", default=".maid/outcomes.json", help="Outcome index output path"
    )
    p.add_argument(
        "--include-status",
        action="append",
        default=None,
        dest="include_status",
        help="Outcome status to index; replaces the completed-only default",
    )
    p.add_argument("--json", action="store_true", help="Print learn result as JSON")
    p.add_argument(
        "--quiet", action="store_true", help="Suppress non-error learn output"
    )


def _register_recall_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("recall", help="Search the deterministic Outcome index")
    p.add_argument(
        "--index", default=".maid/outcomes.json", help="Outcome index path to search"
    )
    p.add_argument(
        "--text", default=None, help="Free-text query matched against learned outcomes"
    )
    p.add_argument(
        "--tag",
        action="append",
        default=None,
        help="Outcome tag filter; may be repeated",
    )
    p.add_argument(
        "--path",
        action="append",
        default=None,
        help="Path signal to match; may be repeated",
    )
    p.add_argument(
        "--artifact",
        action="append",
        default=None,
        help="Artifact signal to match; may be repeated",
    )
    p.add_argument(
        "--validation-command",
        action="append",
        default=None,
        help="Validation command signal to match; may be repeated",
    )
    p.add_argument(
        "--review-text",
        default=None,
        help="Review finding text to use as a recall signal",
    )
    p.add_argument(
        "--manifest-slug",
        action="append",
        default=None,
        help="Manifest slug filter; may be repeated",
    )
    p.add_argument(
        "--for-manifest",
        default=None,
        help="Derive recall signals from a manifest file",
    )
    p.add_argument(
        "--plan-packet",
        action="store_true",
        help="Print a planning-oriented recall packet",
    )
    p.add_argument(
        "--manifest-dir",
        default=None,
        help="Manifest directory used for staleness checks",
    )
    p.add_argument(
        "--project-root",
        default=None,
        help="Project root used to resolve manifest-relative paths",
    )
    p.add_argument(
        "--allow-stale-index",
        action="store_true",
        help="Use the index even when source manifests changed",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of recall matches to print",
    )
    p.add_argument("--json", action="store_true", help="Print recall results as JSON")


def _register_insights_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("insights", help="Aggregate deterministic Outcome insights")
    p.add_argument(
        "--index", default=".maid/outcomes.json", help="Outcome index path to aggregate"
    )
    p.add_argument(
        "--manifest-dir",
        default=None,
        help="Manifest directory used for staleness checks",
    )
    p.add_argument(
        "--project-root",
        default=None,
        help="Project root used to resolve manifest-relative paths",
    )
    p.add_argument(
        "--allow-stale-index",
        action="store_true",
        help="Use the index even when source manifests changed",
    )
    p.add_argument(
        "--theme-map",
        default=None,
        help="Advisory enrichment digest used to re-aggregate lesson types",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of insight groups to print",
    )
    p.add_argument("--json", action="store_true", help="Print insights as JSON")


def _register_enrich_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "enrich",
        help="Build and verify deterministic Outcome enrichment artifacts",
    )
    ssub = p.add_subparsers(dest="enrich_command")

    prompt = ssub.add_parser(
        "prompt", help="Emit the bounded Outcome enrichment prompt corpus"
    )
    _add_enrich_common_options(prompt)
    prompt.add_argument(
        "--output",
        default=None,
        help="Write prompt corpus JSON to this path instead of stdout",
    )

    validate = ssub.add_parser(
        "validate", help="Validate an Outcome enrichment digest against the index"
    )
    _add_enrich_common_options(validate)
    _add_enrich_digest_option(validate)

    render = ssub.add_parser(
        "render", help="Render a validated Outcome enrichment digest as markdown"
    )
    _add_enrich_common_options(render)
    _add_enrich_digest_option(render)
    render.add_argument(
        "--md-output",
        default=".maid/outcomes-digest.md",
        help="Markdown output path for the rendered digest",
    )


def _add_enrich_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--index",
        default=".maid/outcomes.json",
        help="Outcome index path to enrich",
    )
    parser.add_argument(
        "--manifest-dir",
        default=None,
        help="Manifest directory used for staleness checks",
    )
    parser.add_argument(
        "--project-root",
        default=None,
        help="Project root used to resolve manifest-relative paths",
    )
    parser.add_argument(
        "--allow-stale-index",
        action="store_true",
        help="Use stale index or digest inputs explicitly",
    )
    parser.add_argument("--json", action="store_true", help="Print result as JSON")


def _add_enrich_digest_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--digest",
        default=".maid/outcomes-digest.json",
        help="Outcome enrichment digest JSON path",
    )


def _register_benchmark_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "benchmark",
        help="Run local benchmark timings for MAID validation gates",
    )
    p.add_argument("projects", nargs="*", help="Project paths to benchmark")
    p.add_argument(
        "--manifest-dir", default="manifests/", help="Manifest directory to benchmark"
    )
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
    p.add_argument(
        "--json-output", default=None, help="Write benchmark results to a JSON file"
    )
    p.add_argument(
        "--markdown-output",
        default=None,
        help="Write benchmark results to a Markdown file",
    )
    p.add_argument(
        "--json", action="store_true", help="Print benchmark results as JSON"
    )


def _positive_repeat_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("repeat must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("repeat must be a positive integer")
    return parsed


def _register_incident_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("incident", help="Capture and inspect gaming incidents")
    isub = p.add_subparsers(dest="incident_command")

    capture = isub.add_parser("capture", help="Capture a caught gaming incident")
    capture.add_argument(
        "--manifest", required=True, help="Manifest path associated with the incident"
    )
    capture.add_argument(
        "--packet", required=True, help="Failure or review packet JSON path"
    )
    capture.add_argument(
        "--rejected-diff",
        required=True,
        help="Path to the rejected implementation diff",
    )
    capture.add_argument("--tags", required=True, help="Comma-separated incident tags")
    capture.add_argument(
        "--notes", default=None, help="Optional notes to store with the incident"
    )

    update = isub.add_parser("update", help="Attach the accepted fix diff")
    update.add_argument("incident_path")
    update.add_argument(
        "--chosen-diff", required=True, help="Path to the accepted fix diff"
    )

    list_parser = isub.add_parser("list", help="List captured incidents")
    list_parser.add_argument("--tag", default=None, help="Filter incidents by tag")
    list_parser.add_argument(
        "--json", action="store_true", help="Print incident list as JSON"
    )

    export = isub.add_parser("export", help="Export incident training data")
    export.add_argument(
        "--format", choices=["dpo"], required=True, help="Training-data export format"
    )
    export.add_argument(
        "--output", required=True, help="Output file for exported training data"
    )

    suggest = isub.add_parser(
        "suggest-temptations", help="Suggest advisory manifest temptations"
    )
    suggest.add_argument(
        "--paths",
        required=True,
        help="Comma-separated paths to consider for temptations",
    )
    suggest.add_argument(
        "--json", action="store_true", help="Print suggested temptations as JSON"
    )


def _register_daemon_parser(sub: argparse._SubParsersAction) -> None:
    from maid_runner.cli.commands.daemon import register_daemon_subparser

    register_daemon_subparser(sub)


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
    cp.add_argument(
        "--goal", required=True, help="Goal statement for the generated manifest"
    )
    cp.add_argument(
        "--type",
        default="feature",
        dest="task_type",
        help="Task type to write into the manifest",
    )
    cp.add_argument(
        "--artifacts", default=None, help="Comma-separated artifact names to declare"
    )
    cp.add_argument(
        "--output-dir",
        default="manifests/",
        help="Directory where the manifest will be written",
    )
    cp.add_argument(
        "--dry-run", action="store_true", help="Preview the manifest without writing it"
    )
    cp.add_argument(
        "--json", action="store_true", help="Print manifest creation result as JSON"
    )
    cp.add_argument(
        "--delete",
        action="store_true",
        help="Declare the file as deleted instead of edited",
    )
    cp.add_argument(
        "--rename-to", default=None, help="Declare a rename target for the file"
    )
    cp.add_argument(
        "--temptation",
        dest="temptations",
        action="append",
        default=None,
        help="Add task-specific anti-gaming guidance as 'risk::instead'.",
    )
    pp = msub.add_parser("promote", help="Promote a draft manifest")
    pp.add_argument("manifest_path")
    pp.add_argument(
        "--output-dir",
        default="manifests/",
        help="Directory where the promoted manifest will be written",
    )
    pp.add_argument(
        "--no-run",
        action="store_true",
        dest="no_run",
        help="Promote without running migration validation",
    )
    pp.add_argument(
        "--project-root",
        default=".",
        dest="project_root",
        help="Project root containing the draft manifest",
    )
    pp.add_argument(
        "--json", action="store_true", help="Print promotion result as JSON"
    )
    fdp = msub.add_parser(
        "from-diff", help="Generate a draft manifest from git diff scope"
    )
    fdp.add_argument("--since", default=None, help="Commit-ish baseline for the diff")
    fdp.add_argument(
        "--base-ref",
        default=None,
        dest="base_ref",
        help="Ref whose merge-base with HEAD is used as the diff baseline",
    )
    fdp.add_argument(
        "--worktree",
        action="store_true",
        help="Use current worktree changes as the diff source",
    )
    fdp.add_argument(
        "--slug", default=None, help="Slug for the generated draft manifest"
    )
    fdp.add_argument(
        "--output", default=None, help="Explicit output path for the draft manifest"
    )
    fdp.add_argument(
        "--force", action="store_true", help="Overwrite an existing draft manifest"
    )
    fdp.add_argument(
        "--dry-run", action="store_true", help="Preview the draft without writing it"
    )
    fdp.add_argument(
        "--json", action="store_true", help="Print generated draft details as JSON"
    )


def _register_manifests_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("manifests", help="List manifests referencing a file")
    p.add_argument("file_path")
    p.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of manifests to search"
    )
    p.add_argument(
        "--json", action="store_true", help="Print matching manifests as JSON"
    )
    p.add_argument(
        "--quiet", action="store_true", help="Print only matching manifest paths"
    )


def _register_files_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("files", help="Show file tracking status")
    p.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of manifests to inspect"
    )
    p.add_argument(
        "--hide-private",
        action="store_true",
        help="Hide private or ignored files from the report",
    )
    p.add_argument(
        "--fail-on",
        action="append",
        choices=["undeclared", "registered", "any"],
        default=None,
        help="Return 1 when the selected file-tracking status is present",
    )
    p.add_argument(
        "--json", action="store_true", help="Print file-tracking status as JSON"
    )
    p.add_argument(
        "--quiet", action="store_true", help="Print only paths selected by the report"
    )


def _register_init_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("init", help="Initialize MAID in a project")
    p.add_argument(
        "--tool",
        default="auto",
        choices=["claude", "codex", "cursor", "windsurf", "generic", "auto"],
        help="Agent tool payload to initialize",
    )
    p.add_argument(
        "--check",
        action="store_true",
        help="Check whether installed MAID init instruction payloads are current",
    )
    p.add_argument(
        "--json", action="store_true", help="Print init or check result as JSON"
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview initialization without writing files",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing MAID instruction payload files",
    )


def _register_graph_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("graph", help="Knowledge graph operations")
    gsub = p.add_subparsers(dest="graph_command")
    gq = gsub.add_parser("query", help="Query the knowledge graph")
    gq.add_argument("question")
    gq.add_argument(
        "--json", action="store_true", help="Print graph query result as JSON"
    )
    ge = gsub.add_parser("export", help="Export knowledge graph")
    ge.add_argument(
        "--format",
        default="json",
        choices=["json", "dot", "graphml"],
        help="Graph export format",
    )
    ge.add_argument(
        "--output", default=None, help="Output path for exported graph data"
    )
    ga = gsub.add_parser("analyze", help="Analyze file dependencies")
    ga.add_argument("file_path")
    ga.add_argument(
        "--json", action="store_true", help="Print dependency analysis as JSON"
    )
    p.add_argument(
        "--manifest-dir",
        default="manifests/",
        help="Directory of manifests used to build the graph",
    )


def _register_coherence_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("coherence", help="Run coherence checks")
    p.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of manifests to check"
    )
    p.add_argument(
        "--checks", default=None, help="Comma-separated coherence checks to run"
    )
    p.add_argument(
        "--exclude", default=None, help="Comma-separated coherence checks to skip"
    )
    p.add_argument(
        "--json", action="store_true", help="Print coherence results as JSON"
    )


def _register_schema_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("schema", help="Display manifest JSON Schema")
    p.add_argument(
        "--version",
        default="2",
        dest="version",
        help="Manifest schema version to display",
    )


def _register_howto_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("howto", help="Show MAID workflow guidance")
    p.add_argument("--section", dest="topic", help="Guidance section to display")
    p.add_argument("topic", nargs="?", default=argparse.SUPPRESS)


def _register_chain_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("chain", help="Manifest chain operations")
    csub = p.add_subparsers(dest="chain_command")
    clp = csub.add_parser("log", help="Show manifest event log")
    clp.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of manifests to read"
    )
    clp.add_argument("--json", action="store_true", help="Print chain log as JSON")
    clp.add_argument(
        "--active", action="store_true", help="Show only active chain events"
    )
    clp.add_argument(
        "--until-seq",
        type=int,
        default=None,
        dest="until_seq",
        help="Replay events through this sequence number",
    )
    clp.add_argument(
        "--version-tag",
        type=str,
        default=None,
        dest="version_tag",
        help="Replay events through this version tag",
    )

    rp = csub.add_parser(
        "replay", help="Preview effective artifacts at a point in time"
    )
    rp.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of manifests to read"
    )
    rp.add_argument(
        "--json", action="store_true", help="Print chain replay result as JSON"
    )
    rp.add_argument(
        "--until-seq",
        type=int,
        default=None,
        dest="until_seq",
        help="Replay events through this sequence number",
    )
    rp.add_argument(
        "--version-tag",
        type=str,
        default=None,
        dest="version_tag",
        help="Replay events through this version tag",
    )


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
    aup.add_argument(
        "--manifest-dir", default="manifests/", help="Directory of manifests to audit"
    )
    aup.add_argument(
        "--lock", default=None, help="Path to the supersession preservation lock file"
    )
    aup.add_argument(
        "--seal", action="store_true", help="Seal the current audit baseline"
    )
    aup.add_argument(
        "--unseal", action="store_true", help="Remove the current audit baseline seal"
    )
    aup.add_argument("--json", action="store_true", help="Print audit results as JSON")
    aup.add_argument(
        "--quiet", action="store_true", help="Suppress non-error audit output"
    )
    aup.add_argument(
        "--project-root",
        default=".",
        dest="project_root",
        help="Project root used for audit path resolution",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args._maid_argv = list(sys.argv if argv is None else ["maid", *argv])

    if not args.command:
        parser.print_help()
        return 2

    dispatch = {
        "validate": "_cmd_validate",
        "validators": "_cmd_validators",
        "test": "_cmd_test",
        "verify": "_cmd_verify",
        "plan": "_cmd_plan",
        "task": "_cmd_task",
        "hook": "_cmd_hook",
        "snapshot": "_cmd_snapshot",
        "snapshot-system": "_cmd_snapshot_system",
        "bootstrap": "_cmd_bootstrap",
        "learn": "_cmd_learn",
        "recall": "_cmd_recall",
        "insights": "_cmd_insights",
        "enrich": "_cmd_enrich",
        "benchmark": "_cmd_benchmark",
        "incident": "_cmd_incident",
        "daemon": "_cmd_daemon",
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
        "skills": "_cmd_skills",
    }

    handler_name = dispatch.get(args.command)
    if handler_name is None:
        parser.print_help()
        return 2

    # Lazy import command handlers
    from maid_runner.cli.commands import (
        validate as validate_mod,
        validators as validators_mod,
        test as test_mod,
        verify as verify_mod,
        plan as plan_mod,
        task as task_mod,
        hook as hook_mod,
        snapshot as snapshot_mod,
        bootstrap as bootstrap_mod,
        learn as learn_mod,
        recall as recall_mod,
        insights as insights_mod,
        enrich as enrich_mod,
        benchmark as benchmark_mod,
        incident as incident_mod,
        daemon as daemon_mod,
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
        skills as skills_mod,
    )

    handlers = {
        "_cmd_validate": validate_mod.cmd_validate,
        "_cmd_validators": validators_mod.cmd_validators,
        "_cmd_test": test_mod.cmd_test,
        "_cmd_verify": verify_mod.cmd_verify,
        "_cmd_plan": plan_mod.cmd_plan,
        "_cmd_task": task_mod.cmd_task,
        "_cmd_hook": hook_mod.cmd_hook,
        "_cmd_snapshot": snapshot_mod.cmd_snapshot,
        "_cmd_snapshot_system": snapshot_mod.cmd_snapshot_system,
        "_cmd_bootstrap": bootstrap_mod.cmd_bootstrap,
        "_cmd_learn": learn_mod.cmd_learn,
        "_cmd_recall": recall_mod.cmd_recall,
        "_cmd_insights": insights_mod.cmd_insights,
        "_cmd_enrich": enrich_mod.cmd_enrich,
        "_cmd_benchmark": benchmark_mod.cmd_benchmark,
        "_cmd_incident": incident_mod.cmd_incident,
        "_cmd_daemon": daemon_mod.cmd_daemon,
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
        "_cmd_skills": skills_mod.cmd_skills,
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
