"""Named presets for the recurring ``maid verify`` flag stacks.

``maid verify`` exposes 31 options and the useful combinations are not
discoverable from that list, so they end up memorized and copied. A profile
gives a recurring stack a name.

Resolution here is a pure decision -- name in, defaults out -- with no I/O, no
parser, and no repository access, so it is testable on its own. Applying a
profile to parsed arguments is deliberately a reporting event: it returns the
line that discloses which flags the profile contributed, because a preset that
silently changed the effective gate set would be worse than the flag stack it
replaces.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

# Shared with the --packet const in the verify parser so the two cannot drift.
_DEFAULT_FAILURE_PACKET_PATH = ".maid/last-failure-packet.json"


@dataclass(frozen=True)
class VerifyProfile:
    """A named set of ``maid verify`` defaults."""

    name: str
    defaults: Mapping[str, bool | str]


# Each profile records a stack observed in this repository. `handoff` is the
# AGENTS.md step 8 gate; `pre-commit` mirrors the MAID-managed hook that
# `maid init` generates, minus its baseline; `agent-retry` and `deep` cover the
# bounded-retry and high-risk-evidence stacks. No profile supplies --since or
# --base-ref: MAID never guesses a changed-scope baseline.
_PROFILES: Mapping[str, Mapping[str, bool | str]] = MappingProxyType(
    {
        "handoff": MappingProxyType(
            {
                "summary": True,
                "require_plan_lock": True,
                "require_red_evidence": True,
            }
        ),
        "pre-commit": MappingProxyType(
            {
                "summary": True,
                "advisory": True,
                "allow_empty": True,
                "require_plan_lock": True,
                "require_red_evidence": True,
                "fail_fast": True,
                "changed_scope": False,
                "file_tracking_scope": "task",
                "plan_lock_scope": "task",
            }
        ),
        "agent-retry": MappingProxyType(
            {
                "summary": True,
                "packet": _DEFAULT_FAILURE_PACKET_PATH,
            }
        ),
        "deep": MappingProxyType(
            {
                "summary": True,
                "artifact_coverage": True,
                "knockout": True,
            }
        ),
    }
)


def verify_profile_names() -> tuple[str, ...]:
    """Return the shipped profile names in a deterministic order."""
    return tuple(_PROFILES)


def resolve_verify_profile(name: str) -> VerifyProfile:
    """Resolve a profile name to its defaults.

    Raises ``KeyError`` for an unknown name. The returned mapping is read-only
    so a caller cannot mutate one resolution into a later one, which matters in
    the long-lived ``maid serve`` process.
    """
    defaults = _PROFILES.get(name)
    if defaults is None:
        raise KeyError(
            f"Unknown verify profile '{name}'. "
            f"Valid profiles: {', '.join(verify_profile_names())}"
        )
    return VerifyProfile(name=name, defaults=defaults)


def apply_verify_profile(args: argparse.Namespace) -> str | None:
    """Apply the requested profile's defaults to ``args``.

    Options the user passed explicitly always win, so a profile can never
    override a deliberate choice. Explicitness is read from the ``<dest>_explicit``
    markers the verify parser records, not by comparing against parser defaults:
    an explicitly passed value can equal the default, and the two cases must not
    be confused.

    Returns a one-line report naming the profile and the flags it actually
    contributed, or ``None`` when no profile was requested.
    """
    name = getattr(args, "profile", None)
    if not name:
        return None

    profile = resolve_verify_profile(name)
    contributed: list[str] = []
    for dest, value in profile.defaults.items():
        if getattr(args, f"{dest}_explicit", False):
            continue
        setattr(args, dest, value)
        contributed.append(_render_flag(dest, value))

    if not contributed:
        return f"Profile: {profile.name} (no flags contributed; all set explicitly)"
    return f"Profile: {profile.name} -> {' '.join(contributed)}"


def _render_flag(dest: str, value: bool | str) -> str:
    """Render one profile default as the option a reader would have typed."""
    option = dest.replace("_", "-")
    if value is True:
        return f"--{option}"
    if value is False:
        return f"--no-{option}"
    return f"--{option} {value}"
