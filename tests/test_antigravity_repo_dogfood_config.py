"""Behavioral tests for `maid-runner`'s own `.agents/` Antigravity dogfood configuration."""

from __future__ import annotations

import io
import json
import shlex
from pathlib import Path

import pytest

from maid_runner.cli.commands._main import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_GENERIC_SKILLS = {
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
}
EXPECTED_INTERNAL_SKILLS = {
    "maid-runner-cleanup-and-refactor",
    "maid-runner-draft-implement",
    "maid-runner-performance-optimization",
    "maid-runner-self-improvement",
    "maid-validate-hardening",
}


def _resolve_skills_json_entries(skills_json_path: Path) -> list[tuple[str, Path]]:
    config = json.loads(skills_json_path.read_text(encoding="utf-8"))
    resolved: list[tuple[str, Path]] = []
    for entry in config.get("entries", []):
        entry_dir = PROJECT_ROOT / entry["path"]
        assert entry_dir.is_dir(), f"Missing skills entry path: {entry['path']}"
        include_only = set(entry.get("include_only", []))
        exclude = set(entry.get("exclude", []))
        for child in sorted(entry_dir.iterdir()):
            if not child.is_dir() or not (child / "SKILL.md").is_file():
                continue
            if include_only and child.name not in include_only:
                continue
            if child.name in exclude:
                continue
            resolved.append((child.name, child / "SKILL.md"))
    return resolved


def test_repo_antigravity_skills_json_resolves_generic_and_internal_skills_without_duplicates() -> (
    None
):
    skills_json = PROJECT_ROOT / ".agents" / "skills.json"
    assert skills_json.is_file()
    assert not (PROJECT_ROOT / ".agents" / "skills").exists()

    resolved = _resolve_skills_json_entries(skills_json)
    names = [name for name, _ in resolved]
    assert len(names) == len(
        set(names)
    ), f"Duplicate skill names in .agents/skills.json: {names}"
    assert set(names) == EXPECTED_GENERIC_SKILLS | EXPECTED_INTERNAL_SKILLS
    assert "maid-onboard" not in names

    by_name = dict(resolved)
    review_text = by_name["maid-implementation-review"].read_text(encoding="utf-8")
    assert "invoke_subagent" in review_text
    assert 'TypeName: "research"' in review_text
    assert 'subagent_type: "maid-implementation-reviewer"' not in review_text


def test_repo_antigravity_hooks_json_executes_scope_check_from_agents_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hooks_json = PROJECT_ROOT / ".agents" / "hooks.json"
    assert hooks_json.is_file()

    hooks = json.loads(hooks_json.read_text(encoding="utf-8"))
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

    command_str = pre_tool_use[0]["hooks"][0]["command"]
    argv = shlex.split(command_str)
    assert argv[:3] == ["uv", "run", "maid"]
    maid_argv = argv[3:]

    demo_repo = tmp_path / "repo"
    (demo_repo / ".agents").mkdir(parents=True)
    demo_manifest = demo_repo / "manifests" / "demo.manifest.yaml"
    demo_manifest.parent.mkdir(parents=True)
    demo_manifest.write_text(
        'schema: "2"\n'
        'goal: "Demo"\n'
        "type: feature\n"
        'created: "2026-11-26T14:12:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/ok.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: ok\n"
        "validate:\n"
        "  - pytest -q\n",
        encoding="utf-8",
    )
    active_pointer = demo_repo / ".maid" / "active-manifest"
    active_pointer.parent.mkdir(parents=True)
    active_pointer.write_text("manifests/demo.manifest.yaml\n", encoding="utf-8")

    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)
    monkeypatch.chdir(demo_repo / ".agents")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "hookEventName": "PreToolUse",
                    "cwd": str(demo_repo),
                    "toolCall": {
                        "name": "edit_file",
                        "args": {"Path": str(demo_repo / "src" / "blocked.py")},
                    },
                }
            )
        ),
    )
    assert main(maid_argv) == 0
    decision = json.loads(capsys.readouterr().out.strip())
    assert set(decision) == {"decision", "reason"}
    assert decision["decision"] == "deny"

    agents_md = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "invoke_subagent" in agents_md
    assert 'TypeName="research"' in agents_md or "research" in agents_md
