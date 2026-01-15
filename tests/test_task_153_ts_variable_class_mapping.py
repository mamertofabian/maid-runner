"""Behavioral tests for TypeScript variable-to-class mapping enhancement.

Tests that the TypeScript validator correctly maps variables to classes from:
1. Type annotations on variable declarations (let statusBar: MaidStatusBar;)
2. Assignment expressions (statusBar = new MaidStatusBar();)
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


class TestTypeAnnotatedVariables:
    """Tests for extracting variable-to-class mapping from type annotations."""

    def test_extracts_type_from_let_declaration(self):
        """Variable declared with type annotation should map to that class."""
        ts_code = b"""
let statusBar: MaidStatusBar;
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_type_annotated_variables(tree, source_code)
            assert "statusBar" in mapping
            assert mapping["statusBar"] == "MaidStatusBar"
        finally:
            os.unlink(filepath)

    def test_extracts_type_from_const_declaration(self):
        """Const with type annotation should map to that class."""
        ts_code = b"""
const service: UserService;
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_type_annotated_variables(tree, source_code)
            assert "service" in mapping
            assert mapping["service"] == "UserService"
        finally:
            os.unlink(filepath)

    def test_extracts_multiple_type_annotations(self):
        """Multiple type-annotated variables should all be mapped."""
        ts_code = b"""
let statusBar: MaidStatusBar;
let service: UserService;
const config: ConfigManager;
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_type_annotated_variables(tree, source_code)
            assert mapping.get("statusBar") == "MaidStatusBar"
            assert mapping.get("service") == "UserService"
            assert mapping.get("config") == "ConfigManager"
        finally:
            os.unlink(filepath)

    def test_ignores_primitive_types(self):
        """Primitive type annotations should not create mappings."""
        ts_code = b"""
let name: string;
let count: number;
let active: boolean;
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_type_annotated_variables(tree, source_code)
            # Primitive types should not be in the mapping
            assert "name" not in mapping
            assert "count" not in mapping
            assert "active" not in mapping
        finally:
            os.unlink(filepath)


class TestAssignmentInstantiations:
    """Tests for extracting variable-to-class mapping from assignment expressions."""

    def test_extracts_from_assignment_expression(self):
        """Assignment with new expression should map variable to class."""
        ts_code = b"""
let statusBar;
statusBar = new MaidStatusBar();
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_assignment_instantiations(tree, source_code)
            assert "statusBar" in mapping
            assert mapping["statusBar"] == "MaidStatusBar"
        finally:
            os.unlink(filepath)

    def test_extracts_from_assignment_in_callback(self):
        """Assignment in callback should map variable to class."""
        ts_code = b"""
let statusBar: MaidStatusBar;

beforeEach(() => {
    statusBar = new MaidStatusBar();
});
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_assignment_instantiations(tree, source_code)
            assert "statusBar" in mapping
            assert mapping["statusBar"] == "MaidStatusBar"
        finally:
            os.unlink(filepath)

    def test_extracts_multiple_assignments(self):
        """Multiple assignment instantiations should all be mapped."""
        ts_code = b"""
let statusBar;
let service;

beforeEach(() => {
    statusBar = new MaidStatusBar();
    service = new UserService();
});
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_assignment_instantiations(tree, source_code)
            assert mapping.get("statusBar") == "MaidStatusBar"
            assert mapping.get("service") == "UserService"
        finally:
            os.unlink(filepath)


class TestVariableToClassMappingIntegration:
    """Integration tests for the combined variable-to-class mapping."""

    def test_combines_type_annotations_and_assignments(self):
        """Both type annotations and assignments should contribute to mapping."""
        ts_code = b"""
let statusBar: MaidStatusBar;
let service;

beforeEach(() => {
    statusBar = new MaidStatusBar();
    service = new UserService();
});
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            tree, source_code = validator._parse_typescript_file(filepath)
            mapping = validator._extract_variable_to_class_mapping(tree, source_code)
            # statusBar should be mapped (from type annotation or assignment)
            assert mapping.get("statusBar") == "MaidStatusBar"
            # service should be mapped (from assignment)
            assert mapping.get("service") == "UserService"
        finally:
            os.unlink(filepath)

    def test_behavioral_validation_with_separate_declaration_and_assignment(self):
        """Method calls on variables with separate declaration/assignment should resolve to class."""
        ts_code = b"""
import { MaidStatusBar } from "../src/statusBar";

describe("MaidStatusBar", () => {
    let statusBar: MaidStatusBar;

    beforeEach(() => {
        statusBar = new MaidStatusBar();
    });

    it("should dispose", () => {
        statusBar.dispose();
    });

    it("should get state", () => {
        const state = statusBar.getState();
    });
});
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            used_methods = artifacts["used_methods"]
            # Methods should be mapped to MaidStatusBar, not to 'statusBar'
            assert "MaidStatusBar" in used_methods
            assert "dispose" in used_methods["MaidStatusBar"]
            assert "getState" in used_methods["MaidStatusBar"]
        finally:
            os.unlink(filepath)

    def test_existing_pattern_still_works(self):
        """Existing pattern (declaration with instantiation) should still work."""
        ts_code = b"""
const statusBar = new MaidStatusBar();
statusBar.dispose();
"""
        filepath = _create_temp_ts_file(ts_code)
        try:
            validator = TypeScriptValidator()
            artifacts = validator.collect_artifacts(filepath, "behavioral")
            used_methods = artifacts["used_methods"]
            assert "MaidStatusBar" in used_methods
            assert "dispose" in used_methods["MaidStatusBar"]
        finally:
            os.unlink(filepath)
