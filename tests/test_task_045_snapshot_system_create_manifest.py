"""
Behavioral tests for task-045: Implement system manifest creation.

Tests verify that create_system_manifest():
1. Creates a valid manifest structure following the schema
2. Uses systemArtifacts field for artifact blocks
3. Uses validationCommands field for commands
4. Includes all required fields (goal, readonlyFiles, taskType)
5. Generated manifest validates against the schema
6. Handles edge cases (empty artifacts/commands)
"""

import json
import pytest
from pathlib import Path
from jsonschema import validate

from maid_runner.cli.snapshot_system import create_system_manifest


# Load the manifest schema for validation
SCHEMA_PATH = Path("maid_runner/validators/schemas/manifest.schema.json")


@pytest.fixture
def manifest_schema():
    """Load the manifest schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


class TestCreateSystemManifest:
    """Test suite for create_system_manifest() function."""

    def test_function_exists(self):
        """Verify create_system_manifest function exists."""
        assert callable(create_system_manifest)

    def test_creates_basic_structure(self):
        """Verify function returns a dictionary with basic structure."""
        artifact_blocks = [
            {"file": "test.py", "contains": [{"type": "function", "name": "test_func"}]}
        ]
        validation_commands = [["pytest", "tests/"]]

        result = create_system_manifest(artifact_blocks, validation_commands)

        assert isinstance(result, dict)
        assert "goal" in result
        assert "taskType" in result
        assert "systemArtifacts" in result
        assert "validationCommands" in result
        assert "readonlyFiles" in result

    def test_sets_correct_task_type(self):
        """Verify taskType is set to 'system-snapshot'."""
        result = create_system_manifest([], [])
        assert result["taskType"] == "system-snapshot"

    def test_includes_systemArtifacts(self):
        """Verify systemArtifacts field contains the artifact blocks."""
        artifact_blocks = [
            {
                "file": "file1.py",
                "contains": [
                    {"type": "function", "name": "func1"},
                    {"type": "class", "name": "Class1"},
                ],
            },
            {"file": "file2.py", "contains": [{"type": "function", "name": "func2"}]},
        ]
        validation_commands = [["pytest", "tests/"]]

        result = create_system_manifest(artifact_blocks, validation_commands)

        assert result["systemArtifacts"] == artifact_blocks
        assert len(result["systemArtifacts"]) == 2
        assert result["systemArtifacts"][0]["file"] == "file1.py"
        assert len(result["systemArtifacts"][0]["contains"]) == 2

    def test_includes_validationCommands(self):
        """Verify validationCommands field contains the commands."""
        artifact_blocks = []
        validation_commands = [
            ["pytest", "tests/", "-v"],
            ["make", "lint"],
            ["make", "type-check"],
        ]

        result = create_system_manifest(artifact_blocks, validation_commands)

        assert result["validationCommands"] == validation_commands
        assert len(result["validationCommands"]) == 3

    def test_includes_version_field(self):
        """Verify version field is included."""
        result = create_system_manifest([], [])
        assert "version" in result
        assert result["version"] == "1"

    def test_includes_readonlyFiles_field(self):
        """Verify readonlyFiles field exists (required by schema)."""
        result = create_system_manifest([], [])
        assert "readonlyFiles" in result
        assert isinstance(result["readonlyFiles"], list)

    def test_includes_descriptive_goal(self):
        """Verify goal field has a descriptive message."""
        result = create_system_manifest([], [])
        assert "goal" in result
        assert isinstance(result["goal"], str)
        assert len(result["goal"]) > 0
        # Should mention it's a system-wide snapshot
        assert (
            "system" in result["goal"].lower() or "snapshot" in result["goal"].lower()
        )

    def test_handles_empty_artifact_blocks(self):
        """Verify handling of empty artifact blocks."""
        result = create_system_manifest([], [["pytest", "tests/"]])

        assert result["systemArtifacts"] == []
        assert len(result["validationCommands"]) == 1

    def test_handles_empty_validation_commands(self):
        """Verify handling of empty validation commands."""
        artifact_blocks = [
            {"file": "test.py", "contains": [{"type": "function", "name": "f"}]}
        ]
        result = create_system_manifest(artifact_blocks, [])

        assert len(result["systemArtifacts"]) == 1
        assert result["validationCommands"] == []

    def test_handles_both_empty(self):
        """Verify handling when both artifacts and commands are empty."""
        result = create_system_manifest([], [])

        assert result["systemArtifacts"] == []
        assert result["validationCommands"] == []

    def test_does_not_include_expectedArtifacts(self):
        """Verify expectedArtifacts is NOT included (should use systemArtifacts)."""
        result = create_system_manifest([], [])
        assert "expectedArtifacts" not in result

    def test_does_not_include_creatableFiles(self):
        """Verify creatableFiles is not included (system snapshot doesn't create files)."""
        result = create_system_manifest([], [])
        # creatableFiles might be present as empty array, but not required
        # Just verify it doesn't cause validation issues
        assert "creatableFiles" not in result or result.get("creatableFiles") == []

    def test_does_not_include_editableFiles(self):
        """Verify editableFiles is not included (system snapshot doesn't edit files)."""
        result = create_system_manifest([], [])
        # editableFiles might be present as empty array, but not required
        # Just verify it doesn't cause validation issues
        assert "editableFiles" not in result or result.get("editableFiles") == []

    def test_generated_manifest_validates_against_schema(self, manifest_schema):
        """Verify generated manifest passes schema validation."""
        artifact_blocks = [
            {
                "file": "module/file1.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "test_function",
                        "args": [{"name": "arg1", "type": "str"}],
                        "returns": "bool",
                    },
                    {"type": "class", "name": "TestClass", "bases": ["BaseClass"]},
                ],
            },
            {
                "file": "module/file2.py",
                "contains": [{"type": "attribute", "name": "MODULE_CONSTANT"}],
            },
        ]
        validation_commands = [["pytest", "tests/", "-v"], ["make", "lint"]]

        result = create_system_manifest(artifact_blocks, validation_commands)

        # Should not raise ValidationError
        validate(instance=result, schema=manifest_schema)

    def test_preserves_artifact_structure(self):
        """Verify artifact structure is preserved exactly."""
        artifact_blocks = [
            {
                "file": "test.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "complex_func",
                        "args": [
                            {"name": "a", "type": "int"},
                            {"name": "b", "type": "str", "default": "''"},
                        ],
                        "returns": "Dict[str, Any]",
                        "description": "A complex function",
                    }
                ],
            }
        ]
        validation_commands = []

        result = create_system_manifest(artifact_blocks, validation_commands)

        # Verify exact preservation
        assert result["systemArtifacts"] == artifact_blocks
        artifact = result["systemArtifacts"][0]["contains"][0]
        assert artifact["type"] == "function"
        assert artifact["name"] == "complex_func"
        assert len(artifact["args"]) == 2
        assert artifact["args"][1]["default"] == "''"
        assert artifact["returns"] == "Dict[str, Any]"
        assert artifact["description"] == "A complex function"

    def test_preserves_command_structure(self):
        """Verify command structure is preserved exactly."""
        validation_commands = [
            ["pytest", "tests/", "-v", "--cov"],
            ["make", "lint"],
            ["python", "-m", "mypy", "src/"],
        ]

        result = create_system_manifest([], validation_commands)

        assert result["validationCommands"] == validation_commands
        assert result["validationCommands"][0] == ["pytest", "tests/", "-v", "--cov"]
        assert result["validationCommands"][2] == ["python", "-m", "mypy", "src/"]


class TestSchemaCompliance:
    """Test that generated manifests comply with the extended schema."""

    def test_has_required_fields(self):
        """Verify all required schema fields are present."""
        result = create_system_manifest([], [])

        # Required by schema: goal, readonlyFiles
        assert "goal" in result
        assert "readonlyFiles" in result

        # Must have either expectedArtifacts or systemArtifacts
        assert "systemArtifacts" in result
        assert "expectedArtifacts" not in result

        # Must have either validationCommand or validationCommands
        assert "validationCommands" in result

    def test_systemArtifacts_structure_valid(self, manifest_schema):
        """Verify systemArtifacts structure follows schema."""
        artifact_blocks = [
            {
                "file": "test.py",
                "contains": [
                    {"type": "function", "name": "f1"},
                    {"type": "class", "name": "C1"},
                ],
            }
        ]

        result = create_system_manifest(artifact_blocks, [["pytest"]])

        # Validate against schema
        validate(instance=result, schema=manifest_schema)

        # Verify structure
        sys_artifacts = result["systemArtifacts"]
        assert isinstance(sys_artifacts, list)
        for block in sys_artifacts:
            assert "file" in block
            assert "contains" in block
            assert isinstance(block["file"], str)
            assert isinstance(block["contains"], list)

    def test_does_not_have_both_artifact_fields(self, manifest_schema):
        """Verify manifest doesn't have both expectedArtifacts and systemArtifacts."""
        result = create_system_manifest([], [])

        # Should only have systemArtifacts
        assert "systemArtifacts" in result
        assert "expectedArtifacts" not in result

        # Should still validate
        validate(instance=result, schema=manifest_schema)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_large_number_of_artifacts(self):
        """Verify handling of large number of artifact blocks."""
        artifact_blocks = [
            {
                "file": f"file{i}.py",
                "contains": [{"type": "function", "name": f"func{i}"}],
            }
            for i in range(100)
        ]

        result = create_system_manifest(artifact_blocks, [])

        assert len(result["systemArtifacts"]) == 100
        assert result["systemArtifacts"][50]["file"] == "file50.py"

    def test_large_number_of_commands(self):
        """Verify handling of large number of validation commands."""
        validation_commands = [["pytest", f"tests/test{i}.py"] for i in range(50)]

        result = create_system_manifest([], validation_commands)

        assert len(result["validationCommands"]) == 50

    def test_nested_artifact_complexity(self):
        """Verify handling of complex nested artifact structures."""
        artifact_blocks = [
            {
                "file": "complex.py",
                "contains": [
                    {
                        "type": "class",
                        "name": "ComplexClass",
                        "bases": ["Base1", "Base2", "Base3"],
                    },
                    {
                        "type": "function",
                        "name": "complex_method",
                        "class": "ComplexClass",
                        "args": [
                            {"name": "self"},
                            {"name": "a", "type": "List[Dict[str, Any]]"},
                            {"name": "b", "type": "Optional[Callable[[int], str]]"},
                        ],
                        "returns": "Tuple[bool, Optional[Error]]",
                        "raises": ["ValueError", "TypeError", "CustomError"],
                    },
                ],
            }
        ]

        result = create_system_manifest(artifact_blocks, [])

        # Should preserve all complexity
        artifact = result["systemArtifacts"][0]["contains"][1]
        assert len(artifact["args"]) == 3
        assert artifact["returns"] == "Tuple[bool, Optional[Error]]"
        assert len(artifact["raises"]) == 3
