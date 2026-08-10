"""CLI handler for advisory verify-profile assessment."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shlex

from maid_runner.cli.commands._format import print_error
from maid_runner.core.change_assessment import (
    assess_change_signals,
    recommend_verify_profile,
)
from maid_runner.core.config import load_config
from maid_runner.core.diff_scope import DiffScopeBaseline, DiffScopeError


def cmd_assess(args: argparse.Namespace) -> int:
    """Print an advisory verify profile and exact command for a change."""
    json_mode = getattr(args, "json", False)
    since = getattr(args, "since", None)
    base_ref = getattr(args, "base_ref", None)
    since_present = since is not None
    base_ref_present = base_ref is not None
    if not since_present and not base_ref_present:
        print_error(
            "E115: maid assess requires an explicit --since or --base-ref baseline",
            json_mode=json_mode,
        )
        return 2
    if since_present and base_ref_present:
        print_error(
            "E116: maid assess accepts either --since or --base-ref, not both",
            json_mode=json_mode,
        )
        return 2

    baseline_flag = "--since" if since_present else "--base-ref"
    baseline_value = since if since_present else base_ref
    assert baseline_value is not None
    if not baseline_value.strip():
        print_error(
            f"E116: maid assess {baseline_flag} requires a non-empty value",
            json_mode=json_mode,
        )
        return 2
    baseline = DiffScopeBaseline(
        source="since" if since_present else "base-ref",
        commitish=baseline_value,
    )
    root = Path(".")
    try:
        signals = assess_change_signals(
            root,
            baseline,
            manifest_dir=load_config(root).manifest_dir,
        )
        recommendation = recommend_verify_profile(signals)
    except DiffScopeError as exc:
        print_error(f"E116: {exc}", json_mode=json_mode)
        return 2
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        print_error(str(exc), json_mode=json_mode)
        return 2

    verify_argv = [
        "maid",
        "verify",
        "--profile",
        recommendation.profile,
    ]
    if recommendation.profile == "deep":
        verify_argv.extend(("--require-plan-lock", "--require-red-evidence"))
    verify_argv.extend((baseline_flag, baseline_value))
    payload = {
        "tier": recommendation.tier.value,
        "profile": recommendation.profile,
        "rationale": list(recommendation.rationale),
        "human_gate_expected": recommendation.human_gate_expected,
        "signals": asdict(signals),
        "verify_argv": verify_argv,
        "verify_command": shlex.join(verify_argv),
    }
    if json_mode:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Recommended verify profile: {recommendation.profile}")
    print(f"Assessment tier: {recommendation.tier.value}")
    for reason in recommendation.rationale:
        print(f"  - {reason}")
    if recommendation.human_gate_expected:
        print("Human gate expected for this critical change.")
    print(f"Run: {payload['verify_command']}")
    return 0
