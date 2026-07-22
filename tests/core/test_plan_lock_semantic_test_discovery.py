"""Plan-lock regression coverage for production modules with test-like names."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.result import ErrorCode


def test_create_plan_lock_excludes_test_prefixed_production_module_without_pytest_tests(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src" / "prompts").mkdir(parents=True)
    (tmp_path / "quality").mkdir()
    production_path = "src/prompts/test_catalog.py"
    behavioral_path = "quality/test_prompt_contract.py"
    (tmp_path / production_path).write_text(
        "def get_test_cases_user_prompt(value: str) -> str:\n"
        "    return f'prompt: {value}'\n"
    )
    (tmp_path / behavioral_path).write_text(
        "from src.prompts.test_catalog import "
        "get_test_cases_user_prompt\n\n\n"
        "def test_prompt_contract():\n"
        "    assert get_test_cases_user_prompt('case') == 'prompt: case'\n"
    )
    manifest_path = tmp_path / "manifests" / "prompt-task.manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Change a production prompt module with a test-like name",
                "type": "fix",
                "created": "2026-07-09T22:24:43Z",
                "files": {
                    "edit": [
                        {
                            "path": production_path,
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "get_test_cases_user_prompt",
                                    "args": [{"name": "value", "type": "str"}],
                                    "returns": "str",
                                }
                            ],
                        }
                    ]
                },
                "validate": [f"python -m pytest -q {behavioral_path}"],
            },
            sort_keys=False,
        )
    )

    lock = create_plan_lock(manifest_path, tmp_path)

    assert lock.test_hashes.keys() == {behavioral_path}
    assert production_path not in lock.test_hashes


def test_create_plan_lock_keeps_unparseable_test_like_file_fail_closed(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "quality").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo.py").write_text("def demo() -> str:\n    return 'demo'\n")
    behavioral_path = "quality/test_broken_contract.py"
    (tmp_path / behavioral_path).write_text("def test_broken(:\n")
    manifest_path = tmp_path / "manifests" / "broken-test-task.manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Seal an unparseable behavioral test fail closed",
                "type": "fix",
                "created": "2026-07-09T22:24:43Z",
                "files": {
                    "edit": [
                        {
                            "path": "src/demo.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "demo",
                                    "args": [],
                                    "returns": "str",
                                }
                            ],
                        }
                    ],
                    "read": [behavioral_path],
                },
                "validate": [f"python -m pytest -q {behavioral_path}"],
            },
            sort_keys=False,
        )
    )

    with pytest.raises(SyntaxError):
        create_plan_lock(manifest_path, tmp_path)


def test_enforce_plan_lock_ignores_legacy_false_positive_test_hash_entry(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    production_path = "src/test_runner.py"
    ambiguous_production_path = "src/test_helpers.py"
    mixed_test_path = "src/test_mixed_contract.py"
    behavioral_path = "tests/test_runner_contract.py"
    production_file = tmp_path / production_path
    production_source = (
        "def run_tests() -> tuple[str, ...]:\n"
        "    results = ('passed',)\n"
        "    return results\n"
    )
    production_file.write_text(production_source)
    ambiguous_production_file = tmp_path / ambiguous_production_path
    ambiguous_production_file.write_text(
        "def build_test_helper() -> str:\n    value = 'helper'\n    return value\n"
    )
    mixed_test_source = (
        "def build_fixture() -> str:\n"
        "    value = 'fixture'\n"
        "    return value\n\n\n"
        "def test_mixed_contract():\n"
        "    assert build_fixture() == 'fixture'\n"
    )
    mixed_test_file = tmp_path / mixed_test_path
    mixed_test_file.write_text(mixed_test_source)
    (tmp_path / behavioral_path).write_text(
        "from src.test_runner import run_tests\n\n\n"
        "def test_run_tests_contract():\n"
        "    assert run_tests() == ('passed',)\n"
    )
    manifest_path = tmp_path / "manifests" / "runner-task.manifest.yaml"
    manifest_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Change a production runner with a test-like name",
                "type": "fix",
                "created": "2026-07-09T22:24:43Z",
                "files": {
                    "edit": [
                        {
                            "path": production_path,
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "run_tests",
                                    "args": [],
                                    "returns": "tuple[str, ...]",
                                }
                            ],
                        },
                        {
                            "path": mixed_test_path,
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "build_fixture",
                                    "args": [],
                                    "returns": "str",
                                }
                            ],
                        },
                    ],
                    "read": [behavioral_path, ambiguous_production_path],
                },
                "validate": [
                    f"python -m pytest -q {behavioral_path} "
                    f"{mixed_test_path}::test_mixed_contract"
                ],
            },
            sort_keys=False,
        )
    )
    lock = create_plan_lock(manifest_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "runner-task")
    lock.save(lock_path)
    payload = json.loads(lock_path.read_text())
    payload["test_hashes"][production_path] = (
        "sha256:" + hashlib.sha256(production_file.read_bytes()).hexdigest()
    )
    payload["test_hashes"][ambiguous_production_path] = (
        "sha256:" + hashlib.sha256(ambiguous_production_file.read_bytes()).hexdigest()
    )
    payload["_manifest_contract"]["test_files"].extend(
        [production_path, ambiguous_production_path]
    )
    lock_path.write_text(json.dumps(payload, indent=2))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert errors == ()

    scoped_manifest = yaml.safe_load(manifest_path.read_text())
    scoped_manifest["files"]["read"] = [behavioral_path]
    scoped_manifest["files"]["scope"] = [
        {
            "path": ambiguous_production_path,
            "reason": "Keep the unchanged historical helper in task scope",
        }
    ]
    manifest_path.write_text(yaml.safe_dump(scoped_manifest, sort_keys=False))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert errors == ()

    production_file.write_text(
        "def run_tests() -> tuple[str, ...]:\n"
        "    results = ('changed',)\n"
        "    return results\n"
    )

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in {
        error.code for error in errors
    }

    production_file.write_text(production_source)

    production_file.unlink()
    production_file.mkdir()

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in {
        error.code for error in errors
    }

    production_file.rmdir()
    production_file.write_text(production_source)

    mixed_test_file.write_text(
        "def build_fixture() -> str:\n    value = 'fixture'\n    return value\n"
    )

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in {
        error.code for error in errors
    }

    mixed_test_file.write_text(mixed_test_source)

    (tmp_path / behavioral_path).write_text(
        "def contract_helper() -> bool:\n    result = True\n    return result\n"
    )

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in {
        error.code for error in errors
    }


def test_enforce_plan_lock_keeps_implicit_root_historical_tests_fail_closed(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "demo.py").write_text(
        "def demo() -> str:\n    value = 'demo'\n    return value\n"
    )
    legacy_path = "tests/test_legacy_unittest.py"
    current_path = "tests/test_current_contract.py"
    legacy_file = tmp_path / legacy_path
    legacy_file.write_text(
        "import unittest\n\n\n"
        "class ContractCase(unittest.TestCase):\n"
        "    def test_contract(self):\n"
        "        self.assertTrue(True)\n"
    )
    (tmp_path / current_path).write_text(
        "from src.demo import demo\n\n\n"
        "def test_current_contract():\n"
        "    assert demo() == 'demo'\n"
    )
    manifest_path = tmp_path / "manifests" / "implicit-root.manifest.yaml"
    manifest = {
        "schema": "2",
        "goal": "Protect implicit-root historical tests",
        "type": "fix",
        "created": "2026-07-09T22:24:43Z",
        "files": {
            "edit": [
                {
                    "path": "src/demo.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "demo",
                            "args": [],
                            "returns": "str",
                        }
                    ],
                }
            ],
            "read": [legacy_path, current_path],
        },
        "validate": ["cd tests && python -m pytest -q"],
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    lock = create_plan_lock(manifest_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "implicit-root")
    lock.save(lock_path)
    payload = json.loads(lock_path.read_text())
    payload["test_hashes"][legacy_path] = (
        "sha256:" + hashlib.sha256(legacy_file.read_bytes()).hexdigest()
    )
    payload["_manifest_contract"]["test_files"].append(legacy_path)
    lock_path.write_text(json.dumps(payload, indent=2))

    manifest["validate"] = [f"python -m pytest -q {current_path}"]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK in {
        error.code for error in errors
    }

    original_contract = dict(payload["_manifest_contract"])
    for field in ("validate_commands", "test_files"):
        payload["_manifest_contract"] = dict(original_contract)
        payload["_manifest_contract"][field] = []
        lock_path.write_text(json.dumps(payload, indent=2))

        errors = enforce_plan_locks(
            ManifestChain(tmp_path / "manifests", tmp_path),
            tmp_path,
            require_plan_lock=True,
            require_red_evidence=False,
        )

        assert ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK in {
            error.code for error in errors
        }

    locked_command = original_contract["validate_commands"][0]
    payload["_manifest_contract"] = dict(original_contract)
    payload["_manifest_contract"]["validate_commands"] = [
        locked_command,
        locked_command,
    ]
    lock_path.write_text(json.dumps(payload, indent=2))
    manifest["validate"] = [locked_command]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK in {
        error.code for error in errors
    }

    payload["_manifest_contract"] = original_contract
    lock_path.write_text(json.dumps(payload, indent=2))
    manifest["validate"] = [f"python -m pytest -q {current_path}"]
    manifest["files"]["read"] = [current_path]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK in {
        error.code for error in errors
    }

    for malformed_commands in (
        {"not": "an array"},
        [f"python -m pytest -q {current_path}", 7],
    ):
        payload["_manifest_contract"]["validate_commands"] = malformed_commands
        lock_path.write_text(json.dumps(payload, indent=2))

        errors = enforce_plan_locks(
            ManifestChain(tmp_path / "manifests", tmp_path),
            tmp_path,
            require_plan_lock=True,
            require_red_evidence=False,
        )

        assert ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK in {
            error.code for error in errors
        }


def test_enforce_plan_lock_preserves_parent_relative_selector_coverage_after_cd(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "quality").mkdir()
    (tmp_path / "src" / "demo.py").write_text(
        "def demo() -> str:\n    value = 'demo'\n    return value\n"
    )
    legacy_path = "quality/test_legacy_unittest.py"
    current_path = "tests/test_current_contract.py"
    legacy_file = tmp_path / legacy_path
    legacy_file.write_text(
        "import unittest\n\n\n"
        "class ContractCase(unittest.TestCase):\n"
        "    def test_contract(self):\n"
        "        self.assertTrue(True)\n"
    )
    (tmp_path / current_path).write_text(
        "from src.demo import demo\n\n\n"
        "def test_current_contract():\n"
        "    assert demo() == 'demo'\n"
    )
    manifest_path = tmp_path / "manifests" / "parent-selector.manifest.yaml"
    manifest = {
        "schema": "2",
        "goal": "Protect parent-relative selector tests",
        "type": "fix",
        "created": "2026-07-09T22:24:43Z",
        "files": {
            "edit": [
                {
                    "path": "src/demo.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "demo",
                            "args": [],
                            "returns": "str",
                        }
                    ],
                }
            ],
            "read": [legacy_path, current_path],
        },
        "validate": [
            "cd tests && python -m pytest -q "
            "../quality/test_legacy_unittest.py::ContractCase::test_contract"
        ],
    }
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    lock = create_plan_lock(manifest_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "parent-selector")
    lock.save(lock_path)
    payload = json.loads(lock_path.read_text())
    payload["test_hashes"][legacy_path] = (
        "sha256:" + hashlib.sha256(legacy_file.read_bytes()).hexdigest()
    )
    payload["_manifest_contract"]["test_files"].append(legacy_path)
    lock_path.write_text(json.dumps(payload, indent=2))

    manifest["files"]["read"] = [current_path]
    manifest["validate"] = [f"python -m pytest -q {current_path}"]
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK in {
        error.code for error in errors
    }
