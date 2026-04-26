"""Behavioral tests for `maid chain log` CLI command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Subcommand registration
# ---------------------------------------------------------------------------


class TestChainSubparserRegistered:
    def test_build_parser_includes_chain_subcommand(self) -> None:
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()

        # Find the 'chain' subparser by parsing --help-like discovery
        subcommands: dict[str, argparse.ArgumentParser] = {}
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    subcommands[name] = sub

        assert "chain" in subcommands, (
            f"Expected 'chain' subcommand, got: {list(subcommands.keys())}"
        )

    def test_build_parser_chain_has_log_subcommand(self) -> None:
        from maid_runner.cli.commands._main import build_parser

        parser = build_parser()
        chain_parser = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                chain_parser = action.choices.get("chain")
                break

        assert chain_parser is not None

        # chain should have its own subparsers (for 'log')
        chain_subs: dict[str, argparse.ArgumentParser] = {}
        for action in chain_parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    chain_subs[name] = sub

        assert "log" in chain_subs, (
            f"Expected 'log' sub-subcommand, got: {list(chain_subs.keys())}"
        )


# ---------------------------------------------------------------------------
# format_chain_log
# ---------------------------------------------------------------------------


class TestFormatChainLog:
    def test_text_output_includes_expected_columns(self, tmp_path: Path) -> None:
        from maid_runner.core.chain import ManifestChain
        from maid_runner.cli.commands._format import format_chain_log

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a-first.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
            version_tag="v1.0",
        )
        _write_manifest(
            manifest_dir,
            "b-second.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        log = chain.event_log()

        output = format_chain_log(
            log, str(manifest_dir), json_mode=False, active_only=False
        )

        assert "a-first" in output
        assert "b-second" in output
        assert "v1.0" in output  # version_tag column
        assert "1" in output  # sequence_number column

    def test_json_output_is_valid_and_contains_all_entries(
        self, tmp_path: Path
    ) -> None:
        from maid_runner.core.chain import ManifestChain
        from maid_runner.cli.commands._format import format_chain_log

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "first.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "second.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            version_tag="release-2",
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        log = chain.event_log()

        output = format_chain_log(
            log, str(manifest_dir), json_mode=True, active_only=False
        )
        data = json.loads(output)

        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["slug"] == "first"
        assert data[0]["sequence_number"] == 1
        assert data[1]["slug"] == "second"
        assert data[1]["version_tag"] == "release-2"

    def test_active_only_excludes_superseded(self, tmp_path: Path) -> None:
        from maid_runner.core.chain import ManifestChain
        from maid_runner.cli.commands._format import format_chain_log

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "original.manifest.yaml",
            goal="original",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "replacement.manifest.yaml",
            goal="replacement",
            created="2026-02-01",
            sequence_number=2,
            supersedes=["original"],
        )

        chain = ManifestChain(manifest_dir, tmp_path)
        all_log = chain.event_log()

        output = format_chain_log(
            all_log, str(manifest_dir), json_mode=True, active_only=True
        )
        data = json.loads(output)

        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["slug"] == "replacement"


# ---------------------------------------------------------------------------
# cmd_chain integration
# ---------------------------------------------------------------------------


class TestCmdChainLog:
    def test_text_mode_returns_zero(self, tmp_path: Path) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "test.manifest.yaml",
            goal="test",
            created="2026-04-26",
            sequence_number=1,
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=False,
            active=False,
        )
        exit_code = cmd_chain(args)
        assert exit_code == 0

    def test_json_mode_returns_zero(self, tmp_path: Path) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "test.manifest.yaml",
            goal="test",
            created="2026-04-26",
            sequence_number=1,
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=True,
            active=False,
        )
        exit_code = cmd_chain(args)
        assert exit_code == 0

    def test_missing_manifest_dir_returns_2(self, tmp_path: Path) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(tmp_path / "nonexistent"),
            json=False,
            active=False,
        )
        exit_code = cmd_chain(args)
        assert exit_code == 2

    def test_json_output_contains_manifest_fields(self, tmp_path: Path, capsys) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "first.manifest.yaml",
            goal="first task",
            created="2026-01-01",
            sequence_number=10,
            version_tag="v2.0",
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=True,
            active=False,
        )
        cmd_chain(args)

        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert len(data) == 1
        entry = data[0]
        assert entry["slug"] == "first"
        assert entry["sequence_number"] == 10
        assert entry["version_tag"] == "v2.0"
        assert entry["goal"] == "first task"
        assert "source_path" in entry
        assert "superseded" in entry


# ---------------------------------------------------------------------------
# --until-seq and --version-tag flags
# ---------------------------------------------------------------------------


class TestChainLogUntilSeq:
    def test_until_seq_filters_text_output(self, tmp_path: Path, capsys) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=False,
            active=False,
            until_seq=1,
            version_tag=None,
        )
        exit_code = cmd_chain(args)
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "a" in captured.out
        # Two manifests written, only one should appear (b filtered)
        assert captured.out.count(".manifest.yaml") == 1

    def test_until_seq_filters_json_output(self, tmp_path: Path, capsys) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=True,
            active=False,
            until_seq=1,
            version_tag=None,
        )
        cmd_chain(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert len(data) == 1
        assert data[0]["slug"] == "a"

    def test_until_seq_zero_returns_error(self, tmp_path: Path, capsys) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=False,
            active=False,
            until_seq=0,
            version_tag=None,
        )
        exit_code = cmd_chain(args)
        assert exit_code == 2

    def test_until_seq_active_removes_superseded_from_prefix(
        self, tmp_path: Path, capsys
    ) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "original.manifest.yaml",
            goal="original",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "replacement.manifest.yaml",
            goal="replacement",
            created="2026-02-01",
            sequence_number=2,
            supersedes=["original"],
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=True,
            active=True,
            until_seq=2,
            version_tag=None,
        )
        cmd_chain(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert len(data) == 1
        assert data[0]["slug"] == "replacement"


class TestChainLogVersionTag:
    def test_version_tag_filters_text_output(self, tmp_path: Path, capsys) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            version_tag="release-1",
        )
        _write_manifest(
            manifest_dir,
            "c.manifest.yaml",
            goal="third",
            created="2026-03-01",
            sequence_number=3,
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=False,
            active=False,
            until_seq=None,
            version_tag="release-1",
        )
        exit_code = cmd_chain(args)
        assert exit_code == 0

        captured = capsys.readouterr()
        assert "a" in captured.out
        assert "b" in captured.out
        # Three manifests written, only two should appear (c filtered)
        assert captured.out.count(".manifest.yaml") == 2

    def test_version_tag_missing_returns_empty_json(
        self, tmp_path: Path, capsys
    ) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=True,
            active=False,
            until_seq=None,
            version_tag="nonexistent",
        )
        cmd_chain(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert data == []

    def test_both_flags_until_seq_wins(self, tmp_path: Path, capsys) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )
        _write_manifest(
            manifest_dir,
            "b.manifest.yaml",
            goal="second",
            created="2026-02-01",
            sequence_number=2,
            version_tag="v1",
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=True,
            active=False,
            until_seq=1,
            version_tag="v1",
        )
        cmd_chain(args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)

        assert len(data) == 1
        assert data[0]["slug"] == "a"

    def test_version_tag_empty_string_returns_error(
        self, tmp_path: Path, capsys
    ) -> None:
        from maid_runner.cli.commands.chain import cmd_chain

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        _write_manifest(
            manifest_dir,
            "a.manifest.yaml",
            goal="first",
            created="2026-01-01",
            sequence_number=1,
        )

        args = argparse.Namespace(
            chain_command="log",
            manifest_dir=str(manifest_dir),
            json=False,
            active=False,
            until_seq=None,
            version_tag="",
        )
        exit_code = cmd_chain(args)
        assert exit_code == 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(
    manifest_dir: Path,
    filename: str,
    goal: str,
    created: str,
    sequence_number: int | None = None,
    version_tag: str | None = None,
    supersedes: list[str] | None = None,
) -> None:
    data: dict = {
        "schema": "2",
        "goal": goal,
        "type": "feature",
        "created": created,
        "files": {
            "create": [
                {
                    "path": "dummy.py",
                    "artifacts": [{"kind": "function", "name": "_placeholder"}],
                }
            ]
        },
        "validate": ["pytest tests/ -v"],
    }
    if sequence_number is not None:
        data["sequence_number"] = sequence_number
    if version_tag is not None:
        data["version_tag"] = version_tag
    if supersedes:
        data["supersedes"] = supersedes

    path = manifest_dir / filename
    path.write_text(yaml.dump(data))
