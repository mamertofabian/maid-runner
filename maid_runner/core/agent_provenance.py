"""Agent provenance resolution for CLI-captured metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Optional

from maid_runner.core.types import AgentProvenance


@dataclass(frozen=True)
class ProvenanceResolution:
    """Resolved agent provenance, or a visible advisory warning."""

    provenance: Optional[AgentProvenance]
    warning: Optional[str]


def resolve_agent_provenance(
    flag_values: Mapping[str, object], env: Mapping[str, str]
) -> ProvenanceResolution:
    """Resolve --agent-* flags with MAID_AGENT_* environment fallback."""
    fields = {
        "model": _resolve_string(flag_values.get("model"), env.get("MAID_AGENT_MODEL")),
        "reasoning_effort": _resolve_string(
            flag_values.get("reasoning_effort"),
            env.get("MAID_AGENT_REASONING_EFFORT"),
        ),
        "provider": _resolve_string(
            flag_values.get("provider"), env.get("MAID_AGENT_PROVIDER")
        ),
        "client": _resolve_string(
            flag_values.get("client"), env.get("MAID_AGENT_CLIENT")
        ),
        "skills": _resolve_skills(
            flag_values.get("skills"), env.get("MAID_AGENT_SKILLS")
        ),
        "instructions_fingerprint": _resolve_string(
            flag_values.get("instructions_fingerprint"),
            env.get("MAID_AGENT_INSTRUCTIONS_FINGERPRINT"),
        ),
    }
    resolved_values = {
        name: value for name, (value, _source) in fields.items() if value
    }
    if not resolved_values:
        return ProvenanceResolution(provenance=None, warning=None)
    if "model" not in resolved_values:
        return ProvenanceResolution(
            provenance=None,
            warning=(
                "Provenance advisory: agent provenance ignored because "
                "model is required."
            ),
        )

    sources = {
        source for value, source in fields.values() if value and source is not None
    }
    if sources == {"flags"}:
        source = "flags"
    elif sources == {"environment"}:
        source = "environment"
    else:
        source = "mixed"

    return ProvenanceResolution(
        provenance=AgentProvenance(
            model=str(resolved_values["model"]),
            reasoning_effort=_optional_str(resolved_values.get("reasoning_effort")),
            provider=_optional_str(resolved_values.get("provider")),
            client=_optional_str(resolved_values.get("client")),
            skills=tuple(resolved_values.get("skills", ())),
            instructions_fingerprint=_optional_str(
                resolved_values.get("instructions_fingerprint")
            ),
            source=source,
        ),
        warning=None,
    )


def _resolve_string(
    flag_value: object, env_value: str | None
) -> tuple[str | None, str | None]:
    flag_text = _clean_string(flag_value)
    if flag_text is not None:
        return flag_text, "flags"
    env_text = _clean_string(env_value)
    if env_text is not None:
        return env_text, "environment"
    return None, None


def _resolve_skills(
    flag_value: object, env_value: str | None
) -> tuple[tuple[str, ...], str | None]:
    flag_skills = _clean_sequence(flag_value)
    if flag_skills:
        return flag_skills, "flags"
    env_skills = tuple(
        item.strip() for item in (env_value or "").split(",") if item.strip()
    )
    if env_skills:
        return env_skills, "environment"
    return (), None


def _clean_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _clean_sequence(value: object) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return ()
    return tuple(item for item in (_clean_string(item) for item in value) if item)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
