"""Behavioral contract for Git delivery attestations."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from maid_runner.core.plan_lock import (
    PlanLock,
    compute_manifest_contract_hash,
    default_plan_lock_path,
)
from maid_runner.core.result import ErrorCode


def _git(root: Path, *args: str, text: bool = True):
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=text,
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _commit(root: Path, message: str) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _project(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "maid@example.test")
    _git(root, "config", "user.name", "MAID Test")
    _write(root / "src/app.py", "def deliver() -> str:\n    return 'validated'\n")
    _write(root / "src/delete_me.py", "obsolete = True\n")
    manifest = root / "manifests/task.manifest.yaml"
    _write(
        manifest,
        """schema: '2'
goal: Bind delivery bytes
type: feature
created: '2026-08-10T00:00:00Z'
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: deliver
          args: []
          returns: str
  delete:
    - path: src/delete_me.py
      reason: remove obsolete module
  read:
    - tests/test_app.py
validate:
  - python -m pytest tests/test_app.py
""",
    )
    _write(root / "tests/test_app.py", "def test_placeholder():\n    assert True\n")
    validated_sha = _commit(root, "validated tree")
    lock = PlanLock(
        manifest_path="manifests/task.manifest.yaml",
        manifest_hash=compute_manifest_contract_hash(manifest),
        test_hashes={},
        created_at="2026-08-10T00:00:00Z",
    )
    lock.save(default_plan_lock_path(root, "task"))
    _git(root, "branch", "validated", validated_sha)
    return root, manifest, validated_sha


def _delivery_module():
    from maid_runner.core import delivery_attestation

    return delivery_attestation


def _attestation(root: Path, manifest: Path, validated_sha: str) -> dict:
    from maid_runner.core.delivery_attestation import compute_delivery_attestation

    return compute_delivery_attestation(root, [manifest], validated_sha)


def _verify(attestation: dict, root: Path, delivered_ref: str) -> dict:
    from maid_runner.core.delivery_attestation import verify_delivered_attestation

    return verify_delivered_attestation(attestation, root, delivered_ref)


def _render(attestation: dict, verification: dict | None = None) -> str:
    from maid_runner.core.delivery_attestation import render_provenance_record

    return render_provenance_record(attestation, verification)


def _delivered_branch(root: Path, name: str = "delivered") -> str:
    _git(root, "checkout", "-q", "-b", name)
    return name


def test_delivered_ref_with_matching_covered_bytes_passes(tmp_path: Path) -> None:
    root, manifest, validated_sha = _project(tmp_path)
    attestation = _attestation(root, manifest, validated_sha)
    delivered_ref = _delivered_branch(root)

    result = _verify(attestation, root, delivered_ref)

    assert result["success"] is True
    assert result["delivered_ref"] == "refs/heads/delivered"
    assert result["delivered_commit"] == validated_sha
    assert result["mismatches"] == []


def test_delivered_ref_with_mutated_covered_file_fails(tmp_path: Path) -> None:
    root, manifest, validated_sha = _project(tmp_path)
    attestation = _attestation(root, manifest, validated_sha)
    delivered_ref = _delivered_branch(root)
    _write(root / "src/app.py", "def deliver() -> str:\n    return 'mutated'\n")
    _commit(root, "mutate covered file")

    result = _verify(attestation, root, delivered_ref)

    assert result["success"] is False
    assert [item["path"] for item in result["mismatches"]] == ["src/app.py"]
    assert result["errors"][0]["code"] == "E714"


def test_delivered_ref_missing_covered_file_fails_closed(tmp_path: Path) -> None:
    root, manifest, validated_sha = _project(tmp_path)
    attestation = _attestation(root, manifest, validated_sha)
    delivered_ref = _delivered_branch(root)
    (root / "src/app.py").unlink()
    _commit(root, "drop covered file")

    result = _verify(attestation, root, delivered_ref)

    assert result["success"] is False
    assert result["mismatches"] == [
        {
            "path": "src/app.py",
            "expected": attestation["contracts"][0]["covered_files"]["src/app.py"],
            "actual": None,
        }
    ]
    assert result["errors"][0]["code"] == "E714"


def test_squash_or_rebase_preserving_covered_bytes_still_passes(tmp_path: Path) -> None:
    root, manifest, validated_sha = _project(tmp_path)
    attestation = _attestation(root, manifest, validated_sha)
    delivered_ref = _delivered_branch(root)
    _git(root, "commit", "--allow-empty", "-m", "rewritten delivery identity")
    delivered_sha = _git(root, "rev-parse", "HEAD").stdout.strip()

    result = _verify(attestation, root, delivered_ref)

    assert delivered_sha != validated_sha
    assert result["success"] is True
    assert result["delivered_commit"] == delivered_sha


def test_missing_or_mismatched_attestation_fails_closed(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from maid_runner.cli.commands.verify import cmd_verify
    from maid_runner.cli.commands import verify as verify_command
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.core.diagnostics_registry import get_rule
    from maid_runner.core.result import VerificationResult

    root, manifest, validated_sha = _project(tmp_path)
    delivered_ref = _delivered_branch(root)
    missing = _verify({}, root, delivered_ref)
    mismatched = _attestation(root, manifest, validated_sha)
    mismatched["contracts"][0]["manifest_hash"] = "sha256-contract:wrong"
    mismatched_result = _verify(mismatched, root, delivered_ref)
    narrowed = _attestation(root, manifest, validated_sha)
    narrowed["contracts"][0]["covered_files"].pop("src/app.py")
    narrowed_result = _verify(narrowed, root, delivered_ref)
    tampered = _attestation(root, manifest, validated_sha)
    tampered["contracts"][0]["covered_files"]["src/app.py"] = "sha256:" + ("0" * 64)
    tampered_result = _verify(tampered, root, delivered_ref)
    raw_sha_result = _verify(
        _attestation(root, manifest, validated_sha), root, validated_sha
    )
    _git(root, "checkout", "-q", "-b", "malformed-delivery", "validated")
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "goal: Bind delivery bytes\n",
        encoding="utf-8",
    )
    _git(root, "add", "manifests/task.manifest.yaml")
    _git(root, "commit", "-m", "duplicate manifest key")
    malformed_result = _verify(
        _attestation(root, manifest, validated_sha), root, "malformed-delivery"
    )
    _git(root, "checkout", "-q", delivered_ref)
    args = build_parser().parse_args(
        ["verify", "--delivered", delivered_ref, "--attestation", "proof.json"]
    )

    assert missing["success"] is False
    assert missing["errors"][0]["code"] == "E713"
    assert mismatched_result["success"] is False
    assert mismatched_result["errors"][0]["code"] == "E713"
    assert narrowed_result["success"] is False
    assert narrowed_result["errors"][0]["code"] == "E713"
    assert tampered_result["success"] is False
    assert tampered_result["errors"][0]["code"] == "E713"
    assert raw_sha_result["success"] is False
    assert raw_sha_result["errors"][0]["code"] == "E714"
    assert malformed_result["success"] is False
    assert malformed_result["errors"][0]["code"] == "E713"
    assert args.delivered == delivered_ref
    assert args.attestation == "proof.json"
    assert callable(cmd_verify)
    assert ErrorCode.DELIVERY_ATTESTATION_INVALID.value == "E713"
    assert ErrorCode.DELIVERED_CONTENT_MISMATCH.value == "E714"
    assert get_rule("E713").next_action is not None
    assert get_rule("E714").next_action is not None

    proof_path = root / "delivery-proof.json"
    proof_path.write_text(
        _render(_attestation(root, manifest, validated_sha)), encoding="utf-8"
    )
    cli_args = build_parser().parse_args(
        [
            "verify",
            "--no-changed-scope",
            "--delivered",
            delivered_ref,
            "--attestation",
            str(proof_path),
            "--json",
        ]
    )
    monkeypatch.setattr(
        verify_command,
        "_run_verify",
        lambda **_kwargs: VerificationResult(stages=()),
    )
    monkeypatch.chdir(root)

    cli_exit_code = cmd_verify(cli_args)
    cli_payload = json.loads(capsys.readouterr().out)

    assert cli_exit_code == 0
    assert cli_payload["success"] is True
    assert cli_payload["stages"][-1]["name"] == "delivery_attestation"
    assert cli_payload["delivery_provenance"]["validation"]["success"] is True

    valid_proof = proof_path.read_text(encoding="utf-8")
    duplicate_top_level = valid_proof.replace(
        '"schema":',
        '"schema": "maid-delivery-provenance/v1", "schema":',
        1,
    )
    proof_payload = json.loads(valid_proof)
    app_digest = proof_payload["contracts"][0]["covered_files"]["src/app.py"]
    app_entry = f'"src/app.py": "{app_digest}"'
    duplicate_covered_path = valid_proof.replace(
        app_entry,
        f"{app_entry}, {app_entry}",
        1,
    )
    nonstandard_constant = valid_proof.rstrip()[:-1] + ', "ignored": NaN}'
    for invalid_proof in (
        duplicate_top_level,
        duplicate_covered_path,
        nonstandard_constant,
    ):
        proof_path.write_text(invalid_proof, encoding="utf-8")
        invalid_exit_code = cmd_verify(cli_args)
        invalid_payload = json.loads(capsys.readouterr().out)

        assert invalid_exit_code == 1
        assert invalid_payload["stages"][-1]["details"]["errors"][0]["code"] == ("E713")

    proof_path.write_bytes(b"\xff")
    invalid_utf8_exit_code = cmd_verify(cli_args)
    invalid_utf8_payload = json.loads(capsys.readouterr().out)

    assert invalid_utf8_exit_code == 1
    assert invalid_utf8_payload["stages"][-1]["details"]["errors"][0]["code"] == (
        "E713"
    )


def test_ref_adding_only_uncovered_files_still_passes(tmp_path: Path) -> None:
    root, manifest, validated_sha = _project(tmp_path)
    attestation = _attestation(root, manifest, validated_sha)
    delivered_ref = _delivered_branch(root)
    _write(root / "notes/uncovered.txt", "delivery-only metadata\n")
    _commit(root, "add uncovered file")

    result = _verify(attestation, root, delivered_ref)

    assert result["success"] is True
    assert "notes/uncovered.txt" not in attestation["contracts"][0]["covered_files"]


def test_provenance_record_is_independently_recomputable(tmp_path: Path) -> None:
    root, manifest, validated_sha = _project(tmp_path)
    attestation = _attestation(root, manifest, validated_sha)
    delivered_ref = _delivered_branch(root)
    verification = _verify(attestation, root, delivered_ref)

    record = json.loads(_render(attestation, verification))

    assert record["schema"] == "maid-delivery-provenance/v1"
    assert record["validation"]["success"] is True
    with pytest.raises(ValueError, match="Out of range float values"):
        _render(attestation, {"success": float("nan")})
    for contract in record["contracts"]:
        for path, expected in contract["covered_files"].items():
            shown = subprocess.run(
                ["git", "show", f"{record['validation']['delivered_commit']}:{path}"],
                cwd=root,
                check=False,
                capture_output=True,
            )
            actual = (
                f"sha256:{hashlib.sha256(shown.stdout).hexdigest()}"
                if shown.returncode == 0
                else None
            )
            assert actual == expected


def test_attestation_compare_is_deterministic_and_cwd_independent(
    tmp_path: Path, monkeypatch
) -> None:
    root, manifest, validated_sha = _project(tmp_path)
    delivery = _delivery_module()
    first = delivery.compute_delivery_attestation(root, [manifest], validated_sha)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    second = delivery.compute_delivery_attestation(root, [manifest], validated_sha)
    _git(root, "checkout", "-q", "-b", "delivered")
    first_result = _verify(first, root, "delivered")
    second_result = _verify(second, root, "delivered")

    assert first == second
    assert first_result == second_result
    assert _render(first) == _render(second)
