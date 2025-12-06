"""
Private test module for private artifact behavioral validation fix.

Tests verify that:
1. Private functions/classes declared in manifests are NOT skipped in behavioral validation
2. Manifest declaration overrides naming convention - if it's in the manifest, it's part of the contract
3. Private artifacts NOT in manifests are still allowed (handled by unexpected artifact checks)
"""

import pytest
from pathlib import Path

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        should_skip_behavioral_validation,
        validate_with_ast,
    )
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestPrivateArtifactsInManifests:
    """Test that private artifacts declared in manifests are behaviorally validated."""

    def test_private_function_in_manifest_not_skipped(self):
        """Test that a private function declared in manifest is NOT skipped."""
        # Private function declared in manifest
        private_function = {
            "type": "function",
            "name": "_helper_function",
            "parameters": [{"name": "x", "type": "int"}],
        }

        # USE the function - should return False (NOT skipped) because it's in manifest
        result = should_skip_behavioral_validation(private_function)
        assert result is False, (
            "Private functions declared in manifests should NOT be skipped. "
            "Manifest declaration overrides naming convention."
        )

    def test_private_class_in_manifest_not_skipped(self):
        """Test that a private class declared in manifest is NOT skipped."""
        # Private class declared in manifest
        private_class = {
            "type": "class",
            "name": "_HelperClass",
        }

        # USE the function - should return False (NOT skipped) because it's in manifest
        result = should_skip_behavioral_validation(private_class)
        assert result is False, (
            "Private classes declared in manifests should NOT be skipped. "
            "Manifest declaration overrides naming convention."
        )

    def test_private_method_in_manifest_not_skipped(self):
        """Test that a private method declared in manifest is NOT skipped."""
        # Private method declared in manifest
        private_method = {
            "type": "function",
            "name": "_internal_method",
            "class": "PublicClass",
            "parameters": [{"name": "value", "type": "str"}],
        }

        # USE the function - should return False (NOT skipped) because it's in manifest
        result = should_skip_behavioral_validation(private_method)
        assert result is False, (
            "Private methods declared in manifests should NOT be skipped. "
            "Manifest declaration overrides naming convention."
        )

    def test_private_function_with_type_kind_still_skipped(self):
        """Test that explicit type-only metadata still causes skip."""
        # Private function with explicit type-only kind
        private_type_function = {
            "type": "function",
            "name": "_type_helper",
            "artifactKind": "type",  # Explicit opt-out
        }

        # USE the function - should return True (skipped) because of explicit type kind
        result = should_skip_behavioral_validation(private_type_function)
        assert result is True, (
            "Private functions with explicit artifactKind='type' should still be skipped."
        )

    def test_private_function_behavioral_validation_integration(self, tmp_path: Path):
        """Test end-to-end: private function in manifest must be used in behavioral tests."""
        # Create implementation file with private function
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
def _helper_function(x: int) -> int:
    return x * 2

def public_function(value: int) -> int:
    return _helper_function(value)
"""
        )

        # Create test file that uses both functions
        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
from module import _helper_function, public_function

def test_helper_function():
    # USE the private function declared in manifest
    result = _helper_function(5)
    assert result == 10

def test_public_function():
    # USE the public function declared in manifest
    result = public_function(5)
    assert result == 10
"""
        )

        # Manifest declares the private function
        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {"type": "function", "name": "_helper_function", "parameters": [{"name": "x", "type": "int"}]},
                    {"type": "function", "name": "public_function", "parameters": [{"name": "value", "type": "int"}]},
                ],
            },
            "validationCommand": ["pytest", str(test_file), "-v"],
        }

        # Behavioral validation should pass - private function is used in test
        validate_with_ast(manifest, str(test_file), validation_mode="behavioral")

    def test_private_function_not_used_fails_behavioral_validation(self, tmp_path: Path):
        """Test that private function in manifest must be used in behavioral tests."""
        # Create implementation file with private function
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
def _helper_function(x: int) -> int:
    return x * 2

def public_function(value: int) -> int:
    return _helper_function(value)
"""
        )

        # Create test file that does NOT use the private function
        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
from module import public_function

def test_public_function():
    # Only test public function, not the private one
    result = public_function(5)
    assert result == 10
"""
        )

        # Manifest declares the private function
        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {"type": "function", "name": "_helper_function", "parameters": [{"name": "x", "type": "int"}]},
                    {"type": "function", "name": "public_function", "parameters": [{"name": "value", "type": "int"}]},
                ],
            },
            "validationCommand": ["pytest", str(test_file), "-v"],
        }

        # Behavioral validation should FAIL - private function declared but not used
        from maid_runner.validators.manifest_validator import AlignmentError

        with pytest.raises(AlignmentError, match="Function '_helper_function' not called in behavioral test"):
            validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


class TestPrivateArtifactsNotInManifests:
    """Test that private artifacts NOT in manifests are still handled correctly."""

    def test_private_function_not_in_manifest_allowed(self, tmp_path: Path):
        """Test that private functions NOT in manifest are allowed (implementation detail)."""
        # Create implementation file with private function NOT in manifest
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
def _internal_helper(x: int) -> int:
    return x * 2

def public_function(value: int) -> int:
    return _internal_helper(value)
"""
        )

        # Manifest only declares public function
        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {"type": "function", "name": "public_function", "parameters": [{"name": "value", "type": "int"}]},
                    # _internal_helper is NOT declared - should be allowed as implementation detail
                ],
            },
        }

        # Implementation validation should pass - private function not declared is allowed
        validate_with_ast(manifest, str(impl_file), validation_mode="implementation")

