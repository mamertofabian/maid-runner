"""Behavioral contract for adopting verify profiles in this repository.

FROZEN_PRE_MIGRATION_ENTRY is this repository's commit-gate flag stack as it
stood before the migration, held here as data rather than imported. Importing
the live constant would compare the migrated entry against itself once it uses
the profile. Freezing the historical stack keeps the guard meaningful: what it
protects against is the profile drifting away from the gates this repository's
commit gate has always applied.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]

FROZEN_PRE_MIGRATION_ENTRY = (
    "uv run maid verify --summary --require-plan-lock "
    "--require-red-evidence --fail-fast --no-changed-scope"
)
MIGRATED_ENTRY = "uv run maid verify --profile handoff --fail-fast --no-changed-scope"

FROZEN_GENERATED_HOOK_ENTRY = (
    "maid verify --summary --advisory --allow-empty --require-plan-lock "
    "--require-red-evidence --fail-fast --no-changed-scope "
    "--file-tracking-scope task --plan-lock-scope task --since HEAD"
)

UNMATCHED_PAYLOAD_PATHS = {
    "maid_runner/codex/skills/maid-runner-performance-optimization/SKILL.md",
    "maid_runner/codex/skills/maid-runner-performance-optimization/agents/openai.yaml",
    "maid_runner/codex/skills/maid-runner-self-improvement/SKILL.md",
    "maid_runner/codex/skills/maid-validate-hardening/SKILL.md",
    "maid_runner/user_skills/codex/maid-onboard/agents/openai.yaml",
}


def _maid_verify_entry() -> str:
    config = yaml.safe_load(
        (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    entries = [
        hook["entry"]
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == "maid-verify"
    ]
    assert len(entries) == 1
    return entries[0]


def _effective_gates(entry: str) -> dict[str, object]:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.core.verify_profiles import apply_verify_profile

    argv = entry.split()
    assert argv[:3] == ["uv", "run", "maid"]
    args = build_parser().parse_args(argv[3:])
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


def test_repo_commit_gate_uses_the_handoff_profile() -> None:
    assert _maid_verify_entry() == MIGRATED_ENTRY


def test_repo_commit_gate_applies_the_frozen_pre_migration_gates() -> None:
    assert _effective_gates(_maid_verify_entry()) == _effective_gates(
        FROZEN_PRE_MIGRATION_ENTRY
    )


def test_repo_guidance_presents_both_the_profile_and_its_expansion(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.howto import cmd_howto

    # Pinned to the step 8 instruction itself, not to the file. AGENTS.md also
    # carries the explicit flags in a "treat older examples as superseded"
    # clause, so a file-wide assertion stays green even if the augmentation is
    # stripped from the instruction it is supposed to guard.
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    handoff_step = next(
        line for line in agents.splitlines() if line.startswith("8. Before handoff")
    )
    assert "--profile handoff" in handoff_step
    assert "--require-plan-lock --require-red-evidence" in handoff_step

    for topic in ("workflow", "commands"):
        assert cmd_howto(argparse.Namespace(topic=topic)) == 0
        rendered = capsys.readouterr().out
        assert "--profile handoff" in rendered
        assert "--require-plan-lock" in rendered
        assert "--require-red-evidence" in rendered


def test_readme_documents_the_profile_option() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "--profile handoff" in readme
    verify_row = next(
        line for line in readme.splitlines() if line.startswith("| `maid verify`")
    )
    assert "--profile" in verify_row


def test_downstream_facing_call_sites_stay_on_literal_flags() -> None:
    for relative in sorted(UNMATCHED_PAYLOAD_PATHS):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "maid verify" in text
        assert "maid verify --profile" not in text


def test_readme_generated_hook_block_stays_on_literal_flags() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    # The v2.24 expansion remains visible next to the v2.25 profile form so the
    # compatibility floor and the gates hidden behind the preset are auditable.
    assert FROZEN_GENERATED_HOOK_ENTRY in readme
    assert "maid verify --profile pre-commit --since HEAD" in readme
    assert "maid-runner>=2.25.0" in readme
