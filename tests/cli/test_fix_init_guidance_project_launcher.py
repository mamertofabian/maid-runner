"""Generated owned guidance invokes the existing project wrapper consistently."""

import argparse
import importlib
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from maid_runner.cli.commands.init import cmd_init

_START = "<!-- BEGIN MAID RUNNER -->"
_END = "<!-- END MAID RUNNER -->"


@pytest.fixture(autouse=True)
def _real_payload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build real distribution assets in a disposable directory for the I/O adapter."""
    root = Path(__file__).resolve().parents[2]
    workspace = tmp_path / "distribution"
    for directory in (".claude", ".codex", ".cursor"):
        shutil.copytree(root / directory, workspace / directory)
    subprocess.run(
        [sys.executable, str(root / "scripts/sync_claude_files.py")],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    payload_root = workspace / "maid_runner"
    init_command = importlib.import_module("maid_runner.cli.commands.init")
    monkeypatch.setattr(
        init_command, "_agent_payload_root", lambda tool: payload_root / tool
    )
    return payload_root


def _arguments(tool: str, force: bool = True) -> argparse.Namespace:
    return argparse.Namespace(tool=tool, force=force, check=False, dry_run=False)


def _wrapper(root: Path) -> Path:
    scripts = root / "scripts"
    scripts.mkdir(exist_ok=True)
    wrapper = scripts / "maid"
    wrapper.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > invocation.txt\n")
    wrapper.chmod(0o755)
    return wrapper


def _owned(path: Path) -> str:
    text = path.read_text()
    assert text.count(_START) == text.count(_END) == 1
    return text.split(_START, 1)[1].split(_END, 1)[0]


@pytest.mark.parametrize("tool,file", [("claude", "CLAUDE.md"), ("codex", "AGENTS.md")])
def test_wrapper_is_used_for_all_runnable_owned_maid_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    file: str,
    _real_payload: Path,
) -> None:
    root = tmp_path / "project with spaces"
    root.mkdir()
    _wrapper(root)
    monkeypatch.chdir(root)
    assert cmd_init(_arguments(tool)) == 0
    guidance = _owned(root / file)
    installed = root / f".{tool}" / "skills/maid-planner/SKILL.md"
    assert (
        installed.read_bytes()
        == (_real_payload / tool / "skills/maid-planner/SKILL.md").read_bytes()
    )
    for suffix in [
        "recall --for-manifest",
        "insights",
        "learn --include-status",
        "manifest promote",
        "plan revise",
        "learn`",
        "validators",
    ]:
        assert f"./scripts/maid {suffix}" in guidance
    if tool == "codex":
        assert "./scripts/maid hook scope-check --path" in guidance
    snippets = re.findall(r"`([^`]+)`", guidance)
    commands = [
        s
        for s in snippets
        if s.startswith(("maid ", "uv run maid ", "./scripts/maid "))
    ]
    assert commands
    assert all(command.startswith("./scripts/maid ") for command in commands), commands
    assert "`maid-planner`" in guidance and "`maid-implement-draft`" in guidance
    concrete = next(
        command for command in commands if command == "./scripts/maid insights"
    )
    executed = subprocess.run(
        shlex.split(concrete), cwd=root, capture_output=True, text=True, timeout=10
    )
    assert executed.returncode == 0, executed.stderr
    assert (root / "invocation.txt").read_text().splitlines() == ["insights"]


@pytest.mark.parametrize("tool,file", [("claude", "CLAUDE.md"), ("codex", "AGENTS.md")])
def test_force_init_preserves_user_text_and_managed_launcher_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str, file: str
) -> None:
    _wrapper(tmp_path)
    before = "# My instructions\nKeep user command `uv run maid test` unchanged.\n"
    after = "\nUser tail with `maid custom`.\n"
    path = tmp_path / file
    path.write_text(before + _START + "\nold owned text\n" + _END + after)
    monkeypatch.chdir(tmp_path)
    assert cmd_init(_arguments(tool)) == 0
    owned_once = _owned(path)
    assert cmd_init(_arguments(tool)) == 0
    assert _owned(path) == owned_once
    text = path.read_text()
    assert text.startswith(before.rstrip()) and text.endswith(after)
    assert "old owned text" not in text
    assert "./scripts/maid recall" in _owned(path)
    assert "Keep user command `uv run maid test` unchanged." in text
    assert "User tail with `maid custom`." in text


@pytest.mark.parametrize("tool,file", [("claude", "CLAUDE.md"), ("codex", "AGENTS.md")])
def test_without_wrapper_preserves_existing_project_guidance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str, file: str
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="fixture"\nversion="0.0.0"\ndependencies=["maid-runner"]\n'
    )
    monkeypatch.chdir(tmp_path)
    assert cmd_init(_arguments(tool)) == 0
    guidance = _owned(tmp_path / file)
    assert "uv run maid recall --for-manifest" in guidance
    assert "uv run maid manifest promote" in guidance
    assert "./scripts/maid " not in guidance


def test_force_refresh_tracks_wrapper_presence_without_rewriting_user_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cmd_init(_arguments("codex")) == 0
    path = tmp_path / "AGENTS.md"
    assert "uv run maid recall" in _owned(path)
    wrapper = _wrapper(tmp_path)
    assert cmd_init(_arguments("codex")) == 0
    assert "./scripts/maid recall" in _owned(path)
    wrapper.unlink()
    assert cmd_init(_arguments("codex")) == 0
    assert "uv run maid recall" in _owned(path)
    assert "./scripts/maid " not in _owned(path)
