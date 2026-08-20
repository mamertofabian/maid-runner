"""Behavioral contract for the external serial/xdist equivalence probe."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import FrozenInstanceError
from importlib.metadata import version
from pathlib import Path
from platform import python_implementation, python_version

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_project(tmp_path: Path, files: dict[str, str]) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = ['-ra']\n",
        encoding="utf-8",
    )
    for relative_path, source in files.items():
        path = project_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return project_root


def _equivalent_project(tmp_path: Path) -> Path:
    return _write_project(
        tmp_path,
        {
            "tests/test_alpha.py": (
                "import pytest\n\n"
                "@pytest.fixture\n"
                "def token():\n"
                "    yield 'ready'\n\n"
                "def test_alpha(token):\n"
                "    assert token == 'ready'\n"
            ),
            "tests/test_beta.py": (
                "class TestBeta:\n"
                "    def test_one(self):\n"
                "        assert 1 + 1 == 2\n\n"
                "    def test_two(self):\n"
                "        assert sorted([2, 1]) == [1, 2]\n"
            ),
        },
    )


def test_probe_accepts_equivalent_serial_and_loadscope_outcomes(
    tmp_path: Path,
) -> None:
    from tools.check_pytest_parallel_equivalence import (
        CanonicalPytestOutcome,
        PytestEquivalenceReport,
        run_pytest_equivalence_probe,
    )

    project_root = _equivalent_project(tmp_path)

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert isinstance(report, PytestEquivalenceReport)
    assert report.success is True
    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.serial_outcomes == report.parallel_outcomes
    assert all(
        isinstance(outcome, CanonicalPytestOutcome)
        for outcome in report.serial_outcomes
    )
    assert all(outcome.nodeid for outcome in report.serial_outcomes)
    assert {outcome.phase for outcome in report.serial_outcomes} == {
        "collection",
        "setup",
        "call",
        "teardown",
    }


def test_canonical_pytest_outcome_is_immutable() -> None:
    from tools.check_pytest_parallel_equivalence import CanonicalPytestOutcome

    outcome = CanonicalPytestOutcome(
        nodeid="tests/test_alpha.py::test_alpha",
        phase="call",
        outcome="passed",
    )

    with pytest.raises(FrozenInstanceError):
        setattr(outcome, "outcome", "failed")


def test_probe_rejects_process_order_state_leak(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "shared_state.py": "ready = False\n",
            "tests/test_a_seed.py": (
                "import shared_state\n\n"
                "def test_seed_process_state():\n"
                "    shared_state.ready = True\n"
            ),
            "tests/test_b_consumer.py": (
                "import shared_state\n\n"
                "def test_requires_seed_from_prior_module():\n"
                "    assert shared_state.ready is True\n"
            ),
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code != 0
    assert report.success is False
    assert any(
        "parallel pytest exited" in difference for difference in report.differences
    )


def test_probe_rejects_worker_collection_difference(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_collection.py": (
                "import os\n\n"
                "def test_common_node():\n"
                "    assert True\n\n"
                "if os.environ.get('PYTEST_XDIST_WORKER') != 'gw1':\n"
                "    def test_worker_specific_node():\n"
                "        assert True\n"
            )
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.parallel_exit_code != 0
    assert report.success is False
    assert any("worker collections differ" in item for item in report.differences)
    worker_collections = dict(report.parallel_worker_collections)
    assert set(worker_collections) == {"gw0", "gw1"}
    assert worker_collections["gw0"] != worker_collections["gw1"]


def test_probe_uses_requested_worker_count_and_dist_mode(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_scheduler.py": (
                "import os\n\n"
                "def test_parallel_scheduler_contract(request):\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        assert os.environ['PYTEST_XDIST_WORKER_COUNT'] == '3'\n"
                "        assert request.config.getoption('dist') == 'loadfile'\n"
            )
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=3,
        dist_mode="loadfile",
    )

    assert report.success is True
    assert report.workers == 3
    assert report.dist_mode == "loadfile"
    assert {worker_id for worker_id, _ in report.parallel_worker_collections} == {
        "gw0",
        "gw1",
        "gw2",
    }


def test_probe_rejects_phase_outcome_difference(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_phase.py": (
                "import os\n"
                "import pytest\n\n"
                "def test_phase_outcome():\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        pytest.skip('worker-only call outcome difference')\n"
                "    assert True\n"
            )
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.serial_outcomes != report.parallel_outcomes
    assert {(outcome.nodeid, outcome.phase) for outcome in report.serial_outcomes} == {
        (outcome.nodeid, outcome.phase) for outcome in report.parallel_outcomes
    }
    assert report.success is False
    assert any("phase outcomes differ" in item for item in report.differences)


def test_probe_rejects_matching_nonzero_serial_and_parallel_runs(
    tmp_path: Path,
) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {"tests/test_broken.py": "def test_broken():\n    assert False\n"},
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code != 0
    assert report.parallel_exit_code != 0
    assert report.serial_outcomes == report.parallel_outcomes
    assert report.success is False
    assert any("serial pytest exited" in item for item in report.differences)
    assert any("parallel pytest exited" in item for item in report.differences)


@pytest.mark.parametrize(
    ("project_root_arg", "target"),
    [
        (str(REPO_ROOT), "."),
        (str(REPO_ROOT), "tests"),
        (str(REPO_ROOT), str(REPO_ROOT / "tests")),
        (".", "tests/"),
    ],
)
def test_probe_never_recursively_selects_its_own_repository_run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    project_root_arg: str,
    target: str,
) -> None:
    from tools.check_pytest_parallel_equivalence import main

    monkeypatch.setenv(
        "PYTEST_CURRENT_TEST",
        "tests/performance/test_pytest_parallel_equivalence_probe.py::"
        "test_probe_never_recursively_selects_its_own_repository_run (call)",
    )

    exit_code = main(
        [
            "--project-root",
            project_root_arg,
            "--workers",
            "2",
            "--dist",
            "loadscope",
            target,
        ]
    )

    assert exit_code == 2
    assert "recursive pytest equivalence probe" in capsys.readouterr().err


def test_public_probe_never_recursively_selects_its_own_repository_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess as subprocess_module

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    monkeypatch.setenv(
        "PYTEST_CURRENT_TEST",
        "tests/performance/test_pytest_parallel_equivalence_probe.py::"
        "test_public_probe_never_recursively_selects_its_own_repository_run (call)",
    )

    def fail_if_subprocess_starts(*args: object, **kwargs: object) -> None:
        pytest.fail("recursive probe started a pytest subprocess")

    monkeypatch.setattr(subprocess_module, "run", fail_if_subprocess_starts)

    with pytest.raises(RuntimeError, match="recursive pytest equivalence probe"):
        run_pytest_equivalence_probe(
            REPO_ROOT,
            ["tests"],
            workers=2,
            dist_mode="loadscope",
        )


@pytest.mark.parametrize(
    "targets",
    [
        ["--pyargs", "tests.performance.test_pytest_parallel_equivalence_probe"],
        ["@pytest-targets.txt"],
    ],
)
def test_public_probe_rejects_pytest_option_arguments(
    monkeypatch: pytest.MonkeyPatch,
    targets: list[str],
) -> None:
    import subprocess as subprocess_module

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    def fail_if_subprocess_starts(*args: object, **kwargs: object) -> None:
        pytest.fail("option selector started a pytest subprocess")

    monkeypatch.setattr(subprocess_module, "run", fail_if_subprocess_starts)

    with pytest.raises(ValueError, match="path or node selectors"):
        run_pytest_equivalence_probe(
            REPO_ROOT,
            targets,
            workers=2,
            dist_mode="loadscope",
        )


def test_public_probe_refuses_collection_time_recursion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess as subprocess_module

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    def fail_if_subprocess_starts(*args: object, **kwargs: object) -> None:
        pytest.fail("collection-time recursion started a pytest subprocess")

    monkeypatch.setattr(subprocess_module, "run", fail_if_subprocess_starts)

    with pytest.raises(RuntimeError, match="recursive pytest equivalence probe"):
        run_pytest_equivalence_probe(
            REPO_ROOT,
            ["tests"],
            workers=2,
            dist_mode="loadscope",
        )


def test_probe_rejects_serial_project_state_contamination(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "state.txt": "initial project bytes\n",
            "tests/test_persistent_state.py": (
                "import os\n"
                "from pathlib import Path\n\n"
                "STATE = Path(__file__).parents[1] / 'state.txt'\n\n"
                "def test_persistent_state_cannot_mask_dependency():\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        assert STATE.read_text() == 'serial changed bytes'\n"
                "    else:\n"
                "        STATE.write_text('serial changed bytes')\n"
            ),
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code != 0
    assert report.success is False
    assert any("parallel pytest exited" in item for item in report.differences)
    assert (project_root / "state.txt").read_text() == "initial project bytes\n"


def test_probe_isolates_parallel_project_state_from_source_tree(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_parallel_state.py": (
                "import os\n"
                "from pathlib import Path\n\n"
                "MARKER = Path(__file__).parents[1] / 'parallel-created.marker'\n\n"
                "def test_parallel_run_must_not_persist_project_state():\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        MARKER.write_text('parallel touched project state')\n"
                "    assert True\n"
            )
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.success is True
    assert not (project_root / "parallel-created.marker").exists()


def test_probe_rejects_empty_directory_state_contamination(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_empty_directory_state.py": (
                "import os\n"
                "from pathlib import Path\n\n"
                "STATE_DIR = Path(__file__).parents[1] / 'serial-empty-dir'\n\n"
                "def test_empty_directory_cannot_persist_between_runs():\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        assert STATE_DIR.is_dir()\n"
                "    else:\n"
                "        STATE_DIR.mkdir()\n"
            )
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code != 0
    assert report.success is False
    assert any("parallel pytest exited" in item for item in report.differences)
    assert not (project_root / "serial-empty-dir").exists()


def test_probe_rejects_file_mode_state_contamination(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "state.txt": "stable bytes\n",
            "tests/test_file_mode_state.py": (
                "import os\n"
                "import stat\n"
                "from pathlib import Path\n\n"
                "STATE = Path(__file__).parents[1] / 'state.txt'\n\n"
                "def test_file_mode_cannot_persist_between_runs():\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        assert stat.S_IMODE(STATE.stat().st_mode) == 0o600\n"
                "    else:\n"
                "        STATE.chmod(0o600)\n"
            ),
        },
    )
    initial_mode = (project_root / "state.txt").stat().st_mode

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code != 0
    assert report.success is False
    assert any("parallel pytest exited" in item for item in report.differences)
    assert (project_root / "state.txt").stat().st_mode == initial_mode


def test_probe_rejects_pytest_cache_state_contamination(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_excluded_state.py": (
                "import os\n"
                "from pathlib import Path\n\n"
                "STATE = Path(__file__).parents[1] / '.pytest_cache' / 'serial-state'\n\n"
                "def test_excluded_path_cannot_persist_between_runs():\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        assert STATE.read_text() == 'serial state'\n"
                "    else:\n"
                "        STATE.parent.mkdir(exist_ok=True)\n"
                "        STATE.write_text('serial state')\n"
            )
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code != 0
    assert report.success is False
    assert any("parallel pytest exited" in item for item in report.differences)
    assert not (project_root / ".pytest_cache" / "serial-state").exists()


def test_probe_detects_source_worktree_escape(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(tmp_path, {})
    source_state = project_root / "source-state.txt"
    source_state.write_text("initial source bytes", encoding="utf-8")
    test_path = project_root / "tests" / "test_source_escape.py"
    test_path.parent.mkdir()
    test_path.write_text(
        "from pathlib import Path\n\n"
        f"SOURCE_STATE = Path({str(source_state)!r})\n\n"
        "def test_absolute_source_escape():\n"
        "    SOURCE_STATE.write_text('escaped snapshot')\n",
        encoding="utf-8",
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.serial_outcomes == report.parallel_outcomes
    assert report.success is False
    assert any(
        "pytest changed source project state" in item for item in report.differences
    )


def test_probe_detects_source_git_control_escape(tmp_path: Path) -> None:
    project_root = _equivalent_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    test_path = project_root / "tests" / "test_git_escape.py"
    test_path.write_text(
        "import subprocess\n\n"
        f"SOURCE_ROOT = {str(project_root)!r}\n\n"
        "def test_absolute_git_control_escape():\n"
        "    subprocess.run(\n"
        "        ['git', 'config', '--local', 'snapshot.escape', 'yes'],\n"
        "        cwd=SOURCE_ROOT, check=True,\n"
        "    )\n",
        encoding="utf-8",
    )

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.success is False
    assert any("@git" in item for item in report.differences)


def test_probe_detects_source_git_fetch_head_state_channel(tmp_path: Path) -> None:
    project_root = _equivalent_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    source_fetch_head = project_root / ".git" / "FETCH_HEAD"
    test_path = project_root / "tests" / "test_git_fetch_head_escape.py"
    test_path.write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        f"SOURCE_FETCH_HEAD = Path({str(source_fetch_head)!r})\n\n"
        "def test_absolute_git_fetch_head_channel():\n"
        "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
        "        assert SOURCE_FETCH_HEAD.read_text() == 'serial state'\n"
        "    else:\n"
        "        SOURCE_FETCH_HEAD.write_text('serial state')\n",
        encoding="utf-8",
    )

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.serial_outcomes == report.parallel_outcomes
    assert report.success is False
    assert any("@git" in item for item in report.differences)


def test_probe_detects_empty_source_git_directory_state_channel(
    tmp_path: Path,
) -> None:
    project_root = _equivalent_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    source_state_dir = project_root / ".git" / "serial-empty-state"
    test_path = project_root / "tests" / "test_git_directory_escape.py"
    test_path.write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        f"SOURCE_STATE_DIR = Path({str(source_state_dir)!r})\n\n"
        "def test_absolute_git_directory_channel():\n"
        "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
        "        assert SOURCE_STATE_DIR.is_dir()\n"
        "    else:\n"
        "        SOURCE_STATE_DIR.mkdir()\n",
        encoding="utf-8",
    )

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.serial_outcomes == report.parallel_outcomes
    assert report.success is False
    assert any("@git" in item for item in report.differences)


def test_probe_detects_source_git_directory_mode_state_channel(
    tmp_path: Path,
) -> None:
    project_root = _equivalent_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    source_objects = project_root / ".git" / "objects"
    source_objects.chmod(0o755)
    test_path = project_root / "tests" / "test_git_mode_escape.py"
    test_path.write_text(
        "import os\n"
        "import stat\n"
        "from pathlib import Path\n\n"
        f"SOURCE_OBJECTS = Path({str(source_objects)!r})\n\n"
        "def test_absolute_git_directory_mode_channel():\n"
        "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
        "        assert stat.S_IMODE(SOURCE_OBJECTS.stat().st_mode) == 0o700\n"
        "    else:\n"
        "        SOURCE_OBJECTS.chmod(0o700)\n",
        encoding="utf-8",
    )

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.serial_outcomes == report.parallel_outcomes
    assert report.success is False
    assert any("@git" in item for item in report.differences)


def test_probe_maps_inside_root_absolute_targets_into_snapshots(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_absolute_target.py": (
                "from pathlib import Path\n\n"
                "def test_absolute_target_runs_in_snapshot():\n"
                "    marker = Path(__file__).parents[1] / 'snapshot.marker'\n"
                "    marker.write_text('snapshot only')\n"
            )
        },
    )
    absolute_node = (
        f"{project_root / 'tests' / 'test_absolute_target.py'}::"
        "test_absolute_target_runs_in_snapshot"
    )

    report = run_pytest_equivalence_probe(
        project_root,
        [absolute_node],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.success is True
    assert not (project_root / "snapshot.marker").exists()
    assert any(
        outcome.nodeid.endswith(
            "tests/test_absolute_target.py::test_absolute_target_runs_in_snapshot"
        )
        for outcome in report.serial_outcomes
    )


@pytest.mark.parametrize("target_kind", ["parent", "inside_parent", "absolute"])
def test_probe_rejects_outside_root_and_parent_targets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target_kind: str,
) -> None:
    import subprocess as subprocess_module

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _equivalent_project(tmp_path)
    targets = {
        "parent": "../outside.py",
        "inside_parent": "tests/../tests/test_alpha.py",
        "absolute": str(tmp_path / "outside.py"),
    }
    target = targets[target_kind]

    def fail_if_subprocess_starts(*args: object, **kwargs: object) -> None:
        pytest.fail("unsafe target started a pytest subprocess")

    monkeypatch.setattr(subprocess_module, "run", fail_if_subprocess_starts)

    with pytest.raises(ValueError, match="inside project root|parent segments"):
        run_pytest_equivalence_probe(
            project_root,
            [target],
            workers=2,
            dist_mode="loadscope",
        )


@pytest.mark.parametrize(
    ("target", "absolute"),
    [
        (".pytest_cache/test_hidden.py", False),
        (".pytest_cache/test_hidden.py", True),
        (".ruff_cache/test_hidden.py", False),
        (".mypy_cache/test_hidden.py", False),
        (".claude-automation/uv-cache/test_hidden.py", False),
        (".codex-automation/runs/test_hidden.py", False),
        ("tests/__pycache__/test_hidden.py", False),
        ("maid_runner.egg-info/PKG-INFO", False),
    ],
)
def test_probe_rejects_targets_inside_excluded_snapshot_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    target: str,
    absolute: bool,
) -> None:
    import subprocess as subprocess_module

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _equivalent_project(tmp_path)
    cache_test = project_root / target
    cache_test.parent.mkdir(parents=True)
    cache_test.write_text("excluded snapshot state\n", encoding="utf-8")
    selected_target = str(cache_test) if absolute else target

    def fail_if_subprocess_starts(*args: object, **kwargs: object) -> None:
        pytest.fail("excluded target started a pytest subprocess")

    monkeypatch.setattr(subprocess_module, "run", fail_if_subprocess_starts)

    with pytest.raises(ValueError, match="excluded snapshot path"):
        run_pytest_equivalence_probe(
            project_root,
            [selected_target],
            workers=2,
            dist_mode="loadscope",
        )


def test_probe_preserves_snapshot_bytes_modes_empty_dirs_and_internal_symlinks(
    tmp_path: Path,
) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "assets/payload.txt": "exact payload bytes\n",
            "tests/test_snapshot_topology.py": (
                "import os\n"
                "import stat\n"
                "from pathlib import Path\n\n"
                "ROOT = Path(__file__).parents[1]\n\n"
                "def test_snapshot_topology_is_exact():\n"
                "    payload = ROOT / 'assets' / 'payload.txt'\n"
                "    link = ROOT / 'assets' / 'payload-link'\n"
                "    assert payload.read_bytes() == b'exact payload bytes\\n'\n"
                "    assert stat.S_IMODE(payload.stat().st_mode) == 0o640\n"
                "    assert (ROOT / 'assets' / 'empty').is_dir()\n"
                "    assert link.is_symlink()\n"
                "    assert os.readlink(link) == 'payload.txt'\n"
                "    assert link.read_bytes() == payload.read_bytes()\n"
            ),
        },
    )
    assets = project_root / "assets"
    (assets / "payload.txt").chmod(0o640)
    (assets / "empty").mkdir()
    (assets / "payload-link").symlink_to("payload.txt")

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.success is True


@pytest.mark.parametrize(
    "link_kind",
    [
        "absolute_escape",
        "relative_escape",
        "absolute_internal",
        "venv_non_interpreter_absolute",
    ],
)
def test_probe_rejects_symlinks_that_escape_project_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    link_kind: str,
) -> None:
    import subprocess as subprocess_module

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _equivalent_project(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = (
        project_root / ".venv" / "bin" / "not-python"
        if link_kind == "venv_non_interpreter_absolute"
        else project_root / "unsafe-link"
    )
    link.parent.mkdir(parents=True, exist_ok=True)
    if link_kind == "absolute_escape":
        link.symlink_to(outside)
    elif link_kind == "relative_escape":
        link.symlink_to("../outside.txt")
    else:
        link.symlink_to(project_root / "tests")

    def fail_if_subprocess_starts(*args: object, **kwargs: object) -> None:
        pytest.fail("unsafe symlink started a pytest subprocess")

    monkeypatch.setattr(subprocess_module, "run", fail_if_subprocess_starts)

    with pytest.raises(ValueError, match="symlink escapes project root"):
        run_pytest_equivalence_probe(
            project_root,
            ["tests"],
            workers=2,
            dist_mode="loadscope",
        )


def test_probe_rejects_python_named_venv_link_to_non_interpreter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import subprocess as subprocess_module

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _equivalent_project(tmp_path)
    outside = tmp_path / "outside-state.txt"
    outside.write_text("source state", encoding="utf-8")
    backdoor = project_root / ".venv" / "bin" / "python"
    backdoor.parent.mkdir(parents=True)
    backdoor.symlink_to(outside)

    def fail_if_subprocess_starts(*args: object, **kwargs: object) -> None:
        pytest.fail("non-interpreter venv link started a pytest subprocess")

    monkeypatch.setattr(subprocess_module, "run", fail_if_subprocess_starts)

    with pytest.raises(ValueError, match="symlink escapes project root"):
        run_pytest_equivalence_probe(
            project_root,
            ["tests"],
            workers=2,
            dist_mode="loadscope",
        )


def test_probe_preserves_copied_venv_interpreter_links(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_venv_boundary.py": (
                "import os\n"
                "from pathlib import Path\n\n"
                "ROOT = Path(__file__).parents[1]\n\n"
                "def test_venv_boundary_is_snapshot_local():\n"
                "    interpreter = ROOT / '.venv' / 'bin' / 'python'\n"
                "    marker = ROOT / '.venv' / 'serial.marker'\n"
                "    assert interpreter.is_symlink()\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        assert not marker.exists()\n"
                "    else:\n"
                "        marker.write_text('serial snapshot only')\n"
            )
        },
    )
    interpreter_link = project_root / ".venv" / "bin" / "python"
    interpreter_link.parent.mkdir(parents=True)
    interpreter_link.symlink_to(Path(sys.executable).resolve())

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.success is True
    assert interpreter_link.is_symlink()
    assert interpreter_link.resolve() == Path(sys.executable).resolve()
    assert not (project_root / ".venv" / "serial.marker").exists()


def test_probe_copies_node_modules_into_independent_snapshots(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "node_modules/example/package.json": '{"name":"example"}\n',
            "tests/test_node_modules_boundary.py": (
                "import os\n"
                "from pathlib import Path\n\n"
                "ROOT = Path(__file__).parents[1]\n\n"
                "def test_node_modules_boundary_is_snapshot_local():\n"
                "    package = ROOT / 'node_modules' / 'example' / 'package.json'\n"
                "    marker = ROOT / 'node_modules' / 'serial.marker'\n"
                '    assert package.read_text() == \'{"name":"example"}\\n\'\n'
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        assert not marker.exists()\n"
                "    else:\n"
                "        marker.write_text('serial snapshot only')\n"
            ),
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.success is True
    assert not (project_root / "node_modules" / "serial.marker").exists()


def test_probe_isolates_linked_worktree_git_metadata(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(*args: str, cwd: Path = repository) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        )

    git("init", "-q")
    git("config", "user.email", "maid@example.test")
    git("config", "user.name", "MAID Test")
    (repository / "seed.txt").write_text("seed\n", encoding="utf-8")
    git("add", "seed.txt")
    git("commit", "-qm", "seed")
    project_root = tmp_path / "linked-worktree"
    git("worktree", "add", "-q", "-b", "probe", str(project_root))
    git("remote", "add", "upstream", str(tmp_path / "linked-upstream.git"))
    (project_root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = ['-ra']\n",
        encoding="utf-8",
    )
    test_path = project_root / "tests" / "test_git_boundary.py"
    test_path.parent.mkdir()
    test_path.write_text(
        "import os\n"
        "import subprocess\n\n"
        "def test_git_metadata_is_snapshot_local():\n"
        "    remote = subprocess.run(\n"
        "        ['git', 'remote'],\n"
        "        capture_output=True, text=True, check=False,\n"
        "    )\n"
        "    assert remote.returncode == 0\n"
        "    assert remote.stdout == ''\n"
        "    key = 'snapshot.serial-state'\n"
        "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
        "        result = subprocess.run(\n"
        "            ['git', 'config', '--local', '--get', key],\n"
        "            capture_output=True, text=True, check=False,\n"
        "        )\n"
        "        assert result.returncode != 0\n"
        "    else:\n"
        "        subprocess.run(\n"
        "            ['git', 'config', '--local', key, 'serial'], check=True,\n"
        "        )\n",
        encoding="utf-8",
    )

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.success is True
    source_config = subprocess.run(
        ["git", "config", "--local", "--get", "snapshot.serial-state"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert source_config.returncode != 0
    assert source_config.stdout == ""
    assert git("remote").stdout.splitlines() == ["upstream"]


def test_probe_sanitizes_standalone_repository_remotes(tmp_path: Path) -> None:
    project_root = _equivalent_project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    outside_remote = tmp_path / "outside-remote.git"
    subprocess.run(
        ["git", "init", "--bare", "-q", str(outside_remote)],
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(outside_remote)],
        cwd=project_root,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "upstream", str(outside_remote)],
        cwd=project_root,
        check=True,
    )
    test_path = project_root / "tests" / "test_git_remote_boundary.py"
    test_path.write_text(
        "import subprocess\n\n"
        "def test_git_remote_is_removed_from_snapshot():\n"
        "    result = subprocess.run(\n"
        "        ['git', 'remote'],\n"
        "        capture_output=True, text=True, check=False,\n"
        "    )\n"
        "    assert result.returncode == 0\n"
        "    assert result.stdout == ''\n",
        encoding="utf-8",
    )

    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.success is True
    source_remote = subprocess.run(
        ["git", "remote", "-v"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert source_remote.returncode == 0
    assert {line.split()[0] for line in source_remote.stdout.splitlines()} == {
        "origin",
        "upstream",
    }
    assert all(
        str(outside_remote) in line for line in source_remote.stdout.splitlines()
    )


def test_probe_binds_equal_serial_and_parallel_execution_environments(
    tmp_path: Path,
) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _equivalent_project(tmp_path)

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.success is True
    assert report.serial_environment == report.parallel_environment
    environment = dict(report.serial_environment)
    assert set(environment) == {"python", "pytest", "pytest-xdist"}
    assert environment == {
        "python": (
            f"{Path(sys.executable).resolve()}|"
            f"{python_implementation()} {python_version()}"
        ),
        "pytest": pytest.__version__,
        "pytest-xdist": version("pytest-xdist"),
    }


def test_probe_rejects_mismatched_execution_environment(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "conftest.py": (
                "import os\n"
                "import pytest\n\n"
                "@pytest.hookimpl(tryfirst=True)\n"
                "def pytest_sessionfinish(session):\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER') == 'gw1':\n"
                "        pytest.__version__ = 'forged-worker-version'\n"
            ),
            "tests/test_environment.py": (
                "def test_environment_probe():\n    assert True\n"
            ),
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.success is False
    assert any("execution environments differ" in item for item in report.differences)


def test_probe_binds_worker_environment_ids_to_collection_ids(tmp_path: Path) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _write_project(
        tmp_path,
        {
            "conftest.py": (
                "import pytest\n\n"
                "@pytest.hookimpl(optionalhook=True, tryfirst=True)\n"
                "def pytest_testnodedown(node, error):\n"
                "    if node.gateway.id == 'gw1':\n"
                "        node.gateway.id = 'forged-gw1'\n"
            ),
            "tests/test_environment_ids.py": (
                "def test_environment_identity_binding():\n" "    assert True\n"
            ),
        },
    )

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.serial_exit_code == 0
    assert report.parallel_exit_code == 0
    assert report.success is False
    assert any("worker environment ids differ" in item for item in report.differences)


def test_probe_report_binds_evidence_to_exact_worker_count_and_dist_mode(
    tmp_path: Path,
) -> None:
    from tools.check_pytest_parallel_equivalence import (
        run_pytest_equivalence_probe,
    )

    project_root = _equivalent_project(tmp_path)

    report = run_pytest_equivalence_probe(
        project_root,
        ["tests"],
        workers=2,
        dist_mode="loadscope",
    )

    assert report.success is True
    assert report.workers == 2
    assert report.dist_mode == "loadscope"
    assert {worker_id for worker_id, _ in report.parallel_worker_collections} == {
        "gw0",
        "gw1",
    }


def test_probe_cli_reports_green_equivalence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.check_pytest_parallel_equivalence import main

    project_root = _equivalent_project(tmp_path)

    exit_code = main(
        [
            "--project-root",
            str(project_root),
            "--workers",
            "2",
            "--dist",
            "loadscope",
            "tests",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == (
        "PASS serial/parallel pytest equivalence: workers=2 dist=loadscope\n"
    )
    assert captured.err == ""


def test_probe_cli_reports_mismatch_and_nonzero_exit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.check_pytest_parallel_equivalence import main

    project_root = _write_project(
        tmp_path,
        {
            "tests/test_phase.py": (
                "import os\n"
                "import pytest\n\n"
                "@pytest.fixture\n"
                "def worker_sensitive():\n"
                "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
                "        pytest.skip('parallel-only skip')\n"
                "    return 'serial'\n\n"
                "def test_phase(worker_sensitive):\n"
                "    assert worker_sensitive == 'serial'\n"
            )
        },
    )

    exit_code = main(
        [
            "--project-root",
            str(project_root),
            "--workers",
            "2",
            "--dist",
            "loadscope",
            "tests",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.startswith(
        "FAIL serial/parallel pytest equivalence: workers=2 dist=loadscope\n"
    )
    assert "phase outcomes differ" in captured.err


def test_probe_script_rejects_matching_nonzero_runs(tmp_path: Path) -> None:
    project_root = _write_project(
        tmp_path,
        {"tests/test_broken.py": "def test_broken():\n    assert False\n"},
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "check_pytest_parallel_equivalence.py"),
            "--project-root",
            str(project_root),
            "--workers",
            "2",
            "--dist",
            "loadscope",
            "tests",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == (
        "FAIL serial/parallel pytest equivalence: workers=2 dist=loadscope\n"
        "- serial pytest exited with code 1\n"
        "- parallel pytest exited with code 1\n"
    )


def test_probe_dependency_is_declared_and_locked() -> None:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
        import tomli as tomllib

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    dev_dependencies = pyproject["dependency-groups"]["dev"]

    pytest_xdist_dev_dependency = any(
        dependency.startswith("pytest-xdist>=") for dependency in dev_dependencies
    )
    pytest_xdist_lock = 'name = "pytest-xdist"' in (REPO_ROOT / "uv.lock").read_text()

    assert pytest_xdist_dev_dependency
    assert pytest_xdist_lock
