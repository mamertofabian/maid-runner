"""Behavioral tests for local feedback bundle aggregation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from maid_runner.core.feedback import (
    FeedbackBundle,
    FeedbackRecord,
    write_feedback_bundle,
)


def test_feedback_aggregate_parser_requires_local_inputs_and_output() -> None:
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()
    args = parser.parse_args(
        [
            "feedback",
            "aggregate",
            "first.json",
            "second.json",
            "--output",
            "report.json",
            "--force",
            "--json",
        ]
    )

    assert args.command == "feedback"
    assert args.feedback_command == "aggregate"
    assert args.inputs == ["first.json", "second.json"]
    assert args.output == "report.json"
    assert args.force is True
    assert args.json is True
    feedback_parser = parser._subparsers._group_actions[0].choices["feedback"]
    assert "submit" not in feedback_parser._subparsers._group_actions[0].choices


def test_feedback_aggregate_writes_advisory_local_report_without_submission(
    tmp_path: Path,
    capsys,
) -> None:
    cmd_feedback_aggregate = _aggregate_command()
    first = tmp_path / "first.json"
    duplicate = tmp_path / "duplicate.json"
    second = tmp_path / "second.json"
    output = tmp_path / "report.json"
    write_feedback_bundle(_bundle("2.25.0", 2, "passed", "P1"), first)
    write_feedback_bundle(_bundle("2.25.0", 2, "passed", "P1"), duplicate)
    write_feedback_bundle(_bundle("2.26.0", 3, "failed", "ready"), second)

    result = cmd_feedback_aggregate(
        _args((first, duplicate, second), output, json_mode=True)
    )

    assert result == 0
    message = json.loads(capsys.readouterr().out)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert message["bundles_received"] == 3
    assert message["unique_bundles"] == 2
    assert message["review_required"] is True
    assert "advisory" in message["notice"].lower()
    assert "submit" in message["notice"].lower()
    assert report["records"][0]["bundle_count"] == 2
    assert report["records"][0]["reported_source_count"] == 5


def test_feedback_aggregate_fails_atomically_when_any_input_is_invalid(
    tmp_path: Path,
    capsys,
) -> None:
    cmd_feedback_aggregate = _aggregate_command()
    valid = tmp_path / "valid.json"
    invalid = tmp_path / "invalid.json"
    output = tmp_path / "report.json"
    write_feedback_bundle(_bundle("2.25.0", 1, "passed", "ready"), valid)
    invalid.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "exported_with_version": "2.25.0",
                "records": [],
                "project_root": "/private/customer",
            }
        ),
        encoding="utf-8",
    )

    assert cmd_feedback_aggregate(_args((valid, invalid), output)) == 2
    assert "invalid.json" in capsys.readouterr().err
    assert not output.exists()


def test_feedback_aggregate_preserves_existing_output_unless_force_is_explicit(
    tmp_path: Path,
    capsys,
) -> None:
    cmd_feedback_aggregate = _aggregate_command()
    source = tmp_path / "bundle.json"
    output = tmp_path / "report.json"
    write_feedback_bundle(_bundle("2.25.0", 1, "passed", "ready"), source)
    output.write_text("keep me\n", encoding="utf-8")

    assert cmd_feedback_aggregate(_args((source,), output)) == 2
    assert "--force" in capsys.readouterr().err
    assert output.read_text(encoding="utf-8") == "keep me\n"

    assert cmd_feedback_aggregate(_args((source,), output, force=True)) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["records"]


def test_feedback_aggregate_guidance_documents_advisory_count_semantics() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    canonical = (repo_root / "docs/manifest-outcome-records.md").read_text(
        encoding="utf-8"
    )
    packaged = (repo_root / "maid_runner/docs/manifest-outcome-records.md").read_text(
        encoding="utf-8"
    )
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert canonical == packaged
    assert "maid feedback aggregate" in canonical
    assert "reported source" in canonical.lower()
    assert "not unique repositories" in canonical.lower()
    assert "advisory" in canonical.lower()
    assert "does not submit" in canonical.lower()
    assert "maid feedback aggregate" in readme


def _aggregate_command():
    try:
        from maid_runner.cli.commands.feedback import cmd_feedback_aggregate
    except ImportError:
        raise AssertionError("cmd_feedback_aggregate is not implemented") from None
    return cmd_feedback_aggregate


def _args(
    inputs: tuple[Path, ...],
    output: Path,
    *,
    force: bool = False,
    json_mode: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="feedback",
        feedback_command="aggregate",
        inputs=[str(path) for path in inputs],
        output=str(output),
        force=force,
        json=json_mode,
    )


def _bundle(
    version: str,
    source_count: int,
    validation_status: str,
    review_severity: str,
) -> FeedbackBundle:
    lesson_type = "runner-gap"
    summary = "Portable runner lesson."
    canonical = json.dumps(
        {"lesson_type": lesson_type, "summary": summary},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return FeedbackBundle(
        schema_version="1",
        exported_with_version=version,
        records=(
            FeedbackRecord(
                feedback_id=hashlib.sha256(canonical).hexdigest(),
                lesson_type=lesson_type,
                summary=summary,
                source_count=source_count,
                outcome_statuses=("completed",),
                validation_statuses=(validation_status,),
                review_severities=(review_severity,),
            ),
        ),
    )
