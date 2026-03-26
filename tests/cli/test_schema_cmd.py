"""Tests for CLI 'maid schema' command (v2)."""

from __future__ import annotations

import json


class TestCmdSchema:
    def test_schema_v2_outputs_valid_json(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["schema"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["title"] == "MAID Manifest v2"

    def test_schema_v1_outputs_valid_json(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["schema", "--version", "1"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "properties" in data

    def test_schema_invalid_version_returns_2(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["schema", "--version", "99"])
        assert exit_code == 2
