"""Stash restoration must attribute failure to an executing behavioral runner."""

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest
from maid_runner.core.plan_lock import (
    PlanLock,
    capture_red_phase_evidence,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
    revision_preserves_red_evidence,
)
from maid_runner.core.result import ErrorCode
from maid_runner.core.run_evaluation import evaluate_run


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def _args(path: Path, root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        manifest_path=str(path),
        project_root=str(root),
        no_run=False,
        json=False,
        reason="review strengthened behavioral tests",
        stash_implementation=True,
        preserve_red_evidence=False,
        allow_sibling_dirty=False,
        test_only_green=False,
    )


def _project(root: Path, *, wrapper: bool = False) -> Path:
    for directory in ("app", "tests", "tools", "manifests"):
        (root / directory).mkdir()
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (root / "app/__init__.py").write_text("")
    (root / "app/models.py").write_text("def legacy() -> int:\n    return 0\n")
    (root / "tests/test_backend.py").write_text(
        "from app.models import legacy\ndef test_backend():\n    assert legacy() == 1\n"
    )
    (root / "tests/test_frontend.py").write_text(
        "def test_frontend():\n    assert True\n"
    )
    (root / "tools/lint.py").write_text(
        "from pathlib import Path\nraise SystemExit(0 if Path('app/extra.py').exists() else 1)\n"
    )
    path = root / "manifests/policy.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Verify backend and frontend behavior",
                "type": "fix",
                "created": "2026-10-20",
                "files": {
                    "edit": [
                        {
                            "path": "app/models.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "legacy",
                                    "args": [],
                                    "returns": "int",
                                }
                            ],
                        }
                    ],
                    "read": [
                        "tests/test_backend.py",
                        "tests/test_frontend.py",
                        "tools/lint.py",
                    ],
                },
                "validate": [
                    [sys.executable, "-m", "pytest", "tests/test_backend.py", "-q"],
                    [sys.executable, "-m", "pytest", "tests/test_frontend.py", "-q"],
                    [sys.executable, "tools/lint.py"],
                ],
            }
        )
    )
    if wrapper:
        wrapper_path = root / "tools/test"
        wrapper_path.write_text(
            f"#!{sys.executable}\n"
            "import subprocess, sys\n"
            "target = sys.argv[1].replace('.', '/') + '.py'\n"
            "raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', target, '-q']))\n"
        )
        wrapper_path.chmod(0o755)
        (root / ".maidrc.yaml").write_text(
            "test_runner_wrappers:\n  - command: ./tools/test\n    runner: django\n"
        )
        data = yaml.safe_load(path.read_text())
        data["files"]["read"].extend(["tools/test", ".maidrc.yaml"])
        data["validate"][1] = ["./tools/test", "tests.test_frontend"]
        path.write_text(yaml.safe_dump(data))
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "red behavioral baseline")
    assert cmd_plan_lock(_args(path, root)) == 0
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "locked behavioral baseline")
    return path


def _revision(
    root: Path, path: Path, *, red_phase: str = "none", wrapper: bool = False
) -> None:
    (root / "app/models.py").write_text(
        "def legacy() -> int:\n    return 1  # implemented behavior\n"
    )
    (root / "app/extra.py").write_text("def value() -> int:\n    return 1\n")
    (root / "tests/test_backend.py").write_text(
        "from app.models import legacy\nfrom app.extra import value\ndef test_backend():\n"
        f"    assert legacy() == 1\n    assert value() == {2 if red_phase == 'restored' else 1}\n"
    )
    if red_phase == "stashed":
        (root / "tests/test_frontend.py").write_text(
            "def test_frontend():\n    assert False, 'unimplemented frontend behavior'\n"
        )
    data = yaml.safe_load(path.read_text())
    data["files"]["create"] = [
        {
            "path": "app/extra.py",
            "artifacts": [
                {"kind": "function", "name": "value", "args": [], "returns": "int"}
            ],
        }
    ]
    if wrapper:
        # The configured repository wrapper was committed before this revision.
        data["validate"][1] = ["./tools/test", "tests.test_frontend"]
    path.write_text(yaml.safe_dump(data))


def _invalid_payload(path: Path) -> dict:
    commands = [
        shlex.join(command) for command in load_manifest(path).validate_commands
    ]

    def item(command: str, code: int) -> dict:
        return {
            "command": command,
            "exit_code": code,
            "classification": {0: "not_red", 1: "red", 2: "invalid"}[code],
            "output_tail": "captured command output",
        }

    return {
        "red": True,
        "mode": "stash_restoration",
        "captured_at": "2026-10-20T00:00:00Z",
        "restored_captured_at": "2026-10-20T00:00:01Z",
        "commands": [item(commands[0], 2), item(commands[1], 0), item(commands[2], 1)],
        "restored_commands": [item(command, 0) for command in commands],
        "behavioral_red_commands": [
            {
                "phase": "stashed",
                "command": commands[2],
                "test_files": ["tests/test_backend.py"],
            }
        ],
    }


def test_lint_red_cannot_replace_invalid_behavioral_test(tmp_path: Path) -> None:
    path = _project(tmp_path)
    _revision(tmp_path, path)
    lock_path = default_plan_lock_path(tmp_path, "policy")
    before = lock_path.read_bytes()
    implementation = (tmp_path / "app/extra.py").read_bytes()

    result = cmd_plan_revise(_args(path, tmp_path))

    assert result == 1
    assert lock_path.read_bytes() == before
    assert (tmp_path / "app/extra.py").read_bytes() == implementation
    assert _git(tmp_path, "stash", "list") == ""


def test_restored_green_does_not_turn_collection_error_into_behavioral_red(
    tmp_path: Path,
) -> None:
    path = _project(tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "policy")
    lock = PlanLock.load(lock_path)
    replace(lock, red_evidence=_invalid_payload(path)).save(lock_path)

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID in {error.code for error in errors}


@pytest.mark.parametrize("red_phase", ["stashed", "restored"])
def test_genuine_behavioral_red_remains_accepted(
    tmp_path: Path, red_phase: str
) -> None:
    path = _project(tmp_path)
    _revision(tmp_path, path, red_phase=red_phase)

    assert cmd_plan_revise(_args(path, tmp_path)) == 0

    lock = PlanLock.load(default_plan_lock_path(tmp_path, "policy"))
    evidence = lock.red_evidence
    assert evidence is not None
    assert evaluate_run(path, tmp_path).red_evidence_status == "valid"
    proof = evidence["behavioral_red_commands"]
    expected_file = (
        "tests/test_frontend.py" if red_phase == "stashed" else "tests/test_backend.py"
    )
    assert any(
        item["phase"] == red_phase and expected_file in item["test_files"]
        for item in proof
    )
    assert all("tools/lint.py" not in item["command"] for item in proof)
    assert _git(tmp_path, "stash", "list") == ""
    legacy = deepcopy(evidence)
    legacy.pop("behavioral_red_commands")
    replace(lock, red_evidence=legacy).save(default_plan_lock_path(tmp_path, "policy"))
    legacy_errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )
    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID not in {
        error.code for error in legacy_errors
    }
    corrupted = deepcopy(evidence)
    corrupted["behavioral_red_commands"][0]["phase"] = (
        "restored" if red_phase == "stashed" else "stashed"
    )
    replace(lock, red_evidence=corrupted).save(
        default_plan_lock_path(tmp_path, "policy")
    )
    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )
    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID in {error.code for error in errors}


def test_changed_behavioral_contract_cannot_preserve_stale_red(tmp_path: Path) -> None:
    path = _project(tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "policy")
    lock = PlanLock.load(lock_path)
    prior = json.loads(lock_path.read_text())["_manifest_contract"]
    invalid = replace(lock, red_evidence=_invalid_payload(path))

    assert not revision_preserves_red_evidence(invalid, path, tmp_path, prior)
    (tmp_path / "tests/test_backend.py").write_text(
        "def test_backend(): assert False\n"
    )
    assert not revision_preserves_red_evidence(lock, path, tmp_path, prior)


def test_acceptance_behavioral_red_remains_accepted(tmp_path: Path) -> None:
    path = _project(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["acceptance"] = {"tests": [data["validate"][0]]}
    data["validate"] = [[sys.executable, "-c", "pass"]]
    path.write_text(yaml.safe_dump(data))

    evidence = capture_red_phase_evidence(path, tmp_path)

    assert evidence.red is True
    assert evidence.command_source == "validate_and_acceptance"
    assert [command.classification for command in evidence.commands] == [
        "not_red",
        "red",
    ]


def test_registered_wrapper_red_is_attributed(tmp_path: Path) -> None:
    path = _project(tmp_path, wrapper=True)
    _revision(tmp_path, path, red_phase="stashed", wrapper=True)

    assert cmd_plan_revise(_args(path, tmp_path)) == 0

    evidence = PlanLock.load(default_plan_lock_path(tmp_path, "policy")).red_evidence
    assert evidence is not None
    assert any(
        item["command"] == "./tools/test tests.test_frontend"
        and item["test_files"] == ["tests/test_frontend.py"]
        for item in evidence["behavioral_red_commands"]
    )
    legacy = deepcopy(evidence)
    legacy.pop("behavioral_red_commands")
    lock_path = default_plan_lock_path(tmp_path, "policy")
    replace(PlanLock.load(lock_path), red_evidence=legacy).save(lock_path)
    args = _args(path, tmp_path)
    args.stash_implementation = False
    args.preserve_red_evidence = True
    assert cmd_plan_revise(args) == 0
    assert PlanLock.load(lock_path).red_evidence == legacy
    assert evaluate_run(path, tmp_path).red_evidence_status == "valid"


@pytest.mark.parametrize("mode", ["--collect-only", "--help", "--version"])
def test_nonexecuting_runner_cannot_supply_behavioral_red(
    tmp_path: Path, mode: str
) -> None:
    path = _project(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["validate"][2] = [
        sys.executable,
        "-m",
        "pytest",
        mode,
        "tests/test_backend.py",
    ]
    path.write_text(yaml.safe_dump(data))
    lock = create_plan_lock(path, tmp_path)
    replace(lock, red_evidence=_invalid_payload(path)).save(
        default_plan_lock_path(tmp_path, "policy")
    )

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID in {error.code for error in errors}
