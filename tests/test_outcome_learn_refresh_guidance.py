import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

OUTCOME_CAPTURE_GUIDANCE_FILES = (
    "AGENTS.md",
    "docs/manifest-outcome-records.md",
    ".claude/skills/maid-runner-draft-implement/SKILL.md",
    ".codex/skills/maid-runner-draft-implement/SKILL.md",
    "maid_runner/codex/skills/maid-runner-draft-implement/SKILL.md",
    ".claude/skills/maid-implementation-review/SKILL.md",
    ".codex/skills/maid-implementation-review/SKILL.md",
    "maid_runner/codex/skills/maid-implementation-review/SKILL.md",
)

LEARN_REFRESH_TERMS = (
    "After Outcome capture, run `uv run maid learn`",
    "refresh the local `.maid/outcomes.json` advisory index",
    "generated and ignored; do not commit it",
    "report the refresh failure as advisory unless recall or insights are required",
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / ".claude", workspace / ".claude")
    shutil.copytree(ROOT / ".codex", workspace / ".codex")
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(ROOT / "scripts/sync_claude_files.py", scripts_dir)

    subprocess.run(
        [sys.executable, "scripts/sync_claude_files.py"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return workspace


def _assert_learn_refresh_guidance(text: str) -> None:
    for term in LEARN_REFRESH_TERMS:
        assert term in text


def test_outcome_capture_guidance_refreshes_learned_index() -> None:
    for guidance_file in OUTCOME_CAPTURE_GUIDANCE_FILES:
        guidance_text = _read(guidance_file)
        assert "After Outcome capture, run `uv run maid learn`" in guidance_text
        _assert_learn_refresh_guidance(guidance_text)


def test_codex_draft_implement_payload_matches_source_after_refresh_guidance() -> None:
    source = _read(".codex/skills/maid-runner-draft-implement/SKILL.md")
    packaged = _read("maid_runner/codex/skills/maid-runner-draft-implement/SKILL.md")

    assert packaged == source


def test_claude_review_payload_gets_refresh_guidance_from_sync(tmp_path: Path) -> None:
    synced_workspace = _sync_distribution(tmp_path)
    synced_review_skill = (
        synced_workspace
        / "maid_runner/claude/skills/maid-implementation-review/SKILL.md"
    ).read_text(encoding="utf-8")

    assert "After Outcome capture, run `uv run maid learn`" in synced_review_skill
    _assert_learn_refresh_guidance(synced_review_skill)


def test_init_guidance_refreshes_learned_index(tmp_path, monkeypatch) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands.init import cmd_init

    assert callable(cmd_init)

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "codex"]) == 0
    agents_guidance = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    _assert_learn_refresh_guidance(agents_guidance)

    assert main(["init", "--tool", "claude", "--force"]) == 0
    claude_guidance = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    _assert_learn_refresh_guidance(claude_guidance)
