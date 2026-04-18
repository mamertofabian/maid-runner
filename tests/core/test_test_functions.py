"""Tests for test_function artifact support in MAID manifests."""

import json
import tempfile
import pathlib
import pytest
import jsonschema


class TestTestFunctionSchema:
    """Test that test_function kind validates against the JSON schema."""

    @pytest.fixture
    def schema(self):
        schema_path = (
            pathlib.Path(__file__).parents[2]
            / "maid_runner"
            / "schemas"
            / "manifest.v2.schema.json"
        )
        return json.loads(schema_path.read_text())

    def test_test_function_kind_validates(self, schema):
        manifest = {
            "schema": "2",
            "goal": "test",
            "files": {
                "edit": [
                    {
                        "path": "tests/test_auth.test.ts",
                        "artifacts": [
                            {
                                "kind": "test_function",
                                "name": "test_login",
                                "test_function_details": {
                                    "source_scenario": "User logs in",
                                    "tags": ["smoke", "auth"],
                                    "setup": {"auth_required": False},
                                    "actions": [
                                        {
                                            "type": "api_call",
                                            "subject": {
                                                "module": "src/api/auth.ts",
                                                "export": "createLogin",
                                            },
                                            "method": "POST",
                                            "endpoint": "/api/v1/auth/login",
                                        }
                                    ],
                                    "expected": {"response": {"status": 200}},
                                    "dependencies": {"environment": "jsdom"},
                                },
                            }
                        ],
                    }
                ]
            },
            "validate": ["echo test"],
        }
        errors = jsonschema.Draft7Validator(schema).iter_errors(manifest)
        error_msgs = [e.message for e in errors]
        assert not error_msgs, f"Schema validation errors: {error_msgs}"

    def test_test_function_flat_format_validates(self, schema):
        """Test function details at artifact level (not nested)."""
        manifest = {
            "schema": "2",
            "goal": "test",
            "files": {
                "edit": [
                    {
                        "path": "tests/test_auth.py",
                        "artifacts": [
                            {
                                "kind": "test_function",
                                "name": "test_login",
                                "source_scenario": "User logs in",
                                "tags": ["smoke"],
                                "setup": {"auth_required": False},
                                "actions": [],
                                "expected": {},
                                "dependencies": {},
                            }
                        ],
                    }
                ]
            },
            "validate": ["echo test"],
        }
        errors = jsonschema.Draft7Validator(schema).iter_errors(manifest)
        error_msgs = [e.message for e in errors]
        assert not error_msgs, f"Schema validation errors: {error_msgs}"

    def test_backward_compatible_without_test_function(self, schema):
        """Existing manifests without test_function still validate."""
        manifest = {
            "schema": "2",
            "goal": "test",
            "files": {
                "edit": [
                    {
                        "path": "src/greeter.py",
                        "artifacts": [{"kind": "function", "name": "greet"}],
                    }
                ]
            },
            "validate": ["echo test"],
        }
        errors = jsonschema.Draft7Validator(schema).iter_errors(manifest)
        error_msgs = [e.message for e in errors]
        assert not error_msgs, f"Schema validation errors: {error_msgs}"


class TestTestFunctionTypes:
    """Test the Python type definitions for test functions."""

    def test_test_function_kind_exists(self):
        from maid_runner.core.types import ArtifactKind

        assert hasattr(ArtifactKind, "TEST_FUNCTION")
        assert ArtifactKind.TEST_FUNCTION.value == "test_function"

    def test_test_function_details_dataclass(self):
        from maid_runner.core.types import (
            ArtifactKind,
            ArtifactSpec,
            TestFunctionDetails,
            TestFunctionSetup,
        )

        setup = TestFunctionSetup(
            auth_required=True,
            test_data={"email": "user@test.com"},
            setup_actions=({"type": "set_route", "target": "/login"},),
        )
        details = TestFunctionDetails(
            source_scenario="User logs in",
            tags=("smoke", "auth"),
            setup=setup,
            actions=({"type": "api_call", "endpoint": "/login"},),
            expected={"response": {"status": 200}},
            dependencies={"environment": "jsdom"},
        )
        artifact = ArtifactSpec(
            kind=ArtifactKind.TEST_FUNCTION,
            name="test_login",
            test_details=details,
        )
        assert artifact.kind == ArtifactKind.TEST_FUNCTION
        assert artifact.name == "test_login"
        assert artifact.test_details is not None
        assert artifact.test_details.source_scenario == "User logs in"
        assert artifact.test_details.setup.auth_required is True
        assert artifact.merge_key() == "test_login"

    def test_test_function_defaults(self):
        from maid_runner.core.types import TestFunctionDetails

        details = TestFunctionDetails()
        assert details.source_scenario == ""
        assert details.tags == ()
        assert details.actions == ()
        assert details.expected == {}
        assert details.dependencies == {}


class TestTestFunctionParsing:
    """Test manifest parsing of test_function artifacts."""

    def test_parse_test_function_flat(self):
        from maid_runner.core.manifest import load_manifest

        manifest_yaml = """
schema: '2'
goal: test parsing
type: feature
files:
  edit:
    - path: tests/test_auth.test.ts
      artifacts:
        - kind: test_function
          name: test_successful_login
          source_scenario: Successful login
          tags: [smoke, auth]
          setup:
            auth_required: false
            test_data:
              email: user@example.com
          actions:
            - type: api_call
              subject:
                module: src/api/auth.ts
                export: createLogin
              method: POST
              endpoint: /api/v1/auth/login
          expected:
            response:
              status: 200
          dependencies:
            environment: jsdom
validate:
  - vitest tests/test_auth.test.ts
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)
            m = load_manifest(manifest_file)
            fs = m.files_edit[0]
            art = fs.artifacts[0]
            assert art.kind.value == "test_function"
            assert art.name == "test_successful_login"
            assert art.test_details is not None
            assert art.test_details.source_scenario == "Successful login"
            assert art.test_details.tags == ("smoke", "auth")
            assert art.test_details.setup.auth_required is False
            assert art.test_details.setup.test_data == {"email": "user@example.com"}
            assert len(art.test_details.actions) == 1
            assert art.test_details.actions[0]["type"] == "api_call"
            assert art.test_details.actions[0]["endpoint"] == "/api/v1/auth/login"
            assert art.test_details.expected["response"]["status"] == 200
            assert art.test_details.dependencies["environment"] == "jsdom"

    def test_parse_test_function_nested(self):
        """test_function_details nested format also works."""
        from maid_runner.core.manifest import load_manifest

        manifest_yaml = """
schema: '2'
goal: test parsing nested
type: feature
files:
  create:
    - path: tests/test_new.test.ts
      artifacts:
        - kind: test_function
          name: test_new_feature
          test_function_details:
            source_scenario: New feature scenario
            tags: [regression]
            actions: []
            expected: {}
            dependencies: {}
validate:
  - vitest tests/test_new.test.ts
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)
            m = load_manifest(manifest_file)
            fs = m.files_create[0]
            art = fs.artifacts[0]
            assert art.kind.value == "test_function"
            assert art.name == "test_new_feature"
            assert art.test_details is not None
            assert art.test_details.source_scenario == "New feature scenario"

    def test_parse_regular_artifact_unaffected(self):
        """Regular function artifacts still parse correctly."""
        from maid_runner.core.manifest import load_manifest

        manifest_yaml = """
schema: '2'
goal: test regular artifacts
type: feature
files:
  create:
    - path: src/greeter.py
      artifacts:
        - kind: function
          name: greet
          args:
            - name: name
              type: str
          returns: str
validate:
  - pytest src/test_greeter.py
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)
            m = load_manifest(manifest_file)
            fs = m.files_create[0]
            art = fs.artifacts[0]
            assert art.kind.value == "function"
            assert art.test_details is None
