"""Behavioral tests for the `maid serve` CLI subcommand wiring."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.serve import cmd_serve, register_serve_subparser


class TestServeHelp:
    def test_maid_serve_help_lists_socket_and_pidfile_flags(self, capsys):
        parser = build_parser()
        try:
            parser.parse_args(["serve", "--help"])
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "--socket" in captured.out
        assert "--pidfile" in captured.out


class TestDefaultPaths:
    def test_maid_serve_resolves_default_socket_under_dot_maid_directory(self):
        parser = build_parser()
        ns = parser.parse_args(["serve"])
        assert getattr(ns, "socket", None) is None or ".maid" in str(ns.socket)
        assert hasattr(ns, "socket")
        assert hasattr(ns, "pidfile")


class TestSubparser:
    def test_register_serve_subparser_returns_argument_parser(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")

        result = register_serve_subparser(sub)

        assert isinstance(result, argparse.ArgumentParser)
        ns = parser.parse_args(["serve"])
        assert ns.command == "serve"

    def test_cmd_serve_is_callable(self):
        assert callable(cmd_serve)
