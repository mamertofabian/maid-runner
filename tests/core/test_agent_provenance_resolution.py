"""Behavioral tests for resolving CLI-captured agent provenance."""

from __future__ import annotations

import importlib

import pytest

from maid_runner.core.types import AgentProvenance


def _resolve_agent_provenance(flag_values: dict, env: dict):
    try:
        module = importlib.import_module("maid_runner.core.agent_provenance")
    except ModuleNotFoundError as exc:
        pytest.fail(f"resolve_agent_provenance is not implemented: {exc}")
    return module.resolve_agent_provenance(flag_values, env)


def _provenance_resolution_type():
    try:
        module = importlib.import_module("maid_runner.core.agent_provenance")
    except ModuleNotFoundError as exc:
        pytest.fail(f"ProvenanceResolution is not implemented: {exc}")
    return module.ProvenanceResolution


def test_resolve_from_flags_only_sets_source_flags() -> None:
    result = _resolve_agent_provenance(
        {
            "model": "gpt-5-codex",
            "provider": "openai",
            "client": "codex-cli",
            "skills": ["maid-implementer", "maid-implementation-review"],
            "instructions_fingerprint": "sha256:abc",
        },
        {},
    )

    ProvenanceResolution = _provenance_resolution_type()
    assert result == ProvenanceResolution(
        provenance=AgentProvenance(
            model="gpt-5-codex",
            provider="openai",
            client="codex-cli",
            skills=("maid-implementer", "maid-implementation-review"),
            instructions_fingerprint="sha256:abc",
            source="flags",
        ),
        warning=None,
    )


def test_resolve_from_env_only_sets_source_environment() -> None:
    result = _resolve_agent_provenance(
        {},
        {
            "MAID_AGENT_MODEL": "local-model",
            "MAID_AGENT_PROVIDER": "local",
            "MAID_AGENT_CLIENT": "codex-cli",
            "MAID_AGENT_SKILLS": "maid-implementer, maid-plan-review ,,",
            "MAID_AGENT_INSTRUCTIONS_FINGERPRINT": "fingerprint-1",
        },
    )

    assert result.provenance == AgentProvenance(
        model="local-model",
        provider="local",
        client="codex-cli",
        skills=("maid-implementer", "maid-plan-review"),
        instructions_fingerprint="fingerprint-1",
        source="environment",
    )
    assert result.warning is None


def test_resolve_merges_flags_over_env_as_mixed() -> None:
    result = _resolve_agent_provenance(
        {
            "model": "flag-model",
            "provider": None,
            "client": "",
            "skills": ["flag-skill"],
            "instructions_fingerprint": None,
        },
        {
            "MAID_AGENT_MODEL": "env-model",
            "MAID_AGENT_PROVIDER": "env-provider",
            "MAID_AGENT_CLIENT": "env-client",
            "MAID_AGENT_SKILLS": "env-skill",
            "MAID_AGENT_INSTRUCTIONS_FINGERPRINT": "env-fingerprint",
        },
    )

    assert result.provenance == AgentProvenance(
        model="flag-model",
        provider="env-provider",
        client="env-client",
        skills=("flag-skill",),
        instructions_fingerprint="env-fingerprint",
        source="mixed",
    )


def test_resolve_without_input_returns_none_without_warning() -> None:
    result = _resolve_agent_provenance(
        {
            "model": None,
            "provider": None,
            "client": None,
            "skills": [],
            "instructions_fingerprint": None,
        },
        {},
    )

    ProvenanceResolution = _provenance_resolution_type()
    assert result == ProvenanceResolution(provenance=None, warning=None)


def test_resolve_without_model_returns_warning_not_provenance() -> None:
    result = _resolve_agent_provenance(
        {
            "model": None,
            "provider": "openai",
            "client": "codex-cli",
            "skills": [],
            "instructions_fingerprint": None,
        },
        {},
    )

    assert result.provenance is None
    assert result.warning is not None
    assert "agent provenance" in result.warning
    assert "model" in result.warning
