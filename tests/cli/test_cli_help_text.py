"""Behavioral tests for CLI help text completeness."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.daemon import register_daemon_subparser


def test_build_parser_visible_options_have_explicit_help_text() -> None:
    assert callable(register_daemon_subparser)
    parser = build_parser()

    missing_help = list(_visible_options_without_help(parser, ["maid"]))

    assert missing_help == []


def _visible_options_without_help(
    parser: argparse.ArgumentParser, command_path: list[str]
) -> list[str]:
    missing: list[str] = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, subparser in action.choices.items():
                missing.extend(
                    _visible_options_without_help(subparser, [*command_path, name])
                )
            continue
        if not action.option_strings or action.help is argparse.SUPPRESS:
            continue
        if not action.help:
            missing.append(
                f"{' '.join(command_path)} {'/'.join(action.option_strings)}"
            )
    return missing
