"""Optional read-only acceptance against the reported consumer's installed SDK.

Set MAID_CSV_ACCEPTANCE_PROJECT to a local consumer checkout. No consumer code,
configuration, manifests or dependency files are edited or executed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from maid_runner.core._implementation_validation import ImplementationFileValidator
from maid_runner.core.ts_return_contracts import check_return_contracts
from maid_runner.core.types import (
    ArgSpec,
    ArtifactKind,
    ArtifactSpec,
    FileMode,
    FileSpec,
    Manifest,
)
from maid_runner.validators.registry import ValidatorRegistry


def _git_status(root):
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    return subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
        env=environment,
    ).stdout


@pytest.mark.parametrize("component", ["CSVImportDialog", "CSVPreviewStep"])
def test_reported_csv_component_return_contracts_are_verified_read_only(
    tmp_path, component
):
    selected = os.environ.get("MAID_CSV_ACCEPTANCE_PROJECT")
    if not selected:
        pytest.skip(
            "Set MAID_CSV_ACCEPTANCE_PROJECT for optional real-consumer acceptance"
        )
    root = Path(selected).resolve(strict=True)
    relative = f"src/components/import/{component}.tsx"
    watched = [root / relative, root / "tsconfig.app.json", root / "package.json"]
    if (root / ".maidrc.yaml").exists():
        watched.append(root / ".maidrc.yaml")
    before = {path: path.read_bytes() for path in watched}
    status = _git_status(root)
    assert (
        root / "node_modules/typescript"
    ).exists(), "Acceptance requires the consumer's installed local TypeScript SDK"
    (tmp_path / "src").symlink_to(root / "src", target_is_directory=True)
    (tmp_path / "node_modules").symlink_to(
        root / "node_modules", target_is_directory=True
    )
    for name in ("package.json", "tsconfig.app.json"):
        (tmp_path / name).write_bytes((root / name).read_bytes())
    config = tmp_path / ".maidrc.yaml"
    config.write_text(
        "typescript_return_contracts:\n  mode: compiler\n  tsconfig: tsconfig.app.json\n"
    )
    source = (root / relative).read_text()
    registry = ValidatorRegistry.with_builtin_validators()
    collection = registry.get(relative).collect_implementation_artifacts(
        source, relative
    )
    assert collection.errors == []
    found = next(
        item
        for item in collection.artifacts
        if item.name == component and item.of is None
    )
    assert found.returns is None and len(found.args) == 1
    assert (
        found.args[0].name.strip().startswith("{")
        and found.args[0].type == f"{component}Props"
    )

    proofs = []

    def checker(*arguments):
        result = check_return_contracts(*arguments)
        proofs.append(result)
        return result

    def validate(parameter=None, returns='import("react/jsx-runtime").JSX.Element'):
        arguments = tuple(
            ArgSpec(parameter if parameter is not None else arg.name, arg.type)
            for arg in found.args
        )
        spec = ArtifactSpec(
            kind=ArtifactKind.FUNCTION, name=component, args=arguments, returns=returns
        )
        file = FileSpec(path=relative, mode=FileMode.EDIT, artifacts=(spec,))
        manifest = Manifest(
            slug="csv-return-acceptance",
            source_path="",
            goal="Read-only reported component acceptance",
            validate_commands=(),
            files_edit=(file,),
        )
        return ImplementationFileValidator(
            tmp_path, registry, return_contract_checker=checker
        ).validate_file_spec(file, manifest, None)

    try:
        assert validate() == []
        installed = json.loads(
            (root / "node_modules/typescript/package.json").read_text()
        )["version"]
        assert proofs[0].compiler_version == installed
        assert proofs[0].config_path == str(tmp_path / "tsconfig.app.json")
        assert isinstance(proofs[0].strict_null_checks, bool)
        assert [error.code.value for error in validate(parameter="props")] == ["E303"]
        assert [error.code.value for error in validate(returns="number")] == ["E302"]
        config.write_text("typescript_return_contracts:\n  mode: syntax\n")
        assert [(error.code.value, error.severity.value) for error in validate()] == [
            ("E304", "warning")
        ]
        after = registry.get(relative).collect_implementation_artifacts(
            source, relative
        )
        assert after.artifacts == collection.artifacts and after.errors == []
    finally:
        assert {path: path.read_bytes() for path in watched} == before
        assert _git_status(root) == status
