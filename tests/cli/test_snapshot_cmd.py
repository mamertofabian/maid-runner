"""Tests for CLI 'maid snapshot' command (v2)."""

from __future__ import annotations


class TestCmdSnapshot:
    def test_snapshot_module_not_available_returns_2(self, capsys):
        """Snapshot module is Phase 5 - should gracefully report unavailability."""
        from maid_runner.cli.commands._main import main

        exit_code = main(["snapshot", "src/greet.py"])
        # Returns 2 since the snapshot core module doesn't exist yet
        assert exit_code == 2
        captured = capsys.readouterr()
        assert (
            "not available" in captured.err.lower() or "error" in captured.err.lower()
        )


class TestCmdSnapshotSystem:
    def test_snapshot_system_not_available_returns_2(self, capsys):
        from maid_runner.cli.commands._main import main

        exit_code = main(["snapshot-system"])
        assert exit_code == 2
