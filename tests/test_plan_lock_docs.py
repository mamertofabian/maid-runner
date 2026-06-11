from argparse import Namespace
from pathlib import Path

from maid_runner.cli.commands.howto import cmd_howto


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_DOC = ROOT / "CLAUDE.md"
MAID_SPECS_DOC = ROOT / "docs/maid_specs.md"
README_DOC = ROOT / "README.md"
CLAUDE_PLANNER_SKILL = ROOT / ".claude/skills/maid-planner/SKILL.md"
CLAUDE_REVIEW_SKILL = ROOT / ".claude/skills/maid-implementation-review/SKILL.md"
CODEX_PLANNER_SKILL = ROOT / ".codex/skills/maid-planner/SKILL.md"
CODEX_REVIEW_SKILL = ROOT / ".codex/skills/maid-implementation-review/SKILL.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_plan_lock_docs_end_planning_loop_with_plan_lock() -> None:
    docs = {
        "CLAUDE.md": _read(CLAUDE_DOC),
        "docs/maid_specs.md": _read(MAID_SPECS_DOC),
        "README.md": _read(README_DOC),
    }

    for name, content in docs.items():
        assert "maid plan lock" in content, name
        assert "maid verify --require-plan-lock --require-red-evidence" in content, name
        assert "planning loop" in content.lower(), name
        assert "implementation handoff" in content.lower(), name


def test_plan_lock_docs_describe_exit_code_classification_and_revise() -> None:
    combined_docs = "\n".join(
        [
            _read(CLAUDE_DOC),
            _read(MAID_SPECS_DOC),
            _read(README_DOC),
        ]
    )

    for required in (
        "exit-code-only",
        "exit 1",
        "exits 2/3/4/5",
        "exit 0",
        "not red",
        "`maid plan lock --no-run` records `red_evidence: null`",
        "maid plan revise",
        "--reason",
        "E700 PLAN_LOCK_MISSING",
        "E701 BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK",
        "E702 MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK",
        "E703 PLAN_LOCK_STALE",
        "E704 RED_PHASE_EVIDENCE_MISSING",
        "E705 RED_PHASE_EVIDENCE_INVALID",
    ):
        assert required in combined_docs


def test_plan_lock_docs_describe_task_window_scope_and_unreadable_locks() -> None:
    combined_docs = "\n".join(
        [
            _read(CLAUDE_DOC),
            _read(MAID_SPECS_DOC),
            _read(README_DOC),
        ]
    )

    for required in (
        "task window",
        "E706 PLAN_LOCK_UNREADABLE",
    ):
        assert required in combined_docs

    specs = _read(MAID_SPECS_DOC)
    assert "E700" in specs and "task window" in specs
    assert "E704" in specs and "no plan lock" in specs
    assert "E701" in specs and "regardless of" in specs


def test_howto_commands_mention_task_window_scope(capsys) -> None:
    assert cmd_howto(Namespace(topic="commands")) == 0
    commands = capsys.readouterr().out
    assert "task window" in commands


def test_review_skill_payloads_treat_e700_to_e706_as_blockers() -> None:
    for content in (_read(CLAUDE_REVIEW_SKILL), _read(CODEX_REVIEW_SKILL)):
        assert "E700-E706" in content
        assert "task window" in content


def test_plan_lock_skill_payloads_quote_exact_commands() -> None:
    planner_payloads = [
        _read(CLAUDE_PLANNER_SKILL),
        _read(CODEX_PLANNER_SKILL),
    ]
    review_payloads = [
        _read(CLAUDE_REVIEW_SKILL),
        _read(CODEX_REVIEW_SKILL),
    ]

    for content in planner_payloads:
        assert "maid plan lock" in content
        assert "planning loop" in content.lower()

    for content in review_payloads:
        assert "maid verify --require-plan-lock --require-red-evidence" in content
        assert "plan lock" in content.lower()


def test_howto_workflow_mentions_plan_lock_commands(capsys) -> None:
    assert cmd_howto(Namespace(topic="workflow")) == 0
    workflow = capsys.readouterr().out
    assert "maid plan lock" in workflow
    assert "maid verify --require-plan-lock --require-red-evidence" in workflow

    assert cmd_howto(Namespace(topic="commands")) == 0
    commands = capsys.readouterr().out
    assert "maid plan lock" in commands
    assert "maid plan revise" in commands
    assert "maid plan status" in commands
    assert "--require-plan-lock" in commands
    assert "--require-red-evidence" in commands
