"""Tests for CLI entry point and argument parser (v2)."""

from __future__ import annotations

import pytest


class TestBuildParser:
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
