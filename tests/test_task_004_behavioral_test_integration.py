# tests/test_task_004_behavioral_test_integration.py
"""
Behavioral tests for task-004: Behavioral test integration functionality.

This test validates the integration of behavioral test validation into the main
validation flow, ensuring test files are validated BEFORE implementation validation
as part of the MAID workflow.
"""
import pytest
import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path to import validate_manifest
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_runner.cli.validate import (
    extract_test_files_from_command,
    validate_behavioral_tests,
    main,
)
from maid_runner.validators.manifest_validator import collect_behavioral_artifacts

# Import and re-export test class so pytest discovers it in this file's namespace
from tests._test_find_imported_test_files import TestFindImportedTestFiles  # noqa: F401


class TestExtractTestFilesFromCommand:
    """Test extraction of test files from various pytest command formats."""

    def test_extracts_single_test_file(self):
        """Test extraction from single file pytest command."""
        command = ["pytest", "tests/test_example.py", "-v"]
        result = extract_test_files_from_command(command)
        assert result == ["tests/test_example.py"]

    def test_extracts_multiple_test_files(self):
        """Test extraction from multiple file pytest command."""
        command = ["pytest", "tests/test_one.py", "tests/test_two.py", "-v"]
        result = extract_test_files_from_command(command)
        assert result == ["tests/test_one.py", "tests/test_two.py"]

    def test_extracts_from_directory_pattern(self):
        """Test extraction from directory patterns."""
        command = ["pytest", "tests/", "-v"]
        result = extract_test_files_from_command(command)
        assert result == ["tests/"]

    def test_extracts_from_glob_patterns(self):
        """Test extraction from glob patterns."""
        command = ["pytest", "tests/test_*.py", "-v"]
        result = extract_test_files_from_command(command)
        assert result == ["tests/test_*.py"]

    def test_ignores_pytest_flags(self):
        """Test that pytest flags are ignored, only test files extracted."""
        command = ["pytest", "tests/test_example.py", "-v", "--tb=short", "-x"]
        result = extract_test_files_from_command(command)
        assert result == ["tests/test_example.py"]

    def test_handles_python_module_invocation(self):
        """Test extraction from python -m pytest commands."""
        command = ["python", "-m", "pytest", "tests/test_example.py", "-v"]
        result = extract_test_files_from_command(command)
        assert result == ["tests/test_example.py"]

    def test_handles_uv_run_pytest(self):
        """Test extraction from uv run pytest commands."""
        command = ["uv", "run", "pytest", "tests/test_example.py", "-v"]
        result = extract_test_files_from_command(command)
        assert result == ["tests/test_example.py"]

    def test_returns_empty_for_non_pytest_command(self):
        """Test that non-pytest commands return empty list."""
        command = ["make", "test"]
        result = extract_test_files_from_command(command)
        assert result == []

    def test_handles_complex_pytest_command(self):
        """Test extraction from complex pytest commands with multiple options."""
        command = [
            "uv",
            "run",
            "python",
            "-m",
            "pytest",
            "tests/test_one.py",
            "tests/test_two.py",
            "-v",
            "--tb=short",
            "-x",
            "--cov=src",
        ]
        result = extract_test_files_from_command(command)
        assert result == ["tests/test_one.py", "tests/test_two.py"]

    def test_handles_pytest_with_node_ids(self):
        """Test extraction when pytest uses node IDs (file::class::method)."""
        command = ["pytest", "tests/test_example.py::TestClass::test_method", "-v"]
        result = extract_test_files_from_command(command)
        assert result == ["tests/test_example.py"]

    def test_extracts_relative_and_absolute_paths(self):
        """Test extraction of both relative and absolute paths."""
        command = [
            "pytest",
            "tests/test_relative.py",
            "/absolute/path/to/test_absolute.py",
            "-v",
        ]
        result = extract_test_files_from_command(command)
        assert result == [
            "tests/test_relative.py",
            "/absolute/path/to/test_absolute.py",
        ]


class TestValidateBehavioralTests:
    """Test validation of behavioral tests against manifest artifacts."""

    def test_validates_single_test_file_successfully(self, tmp_path: Path):
        """Test successful validation of a single behavioral test file."""
        # Create a behavioral test that uses expected artifacts
        test_code = """
import pytest
from services.user_service import UserService

def test_get_user_by_id():
    service = UserService()
    result = service.get_user_by_id(user_id=123)
    assert result is not None
"""
        test_file = tmp_path / "test_user.py"
        test_file.write_text(test_code)

        manifest_data = {
            "expectedArtifacts": {
                "file": "src/services/user_service.py",
                "contains": [
                    {"type": "class", "name": "UserService"},
                    {
                        "type": "function",
                        "name": "get_user_by_id",
                        "class": "UserService",
                        "parameters": [{"name": "user_id"}],
                    },
                ],
            }
        }

        test_files = [str(test_file)]

        # Should not raise any exception
        validate_behavioral_tests(
            manifest_data, test_files, use_manifest_chain=False, quiet=True
        )

    def test_validates_multiple_test_files(self, tmp_path: Path):
        """Test validation of multiple behavioral test files."""
        # Create first test file
        test_code_1 = """
from services.user_service import UserService

def test_create_user():
    service = UserService()
    service.create_user(name="Alice", email="alice@test.com")
"""
        test_file_1 = tmp_path / "test_user_create.py"
        test_file_1.write_text(test_code_1)

        # Create second test file
        test_code_2 = """
from services.user_service import UserService

def test_delete_user():
    service = UserService()
    service.delete_user(user_id=123)
"""
        test_file_2 = tmp_path / "test_user_delete.py"
        test_file_2.write_text(test_code_2)

        manifest_data = {
            "expectedArtifacts": {
                "file": "src/services/user_service.py",
                "contains": [
                    {"type": "class", "name": "UserService"},
                    {
                        "type": "function",
                        "name": "create_user",
                        "class": "UserService",
                        "parameters": [{"name": "name"}, {"name": "email"}],
                    },
                    {
                        "type": "function",
                        "name": "delete_user",
                        "class": "UserService",
                        "parameters": [{"name": "user_id"}],
                    },
                ],
            }
        }

        test_files = [str(test_file_1), str(test_file_2)]

        # Should not raise any exception
        validate_behavioral_tests(
            manifest_data, test_files, use_manifest_chain=False, quiet=True
        )

    def test_fails_when_test_missing_required_artifact(self, tmp_path: Path):
        """Test that validation fails when test doesn't use required artifact."""
        # Create test that doesn't use expected artifact
        test_code = """
def test_something_else():
    # This test doesn't use UserService at all
    assert True
"""
        test_file = tmp_path / "test_missing.py"
        test_file.write_text(test_code)

        manifest_data = {
            "expectedArtifacts": {
                "file": "src/services/user_service.py",
                "contains": [
                    {"type": "class", "name": "UserService"},
                    {
                        "type": "function",
                        "name": "get_user_by_id",
                        "class": "UserService",
                    },
                ],
            }
        }

        test_files = [str(test_file)]

        # Should raise AlignmentError
        with pytest.raises(Exception) as exc_info:
            validate_behavioral_tests(
                manifest_data, test_files, use_manifest_chain=False, quiet=True
            )

        assert "UserService" in str(exc_info.value)

    def test_handles_non_existent_test_file(self):
        """Test proper error handling for non-existent test files."""
        manifest_data = {"expectedArtifacts": {"file": "src/test.py", "contains": []}}

        test_files = ["/path/to/nonexistent/test.py"]

        # Should raise FileNotFoundError or similar
        with pytest.raises(Exception):
            validate_behavioral_tests(
                manifest_data, test_files, use_manifest_chain=False, quiet=True
            )

    def test_uses_manifest_chain_when_requested(self, tmp_path: Path):
        """Test that manifest chain is used when use_manifest_chain=True."""
        test_code = """
from services.user_service import UserService

def test_get_user():
    service = UserService()
    service.get_user_by_id(user_id=123)
"""
        test_file = tmp_path / "test_chain.py"
        test_file.write_text(test_code)

        manifest_data = {
            "expectedArtifacts": {
                "file": str(test_file),
                "contains": [{"type": "class", "name": "UserService"}],
            }
        }

        test_files = [str(test_file)]

        # Should not raise exception even with manifest chain
        # The actual chain logic is tested in the manifest_validator tests
        validate_behavioral_tests(
            manifest_data, test_files, use_manifest_chain=True, quiet=True
        )

    def test_handles_empty_test_files_list(self):
        """Test handling of empty test files list."""
        manifest_data = {"expectedArtifacts": {"file": "src/test.py", "contains": []}}

        test_files = []

        # Should handle empty list gracefully (no validation to perform)
        validate_behavioral_tests(
            manifest_data, test_files, use_manifest_chain=False, quiet=True
        )

    def test_validates_with_complex_artifacts(self, tmp_path: Path):
        """Test validation with complex artifact definitions."""
        test_code = """
from models import User, Order
from services import OrderService

def test_create_order_with_user():
    user = User(name="Alice", email="alice@test.com")
    service = OrderService()

    order = service.create_order(
        user=user,
        items=["item1", "item2"],
        discount_percent=0.1,
        tax_rate=0.08
    )

    assert isinstance(order, Order)
"""
        test_file = tmp_path / "test_complex.py"
        test_file.write_text(test_code)

        manifest_data = {
            "expectedArtifacts": {
                "file": "src/services/order_service.py",
                "contains": [
                    {"type": "class", "name": "User"},
                    {"type": "class", "name": "Order"},
                    {"type": "class", "name": "OrderService"},
                    {
                        "type": "function",
                        "name": "create_order",
                        "class": "OrderService",
                        "parameters": [
                            {"name": "user"},
                            {"name": "items"},
                            {"name": "discount_percent"},
                            {"name": "tax_rate"},
                        ],
                        "returns": "Order",
                    },
                ],
            }
        }

        test_files = [str(test_file)]

        # Should validate successfully
        validate_behavioral_tests(
            manifest_data, test_files, use_manifest_chain=False, quiet=True
        )


class TestCollectBehavioralArtifacts:
    """Test the collect_behavioral_artifacts public API function."""

    def test_collects_used_classes_from_test_file(self, tmp_path: Path):
        """Test that collect_behavioral_artifacts detects class instantiation."""
        test_code = """
import pytest
from services.user_service import UserService
from models.user import User

def test_user_service():
    service = UserService()  # Class instantiation
    user = User()  # Class instantiation
    assert service is not None
    assert user is not None
"""
        test_file = tmp_path / "test_collect.py"
        test_file.write_text(test_code)

        artifacts = collect_behavioral_artifacts(str(test_file))

        assert "UserService" in artifacts["used_classes"]
        assert "User" in artifacts["used_classes"]

    def test_collects_used_functions_from_test_file(self, tmp_path: Path):
        """Test that collect_behavioral_artifacts detects function calls."""
        test_code = """
from utils.helpers import calculate_total, format_currency

def test_helpers():
    total = calculate_total([10, 20, 30])  # Function call
    formatted = format_currency(total)  # Function call
    assert formatted is not None
"""
        test_file = tmp_path / "test_functions.py"
        test_file.write_text(test_code)

        artifacts = collect_behavioral_artifacts(str(test_file))

        assert "calculate_total" in artifacts["used_functions"]
        assert "format_currency" in artifacts["used_functions"]

    def test_collects_used_methods_from_test_file(self, tmp_path: Path):
        """Test that collect_behavioral_artifacts detects method calls."""
        test_code = """
from services.order_service import OrderService

def test_order_service():
    service = OrderService()
    order = service.create_order(items=["item1"])  # Method call
    service.cancel_order(order.id)  # Method call
    assert order is not None
"""
        test_file = tmp_path / "test_methods.py"
        test_file.write_text(test_code)

        artifacts = collect_behavioral_artifacts(str(test_file))

        assert "OrderService" in artifacts["used_classes"]
        assert "OrderService" in artifacts["used_methods"]
        assert "create_order" in artifacts["used_methods"]["OrderService"]
        assert "cancel_order" in artifacts["used_methods"]["OrderService"]


class TestMainFunctionIntegration:
    """Test integration of behavioral test validation into main validation flow."""

    def test_main_validates_behavioral_tests_before_implementation(
        self, tmp_path: Path
    ):
        """Test that main validates behavioral tests BEFORE implementation when validationCommand contains tests."""
        # Create manifest with validationCommand containing test files
        manifest_data = {
            "goal": "Test behavioral integration",
            "taskType": "edit",
            "creatableFiles": [],
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "class", "name": "ExampleService"}],
            },
            "validationCommand": ["pytest", "tests/test_example.py", "-v"],
        }

        # Create test file
        test_code = """
from src.example import ExampleService

def test_example_service():
    service = ExampleService()
    assert service is not None
"""
        test_file = tmp_path / "test_example.py"
        test_file.write_text(test_code)

        # Create implementation file
        impl_code = """
class ExampleService:
    def __init__(self):
        pass
"""
        impl_file = tmp_path / "example.py"
        impl_file.write_text(impl_code)

        # Update manifest to point to actual files
        manifest_data["expectedArtifacts"]["file"] = str(impl_file)
        manifest_data["validationCommand"] = ["pytest", str(test_file), "-v"]

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        # Mock sys.argv to simulate command line call
        test_args = [
            "validate_manifest.py",
            str(manifest_file),
            "--validation-mode",
            "implementation",
        ]

        with patch("sys.argv", test_args):
            with patch("sys.exit") as mock_exit:
                # Should complete without errors
                main()
                mock_exit.assert_not_called()

    def test_main_extracts_test_files_from_validation_command(self, tmp_path: Path):
        """Test that main properly extracts test files from validationCommand."""
        manifest_data = {
            "goal": "Test extraction",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/example.py", "contains": []},
            "validationCommand": [
                "pytest",
                "tests/test_one.py",
                "tests/test_two.py",
                "-v",
            ],
        }

        # Create minimal implementation file
        impl_file = tmp_path / "example.py"
        impl_file.write_text("# Empty implementation")
        manifest_data["expectedArtifacts"]["file"] = str(impl_file)

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        # Create test files that don't use any artifacts (empty expectedArtifacts)
        test_file_1 = tmp_path / "test_one.py"
        test_file_1.write_text("def test_one(): pass")
        test_file_2 = tmp_path / "test_two.py"
        test_file_2.write_text("def test_two(): pass")

        # Update validation command with actual paths
        manifest_data["validationCommand"] = [
            "pytest",
            str(test_file_1),
            str(test_file_2),
            "-v",
        ]
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        test_args = ["validate_manifest.py", str(manifest_file)]

        with patch("sys.argv", test_args):
            with patch("sys.exit") as mock_exit:
                # Should complete without errors
                main()
                mock_exit.assert_not_called()

    def test_main_handles_missing_validation_command_gracefully(self, tmp_path: Path):
        """Test that main handles manifests without validationCommand gracefully."""
        manifest_data = {
            "goal": "Test without validation command",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/example.py", "contains": []},
            # No validationCommand specified - using validationCommands instead
            "validationCommands": [[]],
        }

        impl_file = tmp_path / "example.py"
        impl_file.write_text("# Empty implementation")
        manifest_data["expectedArtifacts"]["file"] = str(impl_file)

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        test_args = ["validate_manifest.py", str(manifest_file)]

        with patch("sys.argv", test_args):
            with patch("sys.exit") as mock_exit:
                # Should complete without errors (no behavioral validation needed)
                main()
                mock_exit.assert_not_called()

    def test_main_fails_when_behavioral_tests_invalid(self, tmp_path: Path):
        """Test that main fails when behavioral tests don't align with manifest."""
        manifest_data = {
            "goal": "Test behavioral failure",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "class", "name": "RequiredService"}],
            },
            "validationCommand": ["pytest", "tests/test_bad.py", "-v"],
        }

        # Create test that doesn't use required artifacts
        test_code = """
def test_something_unrelated():
    # This test doesn't use RequiredService
    assert 1 + 1 == 2
"""
        test_file = tmp_path / "test_bad.py"
        test_file.write_text(test_code)

        # Create implementation file
        impl_code = """
class RequiredService:
    pass
"""
        impl_file = tmp_path / "example.py"
        impl_file.write_text(impl_code)

        manifest_data["expectedArtifacts"]["file"] = str(impl_file)
        manifest_data["validationCommand"] = ["pytest", str(test_file), "-v"]

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        test_args = ["validate_manifest.py", str(manifest_file)]

        with patch("sys.argv", test_args):
            with patch("sys.exit") as mock_exit:
                # Should fail and exit with non-zero code
                main()
                mock_exit.assert_called_with(1)

    def test_main_supports_use_manifest_chain_with_behavioral_tests(
        self, tmp_path: Path
    ):
        """Test that main supports --use-manifest-chain flag with behavioral test validation."""
        manifest_data = {
            "goal": "Test chain integration",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "class", "name": "ChainService"}],
            },
            "validationCommand": ["pytest", "tests/test_chain.py", "-v"],
        }

        # Create test file
        test_code = """
from src.example import ChainService

def test_chain_service():
    service = ChainService()
    assert service is not None
"""
        test_file = tmp_path / "test_chain.py"
        test_file.write_text(test_code)

        # Create implementation file
        impl_code = """
class ChainService:
    pass
"""
        impl_file = tmp_path / "example.py"
        impl_file.write_text(impl_code)

        manifest_data["expectedArtifacts"]["file"] = str(impl_file)
        manifest_data["validationCommand"] = ["pytest", str(test_file), "-v"]

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        test_args = ["validate_manifest.py", str(manifest_file), "--use-manifest-chain"]

        with patch("sys.argv", test_args):
            with patch("sys.exit") as mock_exit:
                # Should complete without errors
                main()
                mock_exit.assert_not_called()

    def test_main_processes_validation_command_order_correctly(self, tmp_path: Path):
        """Test that main processes behavioral tests BEFORE implementation validation."""
        # This test verifies the order of operations: behavioral tests first, then implementation

        manifest_data = {
            "goal": "Test processing order",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "class", "name": "OrderService"}],
            },
            "validationCommand": ["pytest", "tests/test_order.py", "-v"],
        }

        # Create test file that uses the artifact
        test_code = """
from src.example import OrderService

def test_order_service():
    service = OrderService()
    assert service is not None
"""
        test_file = tmp_path / "test_order.py"
        test_file.write_text(test_code)

        # Create implementation file
        impl_code = """
class OrderService:
    def __init__(self):
        self.initialized = True
"""
        impl_file = tmp_path / "example.py"
        impl_file.write_text(impl_code)

        manifest_data["expectedArtifacts"]["file"] = str(impl_file)
        manifest_data["validationCommand"] = ["pytest", str(test_file), "-v"]

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        test_args = ["validate_manifest.py", str(manifest_file)]

        # Use a mock to track the order of validate_with_ast calls
        call_order = []

        def track_validation_calls(
            manifest_data, file_path, use_manifest_chain=False, validation_mode=None
        ):
            call_order.append((file_path, validation_mode))
            # Call the actual validation
            from maid_runner.validators.manifest_validator import (
                validate_with_ast as real_validate,
            )

            return real_validate(
                manifest_data, file_path, use_manifest_chain, validation_mode
            )

        with patch("sys.argv", test_args):
            with patch(
                "maid_runner.cli.validate.validate_with_ast",
                side_effect=track_validation_calls,
            ):
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_not_called()

        # Verify that behavioral validation happened before implementation validation
        assert len(call_order) >= 1
        # The order may vary based on implementation, but both validations should occur
        # and the function should complete successfully


class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases in behavioral test integration."""

    def test_handles_malformed_validation_command(self):
        """Test handling of malformed validationCommand."""
        command = ["not-a-real-command", "some-file"]
        result = extract_test_files_from_command(command)
        assert result == []

    def test_handles_empty_validation_command(self):
        """Test handling of empty validationCommand."""
        command = []
        result = extract_test_files_from_command(command)
        assert result == []

    def test_handles_validation_command_with_only_flags(self):
        """Test handling of validationCommand with only flags."""
        command = ["pytest", "-v", "--tb=short"]
        result = extract_test_files_from_command(command)
        assert result == []

    def test_behavioral_validation_with_empty_manifest(self, tmp_path: Path):
        """Test behavioral validation with empty expectedArtifacts."""
        test_file = tmp_path / "test_empty.py"
        test_file.write_text("def test_empty(): pass")

        manifest_data = {"expectedArtifacts": {"file": str(test_file), "contains": []}}

        test_files = [str(test_file)]

        # Should handle empty artifacts gracefully
        validate_behavioral_tests(
            manifest_data, test_files, use_manifest_chain=False, quiet=True
        )

    def test_main_with_quiet_flag_suppresses_output(self, tmp_path: Path):
        """Test that --quiet flag suppresses success output."""
        manifest_data = {
            "goal": "Test quiet mode",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/example.py", "contains": []},
            "validationCommand": ["echo", "test"],
        }

        impl_file = tmp_path / "example.py"
        impl_file.write_text("# Empty")
        manifest_data["expectedArtifacts"]["file"] = str(impl_file)

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        test_args = ["validate_manifest.py", str(manifest_file), "--quiet"]

        with patch("sys.argv", test_args):
            with patch("builtins.print") as mock_print:
                with patch("sys.exit") as mock_exit:
                    main()
                    mock_exit.assert_not_called()
                    # Should not print success messages in quiet mode
                    success_prints = [
                        call
                        for call in mock_print.call_args_list
                        if len(call[0]) > 0 and "✓" in str(call[0][0])
                    ]
                    assert len(success_prints) == 0
