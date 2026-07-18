"""Behavioral coverage for Django app-level tests.py recognition."""

from __future__ import annotations

from pathlib import Path

import yaml

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core.manifest import load_manifest, validate_manifest_paths
from maid_runner.core.plan_lock import create_plan_lock
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import validate


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _e200_errors(result) -> list:
    return [
        error
        for error in result.errors
        if error.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
    ]


def test_is_test_file_recognizes_django_tests_py() -> None:
    assert is_test_file("tests.py") is True
    assert is_test_file("importer/tests.py") is True


def test_is_test_file_rejects_similar_non_test_names() -> None:
    assert is_test_file("mytests.py") is False
    assert is_test_file("tests_util.py") is False
    assert is_test_file("test.py") is False
    assert is_test_file("tests.txt") is False


def test_behavioral_validation_sees_artifacts_used_in_django_tests_py(
    tmp_path: Path,
) -> None:
    artifact_path = "app/services.py"
    tests_path = "app/tests.py"
    _write(
        tmp_path / artifact_path,
        "def greet(name: str) -> str:\n    return f'hello {name}'\n",
    )
    _write(
        tmp_path / tests_path,
        (
            "from app.services import greet\n\n\n"
            "def test_greet():\n"
            "    assert greet('world') == 'hello world'\n"
        ),
    )
    manifest_path = _write(
        tmp_path / "manifests" / "django-app.manifest.yaml",
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Cover a Django app artifact through app/tests.py",
                "type": "fix",
                "created": "2026-07-18T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": artifact_path,
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "greet",
                                    "args": [{"name": "name", "type": "str"}],
                                    "returns": "str",
                                }
                            ],
                        }
                    ],
                    "read": [tests_path],
                },
                "validate": [f"python -m pytest -q {tests_path}"],
            },
            sort_keys=False,
        ),
    )

    used_result = validate(
        manifest_path,
        mode=ValidationMode.BEHAVIORAL,
        use_chain=False,
        project_root=tmp_path,
    )
    assert _e200_errors(used_result) == []

    _write(tmp_path / tests_path, "def test_placeholder():\n    assert True\n")
    unused_result = validate(
        manifest_path,
        mode=ValidationMode.BEHAVIORAL,
        use_chain=False,
        project_root=tmp_path,
    )
    assert any(
        error.location.file == artifact_path for error in _e200_errors(unused_result)
    )


def test_plan_lock_hashes_django_tests_py_as_behavioral_test(tmp_path: Path) -> None:
    artifact_path = "app/services.py"
    tests_path = "app/tests.py"
    _write(
        tmp_path / artifact_path,
        "def greet(name: str) -> str:\n    return f'hello {name}'\n",
    )
    _write(
        tmp_path / tests_path,
        (
            "from app.services import greet\n\n\n"
            "def test_greet():\n"
            "    assert greet('world') == 'hello world'\n"
        ),
    )
    manifest_path = _write(
        tmp_path / "manifests" / "django-lock.manifest.yaml",
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Lock a Django app whose only behavioral test is tests.py",
                "type": "fix",
                "created": "2026-07-18T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": artifact_path,
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "greet",
                                    "args": [{"name": "name", "type": "str"}],
                                    "returns": "str",
                                }
                            ],
                        }
                    ],
                    "read": [tests_path],
                },
                "validate": [f"python -m pytest -q {tests_path}"],
            },
            sort_keys=False,
        ),
    )

    lock = create_plan_lock(manifest_path, tmp_path)

    assert tests_path in lock.test_hashes


def test_manifest_path_validation_classifies_django_tests_py(tmp_path: Path) -> None:
    """Private classifier must see tests.py so validate-command escapes are checked."""
    project = tmp_path / "project"
    project.mkdir()
    escaped = "../escape/tests.py"
    manifest_path = _write(
        project / "manifests" / "escape-tests.manifest.yaml",
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Classify Django tests.py in validate-command path checks",
                "type": "fix",
                "created": "2026-07-18T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": "app/services.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "greet",
                                    "args": [{"name": "name", "type": "str"}],
                                    "returns": "str",
                                }
                            ],
                        }
                    ]
                },
                "validate": [f"python custom_harness.py {escaped}"],
            },
            sort_keys=False,
        ),
    )

    errors = validate_manifest_paths(load_manifest(manifest_path), project)

    assert any(
        error.code == ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT
        and error.location is not None
        and error.location.file == escaped
        for error in errors
    )
