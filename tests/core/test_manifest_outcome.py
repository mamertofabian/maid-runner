"""Tests for optional manifest Outcome records."""

from __future__ import annotations

from copy import deepcopy

from maid_runner.core.manifest import (
    ManifestSchemaError,
    load_manifest,
    save_manifest,
    validate_manifest_schema,
)
from maid_runner.core.types import (
    OutcomeLesson,
    OutcomeRecord,
    OutcomeReviewNote,
    OutcomeStatus,
    OutcomeValidationEvidence,
)


OUTCOME_STATUSES = (
    OutcomeStatus.COMPLETED,
    OutcomeStatus.FAILED,
    OutcomeStatus.PARTIAL,
    OutcomeStatus.SUPERSEDED,
    OutcomeStatus.ARCHIVED,
    OutcomeStatus.ABANDONED,
)


def _base_manifest() -> dict:
    return {
        "schema": "2",
        "goal": "Record an outcome",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/outcome.py",
                    "artifacts": [{"kind": "function", "name": "record_outcome"}],
                }
            ]
        },
        "validate": ["pytest tests/test_outcome.py -q"],
    }


def _manifest_with_outcome() -> dict:
    data = _base_manifest()
    data["outcome"] = {
        "status": "completed",
        "summary": "Outcome records now round-trip through manifests.",
        "rationale": "Implementation review found the manifest ready.",
        "lessons": [
            {
                "lesson_type": "schema",
                "summary": "Strict optional records preserve historical manifests.",
                "tags": ["manifest-schema", "outcome"],
                "paths": ["maid_runner/schemas/manifest.v2.schema.json"],
            }
        ],
        "review_notes": [
            {
                "source": "implementation-review",
                "severity": "info",
                "summary": "No scope drift found.",
            }
        ],
        "validation": [
            {
                "command": ["uv", "run", "python", "-m", "pytest"],
                "status": "passed",
                "summary": "Focused outcome tests passed.",
            }
        ],
        "completed_at": "2026-05-30T14:00:00Z",
    }
    return data


def test_manifest_schema_accepts_strict_outcome_record():
    data = _manifest_with_outcome()

    assert validate_manifest_schema(data) == []

    without_outcome = _base_manifest()
    assert validate_manifest_schema(without_outcome) == []


def test_manifest_schema_rejects_outcome_unknown_fields_and_statuses():
    cases = []

    unknown_outcome_field = _manifest_with_outcome()
    unknown_outcome_field["outcome"]["contract_override"] = True
    cases.append(unknown_outcome_field)

    unknown_lesson_field = _manifest_with_outcome()
    unknown_lesson_field["outcome"]["lessons"][0]["private_note"] = "loose"
    cases.append(unknown_lesson_field)

    unsupported_status = _manifest_with_outcome()
    unsupported_status["outcome"]["status"] = "done"
    cases.append(unsupported_status)

    for completed_at in (
        "not-a-date",
        "2026-99-99T99:99:99Z",
        "2026-13-01T00:00:00Z",
        "2026-05-30T24:00:00Z",
        "2026-05-30T14:00:00+99:99",
        "2026-05-30T14:00:00",
        "2026-05-30T14:00:00+00:00:00",
    ):
        malformed_completed_at = _manifest_with_outcome()
        malformed_completed_at["outcome"]["completed_at"] = completed_at
        cases.append(malformed_completed_at)

    for data in cases:
        errors = validate_manifest_schema(data)
        assert errors, "malformed Outcome should not pass schema validation"

    assert validate_manifest_schema([]), "non-object manifests should report errors"


def test_load_manifest_reports_non_object_manifest_as_schema_error(tmp_path):
    path = tmp_path / "list.manifest.yaml"
    path.write_text("[]\n")

    try:
        load_manifest(path)
    except ManifestSchemaError as exc:
        assert "is not of type 'object'" in str(exc)
    else:
        raise AssertionError("non-object manifests should raise ManifestSchemaError")


def test_manifest_schema_pins_exact_outcome_status_values():
    for status in OUTCOME_STATUSES:
        data = _manifest_with_outcome()
        data["outcome"]["status"] = status.value
        assert validate_manifest_schema(data) == []

    for alias in ("done", "skipped", "draft", "cancelled"):
        data = _manifest_with_outcome()
        data["outcome"]["status"] = alias
        errors = validate_manifest_schema(data)
        assert errors, f"unsupported Outcome status {alias!r} should be rejected"


def test_load_manifest_parses_outcome_record(tmp_path):
    path = tmp_path / "with-outcome.manifest.yaml"
    source = _manifest_with_outcome()
    save_manifest(load_manifest_from_dict(source, tmp_path), path)

    manifest = load_manifest(path)

    assert isinstance(manifest.outcome, OutcomeRecord)
    assert manifest.outcome.status is OutcomeStatus.COMPLETED
    assert manifest.outcome.summary == source["outcome"]["summary"]
    assert manifest.outcome.rationale == source["outcome"]["rationale"]
    assert manifest.outcome.completed_at == source["outcome"]["completed_at"]

    assert manifest.outcome.lessons == (
        OutcomeLesson(
            lesson_type="schema",
            summary="Strict optional records preserve historical manifests.",
            tags=("manifest-schema", "outcome"),
            paths=("maid_runner/schemas/manifest.v2.schema.json",),
        ),
    )
    assert manifest.outcome.review_notes == (
        OutcomeReviewNote(
            source="implementation-review",
            severity="info",
            summary="No scope drift found.",
        ),
    )
    assert manifest.outcome.validation == (
        OutcomeValidationEvidence(
            command=("uv", "run", "python", "-m", "pytest"),
            status="passed",
            summary="Focused outcome tests passed.",
        ),
    )


def test_save_manifest_preserves_outcome_round_trip(tmp_path):
    source_path = tmp_path / "source.manifest.yaml"
    saved_path = tmp_path / "saved.manifest.yaml"
    original = load_manifest_from_dict(_manifest_with_outcome(), tmp_path)

    save_manifest(original, source_path)
    loaded = load_manifest(source_path)
    save_manifest(loaded, saved_path)
    reloaded = load_manifest(saved_path)

    assert reloaded.outcome == original.outcome
    assert reloaded.outcome.status is OutcomeStatus.COMPLETED
    assert reloaded.outcome.lessons[0].lesson_type == "schema"
    assert reloaded.outcome.lessons[0].summary.startswith("Strict optional")
    assert reloaded.outcome.lessons[0].tags == ("manifest-schema", "outcome")
    assert reloaded.outcome.lessons[0].paths == (
        "maid_runner/schemas/manifest.v2.schema.json",
    )
    assert reloaded.outcome.review_notes[0].severity == "info"
    assert reloaded.outcome.validation[0].status == "passed"
    assert reloaded.outcome.validation[0].command == (
        "uv",
        "run",
        "python",
        "-m",
        "pytest",
    )
    assert reloaded.outcome.completed_at == "2026-05-30T14:00:00Z"


def load_manifest_from_dict(data: dict, tmp_path):
    import yaml

    path = tmp_path / "input.manifest.yaml"
    path.write_text(yaml.dump(deepcopy(data), sort_keys=False))
    return load_manifest(path)
