"""Behavioral coverage for optional agent reasoning-effort provenance."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from maid_runner.core.agent_provenance import resolve_agent_provenance
from maid_runner.core.manifest import (
    load_manifest,
    save_manifest,
    validate_manifest_schema,
)
from maid_runner.core.outcomes import (
    build_outcome_index,
    read_outcome_index,
    write_outcome_index,
)
from maid_runner.core.plan_lock import (
    PlanLock,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.types import AgentProvenance


def test_resolver_reads_reasoning_effort_from_flags() -> None:
    result = resolve_agent_provenance(
        {"model": "gpt-5.5", "reasoning_effort": "medium"}, {}
    )

    assert result.warning is None
    assert result.provenance == AgentProvenance(
        model="gpt-5.5", reasoning_effort="medium", source="flags"
    )


def test_resolver_reads_reasoning_effort_from_env_fallback() -> None:
    mixed = resolve_agent_provenance(
        {"model": "gpt-5.5"}, {"MAID_AGENT_REASONING_EFFORT": "high"}
    )
    environment = resolve_agent_provenance(
        {},
        {
            "MAID_AGENT_MODEL": "gpt-5.5",
            "MAID_AGENT_REASONING_EFFORT": "minimal",
        },
    )

    assert mixed.provenance is not None
    assert mixed.provenance.reasoning_effort == "high"
    assert mixed.provenance.source == "mixed"
    assert environment.provenance is not None
    assert environment.provenance.reasoning_effort == "minimal"
    assert environment.provenance.source == "environment"


def test_reasoning_effort_without_model_warns_and_drops() -> None:
    result = resolve_agent_provenance({}, {"MAID_AGENT_REASONING_EFFORT": "medium"})

    assert result.provenance is None
    assert result.warning is not None
    assert "Provenance advisory:" in result.warning
    assert "model" in result.warning


def test_outcome_agent_round_trips_reasoning_effort(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _manifest_data(reasoning_effort="medium"))
    saved_path = tmp_path / "saved.manifest.yaml"
    save_manifest(load_manifest(path), saved_path)

    saved = yaml.safe_load(saved_path.read_text())
    assert saved["outcome"]["agent"]["reasoning_effort"] == "medium"

    absent = _write_manifest(tmp_path, _manifest_data(), name="absent.manifest.yaml")
    absent_saved = tmp_path / "absent-saved.manifest.yaml"
    save_manifest(load_manifest(absent), absent_saved)
    assert (
        "reasoning_effort"
        not in yaml.safe_load(absent_saved.read_text())["outcome"]["agent"]
    )


def test_schema_accepts_reasoning_effort_and_rejects_unknown_fields() -> None:
    assert validate_manifest_schema(_manifest_data(reasoning_effort="high")) == []
    assert validate_manifest_schema(_manifest_data(reasoning_effort=""))
    invalid = _manifest_data()
    invalid["outcome"]["agent"]["unknown"] = "nope"
    assert validate_manifest_schema(invalid)


def test_plan_lock_round_trips_reasoning_effort_and_legacy_loads_none(
    tmp_path: Path,
) -> None:
    manifest_path = _write_project_manifest(tmp_path)
    lock = create_plan_lock(
        manifest_path,
        tmp_path,
        agent=AgentProvenance(model="gpt-5.5", reasoning_effort="medium"),
    )
    lock_path = default_plan_lock_path(tmp_path, "demo")
    lock.save(lock_path)
    assert PlanLock.load(lock_path).agent is not None
    assert PlanLock.load(lock_path).agent.reasoning_effort == "medium"

    current_errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    payload = json.loads(lock_path.read_text())
    payload["agent"].pop("reasoning_effort")
    lock_path.write_text(json.dumps(payload))
    legacy = PlanLock.load(lock_path)
    assert legacy.agent is not None
    assert legacy.agent.reasoning_effort is None
    assert (
        enforce_plan_locks(
            ManifestChain(tmp_path / "manifests", tmp_path),
            tmp_path,
            require_plan_lock=True,
            require_red_evidence=False,
        )
        == current_errors
    )
    malformed = json.loads(lock_path.read_text())
    malformed["agent"]["reasoning_effort"] = ""
    lock_path.write_text(json.dumps(malformed))
    with pytest.raises(Exception, match="malformed lock record"):
        PlanLock.load(lock_path)


def test_outcome_index_round_trips_reasoning_effort(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir, _manifest_data(reasoning_effort="high"))
    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    assert index.records[0].agent is not None
    assert index.records[0].agent.reasoning_effort == "high"
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(index, index_path)
    assert read_outcome_index(index_path) == index
    legacy_payload = json.loads(index_path.read_text())
    legacy_payload["records"][0]["agent"].pop("reasoning_effort")
    index_path.write_text(json.dumps(legacy_payload))
    legacy = read_outcome_index(index_path)
    assert legacy.records[0].agent is not None
    assert legacy.records[0].agent.reasoning_effort is None


def _manifest_data(*, reasoning_effort: str | None = None) -> dict:
    agent = {"model": "gpt-5.5", "provider": "openai", "client": "codex-cli"}
    if reasoning_effort is not None:
        agent["reasoning_effort"] = reasoning_effort
    return {
        "schema": "2",
        "goal": "Record reasoning effort",
        "type": "feature",
        "created": "2026-07-19",
        "files": {
            "create": [
                {
                    "path": "src/demo.py",
                    "artifacts": [{"kind": "function", "name": "demo"}],
                }
            ]
        },
        "validate": ["python -m pytest -q tests/test_demo.py"],
        "outcome": {"status": "completed", "summary": "done", "agent": agent},
    }


def _write_manifest(
    directory: Path, data: dict, *, name: str = "demo.manifest.yaml"
) -> Path:
    path = directory / name
    path.write_text(yaml.safe_dump(deepcopy(data), sort_keys=False))
    return path


def _write_project_manifest(tmp_path: Path) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_demo.py").write_text("def test_demo(): assert True\n")
    data = _manifest_data()
    data["files"]["read"] = ["tests/test_demo.py"]
    data["validate"] = ["python -m pytest -q tests/test_demo.py"]
    return _write_manifest(tmp_path / "manifests", data)
