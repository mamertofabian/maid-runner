"""CLI handler for advisory verify-profile assessment."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shlex

from maid_runner.cli.commands._format import print_error
from maid_runner.core.chain import _INACTIVE_MANIFEST_DIR_NAMES
from maid_runner.core.change_assessment import (
    assess_change_signals,
    recommend_verify_profile,
)
from maid_runner.core.config import load_config
from maid_runner.core.diff_scope import (
    DiffScopeBaseline,
    DiffScopeError,
    collect_diff_scope,
)


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
        manifest_dir, manifest_dir_source, emit_manifest_dir = (
            _resolve_assessment_manifest_dir(
                root,
                baseline,
                explicit_manifest_dir=getattr(args, "manifest_dir", None),
            )
        )
        signals = assess_change_signals(
            root,
            baseline,
            manifest_dir=manifest_dir,
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
    if emit_manifest_dir:
        verify_argv.extend(("--manifest-dir", manifest_dir))
    if recommendation.profile == "deep":
        verify_argv.extend(
            (
                "--test-scope",
                "task",
                "--require-plan-lock",
                "--require-red-evidence",
            )
        )
    verify_argv.extend((baseline_flag, baseline_value))
    payload = {
        "tier": recommendation.tier.value,
        "profile": recommendation.profile,
        "rationale": list(recommendation.rationale),
        "human_gate_expected": recommendation.human_gate_expected,
        "manifest_dir": manifest_dir,
        "manifest_dir_source": manifest_dir_source,
        "signals": asdict(signals),
        "verify_argv": verify_argv,
        "verify_command": shlex.join(verify_argv),
    }
    if json_mode:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Recommended verify profile: {recommendation.profile}")
    print(f"Assessment tier: {recommendation.tier.value}")
    print(f"Manifest directory: {manifest_dir} ({manifest_dir_source})")
    for reason in recommendation.rationale:
        print(f"  - {reason}")
    if recommendation.human_gate_expected:
        print("Human gate expected for this critical change.")
    print(f"Run: {payload['verify_command']}")
    return 0


def _resolve_assessment_manifest_dir(
    root: Path,
    baseline: DiffScopeBaseline,
    *,
    explicit_manifest_dir: str | None,
) -> tuple[str, str, bool]:
    configured = load_config(root).manifest_dir
    if explicit_manifest_dir is not None:
        if not explicit_manifest_dir.strip():
            raise ValueError("maid assess --manifest-dir requires a non-empty value")
        return explicit_manifest_dir, "explicit", True

    diff = collect_diff_scope(root, baseline)
    candidates = sorted(
        {
            candidate
            for path in (*diff.created, *diff.edited)
            if (candidate := _active_manifest_parent(root, path)) is not None
        }
    )
    if len(candidates) > 1:
        raise ValueError(
            "Multiple changed manifest directories were found: "
            f"{', '.join(candidates)}. Pass --manifest-dir explicitly."
        )
    if candidates:
        return candidates[0], "changed-manifest", True
    return configured, "configured", False


def _active_manifest_parent(root: Path, path: str) -> str | None:
    candidate = Path(path)
    if not candidate.name.endswith((".manifest.yaml", ".manifest.yml")):
        return None
    if _INACTIVE_MANIFEST_DIR_NAMES.intersection(candidate.parts[:-1]):
        return None
    if not (root / candidate).is_file():
        return None
    parent = candidate.parent.as_posix()
    return parent if parent != "." else "."
