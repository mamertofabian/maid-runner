"""Behavioral contract for named maid verify --profile presets."""

from __future__ import annotations

import argparse
import json

import pytest


DOCUMENTED_PROFILES: dict[str, dict[str, bool | str]] = {
    "handoff": {
        "summary": True,
        "require_plan_lock": True,
        "require_red_evidence": True,
    },
    "pre-commit": {
        "summary": True,
        "advisory": True,
        "allow_empty": True,
        "require_plan_lock": True,
        "require_red_evidence": True,
        "fail_fast": True,
        "changed_scope": False,
        "file_tracking_scope": "task",
        "plan_lock_scope": "task",
    },
    "agent-retry": {
        "summary": True,
        "packet": ".maid/last-failure-packet.json",
    },
    "deep": {
        "summary": True,
        "artifact_coverage": True,
        "knockout": True,
    },
}


def _parse_verify(argv: list[str]) -> argparse.Namespace:
    from maid_runner.cli.commands._main import build_parser

    return build_parser().parse_args(["verify", *argv])


def _verify_subparser() -> argparse.ArgumentParser:
    from maid_runner.cli.commands._main import build_parser

    subparsers = next(
        action
        for action in build_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return subparsers.choices["verify"]


def test_each_shipped_profile_resolves_to_its_documented_flags() -> None:
    from maid_runner.core.verify_profiles import (
        VerifyProfile,
        resolve_verify_profile,
        verify_profile_names,
    )

    assert set(verify_profile_names()) == set(DOCUMENTED_PROFILES)

    for name, defaults in DOCUMENTED_PROFILES.items():
        profile: VerifyProfile = resolve_verify_profile(name)

        assert isinstance(profile, VerifyProfile)
        assert profile.name == name
        assert dict(profile.defaults) == defaults


def test_unknown_profile_exits_non_zero_and_lists_valid_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.core.verify_profiles import verify_profile_names

    with pytest.raises(SystemExit) as excinfo:
        _parse_verify(["--profile", "definitely-not-a-profile"])

    assert excinfo.value.code != 0
    message = capsys.readouterr().err
    for name in verify_profile_names():
        assert name in message


def test_resolve_verify_profile_rejects_an_unknown_name() -> None:
    from maid_runner.core.verify_profiles import resolve_verify_profile

    with pytest.raises(KeyError):
        resolve_verify_profile("definitely-not-a-profile")


def test_resolved_profile_defaults_are_isolated_between_resolutions() -> None:
    from maid_runner.core.verify_profiles import resolve_verify_profile

    first = resolve_verify_profile("handoff")
    try:
        first.defaults["summary"] = False  # type: ignore[index]
    except TypeError:
        pass

    assert resolve_verify_profile("handoff").defaults["summary"] is True


def test_explicitly_passed_flag_overrides_profile_default() -> None:
    from maid_runner.core.verify_profiles import apply_verify_profile

    control = _parse_verify(["--profile", "pre-commit"])
    control_report = apply_verify_profile(control)

    args = _parse_verify(["--profile", "pre-commit", "--keep-going"])
    report = apply_verify_profile(args)

    assert control.fail_fast is True
    assert control_report is not None
    assert "--fail-fast" in control_report

    assert args.fail_fast is False
    assert args.plan_lock_scope == "task"
    assert report is not None
    assert "--fail-fast" not in report


def test_explicit_flag_matching_parser_default_still_wins() -> None:
    from maid_runner.core.verify_profiles import apply_verify_profile

    args = _parse_verify(["--profile", "pre-commit", "--changed-scope"])

    report = apply_verify_profile(args)

    assert args.changed_scope is True
    assert report is not None
    assert "--no-changed-scope" not in report


def test_explicit_valued_option_matching_parser_default_still_wins() -> None:
    from maid_runner.core.verify_profiles import apply_verify_profile

    args = _parse_verify(
        ["--profile", "pre-commit", "--file-tracking-scope", "repository"]
    )

    report = apply_verify_profile(args)

    assert args.file_tracking_scope == "repository"
    assert args.plan_lock_scope == "task"
    assert report is not None
    assert "--file-tracking-scope task" not in report


def test_no_profile_supplies_a_changed_scope_baseline() -> None:
    from maid_runner.core.verify_profiles import (
        apply_verify_profile,
        resolve_verify_profile,
        verify_profile_names,
    )

    for name in verify_profile_names():
        defaults = resolve_verify_profile(name).defaults
        assert "since" not in defaults
        assert "base_ref" not in defaults
        assert "changed_scope_explicit" not in defaults

    args = _parse_verify(["--profile", "handoff"])
    apply_verify_profile(args)

    assert args.since is None
    assert args.base_ref is None
    assert getattr(args, "changed_scope_explicit", False) is False


def test_pre_commit_profile_matches_generated_hook_gate_set() -> None:
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.core.verify_profiles import resolve_verify_profile

    literal = (
        "verify --summary --advisory --allow-empty --require-plan-lock "
        "--require-red-evidence --fail-fast --no-changed-scope "
        "--file-tracking-scope task --plan-lock-scope task --since HEAD"
    ).split()
    since_index = literal.index("--since")
    without_baseline = literal[:since_index] + literal[since_index + 2 :]

    parser_defaults = vars(build_parser().parse_args(["verify"]))
    hook = build_parser().parse_args(without_baseline)
    defaults = resolve_verify_profile("pre-commit").defaults

    # Compare only dests backed by a real verify option. Explicitness
    # bookkeeping attributes record how a value arrived rather than which gate
    # runs, and carry no option_strings whatever they are named, so this stays
    # correct regardless of how the explicit-flag pattern is implemented.
    option_dests = {
        action.dest for action in _verify_subparser()._actions if action.option_strings
    }
    changed_by_hook = {
        dest
        for dest in option_dests
        if dest in parser_defaults and parser_defaults[dest] != getattr(hook, dest)
    }

    assert changed_by_hook
    assert changed_by_hook <= set(defaults)
    for dest, value in defaults.items():
        assert getattr(hook, dest) == value


def test_profile_with_contradictory_flag_still_fails(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.verify import cmd_verify

    args = _parse_verify(["--profile", "pre-commit", "--strict-preview"])

    exit_code = cmd_verify(args)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "contradictory" in (captured.out + captured.err).lower()


def test_cmd_verify_reports_the_applied_profile_in_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.verify import cmd_verify

    args = _parse_verify(["--profile", "pre-commit", "--strict-preview"])

    cmd_verify(args)

    combined = "".join(capsys.readouterr())
    assert "pre-commit" in combined
    assert "--no-changed-scope" in combined


def test_profile_report_does_not_corrupt_json_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands.verify import cmd_verify

    args = _parse_verify(
        ["--profile", "handoff", "--strict-preview", "--advisory", "--json"]
    )

    cmd_verify(args)

    assert json.loads(capsys.readouterr().out)


def test_json_output_discloses_the_applied_profile_and_its_flags(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from maid_runner.cli.commands.verify import cmd_verify

    monkeypatch.chdir(tmp_path)
    (tmp_path / "manifests").mkdir()

    args = _parse_verify(
        ["--profile", "handoff", "--json", "--allow-empty", "--no-changed-scope"]
    )
    cmd_verify(args)

    rendered = json.dumps(json.loads(capsys.readouterr().out))

    assert "handoff" in rendered
    assert "--require-plan-lock" in rendered


def test_apply_verify_profile_reports_the_profile_and_its_flags() -> None:
    from maid_runner.core.verify_profiles import apply_verify_profile

    args = _parse_verify(["--profile", "handoff"])

    report = apply_verify_profile(args)

    assert report is not None
    assert "handoff" in report
    for flag in ("--summary", "--require-plan-lock", "--require-red-evidence"):
        assert flag in report


def test_report_renders_negated_and_valued_flags() -> None:
    from maid_runner.core.verify_profiles import apply_verify_profile

    args = _parse_verify(["--profile", "pre-commit"])

    report = apply_verify_profile(args)

    assert report is not None
    assert "--no-changed-scope" in report
    assert "--file-tracking-scope task" in report
    assert "--plan-lock-scope task" in report


def test_no_profile_produces_no_report() -> None:
    from maid_runner.core.verify_profiles import apply_verify_profile

    args = _parse_verify(["--summary"])

    assert apply_verify_profile(args) is None


def test_profile_resolution_does_not_depend_on_repository_or_cwd(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    monkeypatch.chdir(tmp_path)
    # Reload after the chdir so module-level work is in scope. importlib.reload
    # mutates the module in place, so there is no sys.modules entry to restore;
    # every other test in this file imports the symbols inside the test body
    # and therefore re-reads them after this point.
    module = importlib.reload(
        importlib.import_module("maid_runner.core.verify_profiles")
    )

    resolved = {
        name: module.resolve_verify_profile(name)
        for name in module.verify_profile_names()
    }

    assert set(resolved) == set(DOCUMENTED_PROFILES)
    for name, profile in resolved.items():
        assert dict(profile.defaults) == DOCUMENTED_PROFILES[name]
