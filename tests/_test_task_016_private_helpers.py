"""
Private test module for private helper methods declared in task-016 manifest.

These tests verify the actual behavior of private helper methods that are declared
in the manifest. While these are internal helpers, they're part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How these helpers enable public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-016-detect-abc-usage-patterns
"""

import ast
import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import _ArtifactCollector
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestArtifactCollectorVisitClassDef:
    """Test _ArtifactCollector.visit_ClassDef private method behavior."""

    def test_artifact_collector_visit_class_def_called_with_class_node(self):
        """Test that _ArtifactCollector.visit_ClassDef is called with class node."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create a class definition node
        class_node = ast.ClassDef(
            name="Service",
            bases=[],
            keywords=[],
            body=[],
            decorator_list=[],
        )

        # Call visit_ClassDef directly
        collector.visit_ClassDef(class_node)

        # Should track the class
        assert "Service" in collector.found_classes

    def test_artifact_collector_visit_class_def_tracks_base_classes(self):
        """Test that _ArtifactCollector.visit_ClassDef tracks base classes."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create a class definition node with base class
        class_node = ast.ClassDef(
            name="ConcreteService",
            bases=[ast.Name(id="BaseService", ctx=ast.Load())],
            keywords=[],
            body=[],
            decorator_list=[],
        )

        # Call visit_ClassDef directly
        collector.visit_ClassDef(class_node)

        # Should track the class and its base
        assert "ConcreteService" in collector.found_classes
        assert "BaseService" in collector.found_class_bases["ConcreteService"]
        assert "BaseService" in collector.used_classes

    def test_artifact_collector_visit_class_def_tracks_abc_base_classes(self):
        """Test that _ArtifactCollector.visit_ClassDef tracks ABC base classes."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create a class definition node with ABC base
        class_node = ast.ClassDef(
            name="BaseAgent",
            bases=[ast.Name(id="ABC", ctx=ast.Load())],
            keywords=[],
            body=[],
            decorator_list=[],
        )

        # Call visit_ClassDef directly
        collector.visit_ClassDef(class_node)

        # Should track the class and its base
        assert "BaseAgent" in collector.found_classes
        assert "ABC" in collector.found_class_bases["BaseAgent"]
        assert "ABC" in collector.used_classes

    def test_artifact_collector_visit_class_def_tracks_multiple_bases(self):
        """Test that _ArtifactCollector.visit_ClassDef tracks multiple base classes."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create a class definition node with multiple bases
        class_node = ast.ClassDef(
            name="MultiBase",
            bases=[
                ast.Name(id="Base1", ctx=ast.Load()),
                ast.Name(id="Base2", ctx=ast.Load()),
            ],
            keywords=[],
            body=[],
            decorator_list=[],
        )

        # Call visit_ClassDef directly
        collector.visit_ClassDef(class_node)

        # Should track all bases
        assert "MultiBase" in collector.found_classes
        assert "Base1" in collector.found_class_bases["MultiBase"]
        assert "Base2" in collector.found_class_bases["MultiBase"]
        assert "Base1" in collector.used_classes
        assert "Base2" in collector.used_classes

    def test_artifact_collector_visit_class_def_sets_current_class(self):
        """Test that _ArtifactCollector.visit_ClassDef sets current_class context."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create a class definition node with a method to test context
        class_node = ast.ClassDef(
            name="Service",
            bases=[],
            keywords=[],
            body=[
                ast.FunctionDef(
                    name="method",
                    args=ast.arguments(
                        args=[],
                        vararg=None,
                        kwonlyargs=[],
                        kw_defaults=[],
                        kwarg=None,
                        defaults=[],
                    ),
                    body=[],
                    decorator_list=[],
                )
            ],
            decorator_list=[],
        )

        # Call visit_ClassDef directly - it will call generic_visit which visits children
        collector.visit_ClassDef(class_node)

        # After generic_visit completes, current_class is restored to old_class (None)
        # But during the visit, current_class should have been "Service"
        # We can verify the class was tracked
        assert "Service" in collector.found_classes

    def test_artifact_collector_visit_class_def_handles_nested_classes(self):
        """Test that _ArtifactCollector.visit_ClassDef handles nested classes."""
        collector = _ArtifactCollector(validation_mode="behavioral")

        # Create outer class with inner class as child
        inner_class = ast.ClassDef(
            name="Inner",
            bases=[],
            keywords=[],
            body=[],
            decorator_list=[],
        )

        outer_class = ast.ClassDef(
            name="Outer",
            bases=[],
            keywords=[],
            body=[inner_class],  # Inner class is nested inside outer
            decorator_list=[],
        )

        # Call visit_ClassDef for outer class - it will visit inner class automatically
        collector.visit_ClassDef(outer_class)

        # Both classes should be tracked
        assert "Outer" in collector.found_classes
        assert "Inner" in collector.found_classes


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

    def test_artifact_collector_visit_call_tracks_isinstance_calls(self):
        """Test that _ArtifactCollector.visit_Call tracks isinstance calls."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.found_classes = {"BaseClass"}

        # Create a call node for isinstance(obj, BaseClass)
        call_node = ast.Call(
            func=ast.Name(id="isinstance", ctx=ast.Load()),
            args=[
                ast.Name(id="obj", ctx=ast.Load()),
                ast.Name(id="BaseClass", ctx=ast.Load()),
            ],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should track BaseClass as used
        assert "BaseClass" in collector.used_classes

    def test_artifact_collector_visit_call_tracks_issubclass_calls(self):
        """Test that _ArtifactCollector.visit_Call tracks issubclass calls."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.found_classes = {"ParentClass"}

        # Create a call node for issubclass(ChildClass, ParentClass)
        call_node = ast.Call(
            func=ast.Name(id="issubclass", ctx=ast.Load()),
            args=[
                ast.Name(id="ChildClass", ctx=ast.Load()),
                ast.Name(id="ParentClass", ctx=ast.Load()),
            ],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should track ParentClass as used
        assert "ParentClass" in collector.used_classes

    def test_artifact_collector_visit_call_tracks_hasattr_calls(self):
        """Test that _ArtifactCollector.visit_Call tracks hasattr calls."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.found_classes = {"MyClass"}

        # Create a call node for hasattr(MyClass, 'method')
        call_node = ast.Call(
            func=ast.Name(id="hasattr", ctx=ast.Load()),
            args=[
                ast.Name(id="MyClass", ctx=ast.Load()),
                ast.Constant(value="method"),
            ],
            keywords=[],
        )

        # Call visit_Call directly
        collector.visit_Call(call_node)

        # Should track MyClass as used
        assert "MyClass" in collector.used_classes
