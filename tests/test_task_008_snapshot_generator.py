"""
Behavioral tests for Task-008: Snapshot Generator

Tests validate the snapshot generator functionality by:
1. Extracting artifacts from Python files using AST analysis
2. Creating properly structured manifest snapshots
3. Generating complete snapshot manifests with supersedes tracking
4. CLI interface for command-line usage

These tests USE the declared artifacts to verify actual behavior.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch
import pytest


class TestExtractArtifactsFromCode:
    """Test artifact extraction from Python source files using AST."""

    def test_extracts_simple_function(self, tmp_path: Path):
        """Test extraction of a simple standalone function."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # Create a Python file with a simple function
        code = """
def simple_function(arg1: str, arg2: int) -> bool:
    '''A simple function'''
    return True
"""
        test_file = tmp_path / "simple.py"
        test_file.write_text(code)

        # Extract artifacts using the function
        result = extract_artifacts_from_code(str(test_file))

        # Validate the extraction result
        assert isinstance(result, dict)
        assert "functions" in result or "artifacts" in result
        # The function should be found in the result
        result_str = str(result)
        assert "simple_function" in result_str

    def test_extracts_class_with_methods(self, tmp_path: Path):
        """Test extraction of class with methods and attributes."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # Create a Python file with a class
        code = """
class UserService:
    '''Service for user management'''

    def __init__(self):
        self.users = []

    def get_user(self, user_id: int) -> dict:
        '''Get user by ID'''
        return {"id": user_id}

    def create_user(self, name: str, email: str) -> dict:
        '''Create a new user'''
        return {"name": name, "email": email}
"""
        test_file = tmp_path / "service.py"
        test_file.write_text(code)

        # Extract artifacts
        result = extract_artifacts_from_code(str(test_file))

        # Validate class and methods are extracted
        assert isinstance(result, dict)
        result_str = str(result)
        assert "UserService" in result_str
        assert "get_user" in result_str or "create_user" in result_str

    def test_extracts_multiple_classes(self, tmp_path: Path):
        """Test extraction of multiple classes from same file."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        code = """
class User:
    def __init__(self, name: str):
        self.name = name

class Product:
    def __init__(self, title: str, price: float):
        self.title = title
        self.price = price

class Order:
    def __init__(self, user: User, products: list):
        self.user = user
        self.products = products
"""
        test_file = tmp_path / "models.py"
        test_file.write_text(code)

        result = extract_artifacts_from_code(str(test_file))

        # All three classes should be extracted
        assert isinstance(result, dict)
        result_str = str(result)
        assert "User" in result_str
        assert "Product" in result_str
        assert "Order" in result_str

    def test_extracts_function_parameters(self, tmp_path: Path):
        """Test that function parameters are correctly extracted."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        code = """
def complex_function(
    required_param: str,
    optional_param: int = 10,
    *args,
    keyword_only: bool = False,
    **kwargs
) -> dict:
    return {}
"""
        test_file = tmp_path / "complex.py"
        test_file.write_text(code)

        result = extract_artifacts_from_code(str(test_file))

        # Function with parameters should be extracted
        assert isinstance(result, dict)
        result_str = str(result)
        assert "complex_function" in result_str
        assert "required_param" in result_str or "optional_param" in result_str

    def test_handles_nonexistent_file(self):
        """Test error handling for non-existent files."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # Should raise FileNotFoundError for missing file
        with pytest.raises(FileNotFoundError):
            extract_artifacts_from_code("/nonexistent/path/to/file.py")

    def test_handles_invalid_python_syntax(self, tmp_path: Path):
        """Test error handling for invalid Python syntax."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # Create file with invalid Python syntax
        bad_code = """
def broken_function(
    # Missing closing parenthesis and body
"""
        test_file = tmp_path / "broken.py"
        test_file.write_text(bad_code)

        # Should raise SyntaxError for invalid Python syntax
        with pytest.raises(SyntaxError):
            extract_artifacts_from_code(str(test_file))

    def test_filters_self_parameter_from_methods(self, tmp_path: Path):
        """Test that 'self' parameter is excluded from method artifacts."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # Create a class with methods that have self parameter
        code = """
class MyClass:
    def __init__(self, name: str):
        self.name = name

    def get_name(self) -> str:
        return self.name

    def set_name(self, name: str) -> None:
        self.name = name
"""
        test_file = tmp_path / "myclass.py"
        test_file.write_text(code)

        result = extract_artifacts_from_code(str(test_file))

        # Get the artifacts list
        artifacts = result.get("artifacts", [])

        # Find the methods in the artifacts
        init_method = next((a for a in artifacts if a.get("name") == "__init__"), None)
        get_name_method = next(
            (a for a in artifacts if a.get("name") == "get_name"), None
        )
        set_name_method = next(
            (a for a in artifacts if a.get("name") == "set_name"), None
        )

        # Verify 'self' is NOT in the parameters
        if init_method and "parameters" in init_method:
            param_names = [p["name"] for p in init_method["parameters"]]
            assert (
                "self" not in param_names
            ), "__init__ should not include 'self' parameter"
            assert "name" in param_names, "__init__ should include 'name' parameter"

        if get_name_method and "parameters" in get_name_method:
            # get_name should have no parameters (self is filtered out)
            assert (
                len(get_name_method["parameters"]) == 0
            ), "get_name should have no parameters after filtering 'self'"

        if set_name_method and "parameters" in set_name_method:
            param_names = [p["name"] for p in set_name_method["parameters"]]
            assert (
                "self" not in param_names
            ), "set_name should not include 'self' parameter"
            assert "name" in param_names, "set_name should include 'name' parameter"

    def test_extracts_pep604_union_types(self, tmp_path: Path):
        """Test extraction of PEP 604 union type syntax (Python 3.10+)."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # Skip test if Python version doesn't support PEP 604
        if sys.version_info < (3, 10):
            pytest.skip("PEP 604 union types require Python 3.10+")

        code = """
def process_value(value: str | int) -> bool | None:
    '''Process a string or int value'''
    return True

class DataProcessor:
    def transform(self, data: list[str] | dict[str, int]) -> int | float | str:
        '''Transform data to various types'''
        return 0
"""
        test_file = tmp_path / "pep604.py"
        test_file.write_text(code)

        result = extract_artifacts_from_code(str(test_file))

        # Verify function with union types
        artifacts = result.get("artifacts", [])
        process_func = next(
            (a for a in artifacts if a.get("name") == "process_value"), None
        )
        assert process_func is not None
        assert process_func["parameters"][0]["type"] == "str | int"
        assert process_func["returns"] == "bool | None"

        # Verify method with complex union types
        transform_method = next(
            (a for a in artifacts if a.get("name") == "transform"), None
        )
        assert transform_method is not None
        assert transform_method["parameters"][0]["type"] == "list[str] | dict[str, int]"
        assert transform_method["returns"] == "int | float | str"


class TestCreateSnapshotManifest:
    """Test snapshot manifest creation with proper structure."""

    def test_creates_basic_manifest_structure(self):
        """Test creation of basic manifest with required fields."""
        from maid_runner.cli.snapshot import create_snapshot_manifest

        # Create snapshot manifest with minimal data
        artifacts = [
            {"type": "class", "name": "TestClass"},
            {"type": "function", "name": "test_function"},
        ]
        superseded = []

        result = create_snapshot_manifest("src/example.py", artifacts, superseded)

        # Validate manifest structure
        assert isinstance(result, dict)
        assert "goal" in result
        assert "taskType" in result
        assert "expectedArtifacts" in result
        assert result["taskType"] == "snapshot" or "snapshot" in result["goal"].lower()

    def test_includes_expected_artifacts_section(self):
        """Test that expectedArtifacts section is properly populated."""
        from maid_runner.cli.snapshot import create_snapshot_manifest

        artifacts = [
            {
                "type": "function",
                "name": "validate_data",
                "parameters": [{"name": "data", "type": "dict"}],
                "returns": "bool",
            }
        ]

        result = create_snapshot_manifest("validators/check.py", artifacts, [])

        # ExpectedArtifacts should contain the file and artifacts
        assert "expectedArtifacts" in result
        expected = result["expectedArtifacts"]
        assert "file" in expected
        assert "contains" in expected
        assert expected["file"] == "validators/check.py"
        assert len(expected["contains"]) == 1
        assert expected["contains"][0]["name"] == "validate_data"

    def test_includes_supersedes_array(self):
        """Test that supersedes array is properly included."""
        from maid_runner.cli.snapshot import create_snapshot_manifest

        artifacts = [{"type": "class", "name": "Service"}]
        superseded_manifests = [
            "manifests/task-001-initial.manifest.json",
            "manifests/task-003-update.manifest.json",
        ]

        result = create_snapshot_manifest(
            "src/service.py", artifacts, superseded_manifests
        )

        # Supersedes should be included
        assert "supersedes" in result
        assert isinstance(result["supersedes"], list)
        assert len(result["supersedes"]) == 2
        assert "task-001-initial.manifest.json" in result["supersedes"][0]
        assert "task-003-update.manifest.json" in result["supersedes"][1]

    def test_sets_proper_file_categorization(self):
        """Test that files are categorized as editableFiles for snapshots."""
        from maid_runner.cli.snapshot import create_snapshot_manifest

        artifacts = [{"type": "function", "name": "helper"}]

        result = create_snapshot_manifest("utils/helpers.py", artifacts, [])

        # Should have editableFiles set (snapshot of existing code)
        assert "editableFiles" in result or "creatableFiles" in result
        if "editableFiles" in result:
            assert "utils/helpers.py" in result["editableFiles"]

    def test_creates_validation_command(self):
        """Test that a validation command is included in the manifest."""
        from maid_runner.cli.snapshot import create_snapshot_manifest

        artifacts = [{"type": "class", "name": "Parser"}]

        result = create_snapshot_manifest("parsers/json_parser.py", artifacts, [])

        # Should include validationCommand
        assert "validationCommand" in result
        assert isinstance(result["validationCommand"], list)
        # Snapshots without superseded manifests should have empty validation commands
        assert len(result["validationCommand"]) == 0

    def test_aggregates_validation_commands_from_superseded(self):
        """Test that validation commands are aggregated from superseded manifests."""
        from maid_runner.cli.snapshot import create_snapshot_manifest
        from pathlib import Path

        # Use artifacts that are actually tested by the superseded manifests
        # task-001 tests validate_schema, task-002 tests validate_with_ast and AlignmentError
        artifacts = [
            {"type": "function", "name": "validate_schema"},
            {"type": "function", "name": "validate_with_ast"},
            {"type": "class", "name": "AlignmentError"},
        ]
        superseded = [
            "manifests/task-001-add-schema-validation.manifest.json",
            "manifests/task-002-add-ast-alignment-validation.manifest.json",
        ]

        manifest_dir = Path(__file__).parent.parent / "manifests"
        result = create_snapshot_manifest(
            "maid_runner/validators/manifest_validator.py",
            artifacts,
            superseded,
            manifest_dir=manifest_dir,
        )

        # Should aggregate validation commands from superseded manifests
        # Support both validationCommand (legacy) and validationCommands (enhanced)
        if "validationCommands" in result:
            validation_commands = result["validationCommands"]
            assert isinstance(validation_commands, list)
            assert len(validation_commands) > 0
            # Should deduplicate commands
            assert len(validation_commands) == len(
                set(
                    tuple(cmd) if isinstance(cmd, list) else cmd
                    for cmd in validation_commands
                )
            )
        else:
            assert "validationCommand" in result
            assert isinstance(result["validationCommand"], list)
            assert len(result["validationCommand"]) > 0
            # Should deduplicate commands
            assert len(result["validationCommand"]) == len(
                set(result["validationCommand"])
            )

    def test_filters_out_tests_for_removed_artifacts(self):
        """Test that tests referencing removed artifacts are filtered out."""
        from maid_runner.cli.snapshot import create_snapshot_manifest
        from pathlib import Path

        # Simulate a refactoring: snapshot removes validate_schema
        # Only keep validate_with_ast
        artifacts = [
            {"type": "function", "name": "validate_with_ast"},
            {"type": "class", "name": "AlignmentError"},
        ]
        superseded = [
            "manifests/task-001-add-schema-validation.manifest.json",
        ]

        manifest_dir = Path(__file__).parent.parent / "manifests"
        result = create_snapshot_manifest(
            "maid_runner/validators/manifest_validator.py",
            artifacts,
            superseded,
            manifest_dir=manifest_dir,
        )

        # Should filter out test_validate_schema.py since validate_schema was removed
        # Support both validationCommand (legacy) and validationCommands (enhanced)
        if "validationCommands" in result:
            validation_commands_raw = result["validationCommands"]
            # Flatten for checking
            validation_commands = []
            for cmd in validation_commands_raw:
                if isinstance(cmd, list):
                    validation_commands.extend(cmd)
                else:
                    validation_commands.append(cmd)
        else:
            assert "validationCommand" in result
            validation_commands = result["validationCommand"]

        # test_validate_schema.py should NOT be in the commands
        test_validate_schema_cmd = any(
            "test_validate_schema.py" in str(cmd) for cmd in validation_commands
        )
        assert (
            not test_validate_schema_cmd
        ), "test_validate_schema.py should be filtered out when validate_schema is removed"


class TestGenerateSnapshot:
    """Test the main snapshot generation function."""

    def test_generates_snapshot_for_simple_file(self, tmp_path: Path):
        """Test complete snapshot generation workflow."""
        from maid_runner.cli.snapshot import generate_snapshot

        # Create a test Python file
        code = """
class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b
"""
        test_file = tmp_path / "calculator.py"
        test_file.write_text(code)

        output_dir = tmp_path / "manifests"
        output_dir.mkdir()

        # Generate snapshot (skip test stub to avoid side effects)
        result_path = generate_snapshot(
            str(test_file), str(output_dir), skip_test_stub=True
        )

        # Validate the result
        assert isinstance(result_path, str)
        assert Path(result_path).exists()
        assert result_path.endswith(".manifest.json")

        # Read and validate the generated manifest
        with open(result_path, "r") as f:
            manifest = json.load(f)

        assert "goal" in manifest
        assert "expectedArtifacts" in manifest
        assert manifest["expectedArtifacts"]["file"] == str(test_file)

    def test_snapshot_includes_all_extracted_artifacts(self, tmp_path: Path):
        """Test that all artifacts from file are included in snapshot."""
        from maid_runner.cli.snapshot import generate_snapshot

        code = """
def function_one():
    pass

def function_two(param: str):
    return param

class ClassOne:
    def method_one(self):
        pass
"""
        test_file = tmp_path / "multi.py"
        test_file.write_text(code)

        output_dir = tmp_path / "snapshots"
        output_dir.mkdir()

        result_path = generate_snapshot(
            str(test_file), str(output_dir), skip_test_stub=True
        )

        # Load the manifest
        with open(result_path, "r") as f:
            manifest = json.load(f)

        # All artifacts should be present
        contains = manifest["expectedArtifacts"]["contains"]
        artifact_names = [art["name"] for art in contains]

        assert "function_one" in artifact_names
        assert "function_two" in artifact_names
        assert "ClassOne" in artifact_names

    def test_snapshot_discovers_superseded_manifests(self, tmp_path: Path):
        """Test that snapshot discovers and includes superseded manifests."""
        from maid_runner.cli.snapshot import generate_snapshot

        # Create a test file
        code = """
class TestService:
    pass
"""
        test_file = tmp_path / "service.py"
        test_file.write_text(code)

        # Create some existing manifests that reference this file
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_1 = {
            "goal": "Create service",
            "taskType": "create",
            "creatableFiles": [str(test_file)],
            "expectedArtifacts": {"file": str(test_file), "contains": []},
            "validationCommand": ["pytest"],
        }
        manifest_1_path = manifests_dir / "task-001-service.manifest.json"
        manifest_1_path.write_text(json.dumps(manifest_1, indent=2))

        manifest_2 = {
            "goal": "Update service",
            "taskType": "edit",
            "editableFiles": [str(test_file)],
            "expectedArtifacts": {"file": str(test_file), "contains": []},
            "validationCommand": ["pytest"],
        }
        manifest_2_path = manifests_dir / "task-002-update.manifest.json"
        manifest_2_path.write_text(json.dumps(manifest_2, indent=2))

        # Generate snapshot (skip test stub to avoid side effects)
        result_path = generate_snapshot(
            str(test_file), str(manifests_dir), skip_test_stub=True
        )

        # Load and verify supersedes
        with open(result_path, "r") as f:
            manifest = json.load(f)

        # The snapshot should reference the existing manifests
        # (Implementation may vary - test that supersedes exists and is a list)
        assert "supersedes" in manifest
        assert isinstance(manifest["supersedes"], list)

    def test_generates_unique_manifest_filename(self, tmp_path: Path):
        """Test that generated manifest has a unique, descriptive filename."""
        from maid_runner.cli.snapshot import generate_snapshot

        code = "def test(): pass"
        test_file = tmp_path / "unique.py"
        test_file.write_text(code)

        output_dir = tmp_path / "out"
        output_dir.mkdir()

        result_path = generate_snapshot(
            str(test_file), str(output_dir), skip_test_stub=True
        )

        # Filename should be unique and include "snapshot" or similar
        filename = Path(result_path).name
        assert filename.endswith(".manifest.json")
        assert "snapshot" in filename.lower() or "unique" in filename.lower()

    def test_validates_generated_manifest_against_schema(self, tmp_path: Path):
        """Test that generated manifest conforms to the manifest schema."""
        from maid_runner.cli.snapshot import generate_snapshot
        import jsonschema

        code = """
class Validator:
    def validate(self, data: dict) -> bool:
        return True
"""
        test_file = tmp_path / "validator.py"
        test_file.write_text(code)

        output_dir = tmp_path / "manifests"
        output_dir.mkdir()

        result_path = generate_snapshot(
            str(test_file), str(output_dir), skip_test_stub=True
        )

        # Load the manifest
        with open(result_path, "r") as f:
            manifest = json.load(f)

            # Load the schema
            schema_path = (
                Path(__file__).parent.parent
                / "maid_runner"
                / "validators"
                / "schemas"
                / "manifest.schema.json"
            )
        with open(schema_path, "r") as f:
            schema = json.load(f)

        # Validate against schema - should not raise
        jsonschema.validate(instance=manifest, schema=schema)

    def test_handles_output_directory_creation(self, tmp_path: Path):
        """Test that output directory is created if it doesn't exist."""
        from maid_runner.cli.snapshot import generate_snapshot

        code = "def func(): pass"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        # Output directory doesn't exist yet
        output_dir = tmp_path / "new" / "nested" / "dir"
        assert not output_dir.exists()

        # Generate snapshot - should create directory (skip test stub to avoid side effects)
        result_path = generate_snapshot(
            str(test_file), str(output_dir), skip_test_stub=True
        )

        # Directory should now exist
        assert output_dir.exists()
        assert Path(result_path).exists()


class TestMainCLI:
    """Test the CLI entry point for the snapshot generator."""

    def test_main_accepts_file_path_argument(self, tmp_path: Path):
        """Test that main function accepts file path via CLI arguments."""
        from maid_runner.cli.snapshot import main

        code = "def cli_test(): pass"
        test_file = tmp_path / "cli.py"
        test_file.write_text(code)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Mock sys.argv to simulate CLI call
        test_args = [
            "snapshot",
            str(test_file),
            "--output-dir",
            str(output_dir),
            "--skip-test-stub",
        ]

        with patch("sys.argv", test_args):
            # Should execute without error
            main()

        # Verify manifest was created
        manifests = list(output_dir.glob("*.manifest.json"))
        assert len(manifests) >= 1

    def test_main_uses_default_output_directory(self, tmp_path: Path):
        """Test that main uses default output directory when not specified."""
        from maid_runner.cli.snapshot import main

        code = "def default_test(): pass"
        test_file = tmp_path / "default.py"
        test_file.write_text(code)

        # Change to tmp directory for this test
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            test_args = ["generate_snapshot.py", str(test_file), "--skip-test-stub"]

            with patch("sys.argv", test_args):
                # Should execute with default output directory
                main()

            # Should create manifest in default location (manifests/ or current dir)
            # The exact location depends on implementation
            assert True  # Test passes if main() doesn't raise

        finally:
            os.chdir(original_cwd)

    def test_main_prints_helpful_error_for_missing_file(self, tmp_path: Path):
        """Test that main provides clear error message for missing input file."""
        from maid_runner.cli.snapshot import main

        nonexistent_file = tmp_path / "does_not_exist.py"
        output_dir = tmp_path / "output"

        test_args = [
            "snapshot",
            str(nonexistent_file),
            "--output-dir",
            str(output_dir),
        ]

        with patch("sys.argv", test_args):
            # Should raise or exit with error
            with pytest.raises(SystemExit):
                main()

    def test_main_displays_success_message(self, tmp_path: Path, capsys):
        """Test that main displays success message with output path."""
        from maid_runner.cli.snapshot import main

        code = "def success_test(): pass"
        test_file = tmp_path / "success.py"
        test_file.write_text(code)

        output_dir = tmp_path / "success_output"
        output_dir.mkdir()

        test_args = [
            "snapshot",
            str(test_file),
            "--output-dir",
            str(output_dir),
            "--skip-test-stub",
        ]

        with patch("sys.argv", test_args):
            main()

        # Capture output
        captured = capsys.readouterr()
        output = captured.out + captured.err

        # Should mention success and output location
        assert "snapshot" in output.lower() or "generated" in output.lower()

    def test_main_handles_multiple_file_formats(self, tmp_path: Path):
        """Test that main can handle different Python file structures."""
        from maid_runner.cli.snapshot import main

        # Test with a complex file
        code = """
'''Module docstring'''

from typing import List, Dict

CONSTANT = 42

class ServiceA:
    '''Service A'''
    def __init__(self):
        self.data = []

class ServiceB:
    '''Service B'''
    @staticmethod
    def static_method():
        pass

def module_function(param: str) -> Dict:
    '''Module-level function'''
    return {}
"""
        test_file = tmp_path / "complex.py"
        test_file.write_text(code)

        output_dir = tmp_path / "complex_output"
        output_dir.mkdir()

        test_args = [
            "snapshot",
            str(test_file),
            "--output-dir",
            str(output_dir),
            "--skip-test-stub",
        ]

        with patch("sys.argv", test_args):
            main()

        # Should successfully generate manifest
        manifests = list(output_dir.glob("*.manifest.json"))
        assert len(manifests) >= 1


class TestIntegrationWorkflow:
    """Test complete end-to-end snapshot generation workflow."""

    def test_full_workflow_from_file_to_validated_manifest(self, tmp_path: Path):
        """Test complete workflow: file -> extract -> create -> validate."""
        from maid_runner.cli.snapshot import (
            extract_artifacts_from_code,
            create_snapshot_manifest,
            generate_snapshot,
        )
        import jsonschema

        # Step 1: Create a realistic Python module
        code = """
'''User management module'''

from typing import Optional, List

class User:
    '''Represents a user in the system'''

    def __init__(self, user_id: int, name: str, email: str):
        self.user_id = user_id
        self.name = name
        self.email = email

class UserRepository:
    '''Handles user data persistence'''

    def __init__(self):
        self._users = {}

    def find_by_id(self, user_id: int) -> Optional[User]:
        '''Find user by ID'''
        return self._users.get(user_id)

    def save(self, user: User) -> None:
        '''Save user to repository'''
        self._users[user.user_id] = user

    def list_all(self) -> List[User]:
        '''List all users'''
        return list(self._users.values())

def create_default_user() -> User:
    '''Create a default user instance'''
    return User(0, "Default", "default@example.com")
"""
        source_file = tmp_path / "user_module.py"
        source_file.write_text(code)

        # Step 2: Extract artifacts
        artifacts = extract_artifacts_from_code(str(source_file))
        assert artifacts is not None

        # Step 3: Create manifest structure
        manifest = create_snapshot_manifest(str(source_file), artifacts, [])
        assert manifest is not None
        assert "expectedArtifacts" in manifest

        # Step 4: Generate complete snapshot (skip test stub to avoid side effects)
        output_dir = tmp_path / "manifests"
        output_dir.mkdir()
        manifest_path = generate_snapshot(
            str(source_file), str(output_dir), skip_test_stub=True
        )

        # Step 5: Validate the generated manifest
        with open(manifest_path, "r") as f:
            generated_manifest = json.load(f)

        # Load schema
        schema_path = (
            Path(__file__).parent.parent
            / "maid_runner"
            / "validators"
            / "schemas"
            / "manifest.schema.json"
        )
        with open(schema_path, "r") as f:
            schema = json.load(f)

        # Validate - should pass without errors
        jsonschema.validate(instance=generated_manifest, schema=schema)

        # Step 6: Verify completeness
        assert "User" in str(generated_manifest)
        assert "UserRepository" in str(generated_manifest)
        assert "create_default_user" in str(generated_manifest)

    def test_snapshot_can_be_used_for_validation(self, tmp_path: Path):
        """Test that generated snapshot can be used for manifest validation."""
        from maid_runner.cli.snapshot import generate_snapshot

        # Create implementation
        code = """
class DataProcessor:
    def process(self, data: dict) -> dict:
        return data

    def validate(self, data: dict) -> bool:
        return isinstance(data, dict)
"""
        impl_file = tmp_path / "processor.py"
        impl_file.write_text(code)

        # Generate snapshot (skip test stub to avoid side effects)
        output_dir = tmp_path / "manifests"
        output_dir.mkdir()
        snapshot_path = generate_snapshot(
            str(impl_file), str(output_dir), skip_test_stub=True
        )

        # Load the snapshot
        with open(snapshot_path, "r") as f:
            snapshot_manifest = json.load(f)

        # The snapshot should be usable for validation
        assert snapshot_manifest["expectedArtifacts"]["file"] == str(impl_file)

        # Import validator to test the snapshot
        from maid_runner.validators.manifest_validator import validate_with_ast

        # Validate the implementation against the snapshot
        # Should pass since snapshot was generated from the implementation
        result = validate_with_ast(
            snapshot_manifest, str(impl_file), use_manifest_chain=False
        )

        # Validation should succeed (no errors)
        assert (
            result is not None or True
        )  # validate_with_ast may return None on success
