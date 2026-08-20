"""Behavioral contract for deep knockout evidence consumed by chain merge."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


def test_chain_merge_keeps_cold_detection_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.core import knockout
    from maid_runner.core.chain import ManifestChain

    _initialize_project(tmp_path, monkeypatch)
    chain = ManifestChain("manifests")

    assert (
        knockout.cached_detecting_nodeids_for_file(
            chain.active_manifests(), Path("."), "src/a.py"
        )
        == {}
    )
    assert main(["chain", "merge", "src/a.py", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["acceptance"]["required_detecting_nodeids"] == {}
    assert report["acceptance"]["unknown_detection_artifacts"] == ["function:target"]


def test_chain_merge_reads_file_scoped_detection_from_verify_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.core import knockout
    from maid_runner.core.chain import ManifestChain

    project = _initialize_project(tmp_path, monkeypatch)

    assert (
        main(
            [
                "verify",
                "--artifact-coverage",
                "--knockout",
                "--no-changed-scope",
                "--summary",
            ]
        )
        == 0
    )
    capsys.readouterr()

    chain = ManifestChain("manifests")
    assert knockout.cached_detecting_nodeids_for_file(
        chain.active_manifests(), Path("."), "src/a.py"
    ) == {"function:target": ("tests/test_a.py::test_target",)}
    assert knockout.cached_detecting_nodeids_for_file(
        chain.active_manifests(), Path("."), "src/b.py"
    ) == {"function:target": ("tests/test_b.py::test_target",)}

    reports = {}
    for file_path in ("src/a.py", "src/b.py"):
        assert main(["chain", "merge", file_path, "--json"]) == 0
        reports[file_path] = json.loads(capsys.readouterr().out)

    assert reports["src/a.py"]["acceptance"]["required_detecting_nodeids"] == {
        "function:target": ["tests/test_a.py::test_target"]
    }
    assert reports["src/b.py"]["acceptance"]["required_detecting_nodeids"] == {
        "function:target": ["tests/test_b.py::test_target"]
    }
    assert reports["src/a.py"]["acceptance"]["unknown_detection_artifacts"] == []
    assert reports["src/b.py"]["acceptance"]["unknown_detection_artifacts"] == []

    (project / "src" / "a.py").write_text(
        "def target(value: str) -> str:\n" "    return value.lower() + 'changed'\n",
        encoding="utf-8",
    )
    stale_chain = ManifestChain("manifests")
    assert (
        knockout.cached_detecting_nodeids_for_file(
            stale_chain.active_manifests(), Path("."), "src/a.py"
        )
        == {}
    )
    assert main(["chain", "merge", "src/a.py", "--json"]) == 0
    stale_report = json.loads(capsys.readouterr().out)
    assert stale_report["acceptance"]["required_detecting_nodeids"] == {}
    assert stale_report["acceptance"]["unknown_detection_artifacts"] == [
        "function:target"
    ]


def _initialize_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    _write_project(project)
    _git(project, "init")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "baseline")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(project)
    return project


def _write_project(root: Path) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n.maid/cache/\n",
        encoding="utf-8",
    )
    for suffix, value in (("a", "A"), ("b", "B")):
        hour = "01" if suffix == "b" else "00"
        (root / "src" / f"{suffix}.py").write_text(
            "def target(value: str) -> str:\n"
            f"    return value.upper() + {value!r}\n",
            encoding="utf-8",
        )
        (root / "tests" / f"test_{suffix}.py").write_text(
            f"from src.{suffix} import target\n\n"
            "def test_target():\n"
            f"    assert target('x') == 'X{value}'\n",
            encoding="utf-8",
        )
        (root / "manifests" / f"{suffix}.manifest.yaml").write_text(
            'schema: "2"\n'
            f'goal: "Protect target {suffix}"\n'
            "type: fix\n"
            f'created: "2026-08-19T{hour}:00:00Z"\n'
            "files:\n"
            "  edit:\n"
            f"    - path: src/{suffix}.py\n"
            "      artifacts:\n"
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
