from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
AGENT_SKILLS_DOC = ROOT / "docs/agent-skills.md"

SKILL_GUIDANCE_PATHS = (
    ROOT / ".claude/skills/maid-implementer/SKILL.md",
    ROOT / "maid_runner/claude/skills/maid-implementer/SKILL.md",
    ROOT / ".codex/skills/maid-runner-draft-implement/SKILL.md",
    ROOT / "maid_runner/codex/skills/maid-runner-draft-implement/SKILL.md",
)

TASK_START_ANCHOR = "maid task start manifests/<slug>.manifest.yaml"
TASK_STOP_ANCHOR = "maid task stop"
VERIFY_AUTHORITY_ANCHOR = (
    "maid verify changed-scope checks remain the authoritative handoff evidence"
)
FAIL_OPEN_ANCHOR = "default fail-open policy"
STRICT_MODE_ANCHOR = "pass `--strict`"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_readme_documents_task_and_scope_check_workflow() -> None:
    readme = _read(README)

    assert "## Edit-Time Scope Enforcement" in readme
    assert "Command-specific contracts can define narrower meanings" in readme
    assert "`maid hook scope-check` exits `2` for a denied scope decision" in readme
    assert TASK_START_ANCHOR in readme
    assert TASK_STOP_ANCHOR in readme
    assert "maid hook scope-check --path <file-path>" in readme
    assert "maid hook scope-check --stdin" in readme
    assert '"decision": "allow"|"deny"' in readme
    assert '"active_manifest"' in readme
    assert "exit code 0 for allow, 2 for deny, and 1 for internal errors" in readme
    assert "Claude receives PreToolUse settings" in readme
    assert "Cursor receives `hooks.json`" in readme
    assert "Codex receives managed `AGENTS.md` guidance" in readme


def test_agent_skills_docs_place_task_lifecycle_in_workflow() -> None:
    agent_skills = _read(AGENT_SKILLS_DOC)

    assert TASK_START_ANCHOR in agent_skills
    assert "after `maid manifest promote`" in agent_skills
    assert TASK_STOP_ANCHOR in agent_skills
    assert "at handoff" in agent_skills
    assert FAIL_OPEN_ANCHOR in agent_skills
    assert STRICT_MODE_ANCHOR in agent_skills
    assert VERIFY_AUTHORITY_ANCHOR in agent_skills
    assert "Claude PreToolUse settings" in agent_skills
    assert "Cursor `hooks.json`" in agent_skills
    assert "Codex managed `AGENTS.md` guidance" in agent_skills


def test_skill_guidance_anchors_are_synced_to_distribution_copies() -> None:
    skill_texts = [_read(path) for path in SKILL_GUIDANCE_PATHS]

    for skill_text in skill_texts:
        assert TASK_START_ANCHOR in skill_text
        assert TASK_STOP_ANCHOR in skill_text
        assert FAIL_OPEN_ANCHOR in skill_text
        assert STRICT_MODE_ANCHOR in skill_text
        assert VERIFY_AUTHORITY_ANCHOR in skill_text

    source_claude, distributed_claude, source_codex, distributed_codex = skill_texts
    assert source_claude == distributed_claude
    assert source_codex == distributed_codex
