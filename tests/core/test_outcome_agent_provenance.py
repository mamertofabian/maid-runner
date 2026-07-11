"""Behavioral tests for Outcome agent provenance."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import yaml

from maid_runner.core.manifest import (
    load_manifest,
    save_manifest,
    validate_manifest_schema,
)
from maid_runner.core import types as core_types


_DEFAULT_AGENT = object()


def test_load_manifest_parses_full_agent_provenance_block(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _manifest_with_outcome_agent())

    manifest = load_manifest(path)

    assert manifest.outcome is not None
    assert manifest.outcome.agent == core_types.AgentProvenance(
        model="gpt-5-codex",
        provider="openai",
        client="codex-cli",
        skills=("maid-implementer@1", "maid-implementation-review@1"),
        instructions_fingerprint="sha256:abc123",
        source="mixed",
    )


def test_load_manifest_parses_minimal_agent_block_with_defaults(
    tmp_path: Path,
) -> None:
    data = _manifest_with_outcome_agent(agent={"model": "local-test-model"})
    path = _write_manifest(tmp_path, data)

    manifest = load_manifest(path)

    assert manifest.outcome is not None
    assert manifest.outcome.agent == core_types.AgentProvenance(
        model="local-test-model"
    )
    assert manifest.outcome.agent.provider is None
    assert manifest.outcome.agent.client is None
    assert manifest.outcome.agent.skills == ()
    assert manifest.outcome.agent.instructions_fingerprint is None
    assert manifest.outcome.agent.source is None


def test_save_manifest_round_trips_agent_block_omission_preserving(
    tmp_path: Path,
) -> None:
    full_path = _write_manifest(tmp_path, _manifest_with_outcome_agent())
    full_saved_path = tmp_path / "full-saved.manifest.yaml"
    save_manifest(load_manifest(full_path), full_saved_path)
    assert load_manifest(full_saved_path).outcome == load_manifest(full_path).outcome
    full_saved = yaml.safe_load(full_saved_path.read_text())
    assert full_saved["outcome"]["agent"] == _full_agent_block()

    minimal_path = _write_manifest(
        tmp_path,
        _manifest_with_outcome_agent(agent={"model": "gpt-5-codex"}),
        name="minimal.manifest.yaml",
    )
    minimal_saved_path = tmp_path / "minimal-saved.manifest.yaml"
    save_manifest(load_manifest(minimal_path), minimal_saved_path)
    minimal_saved = yaml.safe_load(minimal_saved_path.read_text())
    assert minimal_saved["outcome"]["agent"] == {"model": "gpt-5-codex"}

    absent_path = _write_manifest(
        tmp_path,
        _manifest_with_outcome_agent(agent=None),
        name="absent.manifest.yaml",
    )
    absent_saved_path = tmp_path / "absent-saved.manifest.yaml"
    save_manifest(load_manifest(absent_path), absent_saved_path)
    absent_saved = yaml.safe_load(absent_saved_path.read_text())
    assert "agent" not in absent_saved["outcome"]


def test_schema_rejects_invalid_agent_blocks_and_accepts_absent() -> None:
    assert validate_manifest_schema(_manifest_with_outcome_agent(agent=None)) == []
    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "maid_runner/schemas/manifest.v2.schema.json"
        ).read_text(encoding="utf-8")
    )
    agent_schema = schema["definitions"]["AgentProvenance"]
    assert agent_schema["additionalProperties"] is False
    assert agent_schema["required"] == ["model"]
    assert schema["definitions"]["OutcomeRecord"]["properties"]["agent"] == {
        "$ref": "#/definitions/AgentProvenance"
    }

    cases = [
        {},
        {"model": ""},
        {"model": "gpt-5-codex", "unexpected": "loose"},
        {"model": "gpt-5-codex", "skills": "maid-implementer"},
        {"model": "gpt-5-codex", "skills": ["maid-implementer", 123]},
    ]
    for agent in cases:
        data = _manifest_with_outcome_agent(agent=agent)
        errors = validate_manifest_schema(data)
        assert errors, f"invalid agent block should fail schema validation: {agent!r}"


def test_manifest_outcome_docs_define_agent_provenance_block() -> None:
    guide = (
        Path(__file__).resolve().parents[2] / "docs/manifest-outcome-records.md"
    ).read_text(encoding="utf-8")

    assert "agent:" in guide
    assert "model:" in guide
    assert "provider:" in guide
    assert "client:" in guide
    assert "skills:" in guide
    assert "instructions_fingerprint:" in guide
    assert "source:" in guide
    assert "optional, advisory, and never a gate" in guide


def test_outcome_index_carries_agent_provenance_round_trip(tmp_path: Path) -> None:
    from maid_runner.core.outcomes import (
        build_outcome_index,
        read_outcome_index,
        write_outcome_index,
    )

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir,
        _manifest_with_outcome_agent(),
        name="with-agent.manifest.yaml",
    )
    _write_manifest(
        manifest_dir,
        _manifest_with_outcome_agent(
            goal="completed outcome without agent",
            agent=None,
            artifact_name="without_agent_task",
            artifact_path="src/without_agent.py",
            validate_path="tests/test_without_agent.py",
        ),
        name="without-agent.manifest.yaml",
    )
    index_path = tmp_path / "outcomes.json"

    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    records_by_slug = {record.manifest_slug: record for record in index.records}

    assert records_by_slug["with-agent"].agent == core_types.AgentProvenance(
        model="gpt-5-codex",
        provider="openai",
        client="codex-cli",
        skills=("maid-implementer@1", "maid-implementation-review@1"),
        instructions_fingerprint="sha256:abc123",
        source="mixed",
    )
    assert records_by_slug["without-agent"].agent is None

    write_outcome_index(index, index_path)
    payload = json.loads(index_path.read_text())
    written_records_by_slug = {
        record["manifest_slug"]: record for record in payload["records"]
    }
    assert written_records_by_slug["with-agent"]["agent"] == _full_agent_block()
    assert written_records_by_slug["without-agent"]["agent"] is None
    assert read_outcome_index(index_path) == index


def test_read_outcome_index_accepts_pre_provenance_index(tmp_path: Path) -> None:
    from maid_runner.core.outcomes import read_outcome_index

    index_path = tmp_path / "pre-provenance-outcomes.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "generated_from": "source-fingerprint",
                "included_statuses": ["completed"],
                "manifest_dir": "manifests",
                "project_root": tmp_path.as_posix(),
                "records": [
                    {
                        "artifacts": ["src/example.py:function:example_task"],
                        "completed_at": "2026-06-01T00:00:00Z",
                        "created": "2026-06-01",
                        "declared_paths": ["src/example.py"],
                        "lifecycle_status": "active",
                        "lessons": [],
                        "manifest_path": "manifests/example.manifest.yaml",
                        "manifest_slug": "example",
                        "review_notes": [],
                        "source_fingerprint": "0" * 64,
                        "status": "completed",
                        "superseded_by": None,
                        "tags": [],
                        "task_type": "feature",
                        "validation_commands": [
                            ["uv", "run", "python", "-m", "pytest", "-q"]
                        ],
                        "validation_evidence": [],
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n"
    )

    index = read_outcome_index(index_path)

    assert len(index.records) == 1
    assert index.records[0].agent is None


def _write_manifest(
    directory: Path,
    data: dict,
    *,
    name: str = "with-agent.manifest.yaml",
) -> Path:
    path = directory / name
    path.write_text(yaml.safe_dump(deepcopy(data), sort_keys=False))
    return path


def _manifest_with_outcome_agent(
    *,
    goal: str = "Record agent provenance",
    agent: dict | None | object = _DEFAULT_AGENT,
    artifact_name: str = "record_agent",
    artifact_path: str = "src/agent.py",
    validate_path: str = "tests/test_agent.py",
) -> dict:
    if agent is _DEFAULT_AGENT:
        agent = _full_agent_block()

    outcome = {
        "status": "completed",
        "summary": "Agent provenance is recorded on the Outcome.",
        "validation": [
            {
                "command": ["uv", "run", "python", "-m", "pytest", "-q"],
                "status": "passed",
                "summary": "Focused tests passed.",
            }
        ],
        "completed_at": "2026-07-06T00:00:00Z",
    }
    if agent is not None:
        outcome["agent"] = agent

    return {
        "schema": "2",
        "goal": goal,
        "type": "feature",
        "created": "2026-07-06",
        "metadata": {"tags": ["outcome-records"], "priority": "medium"},
        "files": {
            "create": [
                {
                    "path": artifact_path,
                    "artifacts": [{"kind": "function", "name": artifact_name}],
                }
            ],
        },
        "validate": [f"uv run python -m pytest -q {validate_path}"],
        "outcome": outcome,
    }


def _full_agent_block() -> dict:
    return {
        "model": "gpt-5-codex",
        "provider": "openai",
        "client": "codex-cli",
        "skills": ["maid-implementer@1", "maid-implementation-review@1"],
        "instructions_fingerprint": "sha256:abc123",
        "source": "mixed",
    }
