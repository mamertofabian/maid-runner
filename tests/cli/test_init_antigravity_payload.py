"""Behavioral tests for Antigravity `maid init --tool antigravity` packaging, install, check, and uninstall."""

from __future__ import annotations

import io
import json
import shlex
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.cli.commands.init import cmd_init, uninstall_init_payload
from maid_runner.instruction_payload import (
    INSTRUCTION_PAYLOAD_VERSION,
    instruction_payload_metadata,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
MAID_SECTION_END = "<!-- END MAID RUNNER -->"
EXPECTED_DISTRIBUTABLE_SKILLS = [
    "maid-planner",
    "maid-plan-review",
    "maid-implement-draft",
    "maid-implementer",
    "maid-implementation-review",
    "maid-evolver",
    "maid-auditor",
    "maid-incident-logger",
    "maid-outcome-enrich",
    "maid-run-review",
]
ANTIGRAVITY_SCOPE_COMMAND = "maid hook scope-check --stdin --format antigravity"


def _commands_from_hooks(payload: object) -> list[str]:
    if isinstance(payload, dict):
        commands = (
            [payload["command"]] if isinstance(payload.get("command"), str) else []
        )
        for value in payload.values():
            commands.extend(_commands_from_hooks(value))
        return commands
    if isinstance(payload, list):
        return [command for item in payload for command in _commands_from_hooks(item)]
    return []


def test_sync_antigravity_payload_derives_skills_overlay_and_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.sync_claude_files import main as sync_main, sync_antigravity_payload

    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
    cursor_dir = workspace / ".cursor"
    cursor_dir.mkdir()
    shutil.copy2(PROJECT_ROOT / ".cursor" / "hooks.json", cursor_dir / "hooks.json")
    monkeypatch.chdir(workspace)

    sync_antigravity_payload()
    dest_root = workspace / "maid_runner" / "antigravity"
    assert (dest_root / "manifest.json").is_file()

    # Clear dest_root before running sync_main() so main() itself must invoke sync_antigravity_payload().
    shutil.rmtree(dest_root)
    sync_main()

    manifest = json.loads((dest_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["root"]["distributable"] == ["hooks.json"]
    assert manifest["skills"]["distributable"] == EXPECTED_DISTRIBUTABLE_SKILLS
    assert "maid-onboard" not in manifest["skills"]["distributable"]
    assert not any(
        name.startswith("maid-runner-") for name in manifest["skills"]["distributable"]
    )
    assert "maid-validate-hardening" not in manifest["skills"]["distributable"]

    hooks = json.loads((dest_root / "hooks.json").read_text(encoding="utf-8"))
    assert "maid-scope-check" in hooks
    pre_tool_use = hooks["maid-scope-check"]["PreToolUse"]
    matcher = pre_tool_use[0]["matcher"]
    for tool_name in (
        "write_file",
        "edit_file",
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
    ):
        assert tool_name in matcher
    assert _commands_from_hooks(pre_tool_use) == [ANTIGRAVITY_SCOPE_COMMAND]

    packaged_root = PROJECT_ROOT / "maid_runner" / "antigravity"
    assert (packaged_root / "manifest.json").read_text(encoding="utf-8") == (
        dest_root / "manifest.json"
    ).read_text(encoding="utf-8")
    assert (packaged_root / "hooks.json").read_text(encoding="utf-8") == (
        dest_root / "hooks.json"
    ).read_text(encoding="utf-8")

    for skill_name in EXPECTED_DISTRIBUTABLE_SKILLS:
        generated = (dest_root / "skills" / skill_name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        source = (workspace / ".claude" / "skills" / skill_name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        packaged = (packaged_root / "skills" / skill_name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert packaged == generated
        if skill_name == "maid-implementation-review":
            assert 'subagent_type: "maid-implementation-reviewer"' not in generated
            assert "invoke_subagent" in generated
            assert 'TypeName: "research"' in generated
            assert 'Model: "inherit"' in generated
            assert "manage_subagents" in generated
            # Ensure the overlay preserves the full surrounding canonical skill.
            for preserved_anchor in (
                "name: maid-implementation-review",
                "## Review Convergence Protocol",
                "## Phase 2 — Build the Review Packet",
                "## Outcome-Aware MAID Guidance",
                "## Phase 9 — Reconcile and Report",
            ):
                assert preserved_anchor in generated
        else:
            assert generated == source

    # Fail loudly if canonical review skill changes the expected Claude subagent block.
    review_source = (
        workspace / ".claude" / "skills" / "maid-implementation-review" / "SKILL.md"
    )
    review_source.write_text("# Unrecognized review skill without Claude block\n")
    with pytest.raises(ValueError, match="maid-implementation-review"):
        sync_antigravity_payload()

    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["maid_runner"]
    for pattern in (
        "antigravity/manifest.json",
        "antigravity/hooks.json",
        "antigravity/skills/*/SKILL.md",
    ):
        assert pattern in package_data

    makefile_text = (PROJECT_ROOT / "Makefile").read_text("utf-8")
    assert "maid_runner/antigravity/" in makefile_text


def test_init_antigravity_installs_agents_skills_hooks_and_shared_agents_md(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()
    parsed = parser.parse_args(["init", "--tool", "antigravity"])
    assert parsed.tool == "antigravity"

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "antigravity", "--dry-run"]) == 0
    dry_run_out = capsys.readouterr().out
    assert "Would create: .agents/manifest.json" in dry_run_out
    assert "Would create: .agents/hooks.json" in dry_run_out
    assert "Would create: .agents/skills/maid-planner/SKILL.md" in dry_run_out
    assert "Would update: AGENTS.md" in dry_run_out
    assert not (tmp_path / ".agents").exists()
    assert not (tmp_path / "AGENTS.md").exists()

    init_args = SimpleNamespace(
        tool="antigravity",
        force=False,
        dry_run=False,
        check=False,
        uninstall=False,
        json=False,
    )
    assert cmd_init(init_args) == 0
    capsys.readouterr()

    manifest = json.loads(
        (tmp_path / ".agents" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["metadata"] == instruction_payload_metadata()
    assert manifest["skills"]["distributable"] == EXPECTED_DISTRIBUTABLE_SKILLS
    installed_skills = sorted(
        path.name for path in (tmp_path / ".agents" / "skills").iterdir()
    )
    assert installed_skills == sorted(EXPECTED_DISTRIBUTABLE_SKILLS)
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".codex").exists()
    assert not (tmp_path / "CLAUDE.md").exists()

    review_skill = (
        tmp_path / ".agents" / "skills" / "maid-implementation-review" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "invoke_subagent" in review_skill
    assert 'TypeName: "research"' in review_skill
    assert 'subagent_type: "maid-implementation-reviewer"' not in review_skill

    agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert MAID_SECTION_START in agents_md
    assert MAID_SECTION_END in agents_md
    assert f"Instruction payload version: {INSTRUCTION_PAYLOAD_VERSION}" in agents_md
    assert "MAID Antigravity Skills Workflow" in agents_md
    assert ".agents/hooks.json" in agents_md
    assert "maid-planner" in agents_md
    assert "maid-implementation-review" in agents_md
    assert "docs/draft-manifest-workflow.md" in agents_md

    # Execute the exact installed hook command from `.agents/` against a real PreToolUse envelope.
    installed_hooks = json.loads(
        (tmp_path / ".agents" / "hooks.json").read_text(encoding="utf-8")
    )
    command_str = _commands_from_hooks(installed_hooks["maid-scope-check"])[0]
    argv = shlex.split(command_str)
    assert argv[0] == "maid"

    active_manifest = tmp_path / "manifests" / "demo.manifest.yaml"
    active_manifest.write_text(
        'schema: "2"\n'
        'goal: "Demo task"\n'
        "type: feature\n"
        'created: "2026-11-26T13:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/allowed.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: allowed\n"
        "validate:\n"
        "  - pytest -q\n",
        encoding="utf-8",
    )
    active_pointer = tmp_path / ".maid" / "active-manifest"
    active_pointer.parent.mkdir(parents=True, exist_ok=True)
    active_pointer.write_text("manifests/demo.manifest.yaml\n", encoding="utf-8")
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)
    monkeypatch.chdir(tmp_path / ".agents")

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "hookEventName": "PreToolUse",
                    "cwd": str(tmp_path),
                    "toolCall": {
                        "id": "toolu_01",
                        "name": "edit_file",
                        "args": {"Path": str(tmp_path / "src" / "allowed.py")},
                    },
                }
            )
        ),
    )
    assert main(argv[1:]) == 0
    allow_out = json.loads(capsys.readouterr().out.strip())
    assert allow_out == {"decision": "allow", "reason": "in-scope"}

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "hookEventName": "PreToolUse",
                    "cwd": str(tmp_path),
                    "toolCall": {
                        "id": "toolu_02",
                        "name": "write_file",
                        "args": {"Path": str(tmp_path / "src" / "blocked.py")},
                    },
                }
            )
        ),
    )
    assert main(argv[1:]) == 0
    deny_out = json.loads(capsys.readouterr().out.strip())
    assert set(deny_out) == {"decision", "reason"}
    assert deny_out["decision"] == "deny"
    assert "manifests/demo.manifest.yaml" in deny_out["reason"]


def test_init_antigravity_merges_existing_hooks_rewrites_launcher_and_prunes_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text(
        "Project header\n\n"
        f"{MAID_SECTION_START}\n"
        "old guidance\n"
        f"{MAID_SECTION_END}\n\n"
        "Project footer\n",
        encoding="utf-8",
    )
    hooks_path = tmp_path / ".agents" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "lint-checker": {
                    "PostToolUse": [
                        {
                            "matcher": "run_command",
                            "hooks": [{"type": "command", "command": "./lint.sh"}],
                        }
                    ]
                },
                "maid-scope-check": {
                    "PreToolUse": [
                        {
                            "matcher": "write_file|edit_file",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": ANTIGRAVITY_SCOPE_COMMAND,
                                },
                                {"type": "command", "command": "python sibling.py"},
                            ],
                        }
                    ]
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".agents" / "manifest.json").write_text(
        json.dumps({"skills": {"distributable": ["old-skill"]}}),
        encoding="utf-8",
    )
    stale_skill = tmp_path / ".agents" / "skills" / "old-skill" / "SKILL.md"
    stale_skill.parent.mkdir(parents=True)
    stale_skill.write_text("stale\n", encoding="utf-8")
    custom_skill = tmp_path / ".agents" / "skills" / "custom-skill" / "SKILL.md"
    custom_skill.parent.mkdir(parents=True)
    custom_skill.write_text("custom\n", encoding="utf-8")

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "maid").write_text('#!/bin/sh\nexec maid "$@"\n', encoding="utf-8")

    assert main(["init", "--tool", "antigravity", "--force"]) == 0
    # Second --force run must remain idempotent with the launcher-rewritten command.
    assert main(["init", "--tool", "antigravity", "--force"]) == 0

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert hooks["lint-checker"]["PostToolUse"][0]["hooks"][0]["command"] == "./lint.sh"
    commands = _commands_from_hooks(hooks["maid-scope-check"])
    assert (
        commands.count("../scripts/maid hook scope-check --stdin --format antigravity")
        == 1
    )
    assert ANTIGRAVITY_SCOPE_COMMAND not in commands
    assert commands.count("python sibling.py") == 1
    maid_entry = next(
        entry
        for entry in hooks["maid-scope-check"]["PreToolUse"]
        if "../scripts/maid hook scope-check --stdin --format antigravity"
        in _commands_from_hooks(entry)
    )
    for tool_name in (
        "write_file",
        "edit_file",
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
    ):
        assert tool_name in maid_entry["matcher"]

    assert not stale_skill.parent.exists()
    assert custom_skill.read_text(encoding="utf-8") == "custom\n"

    agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "Project header" in agents_md
    assert "Project footer" in agents_md
    assert "old guidance" not in agents_md
    assert "`./scripts/maid " in agents_md


def test_init_check_reports_antigravity_current_and_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "antigravity"]) == 0
    capsys.readouterr()

    assert main(["init", "--check", "--json"]) == 0
    current = json.loads(capsys.readouterr().out)
    assert current["status"] == "current"
    assert current["installed"]["antigravity"] == {
        "manifest_path": ".agents/manifest.json",
        "present": True,
        "instruction_payload_version": INSTRUCTION_PAYLOAD_VERSION,
        "status": "current",
    }

    assert main(["init", "--check"]) == 0
    text_out = capsys.readouterr().out
    assert "antigravity: current" in text_out

    manifest_path = tmp_path / ".agents" / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["metadata"]["instruction_payload_version"] = "1900.01.01"
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    assert main(["init", "--check", "--json"]) == 1
    stale = json.loads(capsys.readouterr().out)
    assert stale["status"] == "stale"
    assert stale["installed"]["antigravity"]["status"] == "stale"
    assert (
        stale["installed"]["antigravity"]["instruction_payload_version"] == "1900.01.01"
    )

    # Current codex + stale antigravity still reports overall stale.
    assert main(["init", "--tool", "codex", "--force"]) == 0
    capsys.readouterr()
    assert main(["init", "--check", "--json"]) == 1
    mixed = json.loads(capsys.readouterr().out)
    assert mixed["status"] == "stale"
    assert mixed["installed"]["codex"]["status"] == "current"
    assert mixed["installed"]["antigravity"]["status"] == "stale"


def test_init_uninstall_antigravity_removes_only_owned_payload_and_preserves_user_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("Prefix\n\nSuffix\n", encoding="utf-8")
    hooks_path = tmp_path / ".agents" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "lint-checker": {
                    "PostToolUse": [
                        {
                            "matcher": "run_command",
                            "hooks": [{"type": "command", "command": "./lint.sh"}],
                        }
                    ]
                },
                "custom-strict-guard": {
                    "PreToolUse": [
                        {
                            "matcher": "write_file",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": ANTIGRAVITY_SCOPE_COMMAND,
                                }
                            ],
                        }
                    ]
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    assert main(["init", "--tool", "antigravity"]) == 0
    merged = json.loads(hooks_path.read_text(encoding="utf-8"))
    merged["maid-scope-check"]["PreToolUse"][0]["hooks"].append(
        {"type": "command", "command": "python sibling-user-hook.py"}
    )
    hooks_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    custom = tmp_path / ".agents" / "skills" / "custom-skill" / "SKILL.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("keep me\n", encoding="utf-8")

    preview = uninstall_init_payload(tmp_path, ("antigravity",), dry_run=True)
    assert (tmp_path / ".agents" / "manifest.json").is_file()
    report = uninstall_init_payload(tmp_path, ("antigravity",), dry_run=False)

    assert preview == report
    assert ".agents/manifest.json" in report.removed
    assert ".agents/hooks.json#maid-scope-check" in report.removed
    assert "AGENTS.md#maid-managed-block" in report.removed
    assert not (tmp_path / ".agents" / "manifest.json").exists()
    assert not (tmp_path / ".agents" / "skills" / "maid-planner").exists()
    assert custom.read_text(encoding="utf-8") == "keep me\n"

    remaining_hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert "lint-checker" in remaining_hooks
    assert "custom-strict-guard" in remaining_hooks
    assert _commands_from_hooks(remaining_hooks["custom-strict-guard"]) == [
        ANTIGRAVITY_SCOPE_COMMAND
    ]
    assert ANTIGRAVITY_SCOPE_COMMAND not in _commands_from_hooks(
        remaining_hooks["maid-scope-check"]
    )
    assert "python sibling-user-hook.py" in _commands_from_hooks(
        remaining_hooks["maid-scope-check"]
    )

    agents_md = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert MAID_SECTION_START not in agents_md
    assert agents_md.split() == ["Prefix", "Suffix"]

    # Single-tool uninstall preserves shared AGENTS.md when a co-owner remains installed.
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.chdir(isolated)
    assert main(["init", "--tool", "codex"]) == 0
    assert main(["init", "--tool", "antigravity", "--force"]) == 0
    assert main(["init", "--uninstall", "--tool", "antigravity"]) == 0
    assert not (isolated / ".agents" / "manifest.json").exists()
    assert (isolated / ".codex" / "manifest.json").is_file()
    assert MAID_SECTION_START in (isolated / "AGENTS.md").read_text(encoding="utf-8")
    # Uninstalling already-absent antigravity in a Codex-only repo also preserves AGENTS.md.
    assert main(["init", "--uninstall", "--tool", "antigravity"]) == 0
    assert MAID_SECTION_START in (isolated / "AGENTS.md").read_text(encoding="utf-8")

    # Auto-uninstall deduplicates cleanly when both Codex and Antigravity are installed,
    # prunes empty MAID containers, preserves unrelated empty user containers, and cleans ../scripts/maid hooks.
    coexist = tmp_path / "coexist"
    coexist.mkdir()
    (coexist / "scripts").mkdir()
    (coexist / "scripts" / "maid").write_text('#!/bin/sh\nexec maid "$@"\n')
    coexist_hooks = coexist / ".agents" / "hooks.json"
    coexist_hooks.parent.mkdir(parents=True)
    coexist_hooks.write_text(
        json.dumps({"empty-user-hook": {"PreToolUse": []}}, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(coexist)
    assert main(["init", "--tool", "codex"]) == 0
    assert main(["init", "--tool", "antigravity", "--force"]) == 0
    assert main(["init", "--uninstall"]) == 0
    assert not (coexist / ".codex" / "manifest.json").exists()
    assert not (coexist / ".agents" / "manifest.json").exists()
    assert MAID_SECTION_START not in (coexist / "AGENTS.md").read_text(encoding="utf-8")
    cleaned_coexist_hooks = json.loads(coexist_hooks.read_text(encoding="utf-8"))
    assert "maid-scope-check" not in cleaned_coexist_hooks
    assert cleaned_coexist_hooks == {"empty-user-hook": {"PreToolUse": []}}

    # Preflight failure on malformed `.agents/hooks.json` must not mutate manifest or AGENTS.md.
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    monkeypatch.chdir(malformed)
    assert main(["init", "--tool", "antigravity"]) == 0
    (malformed / ".agents" / "hooks.json").write_text(
        "{not valid json", encoding="utf-8"
    )
    agents_before = (malformed / "AGENTS.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        uninstall_init_payload(malformed, ("antigravity",), dry_run=False)
    assert (malformed / ".agents" / "manifest.json").is_file()
    assert (malformed / "AGENTS.md").read_text(encoding="utf-8") == agents_before


def test_antigravity_docs_cover_init_and_hook_format() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    agent_skills = (PROJECT_ROOT / "docs" / "agent-skills.md").read_text(
        encoding="utf-8"
    )

    assert "maid init --tool antigravity" in readme
    assert "### Repo-Level Antigravity Install" in readme
    assert "--format antigravity" in readme
    assert ".agents/hooks.json" in readme
    assert "maid init --tool antigravity" in agent_skills
    assert ".agents/hooks.json" in agent_skills
