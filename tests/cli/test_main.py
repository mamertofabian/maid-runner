"""Tests for CLI entry point and argument parser (v2)."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestBuildParser:
    def test_parser_help_lists_all_top_level_commands(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()

        help_text = parser.format_help()

        for command in (
            "validate",
            "test",
            "verify",
            "snapshot",
            "snapshot-system",
            "bootstrap",
            "manifest",
            "manifests",
            "files",
            "init",
            "graph",
            "coherence",
            "schema",
            "howto",
            "chain",
            "benchmark",
            "serve",
            "audit",
        ):
            assert command in help_text

    def test_validate_compatibility_aliases_survive_parser_extraction(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()

        args = parser.parse_args(["validate", "--use-manifest-chain", "--json-output"])

        assert args.use_manifest_chain is True
        assert args.json is True

    def test_nested_command_parsers_survive_parser_extraction(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()

        manifest_args = parser.parse_args(
            ["manifest", "create", "src/app.py", "--goal", "Add app"]
        )
        graph_args = parser.parse_args(["graph", "query", "what imports validate"])
        chain_args = parser.parse_args(["chain", "log"])
        audit_args = parser.parse_args(["audit", "supersessions"])

        assert manifest_args.command == "manifest"
        assert manifest_args.manifest_command == "create"
        assert manifest_args.output_dir == "manifests/"
        assert graph_args.command == "graph"
        assert graph_args.graph_command == "query"
        assert graph_args.manifest_dir == "manifests/"
        assert chain_args.command == "chain"
        assert chain_args.chain_command == "log"
        assert chain_args.manifest_dir == "manifests/"
        assert audit_args.command == "audit"
        assert audit_args.audit_command == "supersessions"
        assert audit_args.manifest_dir == "manifests/"

    def test_parser_has_validate_subcommand(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        # Parse "validate" with no args - should work (validates all)
        args = parser.parse_args(["validate"])
        assert args.command == "validate"

    def test_parser_has_test_subcommand(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test"])
        assert args.command == "test"

    def test_benchmark_parser_accepts_output_and_project_options(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "benchmark",
                "../tower-recall",
                "--manifest-dir",
                "contracts/",
                "--command-prefix",
                "uv",
                "--command-prefix",
                "run",
                "--repeat",
                "2",
                "--json-output",
                "benchmark.json",
                "--markdown-output",
                "benchmark.md",
                "--json",
            ]
        )

        assert args.command == "benchmark"
        assert args.projects == ["../tower-recall"]
        assert args.manifest_dir == "contracts/"
        assert args.command_prefix == ["uv", "run"]
        assert args.repeat == 2
        assert args.json_output == "benchmark.json"
        assert args.markdown_output == "benchmark.md"
        assert args.json is True

    def test_parser_has_schema_subcommand(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["schema"])
        assert args.command == "schema"

    def test_parser_has_howto_subcommand(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["howto"])
        assert args.command == "howto"

    def test_validate_accepts_manifest_path(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate", "manifests/add-auth.manifest.yaml"])
        assert args.manifest_path == "manifests/add-auth.manifest.yaml"

    def test_validate_mode_default(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate"])
        assert args.mode == "implementation"

    def test_validate_mode_behavioral(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate", "--mode", "behavioral"])
        assert args.mode == "behavioral"

    def test_validate_mode_schema(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate", "--mode", "schema"])
        assert args.mode == "schema"

    def test_validate_no_chain_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate", "--no-chain"])
        assert args.no_chain is True

    def test_validate_json_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate", "--json"])
        assert args.json is True

    def test_validate_accepts_strict_assertion_stub_warning_flags(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "validate",
                "--strict",
                "--check-assertions",
                "--check-stubs",
                "--fail-on-warnings",
            ]
        )

        assert args.strict is True
        assert args.check_assertions is True
        assert args.check_stubs is True
        assert args.fail_on_warnings is True

    def test_validate_accepts_run_tests_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate", "--run-tests"])

        assert args.run_tests is True

    def test_parser_has_verify_subcommand(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "verify",
                "--manifest-dir",
                "custom-manifests/",
                "--json",
                "--keep-going",
                "--strict",
                "--check-assertions",
                "--check-stubs",
                "--fail-on-warnings",
                "--allow-empty",
                "--worktree-scope",
                "--changed-scope",
                "--since",
                "HEAD~1",
                "--base-ref",
                "origin/main",
                "--include-tests",
            ]
        )

        assert args.command == "verify"
        assert args.manifest_dir == "custom-manifests/"
        assert args.json is True
        assert args.fail_fast is False
        assert args.strict is True
        assert args.check_assertions is True
        assert args.check_stubs is True
        assert args.fail_on_warnings is True
        assert args.allow_empty is True
        assert args.worktree_scope is True
        assert args.changed_scope is True
        assert args.since == "HEAD~1"
        assert args.base_ref == "origin/main"
        assert args.include_tests is True

    def test_verify_changed_scope_defaults_on_and_can_be_disabled(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()

        default_args = parser.parse_args(["verify"])
        disabled_args = parser.parse_args(["verify", "--no-changed-scope"])

        assert default_args.changed_scope is True
        assert disabled_args.changed_scope is False

    def test_validate_accepts_changed_scope_flags(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(
            ["validate", "--changed-scope", "--since", "abc123", "--base-ref", "main"]
        )

        assert args.changed_scope is True
        assert args.since == "abc123"
        assert args.base_ref == "main"

    def test_changed_scope_handoff_docs_are_discoverable(self):
        root = Path(__file__).resolve().parents[2]
        changed_scope_handoff_gate_docs = (root / "README.md").read_text(
            encoding="utf-8"
        )
        changed_scope_agent_handoff_guidance = (
            root / "docs/agent-skills.md"
        ).read_text(encoding="utf-8")
        changed_scope_draft_handoff_gate = (
            root / "docs/draft-manifest-workflow.md"
        ).read_text(encoding="utf-8")

        assert "Changed-Scope Handoff Gate" in changed_scope_handoff_gate_docs
        assert (
            "maid verify --base-ref <parent-branch>" in changed_scope_handoff_gate_docs
        )
        assert "`maid verify` runs changed-scope by default" in (
            changed_scope_handoff_gate_docs
        )
        assert "fails closed with `E115`" in changed_scope_handoff_gate_docs
        assert (
            "`maid verify` runs changed-scope by default"
            in changed_scope_agent_handoff_guidance
        )
        assert "Handoff Scope Gate" in changed_scope_draft_handoff_gate
        assert "it does not guess\n`main`, `master`, `dev`" in (
            changed_scope_draft_handoff_gate
        )

    def test_parser_exposes_verify_advisory_opt_out(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["verify", "--advisory"])

        assert args.command == "verify"
        assert args.advisory is True

    def test_validate_quiet_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate", "--quiet"])
        assert args.quiet is True

    def test_test_fail_fast_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test", "--fail-fast"])
        assert args.fail_fast is True

    def test_test_manifest_option(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test", "--manifest", "manifests/x.yaml"])
        assert args.manifest == "manifests/x.yaml"

    def test_test_verbose_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test", "--verbose"])
        assert args.verbose is True

    def test_schema_version_default(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["schema"])
        assert args.version == "2"

    def test_howto_topic(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["howto", "workflow"])
        assert args.topic == "workflow"

    def test_howto_section_alias(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["howto", "--section", "quickstart"])
        assert args.topic == "quickstart"

    def test_howto_no_topic(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["howto"])
        assert args.topic is None


class TestMainFunction:
    def test_no_command_returns_2(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main([])
        assert exit_code == 2

    def test_version_flag(self, capsys):
        from maid_runner.cli.commands._main import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_invalid_command_exits_with_2(self, capsys):
        from maid_runner.cli.commands._main import main

        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent"])
        assert exc_info.value.code == 2


class TestValidateDefaults:
    def test_default_manifest_dir(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate"])
        assert args.manifest_dir == "manifests/"

    def test_custom_manifest_dir(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["validate", "--manifest-dir", "custom/"])
        assert args.manifest_dir == "custom/"


class TestMissingCLIFlags:
    """Test CLI flags required by spec 09-cli.md."""

    def test_test_batch_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test", "--batch"])
        assert args.batch is True

    def test_test_no_batch_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test", "--no-batch"])
        assert args.batch is False

    def test_test_batch_default_none(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test"])
        assert args.batch is None

    def test_test_parser_accepts_jobs_option(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test", "--jobs", "4", "--batch"])

        assert args.jobs == 4
        assert args.batch is True

    def test_test_parser_rejects_invalid_jobs_option(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()

        for value in ("0", "-1", "not-an-int"):
            with pytest.raises(SystemExit):
                parser.parse_args(["test", "--jobs", value])

    def test_manifest_create_delete_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(
            ["manifest", "create", "src/old.py", "--goal", "Remove old", "--delete"]
        )
        assert args.delete is True

    def test_manifest_create_rename_to_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "manifest",
                "create",
                "src/old.py",
                "--goal",
                "Rename",
                "--rename-to",
                "src/new.py",
            ]
        )
        assert args.rename_to == "src/new.py"

    def test_snapshot_output_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["snapshot", "src/app.py", "--output", "out.yaml"])
        assert args.output == "out.yaml"

    def test_snapshot_with_tests_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["snapshot", "src/app.py", "--with-tests"])
        assert args.with_tests is True

    def test_snapshot_force_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["snapshot", "src/app.py", "--force"])
        assert args.force is True

    def test_files_hide_private_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["files", "--hide-private"])
        assert args.hide_private is True


class TestTestDefaults:
    def test_default_manifest_dir(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test"])
        assert args.manifest_dir == "manifests/"

    def test_json_flag(self):
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        args = parser.parse_args(["test", "--json"])
        assert args.json is True
