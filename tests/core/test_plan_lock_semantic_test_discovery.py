"""Plan-lock regression coverage for production modules with test-like names."""

from __future__ import annotations

from pathlib import Path

import yaml

from maid_runner.core.plan_lock import create_plan_lock


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

    lock = create_plan_lock(manifest_path, tmp_path)

    assert lock.test_hashes.keys() == {behavioral_path}
