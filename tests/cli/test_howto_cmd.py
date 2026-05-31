"""Tests for CLI 'maid howto' command (v2)."""

from __future__ import annotations


class TestCmdHowto:
    def test_howto_no_topic_lists_topics(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "create" in captured.out
        assert "validate" in captured.out
        assert "workflow" in captured.out

    def test_howto_workflow_topic(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto", "workflow"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "MAID Workflow" in captured.out

    def test_howto_create_topic(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto", "create"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Manifest" in captured.out

    def test_howto_quickstart_section_alias(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto", "--section", "quickstart"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Quick Start" in captured.out

    def test_cmd_howto_quickstart_topic(self, capsys):
        import argparse

        from maid_runner.cli.commands.howto import cmd_howto

        exit_code = cmd_howto(argparse.Namespace(topic="quickstart"))
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Quick Start" in captured.out

    def test_howto_commands_section_alias(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto", "--section", "commands"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "CLI Commands" in captured.out

    def test_cmd_howto_commands_topic_mentions_schema_mode(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto", "commands"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "--mode schema" in captured.out

    def test_howto_unknown_topic_returns_2(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto", "nonexistent"])
        assert exit_code == 2

    def test_howto_serve_topic_documents_daemon(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto", "serve"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "maid serve" in captured.out
        assert "NDJSON" in captured.out
        assert "Unix socket" in captured.out
        assert "PATH_ESCAPE" in captured.out
        assert "docs/maid-serve.md" in captured.out

    def test_howto_troubleshooting_topic_links_guide_and_common_codes(self, capsys):
        import argparse

        from maid_runner.cli.commands.howto import cmd_howto

        exit_code = cmd_howto(argparse.Namespace(topic="troubleshooting"))
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Troubleshooting" in captured.out
        assert "docs/troubleshooting.md" in captured.out
        assert "E200" in captured.out
        assert "E300" in captured.out
        assert "E114" in captured.out
        assert "FAQ" in captured.out
