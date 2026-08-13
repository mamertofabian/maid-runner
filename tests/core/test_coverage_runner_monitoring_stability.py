"""Behavioral contract: the coverage runner survives swapped sys.monitoring.

Contract: manifests/drafts/121-26-bind-coverage-runner-monitoring-disable.manifest.yaml

The artifact-coverage runner registers a sys.monitoring PY_START callback to
record which declared artifacts execute. A test in the instrumented suite may
legitimately monkeypatch ``sys.monitoring`` (for example
``tests/core/test_runtime_evidence.py`` swaps it for a stub without
``DISABLE``). If the callback re-reads ``sys.monitoring.DISABLE`` at call time,
that swap makes the callback raise ``AttributeError`` -> unraisable exception
-> a failed pytest session (E900) with empty execution data, which fabricates
E710 coverage gaps for every artifact the command should have proven. The
runner must bind the real ``DISABLE`` sentinel once at registration so a
consumer swapping ``sys.monitoring`` mid-run cannot corrupt coverage evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.artifact_coverage import coverage_is_available


@pytest.mark.skipif(
    not coverage_is_available(), reason="coverage.py is required for this behavior"
)
def test_swapped_monitoring_midrun_does_not_corrupt_coverage_evidence(
    tmp_path: Path,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    project = tmp_path / "project"
    project.mkdir()
    target = project / "target_module.py"
    target.write_text("def probed_call() -> str:\n    return 'probed'\n")
    # The stub mirrors tests/core/test_runtime_evidence.py: a full events
    # namespace (so coverage.py's own sysmon core stays happy) but no DISABLE,
    # which is exactly what breaks a runner that re-reads sys.monitoring.DISABLE
    # inside its callback.
    (project / "test_target_module.py").write_text(
        "import sys\n"
        "from types import SimpleNamespace\n"
        "from target_module import probed_call\n\n"
        "_EVENTS = SimpleNamespace(\n"
        "    PY_START=1, PY_RETURN=2, PY_RESUME=4, PY_YIELD=8,\n"
        "    PY_UNWIND=16, LINE=32,\n"
        ")\n\n\n"
        "def test_probe_runs_while_monitoring_is_swapped():\n"
        "    original = getattr(sys, 'monitoring', None)\n"
        "    sys.monitoring = SimpleNamespace(events=_EVENTS, PROFILER_ID=0)\n"
        "    try:\n"
        "        assert probed_call() == 'probed'\n"
        "    finally:\n"
        "        sys.monitoring = original\n"
    )

    record = SubprocessRuntimeCommandExecutor().execute(
        (
            "-p",
            "no:cacheprovider",
            "-W",
            "error::pytest.PytestUnraisableExceptionWarning",
            "test_target_module.py",
        ),
        {str(target.resolve())},
        project,
        120.0,
    )

    assert record.returncode == 0, (
        "coverage runner failed under swapped sys.monitoring:\n"
        f"{record.stdout}\n{record.stderr}"
    )
    assert not record.report_errors
    assert str(target.resolve()) in record.execution_data
    executed = record.execution_data[str(target.resolve())]
    assert "probed_call" in executed.called_qualnames
