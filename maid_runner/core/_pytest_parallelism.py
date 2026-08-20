"""Content-bound advisory timing and pure pytest worker policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import tempfile
from types import MappingProxyType
from typing import Any


_FORMAT_VERSION = 1
_CACHE_DIRECTORY = Path(".maid/cache")
_ENTRY_KEYS = frozenset(
    {
        "behavior_group_digest",
        "input_digest",
        "collected_at",
        "durations_ms",
    }
)


@dataclass(frozen=True)
class PytestTimingHistory:
    """Immutable advisory per-node timing table with content bindings."""

    durations_ms: Mapping[str, float]
    behavior_group_digest: str
    input_digest: str
    collected_at: str
    format_version: int

    def __post_init__(self) -> None:
        _validate_digest(self.behavior_group_digest, "behavior_group_digest")
        _validate_digest(self.input_digest, "input_digest")
        if self.format_version != _FORMAT_VERSION:
            raise ValueError("Unsupported pytest timing history format version")
        if not isinstance(self.collected_at, str) or not self.collected_at:
            raise ValueError("collected_at must be a non-empty timestamp")

        normalized = _normalize_duration_table(self.durations_ms)
        object.__setattr__(self, "durations_ms", MappingProxyType(normalized))


@dataclass(frozen=True)
class PytestTimingHistoryLoad:
    """Typed result for fail-closed advisory history loading."""

    history: PytestTimingHistory | None
    state: str


@dataclass(frozen=True)
class PytestWorkerDecision:
    """Pure serial/worker decision with a stable disclosure reason."""

    use_workers: bool
    workers: int | str
    predicted_duration_ms: float | None
    history_state: str
    reason: str


def load_pytest_timing_history(
    project_root: Path,
    behavior_group_digest: str,
    input_digest: str,
) -> PytestTimingHistoryLoad:
    """Load current timing history or disclose why it cannot be used."""
    _validate_digest(behavior_group_digest, "behavior_group_digest")
    _validate_digest(input_digest, "input_digest")
    cache_path = _history_cache_path(project_root, behavior_group_digest)
    if not cache_path.is_file():
        return PytestTimingHistoryLoad(history=None, state="missing")

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return PytestTimingHistoryLoad(history=None, state="corrupt")

    if not isinstance(payload, dict):
        return PytestTimingHistoryLoad(history=None, state="corrupt")
    if payload.get("format_version") != _FORMAT_VERSION:
        return PytestTimingHistoryLoad(history=None, state="unsupported")
    if set(payload) != {"format_version", "history"}:
        return PytestTimingHistoryLoad(history=None, state="corrupt")
    entry = payload.get("history")
    history = _parse_history_entry(entry, behavior_group_digest)
    if history is None:
        return PytestTimingHistoryLoad(history=None, state="corrupt")
    if history.input_digest != input_digest:
        return PytestTimingHistoryLoad(history=None, state="stale")
    return PytestTimingHistoryLoad(history=history, state="current")


def record_pytest_timing_history(
    project_root: Path,
    behavior_group_digest: str,
    input_digest: str,
    node_durations_ms: Mapping[str, float],
) -> None:
    """Atomically record advisory durations without test result state."""
    _validate_digest(behavior_group_digest, "behavior_group_digest")
    _validate_digest(input_digest, "input_digest")
    history = PytestTimingHistory(
        durations_ms=node_durations_ms,
        behavior_group_digest=behavior_group_digest,
        input_digest=input_digest,
        collected_at=_utc_now(),
        format_version=_FORMAT_VERSION,
    )

    cache_path = _history_cache_path(project_root, behavior_group_digest)
    payload = {
        "format_version": _FORMAT_VERSION,
        "history": _history_payload(history),
    }
    _atomic_write_json(cache_path, payload)


def predict_pytest_duration_ms(
    selected_nodeids: Sequence[str],
    history: PytestTimingHistory | None,
) -> float | None:
    """Predict serial duration only when every selected node has a timing."""
    if not selected_nodeids:
        return 0.0
    if history is None:
        return None

    predicted = 0.0
    for nodeid in selected_nodeids:
        try:
            normalized = _normalize_nodeid(nodeid)
        except ValueError:
            return None
        duration = history.durations_ms.get(normalized)
        if duration is None:
            return None
        predicted += duration
        if not math.isfinite(predicted):
            return None
    return predicted


def choose_pytest_worker_policy(
    selected_nodeids: Sequence[str],
    history_load: PytestTimingHistoryLoad,
    configured_workers: int | str,
    threshold_ms: float,
    parallel_without_history: bool,
) -> PytestWorkerDecision:
    """Choose workers without mutating or filtering selected nodes."""
    _validate_worker_policy(configured_workers, threshold_ms)

    if not selected_nodeids:
        return PytestWorkerDecision(
            use_workers=False,
            workers=1,
            predicted_duration_ms=0.0,
            history_state=_decision_history_state(history_load, complete=True),
            reason="serial:no-selected-nodes",
        )

    history = history_load.history if history_load.state == "current" else None
    predicted = predict_pytest_duration_ms(selected_nodeids, history)
    history_state = _decision_history_state(
        history_load,
        complete=predicted is not None,
    )

    if configured_workers == 1:
        return PytestWorkerDecision(
            use_workers=False,
            workers=1,
            predicted_duration_ms=predicted,
            history_state=history_state,
            reason="serial:configured-single-worker",
        )

    if predicted is None:
        use_workers = parallel_without_history
        return PytestWorkerDecision(
            use_workers=use_workers,
            workers=configured_workers if use_workers else 1,
            predicted_duration_ms=None,
            history_state=history_state,
            reason=(
                "workers:unknown-history-policy"
                if use_workers
                else "serial:unknown-history"
            ),
        )

    use_workers = predicted >= threshold_ms
    return PytestWorkerDecision(
        use_workers=use_workers,
        workers=configured_workers if use_workers else 1,
        predicted_duration_ms=predicted,
        history_state="complete",
        reason=(
            "workers:predicted-at-or-above-threshold"
            if use_workers
            else "serial:predicted-below-threshold"
        ),
    )


def _validate_digest(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} digest must be a non-empty string")


def _normalize_nodeid(nodeid: str) -> str:
    if not isinstance(nodeid, str) or not nodeid:
        raise ValueError("pytest node ID must be a non-empty string")
    path_part, separator, selector = nodeid.partition("::")
    normalized_path = path_part.replace("\\", "/")
    while normalized_path.startswith("./"):
        normalized_path = normalized_path[2:]
    canonical_path = PurePosixPath(normalized_path)
    parts = canonical_path.parts
    has_windows_drive = (
        len(normalized_path) >= 2
        and normalized_path[0].isalpha()
        and normalized_path[1] == ":"
    )
    if (
        not normalized_path
        or normalized_path == "."
        or normalized_path.startswith("/")
        or has_windows_drive
        or ".." in parts
    ):
        raise ValueError("pytest node ID must be project-relative")
    normalized_path = canonical_path.as_posix()
    return normalized_path + (separator + selector if separator else "")


def _normalize_duration_table(
    durations_ms: Mapping[str, float],
) -> dict[str, float]:
    if not isinstance(durations_ms, Mapping):
        raise ValueError("durations_ms must be a mapping")
    normalized: dict[str, float] = {}
    for nodeid, raw_duration in durations_ms.items():
        normalized_nodeid = _normalize_nodeid(nodeid)
        if isinstance(raw_duration, bool) or not isinstance(raw_duration, (int, float)):
            raise ValueError("pytest durations must be finite and non-negative")
        duration = float(raw_duration)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("pytest durations must be finite and non-negative")
        if normalized_nodeid in normalized:
            raise ValueError("pytest node IDs must be unique after normalization")
        normalized[normalized_nodeid] = duration
    return dict(sorted(normalized.items()))


def _parse_history_entry(
    entry: Any,
    behavior_group_digest: str,
) -> PytestTimingHistory | None:
    if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
        return None
    if entry.get("behavior_group_digest") != behavior_group_digest:
        return None
    try:
        return PytestTimingHistory(
            durations_ms=entry["durations_ms"],
            behavior_group_digest=entry["behavior_group_digest"],
            input_digest=entry["input_digest"],
            collected_at=entry["collected_at"],
            format_version=_FORMAT_VERSION,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _history_payload(history: PytestTimingHistory) -> dict[str, Any]:
    return {
        "behavior_group_digest": history.behavior_group_digest,
        "input_digest": history.input_digest,
        "collected_at": history.collected_at,
        "durations_ms": dict(history.durations_ms),
    }


def _history_cache_path(project_root: Path, behavior_group_digest: str) -> Path:
    cache_key = hashlib.sha256(behavior_group_digest.encode("utf-8")).hexdigest()
    return Path(project_root) / _CACHE_DIRECTORY / f"pytest-timing-{cache_key}.json"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _validate_worker_policy(configured_workers: int | str, threshold_ms: float) -> None:
    if isinstance(configured_workers, bool) or not isinstance(
        configured_workers, (int, str)
    ):
        raise ValueError("configured_workers must be a positive integer or name")
    if isinstance(configured_workers, int) and configured_workers < 1:
        raise ValueError("configured_workers must be positive")
    if isinstance(configured_workers, str) and not configured_workers.strip():
        raise ValueError("configured_workers name must be non-empty")
    if isinstance(threshold_ms, bool) or not isinstance(threshold_ms, (int, float)):
        raise ValueError("threshold_ms must be finite and non-negative")
    if not math.isfinite(float(threshold_ms)) or threshold_ms < 0:
        raise ValueError("threshold_ms must be finite and non-negative")


def _decision_history_state(
    history_load: PytestTimingHistoryLoad,
    *,
    complete: bool,
) -> str:
    if history_load.state == "current":
        return "complete" if complete else "partial"
    return history_load.state
