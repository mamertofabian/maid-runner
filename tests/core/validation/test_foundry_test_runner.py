"""Behavioral coverage for Foundry test command integrity."""

from pathlib import Path

from maid_runner.core._validation_test_artifacts import validate_manifest_test_commands
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


def _write_foundry_project(root: Path, command: str) -> Path:
    test_path = "test/Vault.t.sol"
    test_file = root / test_path
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "contract VaultTest { function testDeposit() public {} }\n",
        encoding="utf-8",
    )
    manifest_path = root / "manifests" / "foundry.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        'schema: "2"\n'
        'goal: "Validate an explicit Foundry behavioral test"\n'
        "type: fix\n"
        'created: "2026-10-01T00:00:00Z"\n'
        "files:\n"
        "  create:\n"
        f"    - path: {test_path}\n"
        "      artifacts:\n"
        "        - kind: test_function\n"
        "          name: testDeposit\n"
        "validate:\n"
        f"  - [{command}]\n",
        encoding="utf-8",
    )
    return manifest_path


def test_command_integrity_accepts_forge_test_for_foundry_file(
    tmp_path: Path,
) -> None:
    manifest_path = _write_foundry_project(
        tmp_path, "forge, test, --match-path, test/Vault.t.sol"
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert errors == []


def test_command_integrity_rejects_non_test_forge_subcommand(
    tmp_path: Path,
) -> None:
    manifest_path = _write_foundry_project(tmp_path, "forge, build, test/Vault.t.sol")

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
