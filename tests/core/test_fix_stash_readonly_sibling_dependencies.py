"""Current sibling dependencies remain visible without exempting active wiring."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pytest import CaptureFixture
import yaml

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.plan_lock import PlanLock, default_plan_lock_path


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


def _commit(root: Path, message: str) -> None:
    _git(root, "add", ".")
    _git(root, "commit", "-qm", message)


def _args(path: Path, root: Path, *, allow_sibling: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        manifest_path=str(path),
        project_root=str(root),
        no_run=False,
        json=False,
        reason="review tightened active behavior",
        stash_implementation=True,
        preserve_red_evidence=False,
        allow_sibling_dirty=allow_sibling,
        test_only_green=False,
    )


def _manifest(
    root: Path, name: str, source: str, function: str, test: str, *, create: bool
) -> Path:
    directory = "contracts" if (root / ".maidrc.yaml").exists() else "manifests"
    path = root / f"{directory}/{name}.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": f"Implement {name}",
                "type": "fix",
                "created": "2026-10-20",
                "files": {
                    "create" if create else "edit": [
                        {
                            "path": source,
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": function,
                                    "args": [],
                                    "returns": "int",
                                }
                            ],
                        }
                    ],
                    "read": [test],
                },
                "validate": [[sys.executable, "-m", "pytest", test, "-q"]],
            }
        )
    )
    return path


def _base(root: Path, *, wiring: bool = False) -> Path:
    for directory in ("app", "tests", "manifests", "contracts"):
        (root / directory).mkdir()
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (root / "app/__init__.py").write_text("")
    (root / "app/target.py").write_text("def result() -> int:\n    return 0\n")
    source = (
        "from app.target import result\ndef test_target():\n    assert result() == 1\n"
    )
    dependency = "app/dependency.py"
    if wiring:
        (root / "app/wiring.py").write_text("def is_wired() -> int:\n    return 0\n")
        dependency = "app/wiring.py"
        source = "from app.target import result\nfrom app.wiring import is_wired\ndef test_target():\n    assert result() == 1 or is_wired() == 1\n"
    (root / "tests/test_target.py").write_text(source)
    path = _manifest(
        root, "active", "app/target.py", "result", "tests/test_target.py", create=False
    )
    data = yaml.safe_load(path.read_text())
    data["files"]["read"].append(dependency)
    path.write_text(yaml.safe_dump(data))
    _git(root, "init", "-q")
    _commit(root, "active red baseline")
    assert cmd_plan_lock(_args(path, root)) == 0
    _commit(root, "active plan lock")
    return path


def _current_sibling(root: Path) -> tuple[Path, Path]:
    path = _base(root)
    (root / "app/dependency.py").write_text("def value() -> int:\n    return 0\n")
    (root / "tests/test_dependency.py").write_text(
        "from app.dependency import value\ndef test_dependency():\n    assert value() == 1\n"
    )
    sibling = _manifest(
        root,
        "sibling",
        "app/dependency.py",
        "value",
        "tests/test_dependency.py",
        create=True,
    )
    assert cmd_plan_lock(_args(sibling, root)) == 0
    (root / "app/dependency.py").write_text(
        "def value() -> int:\n    return 1  # current sibling implementation\n"
    )
    (root / "app/target.py").write_text(
        "def result() -> int:\n    return 1  # active implementation\n"
    )
    (root / "tests/test_target.py").write_text(
        "from app.target import result\nfrom app.dependency import value\ndef test_target():\n"
        "    assert value() == 1, 'sibling dependency must remain visible'\n"
        "    assert result() == 1, f'dependency={value()}'\n"
    )
    return path, sibling


def _scope_sibling(root: Path) -> tuple[Path, Path]:
    path = _base(root)
    (root / "app/dependency.py").write_text("def value() -> int:\n    return 0\n")
    (root / "tests/test_existing_dependency.py").write_text(
        "from app.dependency import value\ndef test_existing():\n    assert value() >= 0\n"
    )
    historical = _manifest(
        root,
        "historical-sdk",
        "app/dependency.py",
        "value",
        "tests/test_existing_dependency.py",
        create=False,
    )
    _commit(root, "existing dependency API and characterization")
    legacy_args = _args(historical, root)
    legacy_args.legacy_baseline = True
    legacy_args.reason = "adopt clean existing dependency API"
    assert cmd_plan_lock(legacy_args) == 0
    _commit(root, "historical dependency adoption")
    (root / "tests/test_dependency.py").write_text(
        "from app.dependency import value\ndef test_dependency():\n    assert value() == 1\n"
    )
    sibling = _manifest(
        root,
        "sibling",
        "app/dependency.py",
        "value",
        "tests/test_dependency.py",
        create=False,
    )
    data = yaml.safe_load(sibling.read_text())
    data["files"] = {
        "scope": [
            {
                "path": "app/dependency.py",
                "reason": "Wire existing public dependency behavior",
            }
        ],
        "read": ["tests/test_dependency.py"],
    }
    sibling.write_text(yaml.safe_dump(data))
    assert cmd_plan_lock(_args(sibling, root)) == 0
    (root / "app/dependency.py").write_text(
        "def value() -> int:\n    return 1  # current scope-only sibling wiring\n"
    )
    (root / "app/target.py").write_text(
        "def result() -> int:\n    return 1  # active implementation\n"
    )
    (root / "tests/test_target.py").write_text(
        "from app.target import result\nfrom app.dependency import value\ndef test_target():\n    assert value() == 1, 'sibling dependency must remain visible'\n    assert result() == 1, f'dependency={value()}'\n"
    )
    return path, sibling


def _bytes(root: Path, paths: list[str]) -> dict[str, bytes | None]:
    return {
        path: (root / path).read_bytes() if (root / path).exists() else None
        for path in paths
    }


@pytest.mark.parametrize(
    "owner_state", ["new", "lock-only", "metadata-read", "scope-only", "custom-dir"]
)
def test_dirty_readonly_sibling_survives_stash_revise(
    tmp_path: Path, owner_state: str
) -> None:
    if owner_state == "custom-dir":
        (tmp_path / ".maidrc.yaml").write_text("manifest_dir: contracts/\n")
    path, sibling = (
        _scope_sibling(tmp_path)
        if owner_state == "scope-only"
        else _current_sibling(tmp_path)
    )
    dependency_value = 1
    if owner_state == "lock-only":
        _git(
            tmp_path,
            "add",
            "app/dependency.py",
            "tests/test_dependency.py",
            "manifests/sibling.manifest.yaml",
            ".maid/plan-locks/sibling.lock.json",
        )
        _git(tmp_path, "commit", "-qm", "previous sibling contract")
        (tmp_path / "tests/test_dependency.py").write_text(
            "from app.dependency import value\n# strengthened sibling behavior\ndef test_dependency():\n    assert value() == 2\n"
        )
        sibling_args = _args(sibling, tmp_path)
        sibling_args.stash_implementation = False
        sibling_args.allow_sibling_dirty = False
        assert cmd_plan_revise(sibling_args) == 0
        (tmp_path / "app/dependency.py").write_text(
            "def value() -> int:\n    return 2  # newer sibling implementation with distinct byte length\n"
        )
        text = (
            (tmp_path / "tests/test_target.py")
            .read_text()
            .replace("assert value() == 1", "assert value() == 2")
        )
        (tmp_path / "tests/test_target.py").write_text(text)
        dependency_value = 2
    if owner_state == "metadata-read":
        data = yaml.safe_load(path.read_text())
        data["files"]["read"].extend(
            ["manifests/sibling.manifest.yaml", ".maid/plan-locks/sibling.lock.json"]
        )
        path.write_text(yaml.safe_dump(data))
    sibling_lock = default_plan_lock_path(tmp_path, "sibling")
    before = _bytes(
        tmp_path, ["app/dependency.py", "app/target.py", "tests/test_dependency.py"]
    )
    sibling_bytes, lock_bytes = sibling.read_bytes(), sibling_lock.read_bytes()

    assert cmd_plan_revise(_args(path, tmp_path)) == 0

    assert _bytes(tmp_path, list(before)) == before
    assert (sibling.read_bytes(), sibling_lock.read_bytes()) == (
        sibling_bytes,
        lock_bytes,
    )
    evidence = PlanLock.load(default_plan_lock_path(tmp_path, "active")).red_evidence
    assert evidence is not None
    assert evidence.get("mode") is None
    assert [command["classification"] for command in evidence["commands"]] == ["red"]
    assert f"dependency={dependency_value}" in evidence["commands"][0]["output_tail"]
    assert "app/dependency.py" in evidence["sibling_dirty_paths"]
    assert _git(tmp_path, "stash", "list") == ""


def test_actual_read_listed_wiring_is_stashed(tmp_path: Path) -> None:
    path = _base(tmp_path, wiring=True)
    (tmp_path / "tests/test_old_wiring.py").write_text(
        "from app.wiring import is_wired\ndef test_wiring():\n    assert is_wired() == 1\n"
    )
    old_owner = _manifest(
        tmp_path,
        "historical-owner",
        "app/wiring.py",
        "is_wired",
        "tests/test_old_wiring.py",
        create=False,
    )
    assert cmd_plan_lock(_args(old_owner, tmp_path)) == 0
    _commit(tmp_path, "historical wiring contract and lock")
    (tmp_path / "app/target.py").write_text(
        "def result() -> int:\n    return 1  # implemented target\n"
    )
    (tmp_path / "app/wiring.py").write_text(
        "def is_wired() -> int:\n    return 1  # implementation wiring\n"
    )
    before = _bytes(tmp_path, ["app/target.py", "app/wiring.py"])

    assert cmd_plan_revise(_args(path, tmp_path)) == 0

    evidence = PlanLock.load(default_plan_lock_path(tmp_path, "active")).red_evidence
    assert evidence is not None and evidence["commands"][0]["classification"] == "red"
    assert _bytes(tmp_path, list(before)) == before
    assert _git(tmp_path, "stash", "list") == ""


def test_failed_revision_restores_all_original_bytes(tmp_path: Path) -> None:
    path, sibling = _current_sibling(tmp_path)
    (tmp_path / "tests/test_target.py").write_text(
        "from app.dependency import value\ndef test_target():\n    assert value() == 1\n"
    )
    paths = [
        "app/target.py",
        "app/dependency.py",
        "tests/test_target.py",
        "manifests/active.manifest.yaml",
        "manifests/sibling.manifest.yaml",
        ".maid/plan-locks/active.lock.json",
        ".maid/plan-locks/sibling.lock.json",
    ]
    before = _bytes(tmp_path, paths)

    assert cmd_plan_revise(_args(path, tmp_path)) == 1

    assert _bytes(tmp_path, paths) == before
    assert sibling.is_file()
    assert _git(tmp_path, "stash", "list") == ""


@pytest.mark.parametrize(
    "owner_case",
    [
        "missing-lock",
        "tampered-lock",
        "malformed-lock",
        "competing-owner",
        "wrong-lock-path",
        "modified-owner-test",
        "spliced-command",
        "invalid-evidence",
        "missing-evidence",
        "missing-test-hash",
    ],
)
def test_invalid_current_sibling_ownership_refuses_without_stash(
    tmp_path: Path, owner_case: str, capsys: CaptureFixture[str]
) -> None:
    path, _ = _current_sibling(tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "sibling")
    if owner_case == "missing-lock":
        lock_path.unlink()
    elif owner_case == "malformed-lock":
        lock_path.write_text("{ invalid lock")
    elif owner_case == "modified-owner-test":
        (tmp_path / "tests/test_dependency.py").write_text(
            "from app.dependency import value\ndef test_dependency():\n    assert value() == 2\n"
        )
    elif owner_case == "competing-owner":
        (tmp_path / "tests/test_competing.py").write_text(
            "from app.dependency import value\ndef test_competing():\n    assert value() == 2\n"
        )
        other = _manifest(
            tmp_path,
            "competing",
            "app/dependency.py",
            "value",
            "tests/test_competing.py",
            create=False,
        )
        assert cmd_plan_lock(_args(other, tmp_path)) == 0
    else:
        data = json.loads(lock_path.read_text())
        if owner_case == "tampered-lock":
            data["manifest_hash"] = "sha256-contract:not-the-current-manifest"
        elif owner_case == "wrong-lock-path":
            data["manifest_path"] = "manifests/another.manifest.yaml"
        elif owner_case == "spliced-command":
            data["red_evidence"]["commands"][0][
                "command"
            ] = "python -c 'raise SystemExit(1)'"
        elif owner_case == "invalid-evidence":
            data["red_evidence"]["red"] = False
        elif owner_case == "missing-evidence":
            data["red_evidence"] = None
        elif owner_case == "missing-test-hash":
            data["test_hashes"] = {}
        lock_path.write_text(json.dumps(data))
    paths = [
        "app/target.py",
        "app/dependency.py",
        "manifests/active.manifest.yaml",
        "manifests/sibling.manifest.yaml",
        ".maid/plan-locks/active.lock.json",
        ".maid/plan-locks/sibling.lock.json",
    ]
    before = _bytes(tmp_path, paths)
    capsys.readouterr()

    assert cmd_plan_revise(_args(path, tmp_path)) == 2

    assert _bytes(tmp_path, paths) == before
    message = capsys.readouterr().err
    assert "ownership" in message.lower() and "app/dependency.py" in message
    assert "files.scope" in message
    assert _git(tmp_path, "stash", "list") == ""


def test_sibling_flag_is_required_for_current_dependency_context(
    tmp_path: Path,
) -> None:
    path, _ = _current_sibling(tmp_path)
    paths = ["app/target.py", "app/dependency.py", ".maid/plan-locks/active.lock.json"]
    before = _bytes(tmp_path, paths)

    assert cmd_plan_revise(_args(path, tmp_path, allow_sibling=False)) == 2

    assert _bytes(tmp_path, paths) == before
    assert _git(tmp_path, "stash", "list") == ""


def test_current_writable_ownership_is_not_exempted_as_sibling_context(
    tmp_path: Path,
) -> None:
    path, _ = _current_sibling(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["files"]["scope"] = [
        {
            "path": "app/dependency.py",
            "reason": "Active task also owns this implementation",
        }
    ]
    path.write_text(yaml.safe_dump(data))
    before = _bytes(
        tmp_path,
        ["app/target.py", "app/dependency.py", ".maid/plan-locks/active.lock.json"],
    )

    assert cmd_plan_revise(_args(path, tmp_path)) == 1

    assert _bytes(tmp_path, list(before)) == before
    assert _git(tmp_path, "stash", "list") == ""


@pytest.mark.parametrize(
    "context", ["source", "manifest", "lock", "proof-test", "directory"]
)
@pytest.mark.parametrize("phase", ["capture", "restored"])
def test_changed_readonly_context_blocks_lock_save(
    tmp_path: Path, context: str, phase: str, capsys: CaptureFixture[str]
) -> None:
    path, _ = _current_sibling(tmp_path)
    relative = {
        "source": "app/dependency.py",
        "directory": "app/dependency.py",
        "manifest": "manifests/sibling.manifest.yaml",
        "lock": ".maid/plan-locks/sibling.lock.json",
        "proof-test": "tests/test_dependency.py",
    }[context]
    before_context = (tmp_path / relative).read_bytes()
    mutation = (
        before_context + b"\n# concurrent context change\n"
        if context != "lock"
        else before_context + b"\n"
    )
    if context == "proof-test":
        mutation = before_context + b"\ndef test_added_behavior(): assert False\n"
    prefix = ""
    owned_paths = ["app/target.py"]
    if phase == "restored":
        (tmp_path / "app/own_new.py").write_text(
            "def own_value() -> int:\n    return 1\n"
        )
        (tmp_path / "tests/test_restore_red.py").write_text(
            "def test_restore_red(): assert False\n"
        )
        data = yaml.safe_load(path.read_text())
        data["files"]["create"] = [
            {
                "path": "app/own_new.py",
                "artifacts": [
                    {
                        "kind": "function",
                        "name": "own_value",
                        "args": [],
                        "returns": "int",
                    }
                ],
            }
        ]
        data["files"]["read"].append("tests/test_restore_red.py")
        data["validate"].append(
            [sys.executable, "-m", "pytest", "tests/test_restore_red.py", "-q"]
        )
        path.write_text(yaml.safe_dump(data))
        prefix = "from app.own_new import own_value\n"
        owned_paths.append("app/own_new.py")
    mutation_code = f"    Path({relative!r}).write_bytes({mutation!r})\n"
    if context == "directory":
        mutation_code = f"    Path({relative!r}).unlink(); Path({relative!r}).mkdir()\n"
    (tmp_path / "tests/test_target.py").write_text(
        prefix
        + "from pathlib import Path\nfrom app.target import result\nfrom app.dependency import value\ndef test_target():\n"
        "    assert value() == 1\n" + mutation_code + "    assert result() == 1\n"
    )
    before_target = _bytes(tmp_path, owned_paths)
    before_lock = default_plan_lock_path(tmp_path, "active").read_bytes()
    capsys.readouterr()

    assert cmd_plan_revise(_args(path, tmp_path)) == 2

    if context == "directory":
        assert (tmp_path / relative).is_dir()
    else:
        assert (tmp_path / relative).read_bytes() == mutation
    assert _bytes(tmp_path, owned_paths) == before_target
    assert default_plan_lock_path(tmp_path, "active").read_bytes() == before_lock
    message = capsys.readouterr().err
    assert "changed" in message.lower() and relative in message
    assert _git(tmp_path, "stash", "list") == ""


@pytest.mark.parametrize("role", ["snapshot", "read"])
def test_context_inventory_is_not_current_writable_ownership(
    tmp_path: Path, role: str
) -> None:
    path = _base(tmp_path)
    (tmp_path / "app/dependency.py").write_text("def value() -> int:\n    return 0\n")
    (tmp_path / "app/other.py").write_text("def other() -> int:\n    return 0\n")
    (tmp_path / "tests/test_dependency.py").write_text(
        "from app.dependency import value\nfrom app.other import other\ndef test_dependency():\n    assert other() == 0\n    assert value() == 1\n"
    )
    owner = _manifest(
        tmp_path,
        "inventory",
        "app/other.py",
        "other",
        "tests/test_dependency.py",
        create=True,
    )
    data = yaml.safe_load(owner.read_text())
    if role == "snapshot":
        data["files"]["snapshot"] = [
            {
                "path": "app/dependency.py",
                "artifacts": [
                    {"kind": "function", "name": "value", "args": [], "returns": "int"}
                ],
            }
        ]
    else:
        data["files"]["read"].append("app/dependency.py")
    owner.write_text(yaml.safe_dump(data))
    assert cmd_plan_lock(_args(owner, tmp_path)) == 0
    (tmp_path / "app/dependency.py").write_text(
        "def value() -> int:\n    return 1  # inventory does not own these implementation bytes\n"
    )
    (tmp_path / "app/target.py").write_text(
        "def result() -> int:\n    return 1  # current target implementation\n"
    )
    (tmp_path / "tests/test_target.py").write_text(
        "from app.target import result\nfrom app.dependency import value\ndef test_target():\n    assert value() == 1\n    assert result() == 1\n"
    )
    before = _bytes(
        tmp_path,
        ["app/dependency.py", "app/target.py", ".maid/plan-locks/active.lock.json"],
    )

    assert cmd_plan_revise(_args(path, tmp_path)) == 1

    assert _bytes(tmp_path, list(before)) == before
    assert _git(tmp_path, "stash", "list") == ""


@pytest.mark.parametrize(
    "context", ["source", "manifest", "lock", "proof-test", "directory"]
)
def test_unsupported_sibling_context_refuses_before_stashing(
    tmp_path: Path, context: str, capsys: CaptureFixture[str]
) -> None:
    path, sibling = _current_sibling(tmp_path)
    selected = {
        "source": tmp_path / "app/dependency.py",
        "directory": tmp_path / "app/dependency.py",
        "manifest": sibling,
        "lock": default_plan_lock_path(tmp_path, "sibling"),
        "proof-test": tmp_path / "tests/test_dependency.py",
    }[context]
    backing = tmp_path.parent / (tmp_path.name + "-backing")
    if context == "manifest":
        (tmp_path / "metadata").mkdir()
        backing = tmp_path / "metadata/sibling.manifest.yaml"
    backing.write_bytes(selected.read_bytes())
    selected.unlink()
    if context == "directory":
        selected.mkdir()
        (selected / "child").write_text("unowned directory content")
    else:
        selected.symlink_to(backing)
    if context == "manifest":
        dependency = tmp_path / "app/dependency.py"
        implemented = dependency.read_bytes()
        dependency.write_text("def value() -> int:\n    return 0\n")
        default_plan_lock_path(tmp_path, "sibling").unlink()
        assert cmd_plan_lock(_args(sibling, tmp_path)) == 0
        dependency.write_bytes(implemented)
    active_lock = default_plan_lock_path(tmp_path, "active")
    before = active_lock.read_bytes()
    own_source = (tmp_path / "app/target.py").read_bytes()
    assert cmd_plan_revise(_args(path, tmp_path)) == 2
    assert active_lock.read_bytes() == before
    assert (tmp_path / "app/target.py").read_bytes() == own_source
    assert selected.is_dir() if context == "directory" else selected.is_symlink()
    message = capsys.readouterr().err.lower()
    assert ("regular file" if context == "directory" else "symlink") in message
    assert not _git(tmp_path, "stash", "list").strip()
