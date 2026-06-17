"""Behavioral tests for hook-enabled `maid init` payloads."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
MAID_SECTION_END = "<!-- END MAID RUNNER -->"
SCOPE_CHECK_COMMAND = "maid hook scope-check --stdin"


def _commands_from_hook_payload(payload: object) -> list[str]:
    commands: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "command" and isinstance(value, str):
                commands.append(value)
            else:
                commands.extend(_commands_from_hook_payload(value))
    elif isinstance(payload, list):
        for item in payload:
            commands.extend(_commands_from_hook_payload(item))
    return commands


def _contains_write_edit_matcher(payload: object) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"matcher", "tool", "tools", "event", "events"}:
                text = " ".join(value) if isinstance(value, list) else str(value)
                if "Write" in text and "Edit" in text:
                    return True
            if _contains_write_edit_matcher(value):
                return True
    elif isinstance(payload, list):
        return any(_contains_write_edit_matcher(item) for item in payload)
    return False


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
    cursor_source = workspace / ".cursor"
    cursor_source.mkdir()
    shutil.copy2(PROJECT_ROOT / ".cursor" / "hooks.json", cursor_source)
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(PROJECT_ROOT / "scripts/sync_claude_files.py", scripts_dir)

    subprocess.run(
        [sys.executable, "scripts/sync_claude_files.py"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return workspace


def _read_project(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text()


def test_init_claude_installs_scope_check_hook_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)

    exit_code = main(["init", "--tool", "claude"])

    assert exit_code == 0
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    pre_tool_use = settings["hooks"]["PreToolUse"]
    assert _contains_write_edit_matcher(pre_tool_use)
    assert SCOPE_CHECK_COMMAND in _commands_from_hook_payload(pre_tool_use)


def test_init_claude_merges_existing_settings_without_clobbering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir()
    settings_path.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Bash(pytest:*)"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python existing-hook.py",
                                }
                            ],
                        }
                    ],
                    "PostToolUse": [
                        {
                            "matcher": "*",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python after-hook.py",
                                }
                            ],
                        }
                    ],
                },
            },
            indent=2,
        )
        + "\n"
    )

    exit_code = main(["init", "--tool", "claude", "--force"])

    assert exit_code == 0
    settings = json.loads(settings_path.read_text())
    assert settings["permissions"] == {"allow": ["Bash(pytest:*)"]}
    assert settings["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == (
        "python after-hook.py"
    )
    pre_tool_use = settings["hooks"]["PreToolUse"]
    assert any(entry.get("matcher") == "Read" for entry in pre_tool_use)
    assert _contains_write_edit_matcher(pre_tool_use)
    assert SCOPE_CHECK_COMMAND in _commands_from_hook_payload(pre_tool_use)


def test_init_cursor_installs_scope_check_hook_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)

    exit_code = main(["init", "--tool", "cursor"])

    assert exit_code == 0
    assert (tmp_path / ".cursor" / "manifest.json").is_file()
    hooks = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
    assert _contains_write_edit_matcher(hooks)
    assert SCOPE_CHECK_COMMAND in _commands_from_hook_payload(hooks)
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".codex").exists()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_init_hook_payload_dry_run_and_distribution_parity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "claude", "--dry-run"]) == 0
    claude_output = capsys.readouterr().out
    assert "Would create: .claude/settings.json" in claude_output

    assert main(["init", "--tool", "cursor", "--dry-run"]) == 0
    cursor_output = capsys.readouterr().out
    assert "Would create: .cursor/manifest.json" in cursor_output
    assert "Would create: .cursor/hooks.json" in cursor_output

    assert main(["init", "--tool", "codex"]) == 0
    agents_md = (tmp_path / "AGENTS.md").read_text()
    managed_section = agents_md.split(MAID_SECTION_START, 1)[1].split(
        MAID_SECTION_END, 1
    )[0]
    assert "maid hook scope-check --path <file>" in managed_section
    assert "exit code 2" in managed_section
    assert "out-of-scope" in managed_section

    pyproject = tomllib.loads(_read_project("pyproject.toml"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["maid_runner"]
    for pattern in (
        "claude/settings.json",
        "cursor/manifest.json",
        "cursor/hooks.json",
    ):
        assert pattern in package_data

    synced_workspace = _sync_distribution(tmp_path)
    assert (
        synced_workspace / "maid_runner" / "claude" / "settings.json"
    ).read_text() == (synced_workspace / ".claude" / "settings.json").read_text()
    cursor_manifest = json.loads(
        (synced_workspace / "maid_runner" / "cursor" / "manifest.json").read_text()
    )
    assert cursor_manifest["root"]["distributable"] == ["hooks.json"]
    assert (synced_workspace / "maid_runner" / "cursor" / "hooks.json").read_text() == (
        synced_workspace / ".cursor" / "hooks.json"
    ).read_text()
