"""Behavioral coverage for Foundry Solidity test discovery."""

from pathlib import Path

from maid_runner.core._file_discovery import discover_source_files, is_test_file
from maid_runner.core._validation_test_artifacts import collect_test_artifacts
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry


class _SolidityValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".sol",)

    def collect_implementation_artifacts(
        self, source: str, file_path: str | Path
    ) -> CollectionResult:
        return CollectionResult([], "solidity", str(file_path))

    def collect_behavioral_artifacts(
        self, source: str, file_path: str | Path
    ) -> CollectionResult:
        return CollectionResult(
            [FoundArtifact(kind="method", name="deposit", of="Vault")],
            "solidity",
            str(file_path),
        )


def test_source_discovery_and_test_classification_support_foundry_solidity(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "src" / "Vault.sol").write_text("contract Vault {}", encoding="utf-8")
    (tmp_path / "test" / "Vault.t.sol").write_text(
        "contract VaultTest {}", encoding="utf-8"
    )

    discovered = discover_source_files(tmp_path)

    assert discovered == ["src/Vault.sol", "test/Vault.t.sol"]
    assert is_test_file("test/Vault.t.sol") is True
    assert is_test_file("src/VaultTest.sol") is False
    assert is_test_file("test/Vault.test.sol") is False


def test_test_artifact_collection_routes_t_sol_files_to_registered_validator(
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "test" / "Vault.t.sol"
    test_file.parent.mkdir()
    test_file.write_text("contract VaultTest {}", encoding="utf-8")
    registry = ValidatorRegistry()
    registry.register(_SolidityValidator)
    errors = []

    collected = collect_test_artifacts(["test/Vault.t.sol"], tmp_path, registry, errors)

    assert errors == []
    assert [artifact.qualified_name for artifact in collected["test/Vault.t.sol"]] == [
        "Vault.deposit"
    ]
