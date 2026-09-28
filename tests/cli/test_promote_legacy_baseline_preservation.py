"""Promotion must preserve audited legacy evidence without laundering changes."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from maid_runner.cli.commands.manifest import cmd_manifest
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    capture_legacy_baseline_evidence,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _legacy_project(
    root: Path, *, provenance: str = "index", self_reference: bool = False
) -> tuple[Path, Path]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src/demo.py").write_text(
        "def demo(a: int, b: int) -> int:\n    return a - b\n"
    )
    (root / "tests/test_demo.py").write_text(
        "from pathlib import Path\n"
        "from src.demo import demo\n"
        "def test_demo():\n"
        "    assert demo(9, 2) == 7\n"
        "    log = Path('.maid/runs')\n"
        "    log.parent.mkdir(exist_ok=True)\n"
        "    log.write_text(log.read_text() + 'run\\n' if log.exists() else 'run\\n')\n"
    )
    (root / "config.txt").write_text("existing configuration\n")
    (root / ".gitignore").write_text(".maid/\n__pycache__/\n.pytest_cache/\n")
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "MAID Test")
    _git(root, "config", "user.email", "maid-test@example.com")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "legacy implementation")
    draft = root / "manifests/drafts/legacy.manifest.yaml"
    draft.parent.mkdir(parents=True)
    commands = [[sys.executable, "-m", "pytest", "tests/test_demo.py", "-q"]]
    if self_reference:
        commands.append(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; import sys; assert Path(sys.argv[1]).is_file()",
                "manifests/drafts/legacy.manifest.yaml",
            ]
        )
    draft.write_text(
        "# manifest-kind: implementation\n"
        + yaml.safe_dump(
            {
                "schema": "2",
                "type": "snapshot",
                "goal": "Adopt legacy implementation",
                "created": "2026-09-28T00:00:00Z",
                "files": {
                    "snapshot": [
                        {
                            "path": "src/demo.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "demo",
                                    "args": [
                                        {"name": "a", "type": "int"},
                                        {"name": "b", "type": "int"},
                                    ],
                                    "returns": "int",
                                }
                            ],
                        }
                    ],
                    "scope": [
                        {"path": "config.txt", "reason": "Existing configuration"}
                    ],
                    "read": ["tests/test_demo.py"],
                },
                "validate": commands,
                "acceptance": {"tests": [[sys.executable, "-c", "pass"]]},
            },
            sort_keys=False,
        )
    )
    _git(root, "add", "manifests/drafts/legacy.manifest.yaml")
    if provenance == "head":
        _git(root, "commit", "-qm", "legacy contract")
    evidence = capture_legacy_baseline_evidence(draft, root, "Adopt historical code")
    assert evidence.baseline_manifest_source == provenance
    lock = replace(create_plan_lock(draft, root), legacy_baseline=evidence.to_payload())
    lock_path = default_plan_lock_path(root, "legacy")
    lock.save(lock_path)
    return draft, lock_path


def _promotion_args(root: Path, draft: Path, no_run: bool) -> argparse.Namespace:
    return argparse.Namespace(
        manifest_command="promote",
        manifest_path=str(draft),
        output_dir=str(root / "manifests"),
        project_root=str(root),
        no_run=no_run,
        json=False,
    )


@pytest.mark.parametrize("provenance", ["index", "head"])
@pytest.mark.parametrize("no_run", [False, True])
def test_promotion_preserves_legacy_provenance_and_strict_lock_gate(
    tmp_path: Path, provenance: str, no_run: bool
) -> None:
    draft, lock_path = _legacy_project(tmp_path, provenance=provenance)
    before = PlanLock.load(lock_path)
    runs = (tmp_path / ".maid/runs").read_bytes()

    result = cmd_manifest(_promotion_args(tmp_path, draft, no_run))

    assert result == 0
    assert not draft.exists()
    promoted = tmp_path / "manifests/legacy.manifest.yaml"
    assert promoted.exists()
    after = PlanLock.load(lock_path)
    assert after.legacy_baseline == before.legacy_baseline
    assert after.red_evidence is None
    assert after.test_hashes == before.test_hashes
    assert after.manifest_path == "manifests/legacy.manifest.yaml"
    assert after.revision == before.revision + 1
    assert (tmp_path / ".maid/runs").read_bytes() == runs
    assert (
        enforce_plan_locks(
            ManifestChain(tmp_path / "manifests", tmp_path),
            tmp_path,
            require_plan_lock=True,
            require_red_evidence=True,
            changed_paths={"manifests/legacy.manifest.yaml"},
            plan_lock_scope="task",
        )
        == ()
    )


@pytest.mark.parametrize("no_run", [False, True])
@pytest.mark.parametrize(
    "change",
    [
        "test",
        "command",
        "scope",
        "artifact",
        "arg-order",
        "acceptance",
        "supersedes",
        "removed-artifacts",
        "type",
        "immutability",
        "invalid-evidence",
        "spliced-command",
        "missing-snapshot",
        "mixed-evidence",
    ],
)
def test_changed_or_invalid_legacy_lock_rolls_back_promotion(
    tmp_path: Path, no_run: bool, change: str, capsys
) -> None:
    draft, lock_path = _legacy_project(tmp_path)
    if change == "test":
        test = tmp_path / "tests/test_demo.py"
        test.write_text(
            test.read_text().replace("assert demo(9, 2) == 7", "assert demo(9, 2) != 0")
        )
    elif change in {
        "command",
        "scope",
        "artifact",
        "arg-order",
        "acceptance",
        "supersedes",
        "removed-artifacts",
        "type",
        "immutability",
    }:
        data = yaml.safe_load(draft.read_text())
        if change == "command":
            data["validate"][0].append("--disable-warnings")
        elif change == "scope":
            data["files"]["scope"].append({"path": "extra.txt", "reason": "New scope"})
        elif change == "arg-order":
            data["files"]["snapshot"][0]["artifacts"][0]["args"].reverse()
        elif change == "supersedes":
            data["supersedes"] = ["other-approved-contract"]
        elif change == "removed-artifacts":
            data["removed_artifacts"] = [
                {"kind": "function", "name": "gone", "file": "src/demo.py"}
            ]
        elif change == "type":
            data["type"] = "fix"
        elif change == "immutability":
            data["acceptance"]["immutable"] = False
        elif change == "acceptance":
            data.pop("acceptance")
        else:
            data["files"]["snapshot"][0]["artifacts"][0]["returns"] = "str"
        draft.write_text(yaml.safe_dump(data))
    else:
        payload = json.loads(lock_path.read_text())
        if change == "invalid-evidence":
            payload["legacy_baseline"]["green"] = False
        elif change == "spliced-command":
            payload["legacy_baseline"]["commands"][0]["command"] = "python -c pass"
        elif change == "missing-snapshot":
            payload.pop("_manifest_contract")
        else:
            payload["red_evidence"] = {"red": True, "commands": []}
        lock_path.write_text(json.dumps(payload))
    original_lock = lock_path.read_bytes()
    original_draft = draft.read_bytes()
    runs = (tmp_path / ".maid/runs").read_bytes()

    result = cmd_manifest(_promotion_args(tmp_path, draft, no_run))

    assert result == 2
    assert "legacy" in capsys.readouterr().err.lower()
    assert draft.read_bytes() == original_draft
    assert lock_path.read_bytes() == original_lock
    assert not (tmp_path / "manifests/legacy.manifest.yaml").exists()
    assert (tmp_path / ".maid/runs").read_bytes() == runs


@pytest.mark.parametrize("no_run", [False, True])
def test_self_referencing_legacy_commands_require_explicit_reconciliation(
    tmp_path: Path, no_run: bool, capsys
) -> None:
    draft, lock_path = _legacy_project(tmp_path, self_reference=True)
    original_lock = lock_path.read_bytes()
    original_draft = draft.read_bytes()

    result = cmd_manifest(_promotion_args(tmp_path, draft, no_run))

    assert result == 2
    diagnostic = capsys.readouterr().err.lower()
    assert "legacy" in diagnostic
    assert "final active path" in diagnostic
    assert lock_path.read_bytes() == original_lock
    assert draft.read_bytes() == original_draft
    assert not (tmp_path / "manifests/legacy.manifest.yaml").exists()


@pytest.mark.parametrize("no_run", [False, True])
def test_unparseable_legacy_test_rolls_back_promotion(
    tmp_path: Path, no_run: bool, capsys
) -> None:
    draft, lock_path = _legacy_project(tmp_path)
    (tmp_path / "tests/test_demo.py").write_text("def test_demo(:\n    assert True\n")
    original_lock = lock_path.read_bytes()
    original_draft = draft.read_bytes()
    runs = (tmp_path / ".maid/runs").read_bytes()

    result = cmd_manifest(_promotion_args(tmp_path, draft, no_run))

    assert result == 2
    diagnostic = capsys.readouterr().err
    assert "promotion rolled back" in diagnostic
    assert "test_demo.py" in diagnostic
    assert lock_path.read_bytes() == original_lock
    assert draft.read_bytes() == original_draft
    assert not (tmp_path / "manifests/legacy.manifest.yaml").exists()
    assert (tmp_path / ".maid/runs").read_bytes() == runs


@pytest.mark.parametrize("no_run", [False, True])
@pytest.mark.parametrize("invalid_source", [[], {}])
def test_malformed_legacy_evidence_type_rolls_back_promotion(
    tmp_path: Path, no_run: bool, invalid_source: list | dict, capsys
) -> None:
    draft, lock_path = _legacy_project(tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["legacy_baseline"]["baseline_manifest_source"] = invalid_source
    lock_path.write_text(json.dumps(payload))
    original_lock = lock_path.read_bytes()
    original_draft = draft.read_bytes()
    runs = (tmp_path / ".maid/runs").read_bytes()

    result = cmd_manifest(_promotion_args(tmp_path, draft, no_run))

    assert result == 2
    assert "promotion rolled back" in capsys.readouterr().err
    assert lock_path.read_bytes() == original_lock
    assert draft.read_bytes() == original_draft
    assert not (tmp_path / "manifests/legacy.manifest.yaml").exists()
    assert (tmp_path / ".maid/runs").read_bytes() == runs


@pytest.mark.parametrize("no_run", [False, True])
@pytest.mark.parametrize("invalid_hash", [None, 7, [], {}])
def test_malformed_locked_test_hash_rolls_back_promotion(
    tmp_path: Path, no_run: bool, invalid_hash: int | list | dict | None, capsys
) -> None:
    draft, lock_path = _legacy_project(tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["test_hashes"]["tests/test_demo.py"] = invalid_hash
    lock_path.write_text(json.dumps(payload))
    original_lock = lock_path.read_bytes()
    original_draft = draft.read_bytes()
    runs = (tmp_path / ".maid/runs").read_bytes()

    result = cmd_manifest(_promotion_args(tmp_path, draft, no_run))

    assert result == 2
    diagnostic = capsys.readouterr().err
    assert "promotion rolled back" in diagnostic
    assert "test hashes" in diagnostic
    assert lock_path.read_bytes() == original_lock
    assert draft.read_bytes() == original_draft
    assert not (tmp_path / "manifests/legacy.manifest.yaml").exists()
    assert (tmp_path / ".maid/runs").read_bytes() == runs


@pytest.mark.parametrize("no_run", [False, True])
def test_formatting_and_outcome_changes_preserve_legacy_promotion(
    tmp_path: Path, no_run: bool
) -> None:
    draft, lock_path = _legacy_project(tmp_path)
    original = PlanLock.load(lock_path).legacy_baseline
    data = yaml.safe_load(draft.read_text())
    data["outcome"] = {
        "status": "completed",
        "completed_at": "2026-09-28T00:00:00Z",
        "summary": "Audited legacy adoption",
    }
    draft.write_text(
        "# Reformatted with an Outcome record\n" + yaml.safe_dump(data, sort_keys=True)
    )

    result = cmd_manifest(_promotion_args(tmp_path, draft, no_run))

    assert result == 0
    assert PlanLock.load(lock_path).legacy_baseline == original
    assert PlanLock.load(lock_path).red_evidence is None
    assert not draft.exists()
    assert (
        enforce_plan_locks(
            ManifestChain(tmp_path / "manifests", tmp_path),
            tmp_path,
            require_plan_lock=True,
            require_red_evidence=True,
            changed_paths={"manifests/legacy.manifest.yaml"},
            plan_lock_scope="task",
        )
        == ()
    )


@pytest.mark.parametrize("no_run", [False, True])
@pytest.mark.parametrize(
    "invalid_hash", [None, "unknown-format", "sha256-contract:" + "0" * 64]
)
def test_legacy_draft_must_match_its_stored_manifest_hash(
    tmp_path: Path, no_run: bool, invalid_hash: str | None, capsys
) -> None:
    draft, lock_path = _legacy_project(tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["manifest_hash"] = invalid_hash
    lock_path.write_text(json.dumps(payload))
    original_lock = lock_path.read_bytes()
    original_draft = draft.read_bytes()

    result = cmd_manifest(_promotion_args(tmp_path, draft, no_run))

    assert result == 2
    assert "legacy baseline" in capsys.readouterr().err.lower()
    assert lock_path.read_bytes() == original_lock
    assert draft.read_bytes() == original_draft
    assert not (tmp_path / "manifests/legacy.manifest.yaml").exists()
