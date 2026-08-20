"""Behavioral contract for duration-informed pytest worker policy."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from threading import Barrier

import pytest


def _history(durations_ms: dict[str, float]):
    from maid_runner.core._pytest_parallelism import PytestTimingHistory

    return PytestTimingHistory(
        durations_ms=durations_ms,
        behavior_group_digest="behavior-a",
        input_digest="input-a",
        collected_at="2026-08-11T00:00:00Z",
        format_version=1,
    )


def _current_load(durations_ms: dict[str, float]):
    from maid_runner.core._pytest_parallelism import PytestTimingHistoryLoad

    return PytestTimingHistoryLoad(history=_history(durations_ms), state="current")


def _decision(
    selected_nodeids,
    history_load,
    *,
    workers: int | str = 8,
    threshold_ms: float = 500.0,
    parallel_without_history: bool = False,
):
    from maid_runner.core._pytest_parallelism import choose_pytest_worker_policy

    return choose_pytest_worker_policy(
        selected_nodeids=selected_nodeids,
        history_load=history_load,
        configured_workers=workers,
        threshold_ms=threshold_ms,
        parallel_without_history=parallel_without_history,
    )


def test_small_predicted_batch_stays_serial() -> None:
    decision = _decision(
        ["tests/test_demo.py::test_one", "tests/test_demo.py::test_two"],
        _current_load(
            {
                "tests/test_demo.py::test_one": 100.0,
                "tests/test_demo.py::test_two": 200.0,
            }
        ),
    )

    assert decision.use_workers is False
    assert decision.workers == 1
    assert decision.predicted_duration_ms == 300.0
    assert decision.history_state == "complete"
    assert decision.reason == "serial:predicted-below-threshold"


def test_expensive_predicted_batch_chooses_configured_workers() -> None:
    from maid_runner.core._pytest_parallelism import PytestWorkerDecision

    decision = _decision(
        ["tests/test_demo.py::test_one", "tests/test_demo.py::test_two"],
        _current_load(
            {
                "tests/test_demo.py::test_one": 250.0,
                "tests/test_demo.py::test_two": 250.0,
            }
        ),
    )

    assert isinstance(decision, PytestWorkerDecision)
    assert decision.use_workers is True
    assert decision.workers == 8
    assert decision.predicted_duration_ms == 500.0
    assert decision.history_state == "complete"
    assert decision.reason == "workers:predicted-at-or-above-threshold"


def test_decision_never_changes_selected_nodeids() -> None:
    selected = ["tests/test_demo.py::test_two", "tests/test_demo.py::test_one"]
    original = list(selected)

    _decision(selected, _current_load({}), parallel_without_history=True)

    assert selected == original


def test_missing_or_partial_history_uses_explicit_unknown_policy() -> None:
    from maid_runner.core._pytest_parallelism import PytestTimingHistoryLoad

    selected = ["tests/test_demo.py::test_one", "tests/test_demo.py::test_two"]
    missing = PytestTimingHistoryLoad(history=None, state="missing")
    partial = _current_load({"tests/test_demo.py::test_one": 900.0})

    missing_serial = _decision(selected, missing)
    partial_workers = _decision(selected, partial, parallel_without_history=True)

    assert (
        missing_serial.use_workers,
        missing_serial.predicted_duration_ms,
        missing_serial.history_state,
        missing_serial.reason,
    ) == (False, None, "missing", "serial:unknown-history")
    assert (
        partial_workers.use_workers,
        partial_workers.workers,
        partial_workers.predicted_duration_ms,
        partial_workers.history_state,
        partial_workers.reason,
    ) == (True, 8, None, "partial", "workers:unknown-history-policy")


def test_content_or_behavior_digest_change_invalidates_history(tmp_path: Path) -> None:
    from maid_runner.core._pytest_parallelism import (
        load_pytest_timing_history,
        record_pytest_timing_history,
    )

    record_pytest_timing_history(
        tmp_path, "behavior-a", "input-a", {"tests/test_demo.py::test_one": 10.0}
    )

    current = load_pytest_timing_history(tmp_path, "behavior-a", "input-a")
    stale = load_pytest_timing_history(tmp_path, "behavior-a", "input-b")
    missing = load_pytest_timing_history(tmp_path, "behavior-b", "input-a")

    assert current.state == "current"
    assert current.history is not None
    assert stale.state == "stale"
    assert stale.history is None
    assert missing.state == "missing"
    assert missing.history is None


def test_corrupt_history_is_not_treated_as_pass_or_zero_duration(
    tmp_path: Path,
) -> None:
    from maid_runner.core._pytest_parallelism import (
        load_pytest_timing_history,
        record_pytest_timing_history,
    )

    record_pytest_timing_history(
        tmp_path, "behavior-a", "input-a", {"tests/test_demo.py::test_one": 10.0}
    )
    cache_file = next((tmp_path / ".maid" / "cache").glob("*.json"))
    cache_file.write_text("{broken", encoding="utf-8")

    loaded = load_pytest_timing_history(tmp_path, "behavior-a", "input-a")
    decision = _decision(
        ["tests/test_demo.py::test_one"], loaded, parallel_without_history=False
    )

    assert loaded.state == "corrupt"
    assert loaded.history is None
    assert decision.predicted_duration_ms is None
    assert decision.use_workers is False


def test_recorded_history_contains_no_test_outcome(tmp_path: Path) -> None:
    from maid_runner.core._pytest_parallelism import record_pytest_timing_history

    record_pytest_timing_history(
        tmp_path, "behavior-a", "input-a", {"tests/test_demo.py::test_one": 10.0}
    )
    cache_file = next((tmp_path / ".maid" / "cache").glob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    entry = payload["history"]

    assert set(payload) == {"format_version", "history"}
    assert set(entry) == {
        "behavior_group_digest",
        "input_digest",
        "collected_at",
        "durations_ms",
    }

    entry["passed"] = True
    cache_file.write_text(json.dumps(payload), encoding="utf-8")
    record_pytest_timing_history(
        tmp_path, "behavior-a", "input-a", {"tests/test_demo.py::test_one": 20.0}
    )
    replaced = json.loads(cache_file.read_text(encoding="utf-8"))["history"]
    assert set(replaced) == set(entry) - {"passed"}


def test_recording_preserves_other_behavior_groups_without_partial_files(
    tmp_path: Path,
) -> None:
    from maid_runner.core._pytest_parallelism import (
        load_pytest_timing_history,
        record_pytest_timing_history,
    )

    record_pytest_timing_history(
        tmp_path, "behavior-a", "input-a", {"tests/test_a.py::test_a": 10.0}
    )
    record_pytest_timing_history(
        tmp_path, "behavior-b", "input-b", {"tests/test_b.py::test_b": 20.0}
    )

    assert load_pytest_timing_history(tmp_path, "behavior-a", "input-a").state == (
        "current"
    )
    assert load_pytest_timing_history(tmp_path, "behavior-b", "input-b").state == (
        "current"
    )
    cache_files = list((tmp_path / ".maid" / "cache").iterdir())
    assert len(cache_files) == 2
    assert all(path.suffix == ".json" for path in cache_files)


def test_concurrent_recording_preserves_every_behavior_group(tmp_path: Path) -> None:
    from maid_runner.core._pytest_parallelism import (
        load_pytest_timing_history,
        record_pytest_timing_history,
    )

    group_count = 8
    start = Barrier(group_count)

    def record(group: int) -> None:
        start.wait()
        record_pytest_timing_history(
            tmp_path,
            f"behavior-{group}",
            f"input-{group}",
            {f"tests/test_{group}.py::test_{group}": float(group)},
        )

    with ThreadPoolExecutor(max_workers=group_count) as executor:
        list(executor.map(record, range(group_count)))

    for group in range(group_count):
        loaded = load_pytest_timing_history(
            tmp_path, f"behavior-{group}", f"input-{group}"
        )
        assert loaded.state == "current"
        assert loaded.history is not None
    cache_files = list((tmp_path / ".maid" / "cache").iterdir())
    assert len(cache_files) == group_count
    assert all(path.suffix == ".json" for path in cache_files)


def test_recorded_nodeids_are_normalized_and_invalid_durations_rejected(
    tmp_path: Path,
) -> None:
    from maid_runner.core._pytest_parallelism import (
        load_pytest_timing_history,
        predict_pytest_duration_ms,
        record_pytest_timing_history,
    )

    record_pytest_timing_history(
        tmp_path,
        "behavior-a",
        "input-a",
        {"./tests\\test_demo.py::test_one": 10.0},
    )
    loaded = load_pytest_timing_history(tmp_path, "behavior-a", "input-a")

    assert loaded.history is not None
    assert dict(loaded.history.durations_ms) == {"tests/test_demo.py::test_one": 10.0}
    assert (
        predict_pytest_duration_ms(
            selected_nodeids=["./tests\\test_demo.py::test_one"],
            history=loaded.history,
        )
        == 10.0
    )
    assert (
        predict_pytest_duration_ms(
            selected_nodeids=["tests//./test_demo.py::test_one"],
            history=loaded.history,
        )
        == 10.0
    )

    with pytest.raises(ValueError, match="unique after normalization"):
        record_pytest_timing_history(
            tmp_path,
            "behavior-a",
            "input-a",
            {
                "tests/test_demo.py::test_one": 10.0,
                "tests//./test_demo.py::test_one": 20.0,
            },
        )

    for invalid in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite and non-negative"):
            record_pytest_timing_history(
                tmp_path,
                "behavior-a",
                "input-a",
                {"tests/test_demo.py::test_one": invalid},
            )


def test_empty_selection_and_single_worker_stay_serial() -> None:
    empty = _decision([], _current_load({}), parallel_without_history=True)
    single = _decision(
        ["tests/test_demo.py::test_one"],
        _current_load({"tests/test_demo.py::test_one": 10_000.0}),
        workers=1,
    )

    assert (empty.use_workers, empty.workers, empty.predicted_duration_ms) == (
        False,
        1,
        0.0,
    )
    assert empty.reason == "serial:no-selected-nodes"
    assert (single.use_workers, single.workers) == (False, 1)
    assert single.reason == "serial:configured-single-worker"


def test_unsupported_format_is_typed_unknown_history(tmp_path: Path) -> None:
    from maid_runner.core._pytest_parallelism import (
        PytestTimingHistoryLoad,
        load_pytest_timing_history,
        record_pytest_timing_history,
    )

    record_pytest_timing_history(
        tmp_path, "behavior-a", "input-a", {"tests/test_demo.py::test_one": 10.0}
    )
    cache_file = next((tmp_path / ".maid" / "cache").glob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["format_version"] = 999
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_pytest_timing_history(tmp_path, "behavior-a", "input-a")

    assert isinstance(loaded, PytestTimingHistoryLoad)
    assert loaded.state == "unsupported"
    assert loaded.history is None


def test_timing_records_and_decisions_are_immutable() -> None:
    history = _history({"tests/test_demo.py::test_one": 10.0})
    decision = _decision(
        ["tests/test_demo.py::test_one"], _current_load(dict(history.durations_ms))
    )

    with pytest.raises(FrozenInstanceError):
        history.input_digest = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        history.durations_ms["tests/test_demo.py::test_one"] = 20.0  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        decision.use_workers = True  # type: ignore[misc]


def test_invalid_timing_identity_or_worker_policy_fails_closed(
    tmp_path: Path,
) -> None:
    from maid_runner.core._pytest_parallelism import record_pytest_timing_history

    invalid_tables = (
        {"": 10.0},
        {"C:\\tests\\test_demo.py::test_one": 10.0},
        {"tests/test_demo.py::test_one": -1.0},
        {"tests/test_demo.py::test_one": float("nan")},
        {"tests/test_demo.py::test_one": float("inf")},
    )
    for durations in invalid_tables:
        with pytest.raises(ValueError):
            record_pytest_timing_history(tmp_path, "behavior-a", "input-a", durations)

    for behavior_digest, input_digest in (("", "input-a"), ("behavior-a", "")):
        with pytest.raises(ValueError, match="digest"):
            record_pytest_timing_history(
                tmp_path,
                behavior_digest,
                input_digest,
                {"tests/test_demo.py::test_one": 10.0},
            )

    valid_load = _current_load({"tests/test_demo.py::test_one": 10.0})
    for workers, threshold in ((0, 500.0), (-1, 500.0), (8, -1.0)):
        with pytest.raises(ValueError):
            _decision(
                ["tests/test_demo.py::test_one"],
                valid_load,
                workers=workers,
                threshold_ms=threshold,
            )


def test_duration_prediction_overflow_is_unknown() -> None:
    from maid_runner.core._pytest_parallelism import predict_pytest_duration_ms

    selected = ["tests/test_demo.py::test_one", "tests/test_demo.py::test_two"]
    history = _history(
        {
            "tests/test_demo.py::test_one": 1e308,
            "tests/test_demo.py::test_two": 1e308,
        }
    )

    assert (
        predict_pytest_duration_ms(selected_nodeids=selected, history=history) is None
    )
    decision = _decision(selected, _current_load(dict(history.durations_ms)))
    assert decision.use_workers is False
    assert decision.predicted_duration_ms is None
    assert decision.history_state == "partial"
    assert decision.reason == "serial:unknown-history"
