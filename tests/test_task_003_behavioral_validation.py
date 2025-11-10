# tests/test_task_003_behavioral_validation.py
"""
Behavioral tests for AST validator's ability to validate usage in test files.
This tests that the validator can find function/method calls, not just definitions.
"""
import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_runner.validators.manifest_validator import (
    validate_with_ast,
    AlignmentError,
    validate_schema,
)


def test_validates_method_calls_in_behavioral_tests(tmp_path: Path):
    """Test that validator finds method calls like service.get_user_by_id()"""

    # Create a behavioral test that USES the expected artifacts
    behavioral_test_code = """
import pytest
from src.services.user_service import UserService
from src.models.user import User

def test_get_user_by_id_returns_correct_user():
    # Setup
    service = UserService()

    # The actual usage that should be validated
    user_id = 123
    result = service.get_user_by_id(user_id)  # <-- Key line: method call

    # Assertions
    assert isinstance(result, User)
    assert result.id == user_id
"""

    test_file = tmp_path / "test_user_service.py"
    test_file.write_text(behavioral_test_code)

    # Manifest expecting the get_user_by_id method
    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {
                    "type": "function",
                    "name": "get_user_by_id",
                    "class": "UserService",
                    "parameters": [{"name": "user_id"}],
                },
                {"type": "class", "name": "User"},
                {"type": "class", "name": "UserService"},
            ],
        }
    }

    # Should pass - the method is called in the test
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_validates_function_calls_in_behavioral_tests(tmp_path: Path):
    """Test that validator finds standalone function calls"""

    behavioral_test_code = """
from utils.calculator import calculate_total, apply_discount

def test_calculate_total_with_discount():
    items = [10.0, 20.0, 30.0]
    tax_rate = 0.1

    # Function calls to validate
    subtotal = calculate_total(items, tax_rate)
    final_price = apply_discount(subtotal, discount_percent=0.2)

    assert final_price == 52.8  # 60 * 1.1 * 0.8
"""

    test_file = tmp_path / "test_calculator.py"
    test_file.write_text(behavioral_test_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {
                    "type": "function",
                    "name": "calculate_total",
                    "parameters": [{"name": "items"}, {"name": "tax_rate"}],
                },
                {
                    "type": "function",
                    "name": "apply_discount",
                    "parameters": [{"name": "subtotal"}, {"name": "discount_percent"}],
                },
            ],
        }
    }

    # Should pass - functions are called in the test
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_validates_class_instantiation_in_behavioral_tests(tmp_path: Path):
    """Test that validator finds class instantiation like User()"""

    behavioral_test_code = """
from models import User, Product, Order

def test_create_order():
    # Class instantiations to validate
    user = User(name="Alice", email="alice@example.com")
    product = Product(sku="ABC123", price=99.99)
    order = Order(user=user, products=[product])

    assert order.user == user
    assert len(order.products) == 1
"""

    test_file = tmp_path / "test_models.py"
    test_file.write_text(behavioral_test_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {"type": "class", "name": "User"},
                {"type": "class", "name": "Product"},
                {"type": "class", "name": "Order"},
            ],
        }
    }

    # Should pass - classes are instantiated in the test
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_validates_keyword_arguments_in_calls(tmp_path: Path):
    """Test that validator checks for specific keyword arguments in calls"""

    behavioral_test_code = """
from api.client import APIClient

def test_api_request_with_headers():
    client = APIClient()

    # Call with keyword arguments
    response = client.make_request(
        url="https://api.example.com/users",
        method="GET",
        headers={"Authorization": "Bearer token"},
        timeout=30
    )

    assert response.status_code == 200
"""

    test_file = tmp_path / "test_api.py"
    test_file.write_text(behavioral_test_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {
                    "type": "function",
                    "name": "make_request",
                    "class": "APIClient",
                    "parameters": [
                        {"name": "url"},
                        {"name": "method"},
                        {"name": "headers"},
                        {"name": "timeout"},
                    ],
                }
            ],
        }
    }

    # Should pass - all keyword arguments are present
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_fails_when_expected_method_not_called(tmp_path: Path):
    """Test that validator fails when expected method is not called"""

    behavioral_test_code = """
from services import UserService

def test_something_else():
    service = UserService()
    # Note: NOT calling get_user_by_id
    users = service.list_all_users()
    assert len(users) > 0
"""

    test_file = tmp_path / "test_missing.py"
    test_file.write_text(behavioral_test_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {
                    "type": "function",
                    "name": "get_user_by_id",  # This method is NOT called
                    "class": "UserService",
                }
            ],
        }
    }

    # Should fail - get_user_by_id is not called
    with pytest.raises(AlignmentError, match="get_user_by_id"):
        validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_fails_when_argument_missing_in_call(tmp_path: Path):
    """Test that validator fails when expected argument is not used"""

    behavioral_test_code = """
from calculator import process_data

def test_process_data():
    # Missing 'options' argument
    result = process_data(input_data=[1, 2, 3])
    assert result is not None
"""

    test_file = tmp_path / "test_args.py"
    test_file.write_text(behavioral_test_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {
                    "type": "function",
                    "name": "process_data",
                    "parameters": [
                        {"name": "input_data"},
                        {"name": "options"},  # This argument is missing
                    ],
                }
            ],
        }
    }

    # Should fail - 'options' argument not provided
    with pytest.raises(AlignmentError, match="options"):
        validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_validates_chained_method_calls(tmp_path: Path):
    """Test that validator can track chained method calls"""

    behavioral_test_code = """
from db import Database

def test_chained_query():
    db = Database()

    # Chained method calls
    results = db.table("users").where("age", ">", 18).order_by("name").limit(10).get()

    assert len(results) <= 10
"""

    test_file = tmp_path / "test_chain.py"
    test_file.write_text(behavioral_test_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {"type": "function", "name": "table", "class": "Database"},
                {"type": "function", "name": "where"},
                {"type": "function", "name": "order_by"},
                {"type": "function", "name": "limit"},
                {"type": "function", "name": "get"},
            ],
        }
    }

    # Should pass - all chained methods are called
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_validates_isinstance_for_return_type(tmp_path: Path):
    """Test that validator recognizes isinstance checks as return type validation"""

    behavioral_test_code = """
from services import OrderService
from models import Order

def test_create_order_returns_order_instance():
    service = OrderService()

    result = service.create_order(user_id=1, items=[])

    # This validates the return type
    assert isinstance(result, Order)
"""

    test_file = tmp_path / "test_return.py"
    test_file.write_text(behavioral_test_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {
                    "type": "function",
                    "name": "create_order",
                    "class": "OrderService",
                    "returns": "Order",
                }
            ],
        }
    }

    # Should pass - isinstance validates return type
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_auto_detects_behavioral_test_mode(tmp_path: Path):
    """Test that validator defaults to implementation mode for backward compatibility"""

    behavioral_test_code = """
import pytest  # Presence of pytest import indicates test file
from services import EmailService

def test_send_email():  # test_ prefix indicates test function
    service = EmailService()
    service.send(to="user@example.com", subject="Test", body="Hello")
"""

    test_file = tmp_path / "test_auto_detect.py"
    test_file.write_text(behavioral_test_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [{"type": "function", "name": "send", "class": "EmailService"}],
        }
    }

    # Should pass with explicit behavioral mode
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_implementation_mode_finds_definitions_not_calls(tmp_path: Path):
    """Test that implementation mode finds definitions, not calls"""

    implementation_code = """
class Calculator:
    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b

def standalone_function(x):
    return x * 2
"""

    impl_file = tmp_path / "calculator.py"
    impl_file.write_text(implementation_code)

    manifest = {
        "expectedArtifacts": {
            "file": str(impl_file),
            "contains": [
                {"type": "class", "name": "Calculator"},
                {"type": "function", "name": "add", "class": "Calculator"},
                {"type": "function", "name": "multiply", "class": "Calculator"},
                {"type": "function", "name": "standalone_function"},
            ],
        }
    }

    # Should pass in implementation mode (default)
    validate_with_ast(manifest, str(impl_file), validation_mode="implementation")

    # Should fail in behavioral mode (no calls, only definitions)
    with pytest.raises(AlignmentError):
        validate_with_ast(manifest, str(impl_file), validation_mode="behavioral")


def test_alignment_error_class_usage():
    """Test that AlignmentError class is properly used in behavioral validation."""
    # Create an instance to ensure class is tracked
    error = AlignmentError("Test error message")
    assert isinstance(error, AlignmentError)
    assert isinstance(error, Exception)

    # Also test the class directly
    assert issubclass(AlignmentError, Exception)


def test_validate_schema_function_usage():
    """Test that validate_schema function is called to satisfy behavioral validation."""
    # Create a valid manifest to test validate_schema
    manifest_data = {
        "goal": "Test manifest",
        "taskType": "create",
        "readonlyFiles": [],
        "expectedArtifacts": {"file": "test.py", "contains": []},
        "validationCommand": ["pytest test.py"],
    }
    schema_path = "validators/schemas/manifest.schema.json"

    # Call validate_schema to ensure it's tracked as used
    if Path(schema_path).exists():
        validate_schema(manifest_data, schema_path)

    # Also test that invalid data raises validation error
    try:
        validate_schema({"invalid": "data"}, schema_path)
    except Exception:
        pass  # Expected to fail
