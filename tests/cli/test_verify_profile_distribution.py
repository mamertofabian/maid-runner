"""Behavioral contract for distributing verify profiles safely."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
GENERATED_PROFILE_ENTRY = "maid verify --profile pre-commit --since HEAD"
FROZEN_V2_24_ENTRY = (
    "maid verify --summary --advisory --allow-empty --require-plan-lock "
    "--require-red-evidence --fail-fast --no-changed-scope "
    "--file-tracking-scope task --plan-lock-scope task --since HEAD"
)
PROFILE_PAYLOAD_FLOOR = "2.25.0"
PRE_CHANGE_PAYLOAD_VERSION = "2026.07.31.1"

PACKAGED_VERIFY_PAYLOADS = {
    "maid_runner/claude/skills/maid-implementation-review/SKILL.md",
    "maid_runner/claude/skills/maid-implementer/SKILL.md",
    "maid_runner/codex/skills/maid-implementation-review/SKILL.md",
    "maid_runner/codex/skills/maid-implementer/SKILL.md",
    "maid_runner/codex/skills/maid-runner-draft-implement/SKILL.md",
    "maid_runner/codex/skills/maid-runner-performance-optimization/SKILL.md",
    "maid_runner/codex/skills/maid-runner-performance-optimization/agents/openai.yaml",
    "maid_runner/codex/skills/maid-runner-self-improvement/SKILL.md",
    "maid_runner/codex/skills/maid-validate-hardening/SKILL.md",
    "maid_runner/user_skills/claude/maid-onboard/SKILL.md",
    "maid_runner/user_skills/codex/maid-onboard/SKILL.md",
    "maid_runner/user_skills/codex/maid-onboard/agents/openai.yaml",
}

ACTIONABLE_SOURCE_COPIES = {
    ".claude/skills/maid-implementation-review/SKILL.md": (
        "maid_runner/claude/skills/maid-implementation-review/SKILL.md"
    ),
    ".codex/skills/maid-implementation-review/SKILL.md": (
        "maid_runner/codex/skills/maid-implementation-review/SKILL.md"
    ),
    ".claude/skills/maid-implementer/SKILL.md": (
        "maid_runner/claude/skills/maid-implementer/SKILL.md"
    ),
    ".codex/skills/maid-implementer/SKILL.md": (
        "maid_runner/codex/skills/maid-implementer/SKILL.md"
    ),
    ".codex/skills/maid-runner-draft-implement/SKILL.md": (
        "maid_runner/codex/skills/maid-runner-draft-implement/SKILL.md"
    ),
    ".claude/skills/maid-onboard/SKILL.md": (
        "maid_runner/user_skills/claude/maid-onboard/SKILL.md"
    ),
    ".codex/skills/maid-onboard/SKILL.md": (
        "maid_runner/user_skills/codex/maid-onboard/SKILL.md"
    ),
}


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _effective_gates(entry: str) -> dict[str, object]:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.core.verify_profiles import apply_verify_profile

    argv = entry.split()
    assert argv[0] == "maid"
    args = build_parser().parse_args(argv[1:])
    apply_verify_profile(args)

    subparsers = next(
        action
        for action in build_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    option_dests = {
        action.dest
        for action in subparsers.choices["verify"]._actions
        if action.option_strings and not action.dest.endswith("_explicit")
    }
    return {
        dest: getattr(args, dest)
        for dest in sorted(option_dests)
        if dest != "profile" and hasattr(args, dest)
    }


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_generated_hook_uses_the_pre_commit_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0

    config = yaml.safe_load((tmp_path / ".pre-commit-config.yaml").read_text())
    entries = [
        hook["entry"]
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == "maid-verify"
    ]
    assert entries == [GENERATED_PROFILE_ENTRY]


def test_generated_hook_profile_is_gate_equivalent_to_frozen_flags() -> None:
    assert _effective_gates(GENERATED_PROFILE_ENTRY) == _effective_gates(
        FROZEN_V2_24_ENTRY
    )


def test_actionable_payload_commands_use_gate_equivalent_profiles() -> None:
    expected = {
        ".claude/skills/maid-implementation-review/SKILL.md": (
            "maid verify --profile handoff --since <baseline>",
            "maid verify --profile deep --since <baseline>",
        ),
        ".codex/skills/maid-implementation-review/SKILL.md": (
            "maid verify --profile handoff --since <baseline>",
            "maid verify --profile deep --since <baseline>",
        ),
        ".claude/skills/maid-implementer/SKILL.md": (
            "maid verify --profile agent-retry --since <baseline>",
            "maid verify --profile handoff --since <baseline>",
        ),
        ".codex/skills/maid-implementer/SKILL.md": (
            "maid verify --profile agent-retry --since <baseline>",
            "maid verify --profile handoff --since <baseline>",
        ),
        ".codex/skills/maid-runner-draft-implement/SKILL.md": (
            "maid verify --profile agent-retry --since <baseline>",
            "uv run maid verify --profile handoff --since <baseline>",
        ),
        ".claude/skills/maid-runner-draft-implement/SKILL.md": (
            "uv run maid verify --profile handoff --since <baseline>",
        ),
        ".claude/skills/maid-onboard/SKILL.md": ("maid verify --profile handoff",),
        ".codex/skills/maid-onboard/SKILL.md": ("maid verify --profile handoff",),
    }

    for relative, commands in expected.items():
        text = _read(relative)
        for command in commands:
            assert command in text, f"{relative} is missing {command}"

    obsolete = {
        ".claude/skills/maid-implementation-review/SKILL.md": (
            "maid verify --summary --require-plan-lock --require-red-evidence",
            "maid verify --artifact-coverage --knockout",
        ),
        ".codex/skills/maid-implementation-review/SKILL.md": (
            "maid verify --summary --require-plan-lock --require-red-evidence",
            "maid verify --artifact-coverage --knockout",
        ),
        ".claude/skills/maid-implementer/SKILL.md": (
            "maid verify --packet --since <baseline>",
            "maid verify --summary --require-plan-lock --require-red-evidence",
        ),
        ".codex/skills/maid-implementer/SKILL.md": (
            "maid verify --packet --since <baseline>",
            "maid verify --summary --require-plan-lock --require-red-evidence",
        ),
        ".codex/skills/maid-runner-draft-implement/SKILL.md": (
            "maid verify --packet --since <baseline>",
            "uv run maid verify --summary --require-plan-lock --require-red-evidence",
        ),
        ".claude/skills/maid-runner-draft-implement/SKILL.md": (
            "uv run maid verify --summary --require-plan-lock --require-red-evidence",
        ),
        ".claude/skills/maid-onboard/SKILL.md": (
            "maid verify --require-plan-lock",
            "maid verify --summary --require-plan-lock --require-red-evidence",
        ),
        ".codex/skills/maid-onboard/SKILL.md": (
            "maid verify --require-plan-lock",
            "maid verify --summary --require-plan-lock --require-red-evidence",
        ),
    }
    for relative, commands in obsolete.items():
        text = _read(relative)
        for command in commands:
            assert command not in text, f"{relative} still carries {command}"


def test_unmatched_payload_commands_stay_literal() -> None:
    for relative in (
        ".claude/skills/maid-implementer/SKILL.md",
        ".codex/skills/maid-implementer/SKILL.md",
        ".codex/skills/maid-runner-draft-implement/SKILL.md",
        ".claude/skills/maid-runner-draft-implement/SKILL.md",
    ):
        assert (
            "maid verify --summary --plan-lock-scope task --since <baseline>"
            in _read(relative)
        )

    assert "time uv run maid verify --keep-going --json" in _read(
        ".codex/skills/maid-runner-performance-optimization/SKILL.md"
    )
    assert "uv run maid verify --summary --keep-going" in _read(
        ".codex/skills/maid-runner-self-improvement/SKILL.md"
    )


def test_verify_payload_inventory_and_generated_copies_are_synchronized() -> None:
    found = {
        path.relative_to(ROOT).as_posix()
        for root in (
            ROOT / "maid_runner" / "claude",
            ROOT / "maid_runner" / "codex",
            ROOT / "maid_runner" / "user_skills",
        )
        for path in root.rglob("*")
        if path.is_file() and "maid verify" in path.read_text(encoding="utf-8")
    }
    assert found == PACKAGED_VERIFY_PAYLOADS

    for source, packaged in ACTIONABLE_SOURCE_COPIES.items():
        assert _read(packaged) == _read(source)


def test_instruction_payload_version_advances_for_profile_guidance() -> None:
    from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION

    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple(
        PRE_CHANGE_PAYLOAD_VERSION
    )


def test_profile_guidance_declares_the_2_25_runner_floor() -> None:
    required = f"maid-runner>={PROFILE_PAYLOAD_FLOOR}"
    assert required in _read("README.md")
    assert required in _read(".claude/skills/maid-onboard/SKILL.md")
    assert required in _read(".codex/skills/maid-onboard/SKILL.md")
