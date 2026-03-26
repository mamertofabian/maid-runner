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

    def test_howto_unknown_topic_returns_2(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["howto", "nonexistent"])
        assert exit_code == 2
