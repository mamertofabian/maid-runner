"""Shared result type for ownership-safe uninstall operations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UninstallReport:
    """Deterministic paths removed, preserved, or already missing."""

    removed: list[str]
    preserved: list[str]
    missing: list[str]
