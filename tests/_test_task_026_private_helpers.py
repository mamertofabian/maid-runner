"""
Private test module for private helper method declared in task-026 manifest.

These tests verify the actual behavior of private helper method that is declared
in the manifest. While this is an internal helper, it's part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How this helper enables public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-026-detect-classmethod-calls-on-class
"""

import ast
import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import _ArtifactCollector
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestArtifactCollectorVisitCall:
    """Test _ArtifactCollector.visit_Call private method behavior."""

    def test_artifact_collector_visit_call_called_with_call_node(self):
        """Test that _ArtifactCollector.visit_Call is called with call node."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.found_classes = {"Service"}

        # Create a call node for Service.method()
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="Service", ctx=ast.Load()),
                attr="method",
                ctx=ast.Load(),
            ),
            args=[],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should track the method call
        assert "method" in collector.used_functions
        assert "Service" in collector.used_classes

    def test_artifact_collector_visit_call_tracks_classmethod_calls(self):
        """Test that _ArtifactCollector.visit_Call tracks classmethod calls on class names."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.found_classes = {"ConfigService"}

        # Create a call node for ConfigService.create_default()
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="ConfigService", ctx=ast.Load()),
                attr="create_default",
                ctx=ast.Load(),
            ),
            args=[ast.Constant(value="test")],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should track the classmethod call
        assert "create_default" in collector.used_functions
        assert "ConfigService" in collector.used_classes

    def test_artifact_collector_visit_call_tracks_staticmethod_calls(self):
        """Test that _ArtifactCollector.visit_Call tracks staticmethod calls on class names."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.found_classes = {"DataValidator"}

        # Create a call node for DataValidator.validate_email()
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="DataValidator", ctx=ast.Load()),
                attr="validate_email",
                ctx=ast.Load(),
            ),
            args=[ast.Constant(value="test@example.com")],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should track the staticmethod call
        assert "validate_email" in collector.used_functions
        assert "DataValidator" in collector.used_classes

    def test_artifact_collector_visit_call_tracks_function_calls(self):
        """Test that _ArtifactCollector.visit_Call tracks regular function calls."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create a call node for process()
        call_node = ast.Call(
            func=ast.Name(id="process", ctx=ast.Load()),
            args=[],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should track the function call
        assert "process" in collector.used_functions

    def test_artifact_collector_visit_call_handles_instance_method_calls(self):
        """Test that _ArtifactCollector.visit_Call handles instance method calls."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.variable_to_class = {"calc": "Calculator"}

        # Create a call node for calc.add()
        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="calc", ctx=ast.Load()),
                attr="add",
                ctx=ast.Load(),
            ),
            args=[ast.Constant(value=2), ast.Constant(value=3)],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should track the method call
        assert "add" in collector.used_functions

    def test_artifact_collector_visit_call_ignores_in_implementation_mode(self):
        """Test that _ArtifactCollector.visit_Call ignores calls in implementation mode."""
        collector = _ArtifactCollector(validation_mode="implementation")

        # Create a call node
        call_node = ast.Call(
            func=ast.Name(id="process", ctx=ast.Load()),
            args=[],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should not track calls in implementation mode
        assert "process" not in collector.used_functions
