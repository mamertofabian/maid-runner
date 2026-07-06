"""CLI behavior for agent provenance captured in plan locks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.plan import (
    cmd_plan_lock,
    cmd_plan_revise,
    cmd_plan_status,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
    revise_plan_lock,
)
from maid_runner.core.types import AgentProvenance


def _write_project(tmp_path: Path, slug: str = "demo-task") -> Path:
    (tmp_path / "manifests").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )
    manifest_path = tmp_path / "manifests" / f"{slug}.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Demo task"
type: feature
created: "2026-07-06T00:00:00Z"
files:
  create:
    - path: src/{slug.replace("-", "_")}.py
      artifacts:
        - kind: function
          name: demo
  read:
    - tests/test_demo.py
validate:
  - python -m pytest -q tests/test_demo.py
"""
    )
    return manifest_path


def _agent_flags() -> dict:
    return {
        "agent_model": "gpt-5-codex",
        "agent_provider": "openai",
        "agent_client": "codex-cli",
        "agent_skill": ["maid-implementer", "maid-implementation-review"],
        "agent_instructions_fingerprint": "sha256:instructions",
    }


def _lock_args(
    manifest_path: Path,
    project_root: Path,
    *,
    no_run: bool = True,
    agent: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=no_run,
        json=False,
        **(agent or _empty_agent_args()),
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    reason: str,
    *,
    agent: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=True,
        preserve_red_evidence=False,
        stash_implementation=False,
        json=False,
        **(agent or _empty_agent_args()),
    )


def _status_args(
    manifest_path: Path, project_root: Path, *, json_mode: bool
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="status",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        json=json_mode,
    )


def _empty_agent_args() -> dict:
    return {
        "agent_model": None,
        "agent_provider": None,
        "agent_client": None,
        "agent_skill": None,
        "agent_instructions_fingerprint": None,
    }


def _lock_record(project_root: Path, slug: str = "demo-task") -> dict:
    return json.loads(default_plan_lock_path(project_root, slug).read_text())


def _chain(project_root: Path) -> ManifestChain:
    return ManifestChain(project_root / "manifests", project_root)


def _plan_subparser(name: str) -> argparse.ArgumentParser:
    parser = build_parser()
    plan_parser = None
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            plan_parser = action.choices["plan"]
            break
    assert plan_parser is not None
    for action in plan_parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[name]
    raise AssertionError("plan subparser not found")


def test_plan_lock_records_agent_from_flags(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    args = _plan_subparser("lock").parse_args(
        [
            "manifests/demo-task.manifest.yaml",
            "--agent-model",
            "gpt-5-codex",
            "--agent-provider",
            "openai",
            "--agent-client",
            "codex-cli",
            "--agent-skill",
            "maid-implementer",
            "--agent-skill",
            "maid-implementation-review",
            "--agent-instructions-fingerprint",
            "sha256:instructions",
        ]
    )
    assert args.agent_skill == ["maid-implementer", "maid-implementation-review"]
    manifest_path = _write_project(tmp_path)
    core_lock = create_plan_lock(
        manifest_path,
        tmp_path,
        agent=AgentProvenance(model="core-model", source="flags"),
    )
    assert core_lock.agent == AgentProvenance(model="core-model", source="flags")

    exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path, agent=_agent_flags()))

    assert exit_code == 0
    assert _lock_record(tmp_path)["agent"] == {
        "model": "gpt-5-codex",
        "provider": "openai",
        "client": "codex-cli",
        "skills": ["maid-implementer", "maid-implementation-review"],
        "instructions_fingerprint": "sha256:instructions",
        "source": "flags",
    }


def test_plan_lock_records_agent_from_env_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_project(tmp_path)
    monkeypatch.setenv("MAID_AGENT_MODEL", "env-model")
    monkeypatch.setenv("MAID_AGENT_PROVIDER", "env-provider")
    monkeypatch.setenv("MAID_AGENT_CLIENT", "env-client")
    monkeypatch.setenv("MAID_AGENT_SKILLS", "env-skill-a, env-skill-b")
    monkeypatch.setenv("MAID_AGENT_INSTRUCTIONS_FINGERPRINT", "env-fingerprint")

    exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

    assert exit_code == 0
    assert _lock_record(tmp_path)["agent"] == {
        "model": "env-model",
        "provider": "env-provider",
        "client": "env-client",
        "skills": ["env-skill-a", "env-skill-b"],
        "instructions_fingerprint": "env-fingerprint",
        "source": "environment",
    }


def test_plan_revise_attaches_agent_to_revision_entry(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    core_lock = create_plan_lock(
        manifest_path,
        tmp_path,
        agent=AgentProvenance(model="creator-model", source="flags"),
    )
    core_revised = revise_plan_lock(
        core_lock,
        manifest_path,
        tmp_path,
        "core revision",
        agent=AgentProvenance(model="reviser-model", source="flags"),
    )
    assert core_revised.agent == core_lock.agent
    assert core_revised.revisions[0].agent == AgentProvenance(
        model="reviser-model", source="flags"
    )

    assert (
        cmd_plan_lock(
            _lock_args(
                manifest_path,
                tmp_path,
                agent={**_agent_flags(), "agent_model": "creator-model"},
            )
        )
        == 0
    )

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "add reviewer-requested behavioral coverage",
            agent={**_agent_flags(), "agent_model": "reviser-model"},
        )
    )

    assert exit_code == 0
    record = _lock_record(tmp_path)
    assert record["agent"]["model"] == "creator-model"
    assert record["revisions"][0]["agent"]["model"] == "reviser-model"
    assert record["revisions"][0]["agent"]["source"] == "flags"


def test_plan_lock_without_model_warns_and_records_no_agent(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    manifest_path = _write_project(tmp_path)

    exit_code = cmd_plan_lock(
        _lock_args(
            manifest_path,
            tmp_path,
            agent={**_empty_agent_args(), "agent_provider": "openai"},
        )
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert "Provenance advisory:" in output.err
    assert "model" in output.err
    assert _lock_record(tmp_path)["agent"] is None


def test_plan_status_reports_agent_in_json_and_text(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path, agent=_agent_flags())) == 0
    assert (
        cmd_plan_revise(
            _revise_args(
                manifest_path,
                tmp_path,
                "revision with provenance",
                agent={**_agent_flags(), "agent_model": "revision-model"},
            )
        )
        == 0
    )
    capsys.readouterr()

    assert cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent"]["model"] == "gpt-5-codex"
    assert payload["revisions"][0]["agent"]["model"] == "revision-model"

    assert cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=False)) == 0
    text = capsys.readouterr().out
    assert "Agent: gpt-5-codex" in text
    assert "Revision agent: revision-model" in text


def test_pre_provenance_lock_loads_and_verifies_identically(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path, agent=_agent_flags())) == 0
    provenance_errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    current_record = _lock_record(tmp_path)

    legacy_record = dict(current_record)
    legacy_record.pop("agent", None)
    legacy_record["revisions"] = [
        {key: value for key, value in revision.items() if key != "agent"}
        for revision in legacy_record["revisions"]
    ]
    default_plan_lock_path(tmp_path, "demo-task").write_text(
        json.dumps(legacy_record, indent=2)
    )
    capsys.readouterr()

    assert cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent"] is None
    assert payload["revisions"] == []
    legacy_errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    assert legacy_errors == provenance_errors

    assert cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=False)) == 0
    assert "Agent:" not in capsys.readouterr().out


def test_malformed_agent_payload_fails_closed(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path, agent=_agent_flags())) == 0
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    payload = _lock_record(tmp_path)
    payload["agent"] = {
        "model": "gpt-5-codex",
        "skills": "not-a-list",
    }
    lock_path.write_text(json.dumps(payload, indent=2))

    with pytest.raises(Exception, match="malformed lock record"):
        PlanLock.load(lock_path)
