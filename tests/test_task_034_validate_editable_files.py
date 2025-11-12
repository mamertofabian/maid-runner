"""
Tests for validating ALL files in editableFiles for undeclared artifacts (Task-034).

This closes the loophole where files in editableFiles could have undeclared
public artifacts without being validated.
"""

import tempfile
import pytest
from pathlib import Path
from maid_runner.validators.manifest_validator import (
    _validate_editable_files,
    _has_undeclared_public_artifacts,
    AlignmentError,
)


class TestHasUndeclaredPublicArtifacts:
    """Test detection of undeclared public artifacts in files."""

    def test_detects_undeclared_public_function(self):
        """Should detect file with undeclared public function."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
def public_function():
    '''A public function.'''
    pass
"""
            )
            f.flush()

            try:
                result = _has_undeclared_public_artifacts(f.name)
                assert result is True, "Should detect undeclared public function"
            finally:
                Path(f.name).unlink()

    def test_detects_undeclared_public_class(self):
        """Should detect file with undeclared public class."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
class PublicClass:
    '''A public class.'''
    pass
"""
            )
            f.flush()

            try:
                result = _has_undeclared_public_artifacts(f.name)
                assert result is True, "Should detect undeclared public class"
            finally:
                Path(f.name).unlink()

    def test_ignores_private_functions(self):
        """Should ignore files with only private functions."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
def _private_function():
    '''A private function.'''
    pass

def __dunder_function__():
    '''A dunder function.'''
    pass
"""
            )
            f.flush()

            try:
                result = _has_undeclared_public_artifacts(f.name)
                assert result is False, "Should ignore private functions"
            finally:
                Path(f.name).unlink()

    def test_ignores_private_classes(self):
        """Should ignore files with only private classes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
class _PrivateClass:
    '''A private class.'''
    pass
"""
            )
            f.flush()

            try:
                result = _has_undeclared_public_artifacts(f.name)
                assert result is False, "Should ignore private classes"
            finally:
                Path(f.name).unlink()

    def test_ignores_empty_file(self):
        """Should ignore empty files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            f.flush()

            try:
                result = _has_undeclared_public_artifacts(f.name)
                assert result is False, "Should ignore empty file"
            finally:
                Path(f.name).unlink()

    def test_ignores_import_only_file(self):
        """Should ignore files with only imports."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
import os
from typing import Dict

# Just imports, no public artifacts
"""
            )
            f.flush()

            try:
                result = _has_undeclared_public_artifacts(f.name)
                assert result is False, "Should ignore import-only file"
            finally:
                Path(f.name).unlink()

    def test_detects_mixed_public_and_private(self):
        """Should detect file with mix of public and private artifacts."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
def _private_helper():
    pass

def public_function():
    '''This is public!'''
    pass
"""
            )
            f.flush()

            try:
                result = _has_undeclared_public_artifacts(f.name)
                assert (
                    result is True
                ), "Should detect public artifact despite private ones"
            finally:
                Path(f.name).unlink()


class TestValidateEditableFiles:
    """Test validation of all files in editableFiles."""

    def test_passes_when_no_editable_files(self):
        """Should pass validation when no editableFiles specified."""
        manifest = {
            "editableFiles": [],
            "expectedArtifacts": {"file": "main.py", "contains": []},
        }
        # Should not raise
        _validate_editable_files(manifest, "implementation")

    def test_passes_when_editable_file_is_expected_artifacts_file(self):
        """Should pass when editableFile is the expectedArtifacts file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(
                """
def public_function():
    pass
"""
            )
            f.flush()

            try:
                manifest = {
                    "editableFiles": [f.name],
                    "expectedArtifacts": {
                        "file": f.name,
                        "contains": [{"type": "function", "name": "public_function"}],
                    },
                }
                # Should not raise - this file will be validated by main validator
                _validate_editable_files(manifest, "implementation")
            finally:
                Path(f.name).unlink()

    def test_raises_error_for_undeclared_artifacts_in_other_files(self):
        """Should raise error when editableFile has undeclared public artifacts."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as main_file:
            main_file.write("def main(): pass")
            main_file.flush()

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as other_file:
                other_file.write(
                    """
def undeclared_public_function():
    '''This is not declared!'''
    pass
"""
                )
                other_file.flush()

                try:
                    manifest = {
                        "editableFiles": [main_file.name, other_file.name],
                        "expectedArtifacts": {
                            "file": main_file.name,
                            "contains": [{"type": "function", "name": "main"}],
                        },
                    }

                    with pytest.raises(AlignmentError) as exc_info:
                        _validate_editable_files(manifest, "implementation")

                    assert other_file.name in str(exc_info.value)
                    assert "undeclared public artifacts" in str(exc_info.value).lower()

                finally:
                    Path(main_file.name).unlink()
                    Path(other_file.name).unlink()

    def test_passes_for_private_only_files(self):
        """Should pass when editableFile has only private artifacts."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as main_file:
            main_file.write("def main(): pass")
            main_file.flush()

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as helper_file:
                helper_file.write(
                    """
def _private_helper():
    '''Private helper function.'''
    pass

class _PrivateClass:
    '''Private class for internal use.'''
    pass
"""
                )
                helper_file.flush()

                try:
                    manifest = {
                        "editableFiles": [main_file.name, helper_file.name],
                        "expectedArtifacts": {
                            "file": main_file.name,
                            "contains": [{"type": "function", "name": "main"}],
                        },
                    }

                    # Should not raise - private artifacts are OK
                    _validate_editable_files(manifest, "implementation")

                finally:
                    Path(main_file.name).unlink()
                    Path(helper_file.name).unlink()

    def test_skips_validation_in_behavioral_mode(self):
        """Should skip validation in behavioral mode."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as other_file:
            other_file.write(
                """
def undeclared_function():
    pass
"""
            )
            other_file.flush()

            try:
                manifest = {
                    "editableFiles": ["main.py", other_file.name],
                    "expectedArtifacts": {"file": "main.py", "contains": []},
                }

                # Should not raise in behavioral mode
                _validate_editable_files(manifest, "behavioral")

            finally:
                Path(other_file.name).unlink()

    def test_handles_missing_editable_files_field(self):
        """Should handle manifests without editableFiles field."""
        manifest = {"expectedArtifacts": {"file": "main.py", "contains": []}}
        # Should not raise
        _validate_editable_files(manifest, "implementation")

    def test_handles_nonexistent_file_gracefully(self):
        """Should handle case where editableFile doesn't exist."""
        manifest = {
            "editableFiles": ["nonexistent.py"],
            "expectedArtifacts": {"file": "main.py", "contains": []},
        }
        # Should not raise - file might not exist yet in planning phase
        # Or it might be handled by other validation
        try:
            _validate_editable_files(manifest, "implementation")
        except FileNotFoundError:
            # Acceptable - implementation may choose to raise or skip
            pass


class TestIntegrationWithMainValidator:
    """Test integration with main validation workflow."""

    def test_catches_loophole_scenario(self):
        """Should catch the loophole where undeclared artifacts sneak through."""
        # Create two files
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as file1:
            file1.write(
                """
def declared_function():
    '''This is declared in manifest.'''
    pass
"""
            )
            file1.flush()

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False
            ) as file2:
                file2.write(
                    """
def sneaky_function():
    '''This is NOT declared but is public!'''
    pass
"""
                )
                file2.flush()

                try:
                    manifest = {
                        "editableFiles": [file1.name, file2.name],
                        "expectedArtifacts": {
                            "file": file1.name,
                            "contains": [
                                {"type": "function", "name": "declared_function"}
                            ],
                        },
                    }

                    # This should now be caught
                    with pytest.raises(AlignmentError) as exc_info:
                        _validate_editable_files(manifest, "implementation")

                    assert file2.name in str(exc_info.value)

                finally:
                    Path(file1.name).unlink()
                    Path(file2.name).unlink()
