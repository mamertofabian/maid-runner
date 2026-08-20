"""Standalone pytest plugin for exact collection and timing evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Sequence

import pytest


class PytestTimingPlugin:
    """Collect controller-side node durations only when evidence is complete."""

    def __init__(
        self,
        output_path: Path,
        *,
        expected_nodeids: Sequence[str] = (),
        collection_output_path: Path | None = None,
        timing_enabled: bool = True,
    ) -> None:
        self.output_path = Path(output_path)
        self.durations_ms: dict[str, float] = {}
        self.incomplete_workers: set[str] = set()
        self.selected_nodeids: set[str] = set(expected_nodeids)
        self.completed_nodeids: set[str] = set()
        self._expected_nodeids = tuple(expected_nodeids)
        self._collection_output_path = collection_output_path
        self._timing_enabled = timing_enabled
        self._invalid_evidence = len(self.selected_nodeids) != len(
            self._expected_nodeids
        )
        self._worker_collections: dict[str, tuple[str, ...]] = {}

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        """Capture serial collection without replacing controller xdist evidence."""
        collected = tuple(item.nodeid for item in getattr(session, "items", ()))
        if not collected:
            return
        if len(set(collected)) != len(collected):
            self._invalid_evidence = True
            return
        collected_set = set(collected)
        if self._expected_nodeids and collected_set != set(self._expected_nodeids):
            self._invalid_evidence = True
            return
        self.selected_nodeids = collected_set

    def pytest_xdist_node_collection_finished(
        self,
        node: object,
        ids: Sequence[str],
    ) -> None:
        """Require every xdist worker to report the same unique collection."""
        worker = _worker_id(node)
        collection = tuple(ids)
        if len(set(collection)) != len(collection):
            self._invalid_evidence = True
            return
        self._worker_collections[worker] = collection
        first = next(iter(self._worker_collections.values()))
        if any(
            set(candidate) != set(first)
            for candidate in self._worker_collections.values()
        ):
            self._invalid_evidence = True
            return
        collection_set = set(collection)
        if self._expected_nodeids and collection_set != set(self._expected_nodeids):
            self._invalid_evidence = True
            return
        self.selected_nodeids = collection_set

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Record normal calls and setup-skipped nodes as completed evidence."""
        phase = getattr(report, "when", None)
        if phase not in {"setup", "call"}:
            return
        nodeid = str(report.nodeid)
        duration_ms = float(report.duration) * 1000.0
        if duration_ms < 0:
            self._invalid_evidence = True
            return
        self.durations_ms[nodeid] = self.durations_ms.get(nodeid, 0.0) + duration_ms
        terminal = phase == "call" or (
            phase == "setup" and bool(getattr(report, "skipped", False))
        )
        if not terminal:
            return
        if nodeid in self.completed_nodeids:
            self._invalid_evidence = True
            return
        self.completed_nodeids.add(nodeid)

    def pytest_testnodedown(self, node: object, error: object | None) -> None:
        """Mark only abnormal worker shutdown as incomplete evidence."""
        if error is not None:
            self.incomplete_workers.add(_worker_id(node))

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Atomically write exact collection/timing evidence or write nothing."""
        if self._collection_output_path is not None:
            if exitstatus in {0, 5} and not self._invalid_evidence:
                _atomic_write_json(
                    self._collection_output_path,
                    {"nodeids": sorted(self.selected_nodeids)},
                )

        if not self._timing_enabled:
            return
        if exitstatus != 0 or self.incomplete_workers or self._invalid_evidence:
            return
        if not self.selected_nodeids:
            return
        if self.selected_nodeids != self.completed_nodeids:
            return
        if set(self.durations_ms) != self.selected_nodeids:
            return
        _atomic_write_json(
            self.output_path,
            {"durations_ms": dict(sorted(self.durations_ms.items()))},
        )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register explicit options while also supporting child-only environment."""
    group = parser.getgroup("maid-timing")
    group.addoption("--maid-timing-output", default=None)
    group.addoption("--maid-selected-nodeids-file", default=None)
    group.addoption("--maid-collection-output", default=None)


def pytest_configure(config: pytest.Config) -> None:
    """Register the evidence plugin only for an explicitly instrumented child."""
    timing_value = config.getoption("--maid-timing-output") or os.environ.get(
        "MAID_TIMING_OUTPUT"
    )
    selected_value = config.getoption("--maid-selected-nodeids-file") or os.environ.get(
        "MAID_SELECTED_NODEIDS_FILE"
    )
    collection_value = config.getoption("--maid-collection-output") or os.environ.get(
        "MAID_COLLECTION_OUTPUT"
    )
    if timing_value is None and collection_value is None:
        return
    for name in (
        "MAID_TIMING_OUTPUT",
        "MAID_SELECTED_NODEIDS_FILE",
        "MAID_COLLECTION_OUTPUT",
    ):
        os.environ.pop(name, None)
    plugins = os.environ.get("PYTEST_PLUGINS")
    if plugins:
        retained = [
            plugin.strip()
            for plugin in plugins.split(",")
            if plugin.strip() and plugin.strip() != "_maid_pytest_timing_plugin"
        ]
        if retained:
            os.environ["PYTEST_PLUGINS"] = ",".join(retained)
        else:
            os.environ.pop("PYTEST_PLUGINS", None)

    expected: tuple[str, ...] = ()
    if selected_value:
        payload = json.loads(Path(selected_value).read_text(encoding="utf-8"))
        if not isinstance(payload, list) or not all(
            isinstance(item, str) and item for item in payload
        ):
            raise pytest.UsageError("MAID selected node evidence is malformed")
        if len(set(payload)) != len(payload):
            raise pytest.UsageError("MAID selected node evidence contains duplicates")
        expected = tuple(payload)

    output_path = Path(timing_value or collection_value)
    plugin = PytestTimingPlugin(
        output_path,
        expected_nodeids=expected,
        collection_output_path=(
            Path(collection_value) if collection_value is not None else None
        ),
        timing_enabled=timing_value is not None,
    )
    config.pluginmanager.register(plugin, "maid-timing-plugin")


def _worker_id(node: object) -> str:
    gateway = getattr(node, "gateway", None)
    return str(getattr(gateway, "id", getattr(node, "workerid", "unknown")))


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
