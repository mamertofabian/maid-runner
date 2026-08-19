"""CLI handler for 'maid chain' command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from maid_runner.core.chain_merge import artifact_requires_knockout_detection

from maid_runner.cli.commands._format import (
    format_chain_log,
    format_chain_merge_apply_result,
    format_chain_merge_equivalence_result,
    format_chain_merge_report,
    format_chain_merge_summary,
    format_replay_result,
    print_error,
)


def cmd_chain(args: argparse.Namespace) -> int:
    from maid_runner.core.chain import ManifestChain

    manifest_dir = args.manifest_dir
    try:
        chain = ManifestChain(manifest_dir)
    except FileNotFoundError:
        print_error(
            f"Manifest directory not found: {manifest_dir}",
            json_mode=args.json,
        )
        return 2

    if args.chain_command == "log":
        return _cmd_chain_log(chain, args)

    if args.chain_command == "replay":
        return _cmd_chain_replay(chain, args)

    if args.chain_command == "merge":
        return _cmd_chain_merge(chain, args)

    print_error(
        f"Unknown chain subcommand: {args.chain_command}",
        json_mode=getattr(args, "json", False),
    )
    return 2


def _cmd_chain_log(chain, args: argparse.Namespace) -> int:
    until_seq = getattr(args, "until_seq", None)
    version_tag = getattr(args, "version_tag", None)

    try:
        log = chain.event_log_until(sequence_number=until_seq, version_tag=version_tag)
    except ValueError as e:
        print_error(str(e), json_mode=args.json)
        return 2

    output = format_chain_log(
        log,
        str(args.manifest_dir),
        json_mode=args.json,
        active_only=args.active,
    )
    print(output)
    return 0


def _cmd_chain_replay(chain, args: argparse.Namespace) -> int:
    until_seq = getattr(args, "until_seq", None)
    version_tag = getattr(args, "version_tag", None)

    try:
        result = chain.replay_until(sequence_number=until_seq, version_tag=version_tag)
    except ValueError as e:
        print_error(str(e), json_mode=args.json)
        return 2

    output = format_replay_result(result, json_mode=args.json)
    print(output)
    return 0


def _cmd_chain_merge(chain, args: argparse.Namespace) -> int:
    from maid_runner.core.chain_merge import build_chain_merge_report

    baseline_path = getattr(args, "verify_equivalence", None)
    if baseline_path and (getattr(args, "all", False) or getattr(args, "apply", False)):
        print_error(
            "--verify-equivalence cannot be combined with --all or --apply",
            json_mode=args.json,
        )
        return 2

    # Read-only. The single-file report reads recorded detecting-nodeids through a
    # per-file-scoped source (UNKNOWN when the knockout cache is cold).
    if getattr(args, "all", False):
        from maid_runner.core.chain_merge_sweep import build_repo_merge_summary

        summary = build_repo_merge_summary(chain)
        print(format_chain_merge_summary(summary, json_mode=args.json))
        return 0

    if not args.file_path:
        print_error(
            "chain merge requires a file path, or use --all",
            json_mode=args.json,
        )
        return 2

    if getattr(args, "apply", False) and not getattr(args, "dry_run", False):
        from maid_runner.core.chain_merge_apply import apply_chain_merge

        result = apply_chain_merge(args.file_path, chain, output_dir=args.manifest_dir)
        print(format_chain_merge_apply_result(result, json_mode=args.json))
        return 0 if result.applied else 1

    from maid_runner.core.chain_merge_evidence import (
        coverage_source_for_file,
        detection_source_for_file,
    )

    detection_source = detection_source_for_file(chain, args.file_path)
    coverage_source = coverage_source_for_file(
        chain,
        args.file_path,
        manifest_dir=str(args.manifest_dir),
    )
    report = build_chain_merge_report(
        args.file_path,
        chain,
        detection_source,
        coverage_source,
    )
    if baseline_path:
        from maid_runner.core.chain_merge_equivalence import check_merge_equivalence

        try:
            acceptance_bar, baseline_blocked = _load_equivalence_baseline(
                baseline_path,
                expected_file_path=args.file_path,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            print_error(
                f"Invalid equivalence baseline {baseline_path}: {exc}",
                json_mode=args.json,
            )
            return 2
        result = check_merge_equivalence(
            args.file_path,
            acceptance_bar,
            report.acceptance,
            baseline_blocked=baseline_blocked,
        )
        print(format_chain_merge_equivalence_result(result, json_mode=args.json))
        return 0 if result.success else 1

    output = format_chain_merge_report(report, json_mode=args.json)
    print(output)
    return 0


def _load_equivalence_baseline(
    baseline_path: str,
    *,
    expected_file_path: str,
):
    from maid_runner.core.chain_merge import ChainMergeAcceptanceSpec

    payload = json.loads(
        Path(baseline_path).read_text(encoding="utf-8"),
        object_pairs_hook=_object_without_duplicate_keys,
    )
    if not isinstance(payload, dict):
        raise ValueError("top-level value must be an object")
    expected_report_keys = {
        "file_path",
        "verdict",
        "active_manifest_count",
        "superseded_manifest_count",
        "distinct_artifact_count",
        "total_declaration_count",
        "redundant_declaration_count",
        "blocking_reasons",
        "acceptance",
    }
    if set(payload) != expected_report_keys:
        raise ValueError("fields do not match a complete chain merge report")
    file_path = payload.get("file_path")
    if not isinstance(file_path, str):
        raise ValueError("file_path must be a string")
    if file_path != expected_file_path:
        raise ValueError(
            f"report is for {file_path}, not requested file {expected_file_path}"
        )
    verdict = payload["verdict"]
    if verdict not in {"lean", "defrag", "blocked"}:
        raise ValueError("verdict must be lean, defrag, or blocked")
    blocking_reasons = _string_tuple(payload["blocking_reasons"], "blocking_reasons")
    if (verdict == "blocked") != bool(blocking_reasons):
        raise ValueError("blocking_reasons must agree with the blocked verdict")
    active_count = _nonnegative_integer(
        payload["active_manifest_count"], "active_manifest_count"
    )
    _nonnegative_integer(
        payload["superseded_manifest_count"], "superseded_manifest_count"
    )
    distinct_count = _nonnegative_integer(
        payload["distinct_artifact_count"], "distinct_artifact_count"
    )
    total_count = _nonnegative_integer(
        payload["total_declaration_count"], "total_declaration_count"
    )
    redundant_count = _nonnegative_integer(
        payload["redundant_declaration_count"], "redundant_declaration_count"
    )
    if total_count < distinct_count or redundant_count != total_count - distinct_count:
        raise ValueError("artifact declaration counts are inconsistent")
    if distinct_count and not active_count:
        raise ValueError("a report with artifacts must have an active manifest")
    acceptance = payload.get("acceptance")
    if not isinstance(acceptance, dict):
        raise ValueError("acceptance must be an object")

    expected_keys = {
        "required_artifacts",
        "detection_available",
        "required_detecting_nodeids",
        "unknown_detection_artifacts",
        "coverage_available",
        "required_covered_artifacts",
        "uncovered_coverage_artifacts",
        "unknown_coverage_artifacts",
    }
    if set(acceptance) != expected_keys:
        raise ValueError("acceptance fields do not match the report schema")

    required_artifacts = _string_tuple(
        acceptance["required_artifacts"], "required_artifacts"
    )
    required_set = set(required_artifacts)
    if distinct_count != len(required_set):
        raise ValueError("distinct_artifact_count does not match required_artifacts")
    detection_available = _boolean(
        acceptance["detection_available"], "detection_available"
    )
    coverage_available = _boolean(
        acceptance["coverage_available"], "coverage_available"
    )
    raw_nodeids = acceptance["required_detecting_nodeids"]
    if not isinstance(raw_nodeids, dict) or not all(
        isinstance(key, str) for key in raw_nodeids
    ):
        raise ValueError("required_detecting_nodeids must be an object of arrays")
    detecting_nodeids = {
        key: _string_tuple(value, f"required_detecting_nodeids.{key}")
        for key, value in raw_nodeids.items()
    }
    detection_unknown = _string_tuple(
        acceptance["unknown_detection_artifacts"],
        "unknown_detection_artifacts",
    )
    detection_keys = set(detecting_nodeids)
    detection_unknown_set = set(detection_unknown)
    detection_required_set = {
        artifact
        for artifact in required_set
        if artifact_requires_knockout_detection(artifact)
    }
    if detection_keys & detection_unknown_set:
        raise ValueError("detection evidence categories must not overlap")
    if detection_keys | detection_unknown_set != detection_required_set:
        raise ValueError(
            "detection evidence must partition knockout-capable required_artifacts"
        )
    if not detection_available and (
        detection_keys or detection_unknown_set != detection_required_set
    ):
        raise ValueError(
            "unavailable detection must mark every knockout-capable artifact unknown"
        )

    covered = _string_tuple(
        acceptance["required_covered_artifacts"],
        "required_covered_artifacts",
    )
    uncovered = _string_tuple(
        acceptance["uncovered_coverage_artifacts"],
        "uncovered_coverage_artifacts",
    )
    coverage_unknown = _string_tuple(
        acceptance["unknown_coverage_artifacts"],
        "unknown_coverage_artifacts",
    )
    coverage_sets = (set(covered), set(uncovered), set(coverage_unknown))
    if any(
        left & right
        for index, left in enumerate(coverage_sets)
        for right in coverage_sets[index + 1 :]
    ):
        raise ValueError("coverage evidence categories must not overlap")
    if set().union(*coverage_sets) != required_set:
        raise ValueError("coverage evidence must partition required_artifacts")
    if not coverage_available and (
        covered or uncovered or set(coverage_unknown) != required_set
    ):
        raise ValueError("unavailable coverage must mark every artifact unknown")

    return (
        ChainMergeAcceptanceSpec(
            required_artifacts=required_artifacts,
            detection_available=detection_available,
            required_detecting_nodeids=detecting_nodeids,
            unknown_detection_artifacts=detection_unknown,
            coverage_available=coverage_available,
            required_covered_artifacts=covered,
            uncovered_coverage_artifacts=uncovered,
            unknown_coverage_artifacts=coverage_unknown,
        ),
        verdict == "blocked",
    )


def _string_tuple(value, field_name: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not all(isinstance(item, str) and item.strip() for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{field_name} must be an array of strings")
    return tuple(value)


def _boolean(value, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _nonnegative_integer(value, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _object_without_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
