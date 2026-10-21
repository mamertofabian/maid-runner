"""Public execution contracts for optional pytest-xdist instrumentation hooks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from maid_runner.core._runtime_command_executor import SubprocessRuntimeCommandExecutor
from maid_runner.core.manifest import load_manifest
from maid_runner.core.runtime_evidence import collect_runtime_evidence


def _project(root: Path, workers: int) -> Path:
    (root / ".maidrc.yaml").write_text("test_execution:\n  max_processes: 4\n")
    (root / "tests").mkdir()
    source = root / "calc.py"
    source.write_text("def compute():\n    return 7\n")
    (root / "tests/test_calc.py").write_text(
        "from calc import compute\n\n"
        "def test_compute(request):\n"
        "    plugins = request.config.pluginmanager\n"
        f"    assert bool(plugins.hasplugin('xdist') or plugins.hasplugin('xdist.plugin')) is {workers > 1}\n"
        "    assert compute() == 7\n\n"
        "def test_second():\n"
        "    assert compute() == 7\n"
    )
    return source


def _executor(*, disable_autoload: bool = True) -> SubprocessRuntimeCommandExecutor:
    return SubprocessRuntimeCommandExecutor(
        environment_overrides=(
            {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"} if disable_autoload else {}
        ),
        environment_removals=(
            "PYTEST_PLUGINS",
            "PYTEST_ADDOPTS",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
        ),
    )


def _worker_options(workers: int) -> tuple[str, ...]:
    if workers == 1:
        return ()
    pytest.importorskip("xdist")
    return ("-p", "xdist.plugin", "-n", str(workers))


@pytest.mark.parametrize("workers", [1, 2])
def test_public_runtime_evidence_preserves_serial_and_worker_execution(
    tmp_path: Path, workers: int
) -> None:
    source = _project(tmp_path, workers)
    _worker_options(workers)
    options = () if workers == 1 else ("-n", str(workers))
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    path = manifests / "calc.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Observe actual optional-worker execution",
                "type": "fix",
                "created": "2026-10-21T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": "calc.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "compute",
                                    "args": [],
                                    "returns": "int",
                                }
                            ],
                        }
                    ],
                    "read": ["tests/test_calc.py"],
                },
                "validate": [
                    ["python", "-m", "pytest", "tests/test_calc.py", "-q", *options]
                ],
            },
            sort_keys=False,
        )
    )

    run = collect_runtime_evidence(
        [load_manifest(path)],
        tmp_path,
        executor=_executor(disable_autoload=workers == 1),
        pytest_workers=workers,
    )

    assert len(run.evidence.commands) == 1
    command = run.evidence.commands[0]
    assert command.result.returncode == 0, command.result.stdout + command.result.stderr
    assert run.test_result.passed == 1
    assert command.completeness.complete, command.completeness
    assert run.evidence.completeness.complete, run.evidence.completeness
    assert set(command.selected_nodeids) == {
        "tests/test_calc.py::test_compute",
        "tests/test_calc.py::test_second",
    }
    observed = [
        execution
        for context in command.contexts
        for target, execution in context.execution_data.items()
        if Path(target) == source
    ]
    assert observed
    assert any("compute" in execution.called_qualnames for execution in observed)
    assert any(2 in execution.executed_lines for execution in observed)


@pytest.mark.parametrize("workers", [1, 2])
def test_public_timing_instrumentation_preserves_exact_serial_and_worker_nodes(
    tmp_path: Path, workers: int
) -> None:
    source = _project(tmp_path, workers)
    timing = tmp_path / "timing.json"
    collection = tmp_path / "collection.json"

    result = _executor().execute(
        (
            "tests/test_calc.py",
            "-q",
            "-p",
            "maid_runner.core._pytest_timing_plugin",
            "--maid-timing-output",
            str(timing),
            "--maid-collection-output",
            str(collection),
            *_worker_options(workers),
        ),
        {str(source)},
        tmp_path,
        timeout_seconds=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected = {"tests/test_calc.py::test_compute", "tests/test_calc.py::test_second"}
    assert set(json.loads(collection.read_text())["nodeids"]) == expected
    durations = json.loads(timing.read_text())["durations_ms"]
    assert set(durations) == expected
    assert all(
        isinstance(value, (int, float)) and value >= 0 for value in durations.values()
    )
    execution = result.execution_data[str(source)]
    assert "compute" in execution.called_qualnames
    assert 2 in execution.executed_lines
    assert not result.report_errors


def test_public_worker_coverage_allows_controller_serial_pytest_child(
    tmp_path: Path,
) -> None:
    source = _project(tmp_path, workers=2)
    (tmp_path / "inner").mkdir()
    (tmp_path / "inner/test_inner.py").write_text(
        "from pathlib import Path\n\n"
        "def test_inner(request):\n"
        "    plugins = request.config.pluginmanager\n"
        "    assert not (plugins.hasplugin('xdist') or plugins.hasplugin('xdist.plugin'))\n"
        "    Path(__file__).with_name('ran.txt').write_text('actual serial test')\n"
    )
    (tmp_path / "conftest.py").write_text(
        "import subprocess\nimport sys\n\n"
        "def pytest_sessionstart(session):\n"
        "    if session.config.pluginmanager.hasplugin('xdist.plugin') and not hasattr(session.config, 'workerinput'):\n"
        "        result = subprocess.run([sys.executable, '-m', 'pytest', 'inner/test_inner.py', '-q'], capture_output=True, text=True, timeout=30)\n"
        "        assert result.returncode == 0, result.stdout + result.stderr\n"
    )

    result = _executor().execute(
        ("tests/test_calc.py", "-q", *_worker_options(2)),
        {str(source)},
        tmp_path,
        timeout_seconds=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "inner/ran.txt").read_text() == "actual serial test"
    execution = result.execution_data[str(source)]
    assert "compute" in execution.called_qualnames
    assert 2 in execution.executed_lines
    assert not result.report_errors
