"""Focused tests for extracted test_function contract validation helpers."""

import yaml

from maid_runner.core._test_function_contracts import (
    merged_test_function_behavior_requirements,
    validate_test_function_behavior,
    validate_test_function_names,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.validators.registry import ValidatorRegistry


def test_validate_test_function_names_requires_real_test_declarations(tmp_path):
    manifest_yaml = yaml.dump(
        {
            "schema": "2",
            "goal": "test",
            "type": "feature",
            "files": {
                "edit": [
                    {
                        "path": "tests/test_contract.py",
                        "artifacts": [
                            {"kind": "test_function", "name": "test_missing"},
                        ],
                    }
                ]
            },
            "validate": ["echo test"],
        }
    )
    test_file = tmp_path / "tests/test_contract.py"
    test_file.parent.mkdir()
    test_file.write_text("test_missing = None\n")
    manifest_file = tmp_path / "contract.manifest.yaml"
    manifest_file.write_text(manifest_yaml)

    manifest = load_manifest(manifest_file)
    errors = validate_test_function_names(
        manifest,
        tmp_path,
        ValidatorRegistry.with_builtin_validators(),
    )

    assert [e.code for e in errors] == [ErrorCode.TEST_FUNCTION_MISSING_IN_CODE]


def test_validate_test_function_behavior_scopes_api_call_to_named_body(tmp_path):
    manifest_yaml = yaml.dump(
        {
            "schema": "2",
            "goal": "test",
            "type": "feature",
            "files": {
                "edit": [
                    {
                        "path": "tests/api.test.ts",
                        "artifacts": [
                            {
                                "kind": "test_function",
                                "name": "test_login",
                                "test_function_details": {
                                    "actions": [
                                        {
                                            "type": "api_call",
                                            "subject": {"export": "doLogin"},
                                            "endpoint": "/api/v1/login",
                                        }
                                    ],
                                },
                            },
                            {
                                "kind": "test_function",
                                "name": "test_logout",
                                "test_function_details": {
                                    "actions": [
                                        {
                                            "type": "api_call",
                                            "subject": {"export": "doLogout"},
                                            "endpoint": "/api/v1/logout",
                                        }
                                    ],
                                },
                            },
                        ],
                    }
                ]
            },
            "validate": ["echo test"],
        }
    )
    test_file = tmp_path / "tests/api.test.ts"
    test_file.parent.mkdir()
    test_file.write_text(
        'it("test_login", () => {\n'
        '  doLogin("/api/v1/login");\n'
        '  doLogout("/api/v1/logout");\n'
        "});\n"
        'it("test_logout", () => {\n'
        "  expect(true).toBe(true);\n"
        "});\n"
    )
    manifest_file = tmp_path / "contract.manifest.yaml"
    manifest_file.write_text(manifest_yaml)

    manifest = load_manifest(manifest_file)
    errors = validate_test_function_behavior(
        manifest,
        tmp_path,
        ValidatorRegistry.with_builtin_validators(),
    )

    messages = [error.message for error in errors]
    assert any("test_logout" in message and "doLogout" in message for message in messages)
    assert any(
        "test_logout" in message and "/api/v1/logout" in message
        for message in messages
    )
    assert not any("test_login" in message for message in messages)


def test_merged_test_function_behavior_requirements_preserves_historical_details(
    tmp_path,
):
    manifest_a = yaml.dump(
        {
            "schema": "2",
            "goal": "first",
            "type": "feature",
            "created": "2026-04-01",
            "files": {
                "edit": [
                    {
                        "path": "tests/shared.test.ts",
                        "artifacts": [
                            {
                                "kind": "test_function",
                                "name": "test_api_call",
                                "test_function_details": {
                                    "actions": [
                                        {
                                            "type": "api_call",
                                            "subject": {"export": "createLogin"},
                                            "endpoint": "/api/v1/auth/login",
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ]
            },
            "validate": ["echo a"],
        }
    )
    manifest_b = yaml.dump(
        {
            "schema": "2",
            "goal": "second",
            "type": "feature",
            "created": "2026-04-10",
            "files": {
                "edit": [
                    {
                        "path": "tests/shared.test.ts",
                        "artifacts": [
                            {"kind": "test_function", "name": "test_api_call"},
                        ],
                    }
                ]
            },
            "validate": ["echo b"],
        }
    )
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    (manifests_dir / "a.manifest.yaml").write_text(manifest_a)
    (manifests_dir / "b.manifest.yaml").write_text(manifest_b)

    chain = ManifestChain(manifests_dir, tmp_path)
    manifest = load_manifest(manifests_dir / "b.manifest.yaml")
    requirements = merged_test_function_behavior_requirements(manifest, chain)

    details = requirements["tests/shared.test.ts"]["test_api_call"]
    assert details is not None
    assert details.actions == (
        {
            "type": "api_call",
            "subject": {"export": "createLogin"},
            "endpoint": "/api/v1/auth/login",
        },
    )
