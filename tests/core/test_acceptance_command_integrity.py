from pathlib import Path

import yaml

from maid_runner.core._validation_test_artifacts import (
    validate_manifest_test_commands,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode


def _write_test(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("test('behavior', () => expect(true).toBe(true));\n")


def _write_manifest(
    project_root: Path,
    *,
    declared_tests: list[str],
    acceptance_command: str,
) -> Path:
    manifest_dir = project_root / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "acceptance-integrity.manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Keep acceptance tests outside the fast gate",
                "type": "fix",
                "files": {
                    "edit": [
                        {
                            "path": "src/example.ts",
                            "artifacts": [{"kind": "function", "name": "example"}],
                        }
                    ],
                    "create": [
                        {
                            "path": test_path,
                            "artifacts": [
                                {"kind": "test_function", "name": "behavior"}
                            ],
                        }
                        for test_path in declared_tests
                    ],
                    "read": ["tests/example.test.ts"],
                },
                "validate": ["bunx vitest run tests/example.test.ts"],
                "acceptance": {"tests": [acceptance_command]},
            }
        )
    )
    return manifest_path


def test_acceptance_targeted_e2e_file_is_not_required_in_validate(
    tmp_path: Path,
) -> None:
    _write_test(tmp_path / "tests/example.test.ts")
    _write_test(tmp_path / "e2e/example.spec.ts")
    manifest_path = _write_manifest(
        tmp_path,
        declared_tests=["e2e/example.spec.ts"],
        acceptance_command="bunx playwright test e2e/example.spec.ts",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert errors == []


def test_uncovered_declared_test_still_requires_validate_coverage(
    tmp_path: Path,
) -> None:
    _write_test(tmp_path / "tests/example.test.ts")
    _write_test(tmp_path / "e2e/covered.spec.ts")
    _write_test(tmp_path / "test/uncovered.spec.ts")
    manifest_path = _write_manifest(
        tmp_path,
        declared_tests=["e2e/covered.spec.ts", "test/uncovered.spec.ts"],
        acceptance_command="bunx playwright test e2e/covered.spec.ts",
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    assert "test/uncovered.spec.ts" in errors[0].message
    assert "e2e/covered.spec.ts" not in errors[0].message
