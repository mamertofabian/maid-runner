"""Behavioral contract for runtime-evidence subprocess environment parity."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys

import pytest


def _initialize_observed_project(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    tests = project / "tests"
    tests.mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = '-p no:cacheprovider'\n",
        encoding="utf-8",
    )
    (project / ".maidrc.yaml").write_text(
        "test_execution:\n"
        "  pytest_workers: 1\n"
        "  accepted_pytest_worker_counts: [2]\n"
        "  max_processes: 2\n",
        encoding="utf-8",
    )
    (project / "environment_observer.py").write_text(
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "import sys\n"
        "import time\n\n"
        "record = {\n"
        "    'snapshot_bound': os.environ.get('SNAPSHOT_BOUND'),\n"
        "    'git_dir': os.environ.get('GIT_DIR'),\n"
        "    'pytest_plugins': os.environ.get('PYTEST_PLUGINS'),\n"
        "    'xdist_worker': os.environ.get('PYTEST_XDIST_WORKER'),\n"
        "    'xdist_worker_count': os.environ.get('PYTEST_XDIST_WORKER_COUNT'),\n"
        "    'argv': sys.argv,\n"
        "}\n"
        "with Path(os.environ['OBSERVATION_PATH']).open('a', encoding='utf-8') as stream:\n"
        "    stream.write(json.dumps(record) + '\\n')\n"
        "time.sleep(0.1)\n",
        encoding="utf-8",
    )
    (project / "sitecustomize.py").write_text(
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "import sys\n\n"
        "output = os.environ.get('PROBE_OBSERVATION_PATH')\n"
        "if output:\n"
        "    record = {\n"
        "        'snapshot_bound': os.environ.get('SNAPSHOT_BOUND'),\n"
        "        'git_dir': os.environ.get('GIT_DIR'),\n"
        "        'pytest_plugins': os.environ.get('PYTEST_PLUGINS'),\n"
        "        'xdist_worker': os.environ.get('PYTEST_XDIST_WORKER'),\n"
        "        'xdist_worker_count': os.environ.get('PYTEST_XDIST_WORKER_COUNT'),\n"
        "        'argv': sys.argv,\n"
        "    }\n"
        "    with Path(output).open('a', encoding='utf-8') as stream:\n"
        "        stream.write(json.dumps(record) + '\\n')\n",
        encoding="utf-8",
    )
    for name in ("alpha", "beta"):
        (tests / f"test_{name}.py").write_text(
            f"def test_{name}():\n    assert True\n",
            encoding="utf-8",
        )
    monkeypatch.setenv("PYTEST_PLUGINS", "environment_observer")
    monkeypatch.setenv("PYTHONPATH", str(project))
    return tests


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_runtime_evidence_applies_snapshot_environment_to_preparation_and_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    project = tmp_path / "project"
    tests = _initialize_observed_project(project, monkeypatch)
    observations = project / "environment-observations.jsonl"
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "ambient-git-dir"))
    monkeypatch.setenv("OBSERVATION_PATH", str(observations))

    executor = SubprocessRuntimeCommandExecutor(
        environment_overrides={
            "SNAPSHOT_BOUND": "yes",
        },
        environment_removals=("GIT_DIR",),
    )
    result = executor.execute_with_contexts(
        (
            sys.executable,
            "-m",
            "pytest",
            "tests/test_alpha.py",
            "-q",
            "-n",
            "2",
        ),
        {str((tests / "test_alpha.py").resolve())},
        project,
        timeout_seconds=30,
        pytest_workers=2,
        logical_selectors=("tests/test_alpha.py",),
    )

    records = _records(observations)
    assert result.result.returncode == 0
    assert any("--collect-only" in record["argv"] for record in records)
    assert any("--version" in record["argv"] for record in records)
    assert any(
        "--collect-only" not in record["argv"] and "--version" not in record["argv"]
        for record in records
    )
    assert all(
        record["snapshot_bound"] == "yes" and record["git_dir"] is None
        for record in records
    )
    assert os.environ["GIT_DIR"] == str(tmp_path / "ambient-git-dir")


def test_runtime_evidence_environment_policies_do_not_bleed_between_concurrent_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    project = tmp_path / "project"
    tests = _initialize_observed_project(project, monkeypatch)
    ambient_observations = project / "ambient-observations.jsonl"
    monkeypatch.setenv("OBSERVATION_PATH", str(ambient_observations))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "ambient-git-dir"))

    def execute(name: str):
        observations = project / f"{name}-observations.jsonl"
        executor = SubprocessRuntimeCommandExecutor(
            environment_overrides={
                "OBSERVATION_PATH": str(observations),
                "SNAPSHOT_BOUND": name,
            },
            environment_removals=("GIT_DIR",),
        )
        result = executor.execute_with_contexts(
            (sys.executable, "-m", "pytest", f"tests/test_{name}.py", "-q"),
            {str((tests / f"test_{name}.py").resolve())},
            project,
            timeout_seconds=30,
            pytest_workers=1,
        )
        return result, observations

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {name: pool.submit(execute, name) for name in ("alpha", "beta")}
        results = {name: future.result() for name, future in futures.items()}

    for name, (result, observations) in results.items():
        records = _records(observations)
        assert result.result.returncode == 0
        assert len(records) >= 2
        assert all(
            record["snapshot_bound"] == name and record["git_dir"] is None
            for record in records
        )
    assert not ambient_observations.exists()
    assert os.environ["GIT_DIR"] == str(tmp_path / "ambient-git-dir")


def test_runtime_evidence_removals_and_pytest_sanitization_apply_to_every_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    project = tmp_path / "project"
    tests = _initialize_observed_project(project, monkeypatch)
    observations = project / "sanitized-observations.jsonl"
    monkeypatch.setenv("PYTEST_PLUGINS", "nonexistent_ambient_plugin")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "ambient-worker")
    monkeypatch.setenv("PYTEST_XDIST_WORKER_COUNT", "99")

    executor = SubprocessRuntimeCommandExecutor(
        environment_overrides={
            "PROBE_OBSERVATION_PATH": str(observations),
            "PYTHONPATH": str(project),
            "SNAPSHOT_BOUND": "sanitized",
        },
        environment_removals=("PYTEST_PLUGINS",),
    )
    result = executor.execute_with_contexts(
        (
            sys.executable,
            "-m",
            "pytest",
            "tests/test_alpha.py",
            "-q",
            "-n",
            "2",
        ),
        {str((tests / "test_alpha.py").resolve())},
        project,
        timeout_seconds=30,
        pytest_workers=2,
        logical_selectors=("tests/test_alpha.py",),
    )

    records = _records(observations)
    preparation_records = [
        record
        for record in records
        if "--collect-only" in record["argv"] or "--version" in record["argv"]
    ]
    assert result.result.returncode == 0, result.result.stderr
    assert any("--collect-only" in record["argv"] for record in records)
    assert any("--version" in record["argv"] for record in records)
    assert all(
        record["snapshot_bound"] == "sanitized"
        and "nonexistent_ambient_plugin"
        not in (record["pytest_plugins"] or "").split(",")
        and record["xdist_worker"] != "ambient-worker"
        and record["xdist_worker_count"] != "99"
        for record in records
    )
    assert all(
        record["xdist_worker"] is None and record["xdist_worker_count"] is None
        for record in preparation_records
    )

    (project / ".maidrc.yaml").write_text(
        "test_execution:\n  pytest_workers: 1\n  max_processes: 2\n",
        encoding="utf-8",
    )
    serial_observations = project / "serial-sanitized-observations.jsonl"
    serial_executor = SubprocessRuntimeCommandExecutor(
        environment_overrides={
            "PROBE_OBSERVATION_PATH": str(serial_observations),
            "PYTHONPATH": str(project),
            "SNAPSHOT_BOUND": "serial-sanitized",
        },
        environment_removals=("PYTEST_PLUGINS",),
    )
    serial_result = serial_executor.execute_with_contexts(
        (sys.executable, "-m", "pytest", "tests/test_alpha.py", "-q"),
        {str((tests / "test_alpha.py").resolve())},
        project,
        timeout_seconds=30,
        pytest_workers=None,
        logical_selectors=("tests/test_alpha.py",),
    )

    serial_records = _records(serial_observations)
    assert serial_result.result.returncode == 0, serial_result.result.stderr
    assert all(
        "nonexistent_ambient_plugin" not in (record["pytest_plugins"] or "").split(",")
        for record in serial_records
    )


def test_runtime_evidence_identity_probe_uses_executor_environment_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )
    from maid_runner.core.manifest import load_manifest
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    project = tmp_path / "project"
    tests = _initialize_observed_project(project, monkeypatch)
    source = project / "src"
    source.mkdir()
    (source / "target.py").write_text(
        "def target():\n    return True\n",
        encoding="utf-8",
    )
    (tests / "test_alpha.py").write_text(
        "from src.target import target\n\n"
        "def test_alpha():\n"
        "    assert target() is True\n",
        encoding="utf-8",
    )
    manifest_path = project / "manifests" / "probe.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        'schema: "2"\n'
        'goal: "Exercise runtime identity policy"\n'
        "type: fix\n"
        'created: "2026-08-20T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/target.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: target\n"
        "          args: []\n"
        "          returns: bool\n"
        "  read:\n"
        "    - tests/test_alpha.py\n"
        "validate:\n"
        "  - python -m pytest -q tests/test_alpha.py\n",
        encoding="utf-8",
    )
    ambient_observations = project / "ambient-probes.jsonl"
    explicit_observations = project / "explicit-probes.jsonl"
    monkeypatch.setenv(
        "OBSERVATION_PATH",
        str(project / "pytest-observations.jsonl"),
    )
    monkeypatch.setenv("PROBE_OBSERVATION_PATH", str(ambient_observations))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "ambient-git-dir"))

    executor = SubprocessRuntimeCommandExecutor(
        environment_overrides={
            "PROBE_OBSERVATION_PATH": str(explicit_observations),
            "PYTHONPATH": str(project),
            "SNAPSHOT_BOUND": "identity",
        },
        environment_removals=("GIT_DIR",),
    )
    run = collect_runtime_evidence(
        [load_manifest(manifest_path)],
        project,
        executor=executor,
    )
    collection_records = _records(explicit_observations)
    collection_probe_count = sum(
        record["argv"] == ["-c"] for record in collection_records
    )
    evaluation = evaluate_artifact_coverage_from_evidence(
        [load_manifest(manifest_path)],
        project,
        run.evidence,
        fallback_executor=executor,
    )

    records = _records(explicit_observations)
    evaluation_probe_count = sum(record["argv"] == ["-c"] for record in records)
    assert run.test_result.failed == 0, run.test_result.results[0].stderr
    assert evaluation.complete is True
    assert evaluation.fallback_identities == ()
    assert collection_probe_count == 1
    assert evaluation_probe_count == collection_probe_count + 1
    assert all(
        record["snapshot_bound"] == "identity" and record["git_dir"] is None
        for record in records
    )
    assert not ambient_observations.exists()
