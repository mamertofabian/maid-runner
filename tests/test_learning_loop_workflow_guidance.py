import json
import shutil
import subprocess
import sys
from pathlib import Path

from maid_runner.cli.commands._main import build_parser


PROJECT_ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_SKILLS = (
    "maid-planner",
    "maid-plan-review",
    "maid-implementer",
    "maid-implementation-review",
)

RECALL_THREADED_SKILLS = (
    "maid-plan-review",
    "maid-implementer",
    "maid-implementation-review",
)

EXACT_RECALL_COMMANDS = (
    "maid recall --for-manifest <path>",
    "maid recall --for-manifest <path> --plan-packet",
)

FAILURE_LESSON_COMMAND = (
    "maid learn --include-status completed --include-status abandoned"
)

PHASE_INFLUENCE_TERMS = {
    "maid-planner": (
        "manifest scope",
        "behavioral tests",
        "temptations",
        "open questions",
    ),
    "maid-plan-review": (
        "review findings",
        "approval questions",
        "requested revisions",
    ),
    "maid-implementer": (
        "focused tests",
        "implementation approach",
        "risk controls",
        "inside the approved scope",
    ),
    "maid-implementation-review": (
        "review focus",
        "Outcome capture",
        "candidate follow-up work",
    ),
}


def _read(relative_path: str, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text()


def _skill_path(tool: str, skill_name: str) -> str:
    return f".{tool}/skills/{skill_name}/SKILL.md"


def _distributed_path(tool: str, skill_name: str) -> str:
    return f"maid_runner/{tool}/skills/{skill_name}/SKILL.md"


def _source_skill_texts() -> dict[tuple[str, str], str]:
    return {
        (tool, skill_name): _read(_skill_path(tool, skill_name))
        for tool in ("claude", "codex")
        for skill_name in WORKFLOW_SKILLS
    }


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _normalized_lower(text: str) -> str:
    return _normalized(text).lower()


def _command_line_count(text: str, command: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip() == command)


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
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


def _command_options(command: str) -> set[str]:
    parser = build_parser()
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if choices and command in choices:
            return {
                option
                for command_action in choices[command]._actions
                for option in command_action.option_strings
            }
    raise AssertionError(f"parser has no {command!r} command")


def test_workflow_skills_have_active_insights_trigger() -> None:
    for skill_name in WORKFLOW_SKILLS:
        for tool in ("claude", "codex"):
            text = _read(_skill_path(tool, skill_name))
            normalized = _normalized_lower(text)

            assert "review recurring outcome lessons with `maid insights`" in normalized
            assert "before" in normalized
            assert "active insights trigger" in normalized


def test_recall_threads_into_implementation_and_review() -> None:
    for skill_name in RECALL_THREADED_SKILLS:
        for tool in ("claude", "codex"):
            text = _read(_skill_path(tool, skill_name))
            normalized = _normalized_lower(text)

            assert "manifest-derived outcome recall" in normalized
            assert "active recall guidance" in normalized
            for command in EXACT_RECALL_COMMANDS:
                assert _command_line_count(text, command) == 1


def test_non_completed_recall_guidance_present() -> None:
    for text in _source_skill_texts().values():
        assert FAILURE_LESSON_COMMAND in text
        normalized = _normalized_lower(text)
        assert "failed or abandoned outcome lessons" in normalized
        assert "intentional opt-in" in normalized
        assert "completed-only default" in normalized


def test_workflow_guidance_uses_registered_options() -> None:
    assert "--include-status" in _command_options("learn")
    recall_options = _command_options("recall")
    insights_options = _command_options("insights")
    assert {"--for-manifest", "--plan-packet", "--allow-stale-index"} <= recall_options
    assert {"--limit", "--json", "--allow-stale-index"} <= insights_options

    invented_insights_flags = (
        "--include-status",
        "--for-manifest",
        "--plan-packet",
        "--status",
        "--tag",
        "--text",
    )
    for text in _source_skill_texts().values():
        for line in text.splitlines():
            if "maid recall" in line:
                assert "--include-status" not in line
            if "maid insights" in line:
                for flag in invented_insights_flags:
                    assert flag not in line


def test_workflow_guidance_handles_stale_indexes_explicitly() -> None:
    for text in _source_skill_texts().values():
        normalized = _normalized_lower(text)
        assert "stale index fails by default" in normalized
        assert "run `maid learn`" in text
        assert "--allow-stale-index" in text
        assert "stale advisory read is acceptable" in normalized


def test_workflow_guidance_requires_learning_evidence_digestion() -> None:
    for text in _source_skill_texts().values():
        normalized = _normalized_lower(text)

        assert "learning evidence digestion" in normalized
        assert "identify applicable lessons" in normalized
        assert "reject stale or irrelevant lessons" in normalized
        assert "state what changed because of the evidence" in normalized


def test_learning_evidence_digest_is_phase_specific() -> None:
    for skill_name, phase_terms in PHASE_INFLUENCE_TERMS.items():
        for tool in ("claude", "codex"):
            normalized = _normalized_lower(_read(_skill_path(tool, skill_name)))
            for term in phase_terms:
                assert term.lower() in normalized


def test_workflow_guidance_closes_loop_between_outcomes_and_decisions() -> None:
    for text in _source_skill_texts().values():
        normalized = _normalized_lower(text)

        assert "close the loop" in normalized
        assert "outcome records and current agent decisions" in normalized
        assert "raw recall or insights transcript" in normalized


def test_workflow_guidance_stays_advisory() -> None:
    for text in _source_skill_texts().values():
        normalized = _normalized_lower(text)

        assert "planning evidence only" in normalized
        assert "do not replace behavioral tests" in normalized
        assert "declared scope" in normalized or "declared artifacts" in normalized
        assert "validation" in normalized
        assert "review" in normalized
        assert (
            "do not create an approval, promotion, done, or review gate" in normalized
        )


def test_workflow_guidance_synced(tmp_path: Path) -> None:
    synced_workspace = _sync_distribution(tmp_path)

    for skill_name in WORKFLOW_SKILLS:
        for tool in ("claude", "codex"):
            source_path = _skill_path(tool, skill_name)
            generated_path = _distributed_path(tool, skill_name)
            source_text = _read(source_path)
            generated_text = _read(generated_path, root=synced_workspace)

            assert generated_text == source_text
            assert "learning evidence digestion" in generated_text
            assert (
                "review recurring Outcome lessons with `maid insights`"
                in generated_text
            )


def test_workflow_guidance_distribution_manifests_include_all_four_skills(
    tmp_path: Path,
) -> None:
    synced_workspace = _sync_distribution(tmp_path)
    claude_manifest = json.loads(
        _read("maid_runner/claude/manifest.json", root=synced_workspace)
    )
    codex_manifest = json.loads(
        _read("maid_runner/codex/manifest.json", root=synced_workspace)
    )

    for skill_name in WORKFLOW_SKILLS:
        assert skill_name in claude_manifest["skills"]["distributable"]
        assert skill_name in codex_manifest["skills"]["distributable"]
