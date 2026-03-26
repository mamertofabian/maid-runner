"""Tests for CLI 'maid snapshot' and 'maid snapshot-system' commands (v2)."""

from __future__ import annotations

import json


class TestCmdSnapshot:
    def test_snapshot_nonexistent_file_returns_2(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["snapshot", "does_not_exist.py"])
        assert exit_code == 2
        captured = capsys.readouterr()
        assert "error" in captured.err.lower()

    def test_snapshot_dry_run(self, tmp_path, capsys, monkeypatch):
        """Snapshot dry-run prints manifest without saving."""
        from maid_runner.cli.commands._main import main

        source = tmp_path / "greet.py"
        source.write_text("def hello():\n    pass\n")
        monkeypatch.chdir(tmp_path)

        exit_code = main(["snapshot", str(source), "--dry-run"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "hello" in captured.out

    def test_snapshot_dry_run_json(self, tmp_path, capsys, monkeypatch):
        from maid_runner.cli.commands._main import main

        source = tmp_path / "greet.py"
        source.write_text("def hello():\n    pass\n")
        monkeypatch.chdir(tmp_path)

        exit_code = main(["snapshot", str(source), "--dry-run", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["goal"].startswith("Snapshot of")

    def test_snapshot_saves_file(self, tmp_path, monkeypatch):
        from maid_runner.cli.commands._main import main

        source = tmp_path / "greet.py"
        source.write_text("def hello():\n    pass\n")
        out_dir = tmp_path / "manifests"
        out_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        exit_code = main(["snapshot", str(source), "--output-dir", str(out_dir)])
        assert exit_code == 0
        files = list(out_dir.glob("*.yaml"))
        assert len(files) == 1


class TestCmdSnapshotSystem:
    def test_snapshot_system_runs_successfully(self, capsys):
        """snapshot-system command runs and produces output."""
        from maid_runner.cli.commands._main import main

        exit_code = main(["snapshot-system"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "snapshot" in captured.out.lower() or captured.out.strip() != ""

    def test_snapshot_system_with_output(self, tmp_path):
        from maid_runner.cli.commands._main import main

        output = tmp_path / "system.manifest.yaml"
        exit_code = main(["snapshot-system", "--output", str(output)])
        assert exit_code == 0
        assert output.exists()
