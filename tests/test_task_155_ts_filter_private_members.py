"""Behavioral tests for TypeScript private member filtering.

Tests that the TypeScript validator correctly filters out private and
protected members from implementation validation.
"""

import tempfile
import os
from maid_runner.validators.typescript_validator import TypeScriptValidator


def _create_temp_ts_file(ts_code: bytes):
    """Helper to create temporary TypeScript file."""
    f = tempfile.NamedTemporaryFile(suffix=".ts", delete=False)
    f.write(ts_code)
    f.flush()
    f.close()
    return f.name


class TestIsPrivateMember:
    """Tests for _is_private_member helper function."""

    def test_detects_private_method(self):
        """Method with private keyword should be detected as private."""
        ts_code = b"""
class MyClass {
    private myMethod(): void {}
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            # Find the method_definition node
            class_body = None
            for node in tree.root_node.children:
                if node.type == "class_declaration":
                    for child in node.children:
                        if child.type == "class_body":
                            class_body = child
                            break
            assert class_body is not None
            method_node = None
            for child in class_body.children:
                if child.type == "method_definition":
                    method_node = child
                    break
            assert method_node is not None
            assert validator._is_private_member(method_node) is True
        finally:
            os.unlink(filepath)

    def test_detects_protected_method(self):
        """Method with protected keyword should be detected as private."""
        ts_code = b"""
class MyClass {
    protected myMethod(): void {}
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            class_body = None
            for node in tree.root_node.children:
                if node.type == "class_declaration":
                    for child in node.children:
                        if child.type == "class_body":
                            class_body = child
                            break
            method_node = None
            for child in class_body.children:
                if child.type == "method_definition":
                    method_node = child
                    break
            assert validator._is_private_member(method_node) is True
        finally:
            os.unlink(filepath)

    def test_public_method_not_private(self):
        """Method with public keyword or no modifier should not be private."""
        ts_code = b"""
class MyClass {
    public myMethod(): void {}
    anotherMethod(): void {}
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            class_body = None
            for node in tree.root_node.children:
                if node.type == "class_declaration":
                    for child in node.children:
                        if child.type == "class_body":
                            class_body = child
                            break
            methods = [c for c in class_body.children if c.type == "method_definition"]
            assert len(methods) == 2
            for method in methods:
                assert validator._is_private_member(method) is False
        finally:
            os.unlink(filepath)

    def test_detects_private_property(self):
        """Property with private keyword should be detected as private."""
        ts_code = b"""
class MyClass {
    private myProperty: string;
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            class_body = None
            for node in tree.root_node.children:
                if node.type == "class_declaration":
                    for child in node.children:
                        if child.type == "class_body":
                            class_body = child
                            break
            prop_node = None
            for child in class_body.children:
                if child.type == "public_field_definition":
                    prop_node = child
                    break
            assert prop_node is not None
            assert validator._is_private_member(prop_node) is True
        finally:
            os.unlink(filepath)


class TestFindClassMethodsFiltersPrivate:
    """Tests for _find_class_methods filtering private members."""

    def test_excludes_private_methods(self):
        """Private methods should not be included in class methods."""
        ts_code = b"""
class MaidStatusBar {
    private statusBarItem: any;
    private currentState: string = "hidden";
    private disposables: any[] = [];

    public show(): void {}
    public hide(): void {}
    private updateVisibility(): void {}
    getState(): string { return this.currentState; }
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            # Find the class node
            class_node = None
            for node in tree.root_node.children:
                if node.type == "class_declaration":
                    class_node = node
                    break
            assert class_node is not None
            methods = validator._find_class_methods(class_node, source_code)
            # Public methods should be included
            assert "show" in methods
            assert "hide" in methods
            assert "getState" in methods
            # Private method should be excluded
            assert "updateVisibility" not in methods
        finally:
            os.unlink(filepath)

    def test_includes_public_and_unmodified_methods(self):
        """Public and unmodified methods should be included."""
        ts_code = b"""
class Service {
    public fetch(): void {}
    update(): void {}
    protected internalMethod(): void {}
    private privateMethod(): void {}
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            class_node = None
            for node in tree.root_node.children:
                if node.type == "class_declaration":
                    class_node = node
                    break
            methods = validator._find_class_methods(class_node, source_code)
            # Public and unmodified should be included
            assert "fetch" in methods
            assert "update" in methods
            # Protected and private should be excluded
            assert "internalMethod" not in methods
            assert "privateMethod" not in methods
        finally:
            os.unlink(filepath)


class TestArrowFunctionsFiltersPrivate:
    """Tests for filtering private arrow function class properties."""

    def test_excludes_private_arrow_functions(self):
        """Private arrow function class properties should be excluded."""
        ts_code = b"""
class Service {
    private privateHandler = () => {};
    public publicHandler = () => {};
    protectedHandler = () => {};
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "implementation")
            functions = artifacts["found_functions"]
            # Public arrow function should be included
            assert "publicHandler" in functions
            # Unmodified arrow function should be included (default public)
            assert "protectedHandler" in functions
            # Private arrow function should be excluded
            assert "privateHandler" not in functions
        finally:
            os.unlink(filepath)

    def test_excludes_protected_arrow_functions(self):
        """Protected arrow function class properties should be excluded."""
        ts_code = b"""
class Service {
    protected protectedMethod = (x: number) => x * 2;
    public publicMethod = (x: number) => x + 1;
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "implementation")
            functions = artifacts["found_functions"]
            # Public should be included
            assert "publicMethod" in functions
            # Protected should be excluded
            assert "protectedMethod" not in functions
        finally:
            os.unlink(filepath)


class TestCollectArtifactsFiltersPrivate:
    """Integration tests for full artifact collection with private filtering."""

    def test_implementation_artifacts_exclude_private_members(self):
        """Implementation mode should not include private class members."""
        ts_code = b"""
export class MaidStatusBar {
    private statusBarItem: any;
    private currentState: string = "hidden";
    private disposables: any[] = [];

    public show(): void {}
    public hide(): void {}
    private updateVisibility(): void {}
    public getState(): string { return this.currentState; }
    public dispose(): void {}
}
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "implementation")

            # Class should be found
            assert "MaidStatusBar" in artifacts["found_classes"]

            # Public methods should be in methods
            methods = artifacts["found_methods"].get("MaidStatusBar", {})
            assert "show" in methods
            assert "hide" in methods
            assert "getState" in methods
            assert "dispose" in methods

            # Private members should NOT be in methods
            assert "updateVisibility" not in methods
            assert "statusBarItem" not in methods
            assert "currentState" not in methods
            assert "disposables" not in methods
        finally:
            os.unlink(filepath)
