"""Tests for maid bootstrap CLI command."""

from __future__ import annotations

import json

from maid_runner.cli.commands.bootstrap import cmd_bootstrap
from maid_runner.cli.commands._format import format_bootstrap_report
from maid_runner.core.bootstrap import BootstrapReport


class TestFormatBootstrapReport:
    def test_normal_output(self):
        """format_bootstrap_report returns human-readable summary."""
        report = BootstrapReport(
            results=(),
            total_discovered=5,
            captured=3,
            skipped=1,
            failed=1,
            excluded=0,
            total_artifacts=10,
            manifests_dir="manifests/",
        )
        output = format_bootstrap_report(report)
        assert "5 source files discovered" in output
        assert "Captured:  3 files" in output

    def test_json_output(self):
        """format_bootstrap_report JSON mode returns valid JSON."""
        report = BootstrapReport(
            results=(),
            total_discovered=2,
            captured=2,
            skipped=0,
            failed=0,
            excluded=0,
            total_artifacts=5,
        )
        output = format_bootstrap_report(report, json_mode=True)
        data = json.loads(output)
        assert data["captured"] == 2
        assert data["total_discovered"] == 2


class TestCmdBootstrapFunction:
    def test_cmd_bootstrap_callable(self):
        """cmd_bootstrap is a callable function."""
        assert callable(cmd_bootstrap)


class TestCmdBootstrap:
    def test_bootstrap_dry_run(self, tmp_path, capsys, monkeypatch):
        """Dry run exits 0 and writes no manifest files."""
        from maid_runner.cli.commands._main import main

        (tmp_path / "app.py").write_text("def run(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        exit_code = main(
            ["bootstrap", str(tmp_path), "--output-dir", str(manifest_dir), "--dry-run"]
        )

        assert exit_code == 0
        assert len(list(manifest_dir.glob("*.manifest.yaml"))) == 0
        captured = capsys.readouterr()
        assert "Captured" in captured.out or "captured" in captured.out.lower()

    def test_bootstrap_dry_run_json(self, tmp_path, capsys, monkeypatch):
        """JSON output is valid and contains expected fields."""
        from maid_runner.cli.commands._main import main

        (tmp_path / "greet.py").write_text("def hello(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        exit_code = main(
            [
                "bootstrap",
                str(tmp_path),
                "--output-dir",
                str(manifest_dir),
                "--dry-run",
                "--json",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "captured" in data
        assert "total_discovered" in data
        assert data["captured"] >= 1

    def test_bootstrap_saves_manifests(self, tmp_path, monkeypatch):
        """Bootstrap creates manifest files in the output directory."""
        from maid_runner.cli.commands._main import main

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("def main(): pass\n")
        (tmp_path / "src" / "utils.py").write_text("def helper(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        exit_code = main(
            ["bootstrap", str(tmp_path), "--output-dir", str(manifest_dir)]
        )

        assert exit_code == 0
        manifests = list(manifest_dir.glob("*.manifest.yaml"))
        assert len(manifests) == 2

    def test_bootstrap_with_exclude(self, tmp_path, capsys, monkeypatch):
        """--exclude flag filters out matching files."""
        from maid_runner.cli.commands._main import main

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("def main(): pass\n")
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "lib.py").write_text("def vendored(): pass\n")
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        monkeypatch.chdir(tmp_path)

        exit_code = main(
            [
                "bootstrap",
                str(tmp_path),
                "--output-dir",
                str(manifest_dir),
                "--exclude",
                "vendor/*",
            ]
        )

        assert exit_code == 0
        manifests = list(manifest_dir.glob("*.manifest.yaml"))
        assert len(manifests) == 1

    def test_bootstrap_nonexistent_dir_returns_2(self, capsys):
        """Bootstrapping a nonexistent directory returns exit code 2."""
        from maid_runner.cli.commands._main import main

        exit_code = main(["bootstrap", "/nonexistent/path/xyz"])

        assert exit_code == 2
