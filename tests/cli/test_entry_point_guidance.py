"""Behavioral contract for newcomer guidance wired to MAID entry points."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

QUICKSTART_POINTER = "maid howto quickstart"
COMMAND_LIST_MARKER = "Validate manifests against code"


def _help_text() -> str:
    from maid_runner.cli.commands._main import build_parser

    return build_parser().format_help()


def _topic_output(topic: str, capsys: pytest.CaptureFixture[str]) -> str:
    import argparse

    from maid_runner.cli.commands.howto import cmd_howto

    assert cmd_howto(argparse.Namespace(topic=topic)) == 0
    return capsys.readouterr().out


def _listed_topics(capsys: pytest.CaptureFixture[str]) -> list[str]:
    import argparse

    from maid_runner.cli.commands.howto import cmd_howto

    assert cmd_howto(argparse.Namespace(topic=None)) == 0
    listing = capsys.readouterr().out
    return re.findall(r"^\s+maid howto (\S+)$", listing, flags=re.MULTILINE)


def _run_init(capsys: pytest.CaptureFixture[str]) -> str:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.init import cmd_init

    args = build_parser().parse_args(["init", "--tool", "generic"])

    assert cmd_init(args) == 0
    return capsys.readouterr().out


def _readme_section(heading: str) -> str:
    text = README.read_text(encoding="utf-8")
    body = text.split(f"\n## {heading}\n", 1)[1]
    return body.split("\n## ", 1)[0]


def test_top_level_help_replaces_command_wall_with_metavar() -> None:
    help_text = _help_text()

    assert "<command>" in help_text
    assert "{validate,validators" not in help_text


def test_top_level_help_points_newcomers_at_quickstart() -> None:
    help_text = _help_text()

    assert QUICKSTART_POINTER in help_text
    assert help_text.index(QUICKSTART_POINTER) < help_text.index(COMMAND_LIST_MARKER)


def test_top_level_help_start_here_block_names_core_commands() -> None:
    help_text = _help_text()

    assert "Start here:" in help_text
    start_here = help_text.split("Start here:", 1)[1]

    for command in ("maid init", QUICKSTART_POINTER, "maid validate", "maid test"):
        assert command in start_here


def test_top_level_help_still_lists_every_command() -> None:
    help_text = _help_text()

    for command in (
        "validate",
        "test",
        "verify",
        "snapshot",
        "snapshot-system",
        "bootstrap",
        "manifest",
        "manifests",
        "files",
        "init",
        "graph",
        "coherence",
        "schema",
        "howto",
        "chain",
        "benchmark",
        "serve",
        "audit",
    ):
        assert command in help_text


def test_init_output_ends_with_quickstart_next_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    output = _run_init(capsys)

    assert "Next steps:" in output
    assert QUICKSTART_POINTER in output
    assert output.rstrip().endswith(QUICKSTART_POINTER)


def test_init_next_steps_follow_git_hook_guidance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    output = _run_init(capsys)

    assert "core.hooksPath" in output
    assert "Next steps:" in output
    assert output.index("core.hooksPath") < output.index("Next steps:")


def test_howto_quickstart_omits_advanced_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    quickstart = _topic_output("quickstart", capsys)

    assert "bootstrap --rank" not in quickstart
    assert "risk-v1" not in quickstart
    assert "plan lock" not in quickstart
    assert "maid verify" not in quickstart
    assert "--mode" not in quickstart


def test_howto_quickstart_covers_first_win_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    quickstart = _topic_output("quickstart", capsys)

    assert "Quick Start" in quickstart
    assert "maid init" in quickstart
    assert "maid validate" in quickstart
    assert "maid test" in quickstart


def test_howto_brownfield_topic_covers_rank_and_from_diff(
    capsys: pytest.CaptureFixture[str],
) -> None:
    brownfield = _topic_output("brownfield", capsys)

    assert "maid bootstrap --rank" in brownfield
    assert "maid manifest from-diff" in brownfield
    assert "needs_review" in brownfield
    assert "Exactly one of --since, --base-ref, or --worktree is required" in brownfield


def test_howto_brownfield_topic_states_deterministic_ranking_semantics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    brownfield = _topic_output("brownfield", capsys)

    assert "risk-v1" in brownfield
    assert "legacy-v1" in brownfield
    assert "orders by churn descending" in brownfield
    assert "inbound_refs descending" in brownfield
    assert "public_artifacts descending" in brownfield
    assert "path ascending" in brownfield


def test_howto_topic_list_includes_brownfield(
    capsys: pytest.CaptureFixture[str],
) -> None:
    topics = _listed_topics(capsys)

    assert "quickstart" in topics
    assert "brownfield" in topics


def test_howto_topics_chain_to_a_next_topic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    topics = _listed_topics(capsys)
    assert topics

    broken_links: list[str] = []
    next_topic: dict[str, str] = {}
    for topic in topics:
        targets = re.findall(
            r"^Next: maid howto (\S+)$",
            _topic_output(topic, capsys),
            flags=re.MULTILINE,
        )
        if len(targets) != 1:
            broken_links.append(f"{topic}: expected one Next link, got {targets}")
            continue
        target = targets[0]
        if target == topic:
            broken_links.append(f"{topic}: links to itself")
        elif target not in topics:
            broken_links.append(f"{topic}: links to unknown topic '{target}'")
        else:
            next_topic[topic] = target

    assert broken_links == []

    visited: list[str] = []
    current = "quickstart"
    while current not in visited:
        visited.append(current)
        current = next_topic[current]

    assert sorted(visited) == sorted(topics)


def test_readme_quick_start_presents_flagless_first_win() -> None:
    quick_start = _readme_section("Quick Start")

    assert "pip install maid-runner" in quick_start
    assert "maid init" in quick_start
    assert "maid howto" in quick_start
    assert "maid verify" not in quick_start
    assert "risk-v1" not in quick_start
    assert "maid manifest from-diff" not in quick_start
    assert "--mode" not in quick_start
    assert "manifests/drafts/" not in quick_start


def test_readme_howto_row_lists_actual_topics(
    capsys: pytest.CaptureFixture[str],
) -> None:
    readme = README.read_text(encoding="utf-8")
    howto_row = next(
        line for line in readme.splitlines() if line.startswith("| `maid howto`")
    )

    spec = howto_row.split("--section ", 1)[1].split("`", 1)[0]
    advertised = {part.strip() for part in spec.split("\\|")}

    assert advertised == set(_listed_topics(capsys))


def test_readme_retains_brownfield_entry_outside_quick_start() -> None:
    readme = README.read_text(encoding="utf-8")
    quick_start = _readme_section("Quick Start")

    for term in (
        "Brownfield entry",
        "maid bootstrap --rank",
        "maid manifest from-diff",
        "reviewed drafts per change",
    ):
        assert term in readme
        assert term not in quick_start
