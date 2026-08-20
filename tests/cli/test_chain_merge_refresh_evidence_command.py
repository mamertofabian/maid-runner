"""Behavioral contract for explicit file-scoped chain-merge evidence refresh."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


def test_chain_merge_refreshes_only_requested_file_with_complete_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.core.chain_merge_evidence import (
        ChainMergeEvidenceRefreshResult,
        RecordedCoverageEvidenceSource,
        RecordedDetectionEvidenceSource,
        refresh_chain_merge_evidence,
    )
    from maid_runner.core.knockout import run_knockout_for_file

    artifact_shape = ChainMergeEvidenceRefreshResult(
        detection_source=RecordedDetectionEvidenceSource({}),
        coverage_source=RecordedCoverageEvidenceSource({}),
        errors=(),
    )
    assert callable(refresh_chain_merge_evidence)
    assert callable(run_knockout_for_file)
    assert (
        artifact_shape.detection_source.detecting_nodeids_for("function:target") is None
    )
    assert (
        artifact_shape.coverage_source.coverage_for(
            "src/b.py", "attribute:Config.enabled"
        )
        is None
    )

    _initialize_project(tmp_path, monkeypatch, requested_suffix="b")

    exit_code = main(
        [
            "chain",
            "merge",
            "src/b.py",
            "--refresh-evidence",
            "--dry-run",
            "--json",
        ]
    )
    refreshed = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert refreshed["acceptance"]["required_artifacts"] == [
        "attribute:Config.enabled",
        "class:Config",
        "function:target",
    ]
    assert refreshed["acceptance"]["required_covered_artifacts"] == [
        "attribute:Config.enabled",
        "class:Config",
        "function:target",
    ]
    assert refreshed["acceptance"]["unknown_coverage_artifacts"] == []
    assert refreshed["acceptance"]["required_detecting_nodeids"] == {
        "function:target": ["tests/test_b.py::test_target"]
    }
    assert refreshed["acceptance"]["unknown_detection_artifacts"] == []

    assert main(["chain", "merge", "src/b.py", "--json"]) == 0
    warm_target = json.loads(capsys.readouterr().out)
    assert warm_target["acceptance"]["required_detecting_nodeids"] == {
        "function:target": ["tests/test_b.py::test_target"]
    }
    assert warm_target["acceptance"]["required_covered_artifacts"] == []
    assert warm_target["acceptance"]["unknown_coverage_artifacts"] == [
        "attribute:Config.enabled",
        "class:Config",
        "function:target",
    ]

    assert main(["chain", "merge", "src/a.py", "--json"]) == 0
    cold_sibling = json.loads(capsys.readouterr().out)
    assert cold_sibling["acceptance"]["required_detecting_nodeids"] == {}
    assert cold_sibling["acceptance"]["unknown_detection_artifacts"] == [
        "function:target"
    ]
    assert cold_sibling["acceptance"]["required_covered_artifacts"] == []
    assert cold_sibling["acceptance"]["unknown_coverage_artifacts"] == [
        "attribute:Config.enabled",
        "class:Config",
        "function:target",
    ]


def test_chain_merge_refresh_verifies_equivalence_across_changed_test_nodeids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    project = _initialize_project(tmp_path, monkeypatch, include_sibling=False)
    assert (
        main(
            [
                "chain",
                "merge",
                "src/a.py",
                "--refresh-evidence",
                "--json",
            ]
        )
        == 0
    )
    baseline = project / "before.json"
    baseline.write_text(capsys.readouterr().out, encoding="utf-8")
    (project / "tests/test_a.py").write_text(
        "from src.a import Config, target\n\n"
        "def test_consolidated_contract():\n"
        "    assert target('x') == 'XA'\n"
        "    assert Config.enabled is True\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "chain",
            "merge",
            "src/a.py",
            "--refresh-evidence",
            "--verify-equivalence",
            str(baseline),
            "--json",
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert result["success"] is True
    assert result["detection_regressions"] == []
    assert result["coverage_regressions"] == []
    assert result["evidence_regressions"] == []


def test_chain_merge_refresh_fails_closed_when_knockout_survives(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    project = _initialize_project(tmp_path, monkeypatch, include_sibling=False)
    (project / "tests/test_a.py").write_text(
        "from src.a import Config, target\n\n"
        "def test_target():\n"
        "    assert callable(target)\n"
        "    assert Config.enabled is True\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "chain",
            "merge",
            "src/a.py",
            "--refresh-evidence",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert "E711" in {error["code"] for error in payload["errors"]}
    assert any(
        "differential detection" in error["message"].lower()
        for error in payload["errors"]
    )
    assert "acceptance" not in payload


def test_chain_merge_refresh_fails_closed_with_coverage_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    _initialize_class_only_project(tmp_path, monkeypatch)

    exit_code = main(
        [
            "chain",
            "merge",
            "src/model.py",
            "--refresh-evidence",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert "E710" in {error["code"] for error in payload["errors"]}
    assert "acceptance" not in payload


def test_chain_merge_refresh_fails_closed_with_harness_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    project = _initialize_project(tmp_path, monkeypatch, include_sibling=False)
    manifest = project / "manifests/a.manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("name: target", "name: missing"),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "chain",
            "merge",
            "src/a.py",
            "--refresh-evidence",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert "E712" in {error["code"] for error in payload["errors"]}
    assert "acceptance" not in payload


@pytest.mark.parametrize("restore_write", [False, True])
def test_chain_merge_refresh_isolates_and_rejects_material_test_writes(
    restore_write: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    project = _initialize_structural_write_project(
        tmp_path,
        monkeypatch,
        restore_write=restore_write,
    )
    monkeypatch.setenv("GIT_WORK_TREE", str(project))

    exit_code = main(
        [
            "chain",
            "merge",
            "src/model.py",
            "--refresh-evidence",
            "--dry-run",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert {error["code"] for error in payload["errors"]} == {"E712"}
    assert "acceptance" not in payload
    assert not (project / "material-write.txt").exists()


def test_chain_merge_refresh_discards_only_owned_pytest_timing_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    project = _initialize_project(tmp_path, monkeypatch, include_sibling=False)
    (project / ".maidrc.yaml").write_text(
        "test_execution:\n"
        "  pytest_workers: 2\n"
        "  accepted_pytest_worker_counts: [2]\n"
        "  parallel_without_history: true\n"
        "  max_processes: 2\n",
        encoding="utf-8",
    )

    exit_code = main(["chain", "merge", "src/a.py", "--refresh-evidence", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0, payload
    assert payload["acceptance"]["unknown_coverage_artifacts"] == []
    assert not list((project / ".maid/cache").glob("pytest-timing-*.json"))


@pytest.mark.parametrize(
    ("relative_path", "expected_non_material"),
    [
        (f".maid/cache/pytest-timing-{'a' * 64}.json", True),
        (f".maid/cache/.pytest-timing-{'a' * 64}.json.123.tmp", True),
        (".maid/cache/project-state.json", False),
        (".maid/cache/pytest-timing-not-a-digest.json", False),
        (f".maid/cache/nested/pytest-timing-{'a' * 64}.json", False),
        (f".maid/cache/pytest-timing-{'a' * 64}.json.backup", False),
        (f".maid/cache/.pytest-timing-{'a' * 64}.json.tmp", False),
        (f".maid/cache/.pytest-timing-{'a' * 64}.json.tmp.backup", False),
    ],
)
def test_chain_merge_refresh_timing_cache_path_policy(
    relative_path: str,
    expected_non_material: bool,
) -> None:
    from maid_runner.core._artifact_coverage_fallback_worker import _is_non_material

    assert _is_non_material(relative_path) is expected_non_material


@pytest.mark.parametrize(
    "relative_path",
    [
        ".maid/cache/project-state.json",
        ".maid/cache/pytest-timing-not-a-digest.json",
        f".maid/cache/nested/pytest-timing-{'a' * 64}.json",
        f".maid/cache/pytest-timing-{'a' * 64}.json.backup",
        f".maid/cache/.pytest-timing-{'a' * 64}.json.tmp",
    ],
)
def test_chain_merge_refresh_rejects_unowned_maid_cache_write(
    relative_path: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    project = _initialize_structural_write_project(
        tmp_path,
        monkeypatch,
        restore_write=False,
        relative_path=relative_path,
    )
    monkeypatch.setenv("GIT_WORK_TREE", str(project))

    exit_code = main(["chain", "merge", "src/model.py", "--refresh-evidence", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert {error["code"] for error in payload["errors"]} == {"E712"}
    assert any(relative_path in error["message"] for error in payload["errors"])


def test_snapshot_runtime_executor_applies_environment_to_both_execution_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    target = tmp_path / "src/target.py"
    target.write_text("def target():\n    return 'ok'\n", encoding="utf-8")
    (tmp_path / "tests/test_environment.py").write_text(
        "import os\nfrom src.target import target\n\n"
        "def test_environment():\n"
        "    assert os.environ['SNAPSHOT_BOUND'] == 'yes'\n"
        "    assert 'SOURCE_ONLY' not in os.environ\n"
        "    assert target() == 'ok'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SOURCE_ONLY", "present")
    executor = SubprocessRuntimeCommandExecutor(
        environment_overrides={"SNAPSHOT_BOUND": "yes"},
        environment_removals=("SOURCE_ONLY",),
    )
    pytest_args = ("-q", "tests/test_environment.py")
    command = ("python", "-m", "pytest", *pytest_args)
    targets = {str(target.resolve())}

    ordinary = executor.execute(pytest_args, targets, tmp_path, 30)
    contextual = executor.execute_with_contexts(
        command,
        targets,
        tmp_path,
        30,
    )

    assert ordinary.returncode == 0
    assert contextual.result.returncode == 0
    assert contextual.selected_nodeids == (
        "tests/test_environment.py::test_environment",
    )


@pytest.mark.parametrize("mode_args", [("--all",), ("--apply",)])
def test_chain_merge_refresh_rejects_structural_modes(
    mode_args: tuple[str, ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    project = _initialize_project(tmp_path, monkeypatch, include_sibling=False)

    exit_code = main(
        [
            "chain",
            "merge",
            "src/a.py",
            "--refresh-evidence",
            *mode_args,
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert "cannot be combined" in payload["error"]
    assert not list((project / ".maid/cache").glob("**/*.json"))


def _initialize_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_sibling: bool = True,
    requested_suffix: str = "a",
) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    if requested_suffix == "b":
        _write_owner(project, "a", "A", failing=True)
        _write_owner(project, "b", "B", failing=False)
    else:
        _write_owner(project, "a", "A", failing=False)
        if include_sibling:
            _write_owner(project, "b", "B", failing=True)
    (project / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n.maid/cache/\n",
        encoding="utf-8",
    )
    _git(project, "init")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "baseline")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(project)
    return project


def _initialize_class_only_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "tests").mkdir()
    (project / "manifests").mkdir()
    (project / "src/model.py").write_text(
        "def model(value: str) -> str:\n    return value.upper()\n",
        encoding="utf-8",
    )
    (project / "tests/test_model.py").write_text(
        "from src.model import model\n\n"
        "def test_unrelated():\n    assert callable(model)\n",
        encoding="utf-8",
    )
    (project / "manifests/model.manifest.yaml").write_text(
        'schema: "2"\n'
        'goal: "Protect model"\n'
        "type: fix\n"
        'created: "2026-08-19T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/model.py\n"
        "      artifacts:\n"
        "        - kind: function\n"
        "          name: model\n"
        "          args:\n"
        "            - {name: value, type: str}\n"
        "          returns: str\n"
        "validate:\n"
        "  - python -m pytest -q tests/test_model.py\n",
        encoding="utf-8",
    )
    (project / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n.maid/cache/\n",
        encoding="utf-8",
    )
    _git(project, "init")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "baseline")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(project)
    return project


def _initialize_structural_write_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    restore_write: bool,
    relative_path: str = "material-write.txt",
) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "tests").mkdir()
    (project / "manifests").mkdir()
    (project / "src/model.py").write_text(
        "class Model:\n    enabled: bool = True\n",
        encoding="utf-8",
    )
    restore = "    material_path.unlink()\n" if restore_write else ""
    (project / "tests/test_model.py").write_text(
        "import os\nfrom pathlib import Path\nfrom src.model import Model\n\n"
        "def test_model():\n"
        "    material_path = Path(os.environ.get('GIT_WORK_TREE', '.')) / "
        f"{relative_path!r}\n"
        "    material_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    material_path.write_text('changed', encoding='utf-8')\n"
        f"{restore}"
        "    assert Model.enabled is True\n",
        encoding="utf-8",
    )
    (project / "manifests/model.manifest.yaml").write_text(
        'schema: "2"\n'
        'goal: "Protect structural model"\n'
        "type: fix\n"
        'created: "2026-08-19T00:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        "    - path: src/model.py\n"
        "      artifacts:\n"
        "        - {kind: class, name: Model}\n"
        "        - {kind: attribute, name: enabled, of: Model, type: bool}\n"
        "  read:\n"
        "    - tests/test_model.py\n"
        "validate:\n"
        "  - python -m pytest -q tests/test_model.py\n",
        encoding="utf-8",
    )
    (project / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n.maid/cache/\n",
        encoding="utf-8",
    )
    _git(project, "init")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "baseline")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(project)
    return project


def _write_owner(
    root: Path,
    suffix: str,
    value: str,
    *,
    failing: bool,
) -> None:
    (root / "src").mkdir(exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "manifests").mkdir(exist_ok=True)
    (root / "src" / f"{suffix}.py").write_text(
        "class Config:\n"
        "    enabled: bool = True\n\n"
        "def target(value: str) -> str:\n"
        f"    return value.upper() + {value!r}\n",
        encoding="utf-8",
    )
    marker = "\n    assert False\n" if failing else ""
    (root / "tests" / f"test_{suffix}.py").write_text(
        f"from src.{suffix} import Config, target\n\n"
        "def test_target():\n"
        f"    assert target('x') == 'X{value}'\n"
        "    assert Config.enabled is True\n"
        f"{marker}",
        encoding="utf-8",
    )
    hour = "01" if suffix == "b" else "00"
    (root / "manifests" / f"{suffix}.manifest.yaml").write_text(
        'schema: "2"\n'
        f'goal: "Protect target {suffix}"\n'
        "type: fix\n"
        f'created: "2026-08-19T{hour}:00:00Z"\n'
        "files:\n"
        "  edit:\n"
        f"    - path: src/{suffix}.py\n"
        "      artifacts:\n"
        "        - {kind: class, name: Config}\n"
        "        - {kind: attribute, name: enabled, of: Config, type: bool}\n"
        "        - kind: function\n"
        "          name: target\n"
        "          args:\n"
        "            - {name: value, type: str}\n"
        "          returns: str\n"
        "  read:\n"
        f"    - tests/test_{suffix}.py\n"
        "validate:\n"
        f"  - python -m pytest -q tests/test_{suffix}.py\n",
        encoding="utf-8",
    )


def _git(root: Path, *args: str) -> None:
    command = ["git", "-C", str(root)]
    if args and args[0] == "commit":
        command.extend(
            [
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "user.name=Test User",
            ]
        )
    command.extend(args)
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
