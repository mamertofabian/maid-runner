"""Node module test inputs must remain protected by the behavioral contract."""

from pathlib import Path

import pytest
import yaml

from maid_runner.core._command_integrity_test_discovery import (
    is_command_integrity_test_file,
)
from maid_runner.core._file_discovery import is_test_file
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.result import ErrorCode


@pytest.mark.parametrize("extension", ["mjs", "cjs"])
@pytest.mark.parametrize("pattern", ["test", "spec"])
@pytest.mark.parametrize("directory", ["tests/tooling", "src"])
def test_module_test_names_are_behavioral_inputs(
    tmp_path: Path, extension: str, pattern: str, directory: str
) -> None:
    path = f"{directory}/boundary.{pattern}.{extension}"

    assert is_test_file(path)
    assert is_command_integrity_test_file(path, tmp_path)
    assert not is_test_file(f"{directory}/boundary.{extension}")
    assert not is_command_integrity_test_file(
        f"{directory}/boundary.{extension}", tmp_path
    )


@pytest.mark.parametrize("extension", ["mjs", "cjs"])
@pytest.mark.parametrize("selection", ["explicit", "directory", "read", "create"])
@pytest.mark.parametrize("mutation", ["edit", "delete"])
def test_plan_lock_detects_module_test_changes(
    tmp_path: Path, extension: str, selection: str, mutation: str
) -> None:
    test_path = f"src/boundary.test.{extension}"
    test_file = tmp_path / test_path
    test_file.parent.mkdir()
    test_file.write_text(
        "import test from 'node:test';\n"
        "import assert from 'node:assert/strict';\n"
        "test('boundary', () => { assert.equal(1, 2); });\n"
        if extension == "mjs"
        else "const test = require('node:test');\n"
        "const assert = require('node:assert/strict');\n"
        "test('boundary', () => { assert.equal(1, 2); });\n"
    )
    files = {"scope": [{"path": "src/service.js", "reason": "Production wiring"}]}
    (tmp_path / "src/service.js").write_text("export const value = 1;\n")
    if selection == "directory":
        files["read"] = ["src"]
    elif selection == "read":
        files["read"] = [test_path]
    elif selection == "create":
        files["create"] = [
            {
                "path": test_path,
                "artifacts": [{"kind": "test_function", "name": "boundary"}],
            }
        ]
    selector = test_path
    if selection in {"directory", "read", "create"}:
        (tmp_path / "unrelated").mkdir()
        selector = "unrelated"
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    manifest_path = manifest_dir / "node-boundary.manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Protect Node module behavioral inputs",
                "type": "fix",
                "created": "2026-09-28",
                "files": files,
                "validate": [["node", "--test", selector]],
            }
        )
    )

    lock = create_plan_lock(manifest_path, tmp_path)

    assert set(lock.test_hashes) == {test_path}
    lock.save(default_plan_lock_path(tmp_path, "node-boundary"))
    chain = ManifestChain(manifest_dir, tmp_path)
    assert (
        enforce_plan_locks(
            chain, tmp_path, require_plan_lock=True, require_red_evidence=False
        )
        == ()
    )
    if mutation == "edit":
        test_file.write_text(
            test_file.read_text().replace("equal(1, 2)", "equal(1, 1)")
        )
    else:
        test_file.unlink()

    errors = enforce_plan_locks(
        chain, tmp_path, require_plan_lock=True, require_red_evidence=False
    )

    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in {
        error.code for error in errors
    }


def test_direct_node_test_command_covers_module_tests(tmp_path: Path) -> None:
    from maid_runner.core._validation_test_artifacts import (
        validate_manifest_test_commands,
    )
    from maid_runner.core.manifest import load_manifest

    manifest_path = _write_node_command_project(
        tmp_path, ["node", "--test", "tests/boundary.test.mjs"]
    )

    assert validate_manifest_test_commands(load_manifest(manifest_path), tmp_path) == []
    lock = create_plan_lock(manifest_path, tmp_path)
    assert set(lock.test_hashes) == {"tests/boundary.test.mjs"}


@pytest.mark.parametrize(
    "prefix",
    [
        ["node"],
        ["node", "script.js", "--test"],
        ["node", "--test", "--help"],
        ["node", "--test", "--check"],
        ["node", "--test", "--test-only"],
        ["node", "--test", "--test-name-pattern=missing"],
        ["node", "--test", "--test-skip-pattern=boundary"],
        ["node", "--test", "--test-shard=1/2"],
        ["node", "--test", "--test-reporter-destination"],
        ["node", "--test", "--eval"],
    ],
)
def test_node_commands_that_do_not_prove_full_execution_are_rejected(
    tmp_path: Path, prefix: list[str]
) -> None:
    from maid_runner.core._validation_test_artifacts import (
        validate_manifest_test_commands,
    )
    from maid_runner.core.manifest import load_manifest

    manifest_path = _write_node_command_project(
        tmp_path, [*prefix, "tests/boundary.test.mjs"]
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_manifest_tests_execute_direct_node_module_suite(tmp_path: Path) -> None:
    import shutil

    from maid_runner.core.test_runner import run_manifest_tests

    if shutil.which("node") is None:
        pytest.skip("Node is needed only for the native execution smoke test")
    manifest_path = _write_node_command_project(
        tmp_path, ["node", "--test", "tests/boundary.test.mjs"]
    )

    result = run_manifest_tests(manifest_path, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (1, 1, 0)
    assert (tmp_path / "executed.txt").read_text() == "boundary"


def _write_node_command_project(root: Path, command: list[str]) -> Path:
    (root / "tests").mkdir()
    (root / "tests/boundary.test.mjs").write_text(
        "import test from 'node:test';\n"
        "import assert from 'node:assert/strict';\n"
        "import { writeFileSync } from 'node:fs';\n"
        "test('boundary', () => { assert.equal(2 + 2, 4); "
        "writeFileSync('executed.txt', 'boundary'); });\n"
    )
    manifest_path = root / "node-command.manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Run a direct Node module suite",
                "type": "fix",
                "created": "2026-09-28",
                "files": {
                    "scope": [{"path": "src/service.js", "reason": "Production"}],
                    "read": ["tests/boundary.test.mjs"],
                },
                "validate": [command],
            }
        )
    )
    return manifest_path


@pytest.mark.parametrize("target", ["tests", "tests/directory.test.mjs"])
def test_node_directory_targets_do_not_cover_nested_tests(
    tmp_path: Path, target: str
) -> None:
    from maid_runner.core._validation_test_artifacts import (
        validate_manifest_test_commands,
    )
    from maid_runner.core.manifest import load_manifest

    manifest_path = _write_node_command_project(tmp_path, ["node", "--test", target])
    (tmp_path / "tests/directory.test.mjs").mkdir()

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


@pytest.mark.parametrize(
    "command",
    [
        ["sh", "-c", "node --test tests"],
        ["sh", "-c", "node --test tests/boundary.test.mjs"],
        [
            "sh",
            "-c",
            "NODE_OPTIONS=--test-name-pattern=missing node --test tests/boundary.test.mjs",
        ],
        [
            "env",
            "NODE_OPTIONS=--test-name-pattern=missing",
            "node",
            "--test",
            "tests/boundary.test.mjs",
        ],
        [
            "env",
            "NODE_OPTIONS=--test-name-pattern=missing",
            "uv",
            "run",
            "node",
            "--test",
            "tests/boundary.test.mjs",
        ],
        ["uv", "run", "node", "--test", "tests/boundary.test.mjs"],
    ],
)
def test_wrapped_node_commands_cannot_claim_execution_coverage(
    tmp_path: Path, command: list[str]
) -> None:
    from maid_runner.core._validation_test_artifacts import (
        validate_manifest_test_commands,
    )
    from maid_runner.core.manifest import load_manifest

    manifest_path = _write_node_command_project(tmp_path, command)
    (tmp_path / "tests/index.js").write_text(
        "// Directory entry point runs no tests.\n"
    )
    test_file = tmp_path / "tests/boundary.test.mjs"
    test_file.write_text(
        test_file.read_text().replace("equal(2 + 2, 4)", "equal(2 + 2, 5)")
    )

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]


def test_inherited_node_options_cannot_hide_a_failing_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from maid_runner.core.test_runner import run_manifest_tests

    if shutil.which("node") is None:
        pytest.skip("Node is needed for the native inherited-environment regression")
    manifest_path = _write_node_command_project(
        tmp_path, ["node", "--test", "tests/boundary.test.mjs"]
    )
    test_file = tmp_path / "tests/boundary.test.mjs"
    test_file.write_text(
        test_file.read_text().replace("equal(2 + 2, 4)", "equal(2 + 2, 5)")
    )
    monkeypatch.setenv("NODE_OPTIONS", "--test-name-pattern=missing")

    result = run_manifest_tests(manifest_path, project_root=tmp_path)

    assert (result.total, result.passed, result.failed) == (1, 0, 1)


@pytest.mark.parametrize(
    "name",
    ["[x].test.mjs", "{x,y}.test.mjs", "@(x).test.mjs", "x?.test.mjs", "x*.test.mjs"],
)
def test_node_glob_names_cannot_claim_literal_file_coverage(
    tmp_path: Path, name: str
) -> None:
    from maid_runner.core._validation_test_artifacts import (
        validate_manifest_test_commands,
    )
    from maid_runner.core.manifest import load_manifest
    from maid_runner.core.test_runner import run_manifest_tests

    target = f"tests/{name}"
    manifest_path = _write_node_command_project(tmp_path, ["node", "--test", target])
    literal_file = tmp_path / target
    original = tmp_path / "tests/boundary.test.mjs"
    literal_file.write_text(
        original.read_text().replace("equal(2 + 2, 4)", "equal(2 + 2, 5)")
    )
    (tmp_path / "tests/x.test.mjs").write_text(original.read_text())
    data = yaml.safe_load(manifest_path.read_text())
    data["files"]["read"] = [target]
    manifest_path.write_text(yaml.safe_dump(data))

    errors = validate_manifest_test_commands(load_manifest(manifest_path), tmp_path)

    assert [error.code for error in errors] == [
        ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS
    ]
    result = run_manifest_tests(manifest_path, project_root=tmp_path)
    assert result.total == 0
    assert not (tmp_path / "executed.txt").exists()
