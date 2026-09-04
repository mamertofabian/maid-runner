"""Behavioral coverage for portable MAID init payloads."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from maid_runner.cli.commands._main import main


def _hook_commands(value: object) -> list[str]:
    if isinstance(value, dict):
        commands = [value["command"]] if isinstance(value.get("command"), str) else []
        for child in value.values():
            commands.extend(_hook_commands(child))
        return commands
    if isinstance(value, list):
        return [command for child in value for command in _hook_commands(child)]
    return []


def test_init_installs_generic_draft_guidance_without_runner_only_references(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "generic"]) == 0

    guidance = (tmp_path / "manifests" / "drafts" / "README.md").read_text()
    assert "000-parser-replacement-roadmap.md" not in guidance
    assert "Compiler-backed work must preserve the fast path" not in guidance


def test_init_adds_generated_advisory_paths_to_gitignore_without_clobbering(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("dist/\n# user rule\n")

    assert main(["init", "--tool", "generic"]) == 0

    updated = gitignore.read_text()
    assert updated.startswith("dist/\n# user rule\n")
    for path in (
        ".maid/outcomes.json",
        ".maid/outcomes-digest.json",
        ".maid/outcomes-digest.md",
        ".maid/outcomes-enrichment-prompt.json",
        ".maid/run-review-request.json",
        ".maid/run-review.json",
        ".maid/run-reviews/",
        ".maid/cache/",
    ):
        assert path in updated
    assert updated.count("# BEGIN MAID RUNNER GENERATED FILES") == 1
    assert updated.count("# END MAID RUNNER GENERATED FILES") == 1

    assert main(["init", "--tool", "generic", "--force"]) == 0
    assert gitignore.read_text() == updated


def test_init_upgrades_managed_gitignore_to_include_maid_cache(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(
        "dist/\n"
        "# BEGIN MAID RUNNER GENERATED FILES\n"
        ".maid/outcomes.json\n"
        ".maid/outcomes-digest.json\n"
        ".maid/outcomes-digest.md\n"
        ".maid/outcomes-enrichment-prompt.json\n"
        ".maid/run-review-request.json\n"
        ".maid/run-review.json\n"
        ".maid/run-reviews/\n"
        "# END MAID RUNNER GENERATED FILES\n"
    )

    assert main(["init", "--tool", "generic"]) == 0

    updated = gitignore.read_text()
    assert updated.startswith("dist/\n")
    assert ".maid/cache/" in updated
    assert ".maid/outcomes.json" in updated
    assert ".maid/run-reviews/" in updated
    assert updated.count("# BEGIN MAID RUNNER GENERATED FILES") == 1
    assert updated.count("# END MAID RUNNER GENERATED FILES") == 1


def test_init_uses_existing_project_maid_wrapper_for_generated_hooks(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "maid").write_text('#!/bin/sh\nexec maid "$@"\n')

    assert main(["init", "--tool", "claude"]) == 0

    pre_commit = yaml.safe_load((tmp_path / ".pre-commit-config.yaml").read_text())
    hook = pre_commit["repos"][0]["hooks"][0]
    assert hook["entry"].startswith("scripts/maid verify ")
    settings = json.loads((tmp_path / ".claude" / "settings.json").read_text())
    assert "./scripts/maid hook scope-check --stdin" in _hook_commands(settings)


def test_force_reinit_migrates_bare_scope_hook_to_project_wrapper(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "claude"]) == 0
    settings_path = tmp_path / ".claude" / "settings.json"
    before = json.loads(settings_path.read_text())
    before["hooks"]["PreToolUse"][0]["hooks"].append(
        {"type": "command", "command": "python user-scope-audit.py"}
    )
    empty_user_entry = {
        "matcher": "UserTool",
        "hooks": [],
        "metadata": {"owner": "user"},
    }
    before["hooks"]["PreToolUse"].append(empty_user_entry)
    settings_path.write_text(json.dumps(before))

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "maid").write_text('#!/bin/sh\nexec maid "$@"\n')

    assert main(["init", "--tool", "claude", "--force"]) == 0

    settings = json.loads(settings_path.read_text())
    commands = _hook_commands(settings)
    assert commands.count("./scripts/maid hook scope-check --stdin") == 1
    assert "maid hook scope-check --stdin" not in commands
    assert commands.count("python user-scope-audit.py") == 1
    assert empty_user_entry in settings["hooks"]["PreToolUse"]


def test_init_reports_malformed_gitignore_markers_as_gitignore_conflict(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".gitignore").write_text(
        "# BEGIN MAID RUNNER GENERATED FILES\n.maid/outcomes.json\n"
    )

    assert main(["init", "--tool", "generic"]) == 1

    error = capsys.readouterr().err
    assert ".gitignore configuration conflict" in error
    assert "Pre-commit configuration conflict" not in error
    assert not (tmp_path / ".pre-commit-config.yaml").exists()
