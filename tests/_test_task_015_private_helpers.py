"""
Private test module for private helper method declared in task-015 manifest.

These tests verify the actual behavior of private helper method that is declared
in the manifest. While this is an internal helper, it's part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How this helper enables public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-015-fix-enum-import-detection
"""

import ast
import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import _ArtifactCollector
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestArtifactCollectorIsLocalImport:
    """Test _ArtifactCollector._is_local_import private method behavior."""

    def test_artifact_collector_is_local_import_called_with_import_node(self):
        """Test that _ArtifactCollector._is_local_import is called with import node."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create an import from node for enum.Enum
        import_node = ast.ImportFrom(
            module="enum",
            names=[ast.alias(name="Enum", asname=None)],
            level=0,
        )

        # Call _is_local_import directly
        is_local = collector._is_local_import(import_node)

        # enum is stdlib, so should return False
        assert is_local is False

    def test_artifact_collector_is_local_import_returns_false_for_stdlib_modules(self):
        """Test that _ArtifactCollector._is_local_import returns False for stdlib modules."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Test various stdlib modules
        stdlib_modules = [
            "enum",
            "pathlib",
            "typing",
            "collections",
            "datetime",
            "json",
            "ast",
        ]

        for module in stdlib_modules:
            import_node = ast.ImportFrom(
                module=module,
                names=[ast.alias(name="SomeClass", asname=None)],
                level=0,
            )

            is_local = collector._is_local_import(import_node)
            assert is_local is False, f"{module} should not be local"

    def test_artifact_collector_is_local_import_returns_true_for_relative_imports(self):
        """Test that _ArtifactCollector._is_local_import returns True for relative imports."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Test relative imports (level > 0)
        for level in [1, 2, 3]:
            import_node = ast.ImportFrom(
                module="models",
                names=[ast.alias(name="User", asname=None)],
                level=level,
            )

            is_local = collector._is_local_import(import_node)
            assert (
                is_local is True
            ), f"Relative import with level {level} should be local"

    def test_artifact_collector_is_local_import_returns_true_for_non_stdlib_modules(
        self,
    ):
        """Test that _ArtifactCollector._is_local_import returns True for non-stdlib modules."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Test non-stdlib modules
        non_stdlib_modules = ["maid_runner", "my_module", "custom_package"]

        for module in non_stdlib_modules:
            import_node = ast.ImportFrom(
                module=module,
                names=[ast.alias(name="SomeClass", asname=None)],
                level=0,
            )

            is_local = collector._is_local_import(import_node)
            assert is_local is True, f"{module} should be local"

    def test_artifact_collector_is_local_import_handles_enum_module(self):
        """Test that _ArtifactCollector._is_local_import correctly handles enum module."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create an import from node for enum.Enum
        import_node = ast.ImportFrom(
            module="enum",
            names=[ast.alias(name="Enum", asname=None)],
            level=0,
        )

        # Call _is_local_import directly
        is_local = collector._is_local_import(import_node)

        # enum is stdlib, so should return False
        assert is_local is False

    def test_artifact_collector_is_local_import_handles_none_module(self):
        """Test that _ArtifactCollector._is_local_import handles None module (relative import)."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create a relative import with None module
        import_node = ast.ImportFrom(
            module=None,
            names=[ast.alias(name="User", asname=None)],
            level=1,
        )

        # Call _is_local_import directly
        is_local = collector._is_local_import(import_node)

        # Relative imports should return True
        assert is_local is True
