import argparse
from argparse import Namespace
from pathlib import Path

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.howto import cmd_howto
from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


ROOT = Path(__file__).resolve().parents[1]
AUDITOR_SKILLS = (
    ROOT / ".claude/skills/maid-auditor/SKILL.md",
    ROOT / ".codex/skills/maid-auditor/SKILL.md",
    ROOT / "maid_runner/claude/skills/maid-auditor/SKILL.md",
    ROOT / "maid_runner/codex/skills/maid-auditor/SKILL.md",
)
ONBOARD_SKILLS = (
    ROOT / ".claude/skills/maid-onboard/SKILL.md",
    ROOT / ".codex/skills/maid-onboard/SKILL.md",
    ROOT / "maid_runner/user_skills/claude/maid-onboard/SKILL.md",
    ROOT / "maid_runner/user_skills/codex/maid-onboard/SKILL.md",
)


def _subparser(
    parser: argparse.ArgumentParser, command: str
) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[command]
    raise AssertionError(f"subparser not found: {command}")


def _action(parser: argparse.ArgumentParser, option: str) -> argparse.Action:
    for action in parser._actions:
        if option in action.option_strings:
            return action
    raise AssertionError(f"option not found: {option}")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_bootstrap_help_recommends_risk_v1_and_preserves_legacy_default() -> None:
    parser = build_parser()
    bootstrap = _subparser(parser, "bootstrap")
    help_text = bootstrap.format_help()

    assert "inadequately covered files" in _action(bootstrap, "--rank").help
    assert "undeclared" in _action(bootstrap, "--rank").help
    assert "read-only" in _action(bootstrap, "--rank").help
    assert "writable without artifacts" in _action(bootstrap, "--rank").help
    assert "risk-v1" in _action(bootstrap, "--model").help
    assert "recommended" in _action(bootstrap, "--model").help
    assert "legacy-v1" in help_text
    assert "compatibility default" in help_text
    assert parser.parse_args(["bootstrap", "--rank"]).model == "legacy-v1"


def test_howto_distinguishes_risk_v1_from_legacy_ordering(capsys) -> None:
    exit_code = cmd_howto(Namespace(topic="commands"))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "maid bootstrap --rank --model risk-v1 --limit 20" in output
    assert "maid bootstrap --rank --model risk-v1 --json" in output
    assert "inadequately covered files" in output
    assert "undeclared files" in output
    assert "read-only registrations" in output
    assert "writable manifests without declared artifacts" in output
    assert "evidence" in output
    assert "confidence" in output
    assert "--explain" in output
    assert "legacy-v1" in output
    assert "orders by churn descending" in output
    assert "inbound_refs descending" in output
    assert "public_artifacts descending" in output
    assert "path ascending" in output


def test_auditor_uses_risk_v1_for_priority_not_verdict() -> None:
    for path in AUDITOR_SKILLS:
        guidance = _read(path)
        assert "maid files" in guidance, path
        assert "maid bootstrap --rank --model risk-v1" in guidance, path
        assert "incomplete brownfield coverage" in guidance, path
        assert "advisory" in guidance, path
        assert "must not change the audit verdict" in guidance, path


def test_onboard_offers_risk_v1_for_incomplete_brownfield_coverage() -> None:
    for path in ONBOARD_SKILLS:
        guidance = _read(path)
        assert "maid bootstrap --rank --model risk-v1" in guidance, path
        assert "incomplete brownfield coverage" in guidance, path
        assert "optional" in guidance, path
        assert "not a prerequisite" in guidance, path


def test_risk_v1_skill_guidance_sources_match_packaged_copies() -> None:
    assert _read(AUDITOR_SKILLS[0]) == _read(AUDITOR_SKILLS[2])
    assert _read(AUDITOR_SKILLS[1]) == _read(AUDITOR_SKILLS[3])
    assert _read(ONBOARD_SKILLS[0]) == _read(ONBOARD_SKILLS[2])
    assert _read(ONBOARD_SKILLS[1]) == _read(ONBOARD_SKILLS[3])


def test_instruction_payload_version_bumped_for_risk_v1_skill_guidance() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple("2026.07.25.1")
