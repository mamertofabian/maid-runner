"""Behavioral tests for manifest-derived recall planning packets."""

from __future__ import annotations

from pathlib import Path

import yaml

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord
from maid_runner.core.types import OutcomeLesson, OutcomeValidationEvidence


def test_build_plan_packet_uses_fixed_sections_caps_and_stable_order(tmp_path: Path):
    from maid_runner.core.outcome_recall import (
        PlanPacket,
        PlanPacketSection,
        build_plan_packet,
        derive_recall_query,
        render_plan_packet,
    )

    query_manifest = tmp_path / "query.manifest.yaml"
    _write_query_manifest(query_manifest)
    derivation = derive_recall_query(query_manifest, project_root=tmp_path)
    records = tuple(
        _record(
            slug,
            status=status,
            lessons=(
                OutcomeLesson(
                    lesson_type="testing",
                    summary=f"{slug} lesson touches the shared path.",
                    paths=("src/shared.py",),
                ),
            ),
            validation_evidence=(
                OutcomeValidationEvidence(
                    command=("uv", "run", "pytest", f"tests/{slug}.py"),
                    status="failed",
                    summary=f"{slug} validation failed.",
                ),
            ),
        )
        for slug, status in (
            ("alpha", "completed"),
            ("bravo", "failed"),
            ("charlie", "completed"),
            ("delta", "completed"),
            ("echo", "failed"),
            ("foxtrot", "completed"),
        )
    )

    packet = build_plan_packet(_index(*reversed(records)), derivation)

    assert isinstance(packet, PlanPacket)
    assert packet.manifest_path == "query.manifest.yaml"
    assert tuple(section.title for section in packet.sections) == (
        "Related manifests",
        "Outcome statuses",
        "Recurring lessons touching the same paths",
        "Prior validation-command failures",
    )
    assert isinstance(packet.sections[0], PlanPacketSection)
    assert packet.sections[0].entries == (
        "alpha (manifests/alpha.manifest.yaml)",
        "bravo (manifests/bravo.manifest.yaml)",
        "charlie (manifests/charlie.manifest.yaml)",
        "delta (manifests/delta.manifest.yaml)",
        "echo (manifests/echo.manifest.yaml)",
    )
    assert packet.sections[0].omitted_count == 1
    assert packet.sections[1].entries == (
        "alpha: completed",
        "bravo: failed",
        "charlie: completed",
        "delta: completed",
        "echo: failed",
    )
    assert packet.sections[2].entries[0] == (
        "alpha: alpha lesson touches the shared path. (paths: src/shared.py)"
    )
    assert packet.sections[3].entries[0] == (
        "alpha: failed: uv run pytest tests/alpha.py - alpha validation failed."
    )

    rendered_once = render_plan_packet(packet)
    rendered_twice = render_plan_packet(packet)

    assert rendered_once == rendered_twice
    assert rendered_once.splitlines()[:3] == [
        "Planning recall packet for query.manifest.yaml",
        "",
        "Related manifests:",
    ]
    assert "... 1 more omitted" in rendered_once


def test_build_plan_packet_renders_empty_sections_explicitly():
    from maid_runner.core.outcome_recall import (
        PlanPacket,
        PlanPacketSection,
        render_plan_packet,
    )

    packet = PlanPacket(
        manifest_path="manifests/empty.manifest.yaml",
        sections=(
            PlanPacketSection("Related manifests", (), 0),
            PlanPacketSection("Outcome statuses", (), 0),
            PlanPacketSection("Recurring lessons touching the same paths", (), 0),
            PlanPacketSection("Prior validation-command failures", (), 0),
        ),
    )

    rendered = render_plan_packet(packet)

    assert rendered.count("- none") == 4
    assert "Related manifests:\n- none" in rendered
    assert "Prior validation-command failures:\n- none" in rendered


def _write_query_manifest(path: Path) -> None:
    data = {
        "schema": "2",
        "goal": "query related outcomes",
        "type": "feature",
        "created": "2026-06-10T06:02:00Z",
        "metadata": {"tags": ["planning"]},
        "files": {"edit": [{"path": "src/shared.py"}]},
        "validate": ["uv run python -m pytest -q tests/core/test_plan_packet.py"],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _index(*records: OutcomeIndexRecord) -> OutcomeIndex:
    return OutcomeIndex(
        schema_version="1",
        generated_from="test",
        included_statuses=("completed", "failed"),
        manifest_dir="manifests",
        project_root=".",
        records=tuple(records),
    )


def _record(
    slug: str,
    *,
    status: str,
    lessons: tuple[OutcomeLesson, ...] = (),
    validation_evidence: tuple[OutcomeValidationEvidence, ...] = (),
) -> OutcomeIndexRecord:
    return OutcomeIndexRecord(
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        status=status,
        lifecycle_status="active",
        superseded_by=None,
        task_type="feature",
        created="2026-05-30",
        completed_at="2026-05-31T01:02:03Z",
        tags=("planning",),
        declared_paths=("src/shared.py",),
        artifacts=(),
        validation_commands=(("uv", "run", "pytest"),),
        validation_evidence=validation_evidence,
        lessons=lessons,
        review_notes=(),
        source_fingerprint="0" * 64,
    )
