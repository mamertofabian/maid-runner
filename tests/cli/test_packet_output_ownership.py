"""Behavioral contract for failure-packet destination ownership."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


def _write_project(root: Path, *, passing: bool) -> Path:
    (root / "manifests").mkdir()
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "gate.py").write_text(
        "def gate() -> str:\n    return 'ok'\n" if passing else "# missing gate\n"
    )
    (root / "tests" / "test_gate.py").write_text(
        "from src.gate import gate\n\n"
        "def test_gate():\n"
        "    assert gate() == 'ok'\n"
    )
    manifest_path = root / "manifests" / "packet-task.manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Exercise packet ownership",
                "type": "fix",
                "files": {
                    "create": [
                        {
                            "path": "src/gate.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "gate",
                                    "args": [],
                                    "returns": "str",
                                }
                            ],
                        }
                    ],
                    "read": ["tests/test_gate.py"],
                },
                "validate": ["python -m pytest -q tests/test_gate.py"],
            },
            sort_keys=False,
        )
    )
    return manifest_path


def _packet_payload(root: Path, *, exit_code: int = 1) -> dict:
    return {
        "packet_version": 1,
        "command": ["maid", "validate", "--packet"],
        "exit_code": exit_code,
        "project_root": str(root),
        "manifest": [],
        "diagnostics": [],
        "test_output": [],
        "environment": {
            "maid_version": "ownership-test",
            "python_version": "ownership-test",
        },
    }


def _write_packet(path: Path) -> None:
    path.write_text(json.dumps(_packet_payload(path.parent)) + "\n")


def test_validate_packet_argument_order_preserves_manifest_destination(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=True)
    original = manifest_path.read_bytes()

    exit_code = main(
        ["validate", "--mode", "implementation", "--packet", str(manifest_path)]
    )

    assert exit_code == 2
    assert manifest_path.read_bytes() == original
    assert "not a MAID failure packet" in capsys.readouterr().err


def test_failing_validate_preserves_arbitrary_packet_destination(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    manifest_path = _write_project(tmp_path, passing=False)
    destination = tmp_path / "operator-notes.txt"
    destination.write_text("keep this operator-owned content\n")
    original = destination.read_bytes()

    exit_code = main(
        [
            "validate",
            str(manifest_path),
            "--mode",
            "implementation",
            "--no-chain",
            "--packet",
            str(destination),
        ]
    )

    assert exit_code == 1
    assert destination.read_bytes() == original
    assert "not a MAID failure packet" in capsys.readouterr().err


def test_passing_verify_preserves_arbitrary_packet_destination(
    tmp_path: Path, capsys
) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    (tmp_path / "manifests").mkdir()
    destination = tmp_path / "operator-notes.txt"
    destination.write_text("keep this operator-owned content\n")
    original = destination.read_bytes()

    exit_code = main(
        [
            "verify",
            "--allow-empty",
            "--packet",
            str(destination),
            "--keep-going",
        ]
    )

    assert exit_code == 2
    assert destination.read_bytes() == original
    assert "not a MAID failure packet" in capsys.readouterr().err


def test_validate_packet_refuses_symlink_destination(tmp_path: Path, capsys) -> None:
    from maid_runner.cli.commands._main import main

    os.chdir(tmp_path)
    _write_project(tmp_path, passing=True)
    target = tmp_path / "operator-notes.txt"
    target.write_text("keep this operator-owned content\n")
    destination = tmp_path / "packet.json"
    destination.symlink_to(target)
    original = target.read_bytes()

    exit_code = main(
        ["validate", "--mode", "implementation", "--packet", str(destination)]
    )

    assert exit_code == 2
    assert destination.is_symlink()
    assert target.read_bytes() == original
    assert "symbolic link" in capsys.readouterr().err


def test_write_failure_packet_preserves_raced_path_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core.failure_packet import write_failure_packet

    destination = tmp_path / "packet.json"
    _write_packet(destination)
    verified_packet = tmp_path / "verified-packet.json"
    operator_bytes = b"operator-owned replacement\n"
    real_write = os.write
    swapped = False

    def swap_path_then_write(fd: int, data: bytes) -> int:
        nonlocal swapped
        if not swapped:
            destination.rename(verified_packet)
            destination.write_bytes(operator_bytes)
            swapped = True
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", swap_path_then_write)

    with pytest.raises(ValueError, match="changed during failure packet update"):
        write_failure_packet(_packet_payload(tmp_path), destination)

    assert destination.read_bytes() == operator_bytes


def test_clear_failure_packet_preserves_raced_path_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core.failure_packet import clear_failure_packet

    destination = tmp_path / "packet.json"
    _write_packet(destination)
    verified_packet = tmp_path / "verified-packet.json"
    operator_bytes = b"operator-owned replacement\n"
    real_write = os.write
    swapped = False

    def swap_path_then_write(fd: int, data: bytes) -> int:
        nonlocal swapped
        if not swapped:
            destination.rename(verified_packet)
            destination.write_bytes(operator_bytes)
            swapped = True
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", swap_path_then_write)

    with pytest.raises(ValueError, match="changed during failure packet update"):
        clear_failure_packet(destination)

    assert destination.read_bytes() == operator_bytes
