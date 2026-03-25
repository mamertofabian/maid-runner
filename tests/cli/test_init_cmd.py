"""Tests for CLI 'maid init' command (v2)."""

from __future__ import annotations

import os


class TestCmdInit:
    def test_init_creates_manifests_dir_and_config(self, tmp_path):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(["init"])
        assert exit_code == 0
        assert (tmp_path / "manifests").is_dir()
        assert (tmp_path / ".maidrc.yaml").is_file()

    def test_init_dry_run_does_not_create(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(["init", "--dry-run"])
        assert exit_code == 0
        assert not (tmp_path / "manifests").exists()
        assert not (tmp_path / ".maidrc.yaml").exists()
        captured = capsys.readouterr()
        assert "Would create" in captured.out

    def test_init_already_initialized_returns_2(self, tmp_path):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        # Initialize first
        main(["init"])
        # Try again without --force
        exit_code = main(["init"])
        assert exit_code == 2

    def test_init_force_reinitializes(self, tmp_path):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        main(["init"])
        exit_code = main(["init", "--force"])
        assert exit_code == 0

    def test_init_config_contains_schema_version(self, tmp_path):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        main(["init"])
        content = (tmp_path / ".maidrc.yaml").read_text()
        assert "schema_version: 2" in content
