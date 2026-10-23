"""Actionable, fail-closed recovery when new tests require an upgraded SDK API."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise


_BASELINE = "def demo() -> int:\n    return 0\n"
_IMPLEMENTED = (
    "from sdk import Client\n\ndef demo() -> int:\n    return Client().version - 1\n"
)
_TEST = "from sdk import Client\nfrom src.demo import demo\n\ndef test_demo():\n    assert Client().version == 2\n    assert demo() == 1\n"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.com",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _sdk_lock(version: int) -> str:
    return (
        f'[[package]]\nname = "fixture-sdk"\nversion = "{version}.0.0"\noptional = false\npython-versions = ">=3.10"\nfiles = []\n\n[metadata]\nlock-version = "2.0"\npython-versions = ">=3.10"\ncontent-hash = "'
        + "0" * 64
        + '"\n'
    )


def _project(root: Path) -> Path:
    for name in ("manifests", "src", "tests", "vendor/v1", "vendor/v2"):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n.maid/cache/\n")
    (root / "src/__init__.py").write_text("")
    (root / "src/demo.py").write_text(_BASELINE)
    (root / "vendor/v1/sdk.py").write_text("VERSION = 1\n")
    (root / "vendor/v2/sdk.py").write_text("class Client:\n    version = 2\n")
    # Owned SDK-version selection adapter: real modules expose different APIs.
    # This needs no package install and exercises actual pytest collection.
    (root / "tests/conftest.py").write_text(
        "from pathlib import Path\nimport sys\n"
        "try:\n    import tomllib\nexcept ModuleNotFoundError:\n    import tomli as tomllib\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "version = tomllib.loads((ROOT / 'poetry.lock').read_text())['package'][0]['version'].split('.')[0]\n"
        "sys.path.insert(0, str(ROOT / 'vendor' / ('v' + version)))\n"
    )
    (root / "tests/test_demo.py").write_text(_TEST)
    (root / "pyproject.toml").write_text(
        '[project]\nname="sdk-fixture"\nversion="0.0.0"\ndependencies=["fixture-sdk>=1"]\n'
    )
    (root / "poetry.lock").write_text(_sdk_lock(1))
    manifest = root / "manifests/sdk-prerequisite.manifest.yaml"
    manifest.write_text(
        "schema: '2'\ngoal: Support upgraded SDK\ntype: fix\nfiles:\n  edit:\n"
        "  - path: src/demo.py\n    artifacts:\n    - kind: function\n      name: demo\n      args: []\n      returns: int\n"
        "  scope:\n  - path: pyproject.toml\n    reason: Declare SDK prerequisite\n"
        "  - path: poetry.lock\n    reason: Select fixture dependency version\n"
        "  read:\n  - tests/test_demo.py\n  - tests/conftest.py\n  - vendor/v1/sdk.py\n  - vendor/v2/sdk.py\n"
        f"validate:\n- [{sys.executable!r}, '-B', '-m', pytest, tests/test_demo.py, '-q']\n"
    )
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "SDK baseline and planned behavioral contract")
    (root / "poetry.lock").write_text(_sdk_lock(2))
    (root / "pyproject.toml").write_text(
        '[project]\nname="sdk-fixture"\nversion="0.0.0"\ndependencies=["fixture-sdk>=2"]\n'
    )
    assert (
        cmd_plan_lock(
            argparse.Namespace(
                manifest_path=str(manifest),
                project_root=str(root),
                no_run=False,
                json=False,
            )
        )
        == 0
    )
    record = _lock(root)
    assert record["red_evidence"]["commands"][0]["exit_code"] == 1
    assert "assert 0 == 1" in record["red_evidence"]["commands"][0]["output_tail"]
    _git(root, "add", ".maid/plan-locks/sdk-prerequisite.lock.json")
    _git(root, "commit", "-qm", "Lock genuine baseline red with SDK prerequisite")
    (root / "src/demo.py").write_text(_IMPLEMENTED)
    (root / "tests/test_demo.py").write_text(
        _TEST + "    assert isinstance(demo(), int)\n"
    )
    _assert_green(root)
    return manifest


def _args(root: Path, manifest: Path, *, stash: bool = True) -> argparse.Namespace:
    return argparse.Namespace(
        manifest_path=str(manifest),
        project_root=str(root),
        reason="Strengthen behavioral type assertion",
        no_run=False,
        json=False,
        preserve_red_evidence=False,
        stash_implementation=stash,
        allow_sibling_dirty=False,
        test_only_green=False,
    )


def _lock(root: Path) -> dict:
    return json.loads(
        (root / ".maid/plan-locks/sdk-prerequisite.lock.json").read_text()
    )


def _assert_green(root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", "tests/test_demo.py", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _state(root: Path, manifest: Path) -> dict[str, tuple[bytes, int]]:
    paths = [
        root / "src/demo.py",
        root / "pyproject.toml",
        root / "poetry.lock",
        root / "tests/test_demo.py",
        manifest,
        root / ".maid/plan-locks/sdk-prerequisite.lock.json",
    ]
    return {
        str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mode)
        for path in paths
    }


def test_upgraded_dependency_tests_get_source_baseline_recovery(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _project(tmp_path)
    capsys.readouterr()
    assert cmd_plan_revise(_args(tmp_path, manifest)) == 1
    error = capsys.readouterr().err.lower()
    before = _lock(tmp_path)["revision"]
    current = (tmp_path / "src/demo.py").read_bytes()
    baseline = subprocess.check_output(
        ["git", "show", "HEAD:src/demo.py"], cwd=tmp_path
    )
    try:
        (tmp_path / "src/demo.py").write_bytes(baseline)
        assert cmd_plan_revise(_args(tmp_path, manifest, stash=False)) == 0
        record = _lock(tmp_path)
        assert record["revision"] == before + 1
        assert record["red_evidence"]["commands"][0]["exit_code"] == 1
        assert "ImportError" not in record["red_evidence"]["commands"][0]["output_tail"]
    finally:
        (tmp_path / "src/demo.py").write_bytes(current)
    _assert_green(tmp_path)
    assert 'version = "2.0.0"' in (tmp_path / "poetry.lock").read_text()
    for phrase in (
        "required to collect",
        "save the current implementation",
        "prerequisite environment",
        "implementation source",
        "controlled checkout",
        "plain plan revise",
    ):
        assert phrase in error


def test_dependency_failure_preserves_original_lock_and_restores_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _project(tmp_path)
    before = _state(tmp_path, manifest)
    capsys.readouterr()
    assert cmd_plan_revise(_args(tmp_path, manifest)) == 1
    error = capsys.readouterr().err
    assert "ImportError" in error and "Client" in error
    assert "exit 2" in error and "invalid" in error
    assert _state(tmp_path, manifest) == before
    assert _git(tmp_path, "stash", "list", "--format=%H") == ""
    _assert_green(tmp_path)


def test_recovery_does_not_claim_legacy_baseline_always_applies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _project(tmp_path)
    capsys.readouterr()
    assert cmd_plan_revise(_args(tmp_path, manifest)) == 1
    error = capsys.readouterr().err.lower()
    assert "prior dependency state only when" in error
    assert "legacy baseline" in error and "eligible" in error and "tracked" in error
    assert "collection" in error
