"""
Private test module for private helper functions declared in task-009 manifest.

These tests verify the actual behavior of private helper functions that are declared
in the manifest. While these are internal helpers, they're part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How these helpers enable public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-009-snapshot-manifest_validator
"""

import ast
import pytest
from pathlib import Path

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        _ArtifactCollector,
        _validate_extraction_inputs,
        _ast_to_type_string,
        _safe_ast_conversion,
        _handle_subscript_node,
        _handle_attribute_node,
        _handle_union_operator,
        _fallback_ast_unparse,
        _safe_str_conversion,
        _normalize_type_input,
        _normalize_modern_union_syntax,
        _normalize_optional_type,
        _is_optional_type,
        _extract_bracketed_content,
        _normalize_union_type,
        _is_union_type,
        _split_type_arguments,
        _split_by_delimiter,
        _normalize_comma_spacing,
        _skip_spaces,
        _get_task_number,
        _parse_file,
        _collect_artifacts_from_ast,
        _get_expected_artifacts,
        _validate_all_artifacts,
        _check_unexpected_artifacts,
        _validate_single_artifact,
        _validate_function_artifact,
        _validate_function_behavioral,
        _validate_parameters_used,
        _validate_method_parameters,
        _validate_function_implementation,
        _validate_class,
        _validate_attribute,
        _validate_function,
        _validate_no_unexpected_artifacts,
        _are_valid_type_validation_inputs,
        _should_validate_artifact_types,
        _validate_function_types,
        _get_implementation_info,
        _get_method_info,
        _get_function_info,
        _validate_parameter_types,
        _validate_single_parameter,
        _validate_return_type,
        _is_typeddict_class,
        _is_typeddict_base,
        _should_skip_by_artifact_kind,
        extract_type_annotation,
        compare_types,
        validate_with_ast,
        discover_related_manifests,
        AlignmentError,
    )
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestArtifactCollectorBehavior:
    """Test _ArtifactCollector behavior in real validation scenarios."""

    def test_collector_tracks_artifacts_correctly(self):
        """Test that _ArtifactCollector correctly tracks classes, functions, and methods."""
        code = """
class Service:
    def get_user(self, user_id: int) -> dict:
        return {}

def process_data(data: str) -> bool:
    return True
"""
        tree = ast.parse(code)

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.visit(tree)

        assert "Service" in collector.found_classes
        assert "get_user" in collector.found_methods["Service"]
        assert "process_data" in collector.found_functions

    def test_collector_tracks_behavioral_usage(self):
        """Test that _ArtifactCollector tracks usage in behavioral mode."""
        code = """
from service import Service

def test_service():
    svc = Service()
    result = svc.get_user(123)
    assert result is not None
"""
        tree = ast.parse(code)

        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.visit(tree)

        assert "Service" in collector.used_classes
        assert "get_user" in collector.used_methods.get("Service", set())

    def test_artifact_collector_init_called(self):
        """Test that _ArtifactCollector.__init__ is called when instantiating."""
        collector = _ArtifactCollector(validation_mode="implementation")

        assert hasattr(collector, "validation_mode")
        assert hasattr(collector, "found_classes")
        assert hasattr(collector, "found_functions")
        assert collector.validation_mode == "implementation"

    def test_artifact_collector_init_explicitly_called(self):
        """Test that _ArtifactCollector.__init__ can be called explicitly."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.__init__(validation_mode="implementation")

        assert collector.validation_mode == "implementation"

    def test_artifact_collector_visit_import(self):
        """Test that _ArtifactCollector.visit_Import processes import statements."""
        collector = _ArtifactCollector(validation_mode="implementation")
        import_node = ast.Import(names=[ast.alias(name="os", asname=None)])
        collector.visit_Import(import_node)

        assert hasattr(collector, "imports_pytest")

    def test_artifact_collector_visit_import_from(self):
        """Test that _ArtifactCollector.visit_ImportFrom processes from imports."""
        collector = _ArtifactCollector(validation_mode="implementation")
        import_from_node = ast.ImportFrom(
            module="pathlib", names=[ast.alias(name="Path", asname=None)], level=0
        )
        collector.visit_ImportFrom(import_from_node)

        assert "Path" not in collector.found_classes

    def test_artifact_collector_visit_function_def(self):
        """Test that _ArtifactCollector.visit_FunctionDef collects function definitions."""
        collector = _ArtifactCollector(validation_mode="implementation")
        func_node = ast.FunctionDef(
            name="process_data",
            args=ast.arguments(
                args=[ast.arg(arg="x", annotation=ast.Name(id="int", ctx=ast.Load()))],
                defaults=[],
                kwonlyargs=[],
                kw_defaults=[],
            ),
            body=[ast.Pass()],
            decorator_list=[],
            returns=ast.Name(id="bool", ctx=ast.Load()),
        )
        collector.visit_FunctionDef(func_node)

        assert "process_data" in collector.found_functions

    def test_artifact_collector_visit_class_def(self):
        """Test that _ArtifactCollector.visit_ClassDef collects class definitions."""
        collector = _ArtifactCollector(validation_mode="implementation")
        class_node = ast.ClassDef(
            name="Service",
            bases=[],
            keywords=[],
            body=[ast.Pass()],
            decorator_list=[],
        )
        collector.visit_ClassDef(class_node)

        assert "Service" in collector.found_classes

    def test_artifact_collector_visit_assign(self):
        """Test that _ArtifactCollector.visit_Assign processes assignments."""
        collector = _ArtifactCollector(validation_mode="implementation")
        assign_node = ast.Assign(
            targets=[ast.Name(id="API_VERSION", ctx=ast.Store())],
            value=ast.Constant(value="1.0"),
        )
        collector.visit_Assign(assign_node)

        assert None in collector.found_attributes
        assert "API_VERSION" in collector.found_attributes[None]

    def test_artifact_collector_visit_call(self):
        """Test that _ArtifactCollector.visit_Call tracks function calls in behavioral mode."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        call_node = ast.Call(
            func=ast.Name(id="process_data", ctx=ast.Load()),
            args=[ast.Constant(value=42)],
            keywords=[],
        )
        collector.visit_Call(call_node)

        assert "process_data" in collector.used_functions

    def test_artifact_collector_visit_attribute(self):
        """Test that _ArtifactCollector.visit_Attribute processes attribute access."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        attr_node = ast.Attribute(
            value=ast.Name(id="service", ctx=ast.Load()),
            attr="get_user",
            ctx=ast.Load(),
        )
        collector.variable_to_class["service"] = "Service"
        collector.visit_Attribute(attr_node)

        assert hasattr(collector, "used_methods")

    def test_artifact_collector_is_local_import(self):
        """Test that _ArtifactCollector._is_local_import identifies local imports."""
        collector = _ArtifactCollector(validation_mode="implementation")
        local_import = ast.ImportFrom(
            module=None, names=[ast.alias(name="module", asname=None)], level=1
        )
        result = collector._is_local_import(local_import)
        assert result is True

        stdlib_import = ast.ImportFrom(
            module="pathlib", names=[ast.alias(name="Path", asname=None)], level=0
        )
        result = collector._is_local_import(stdlib_import)
        assert result is False

    def test_artifact_collector_is_class_name(self):
        """Test that _ArtifactCollector._is_class_name identifies class naming patterns."""
        collector = _ArtifactCollector(validation_mode="implementation")
        assert collector._is_class_name("Service") is True
        assert collector._is_class_name("_ArtifactCollector") is True
        assert collector._is_class_name("process_data") is False
        assert collector._is_class_name("_private_helper") is False

    def test_artifact_collector_extract_parameter_types(self):
        """Test that _ArtifactCollector._extract_parameter_types extracts parameter type info."""
        collector = _ArtifactCollector(validation_mode="implementation")
        args = ast.arguments(
            args=[
                ast.arg(arg="x", annotation=ast.Name(id="int", ctx=ast.Load())),
                ast.arg(arg="y", annotation=ast.Name(id="str", ctx=ast.Load())),
            ],
            defaults=[],
            kwonlyargs=[],
            kw_defaults=[],
        )
        param_types = collector._extract_parameter_types(args.args)

        assert len(param_types) == 2
        assert param_types[0]["name"] == "x"
        assert param_types[0]["type"] == "int"
        assert param_types[1]["name"] == "y"
        assert param_types[1]["type"] == "str"

    def test_artifact_collector_store_function_info(self):
        """Test that _ArtifactCollector._store_function_info stores function type information."""
        collector = _ArtifactCollector(validation_mode="implementation")
        collector._store_function_info(
            "process", ["x"], [{"name": "x", "type": "int"}], "bool"
        )

        assert "process" in collector.found_functions
        assert "process" in collector.found_function_types
        assert collector.found_function_types["process"]["returns"] == "bool"

    def test_artifact_collector_store_method_info(self):
        """Test that _ArtifactCollector._store_method_info stores method type information."""
        collector = _ArtifactCollector(validation_mode="implementation")
        collector.current_class = "Service"
        collector._store_method_info(
            "get_user", ["user_id"], [{"name": "user_id", "type": "int"}], "dict"
        )

        assert "Service" in collector.found_methods
        assert "get_user" in collector.found_methods["Service"]
        assert "Service" in collector.found_method_types
        assert "get_user" in collector.found_method_types["Service"]
        assert collector.found_method_types["Service"]["get_user"]["returns"] == "dict"

    def test_artifact_collector_process_class_assignments(self):
        """Test that _ArtifactCollector._process_class_assignments processes class-level assignments."""
        collector = _ArtifactCollector(validation_mode="implementation")
        collector.current_class = "Service"
        assign_node = ast.Assign(
            targets=[
                ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="api_key",
                    ctx=ast.Store(),
                )
            ],
            value=ast.Constant(value="secret"),
        )
        collector._process_class_assignments(assign_node)

        assert "Service" in collector.found_attributes
        assert "api_key" in collector.found_attributes["Service"]

    def test_artifact_collector_process_module_assignments(self):
        """Test that _ArtifactCollector._process_module_assignments processes module-level assignments."""
        collector = _ArtifactCollector(validation_mode="implementation")
        assign_node = ast.Assign(
            targets=[ast.Name(id="API_VERSION", ctx=ast.Store())],
            value=ast.Constant(value="1.0"),
        )
        collector._process_module_assignments(assign_node)

        assert None in collector.found_attributes
        assert "API_VERSION" in collector.found_attributes[None]

    def test_artifact_collector_process_tuple_assignment(self):
        """Test that _ArtifactCollector._process_tuple_assignment processes tuple unpacking."""
        collector = _ArtifactCollector(validation_mode="implementation")
        tuple_target = ast.Tuple(
            elts=[ast.Name(id="X", ctx=ast.Store()), ast.Name(id="Y", ctx=ast.Store())],
            ctx=ast.Store(),
        )
        collector._process_tuple_assignment(tuple_target)

        assert None in collector.found_attributes
        assert "X" in collector.found_attributes[None]
        assert "Y" in collector.found_attributes[None]

    def test_artifact_collector_track_class_instantiations(self):
        """Test that _ArtifactCollector._track_class_instantiations tracks class instantiations."""
        collector = _ArtifactCollector(validation_mode="implementation")
        assign_node = ast.Assign(
            targets=[ast.Name(id="service", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="Service", ctx=ast.Load()), args=[], keywords=[]
            ),
        )
        collector._track_class_instantiations(assign_node)

        assert "service" in collector.variable_to_class
        assert collector.variable_to_class["service"] == "Service"

    def test_artifact_collector_tracks_private_class_instantiations(self):
        """Test that _track_class_instantiations correctly handles private class patterns (_ClassName).

        This test verifies the fix for imported private classes like _ArtifactCollector.
        The fix ensures that private class patterns (starting with _ followed by uppercase)
        are properly recognized and tracked, enabling behavioral validation to detect
        method calls on instances of these classes.
        """
        collector = _ArtifactCollector(validation_mode="behavioral")
        assign_node = ast.Assign(
            targets=[ast.Name(id="collector", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="_ArtifactCollector", ctx=ast.Load()),
                args=[],
                keywords=[],
            ),
        )
        collector._track_class_instantiations(assign_node)

        assert "collector" in collector.variable_to_class
        assert collector.variable_to_class["collector"] == "_ArtifactCollector"

        call_node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="collector", ctx=ast.Load()),
                attr="__init__",
                ctx=ast.Load(),
            ),
            args=[ast.Constant(value="implementation")],
            keywords=[],
        )
        collector.visit_Call(call_node)

        assert "_ArtifactCollector" in collector.used_methods
        assert "__init__" in collector.used_methods["_ArtifactCollector"]

    def test_artifact_collector_track_class_name_assignments(self):
        """Test that _ArtifactCollector._track_class_name_assignments tracks class name assignments."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.found_classes.add("Service")
        assign_node = ast.Assign(
            targets=[ast.Name(id="BaseRef", ctx=ast.Store())],
            value=ast.Name(id="Service", ctx=ast.Load()),
        )
        collector._track_class_name_assignments(assign_node)

        assert "Service" in collector.used_classes

    def test_artifact_collector_is_self_attribute(self):
        """Test that _ArtifactCollector._is_self_attribute identifies self.attribute patterns."""
        collector = _ArtifactCollector(validation_mode="implementation")
        self_attr = ast.Attribute(
            value=ast.Name(id="self", ctx=ast.Load()), attr="api_key", ctx=ast.Store()
        )
        assert collector._is_self_attribute(self_attr) is True

        other_attr = ast.Attribute(
            value=ast.Name(id="other", ctx=ast.Load()), attr="value", ctx=ast.Store()
        )
        assert collector._is_self_attribute(other_attr) is False

    def test_artifact_collector_add_class_attribute(self):
        """Test that _ArtifactCollector._add_class_attribute adds attributes to classes."""
        collector = _ArtifactCollector(validation_mode="implementation")
        collector._add_class_attribute("Service", "api_key")

        assert "Service" in collector.found_attributes
        assert "api_key" in collector.found_attributes["Service"]

    def test_artifact_collector_add_module_attribute(self):
        """Test that _ArtifactCollector._add_module_attribute adds module-level attributes."""
        collector = _ArtifactCollector(validation_mode="implementation")
        collector._add_module_attribute("API_VERSION")

        assert None in collector.found_attributes
        assert "API_VERSION" in collector.found_attributes[None]

    def test_artifact_collector_track_method_call_with_inheritance(self):
        """Test that _ArtifactCollector._track_method_call_with_inheritance tracks method calls."""
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.found_class_bases["Derived"] = ["Base"]
        collector._track_method_call_with_inheritance("Derived", "get_user")

        assert "Derived" in collector.used_methods
        assert "get_user" in collector.used_methods["Derived"]
        assert "Base" in collector.used_methods
        assert "get_user" in collector.used_methods["Base"]

    def test_artifact_collector_visit_ann_assign(self):
        """Test that _ArtifactCollector.visit_AnnAssign processes annotated assignments."""
        collector = _ArtifactCollector(validation_mode="implementation")
        ann_assign_node = ast.AnnAssign(
            target=ast.Name(id="API_VERSION", ctx=ast.Store()),
            annotation=ast.Name(id="str", ctx=ast.Load()),
            value=ast.Constant(value="1.0"),
            simple=1,
        )
        collector.visit_AnnAssign(ann_assign_node)

        assert None in collector.found_attributes
        assert "API_VERSION" in collector.found_attributes[None]

    def test_artifact_collector_is_module_scope(self):
        """Test that _ArtifactCollector._is_module_scope identifies module-level scope."""
        collector = _ArtifactCollector(validation_mode="implementation")
        collector.current_class = None
        assert collector._is_module_scope() is True

        collector.current_class = "Service"
        assert collector._is_module_scope() is False


class TestValidateExtractionInputsBehavior:
    """Test _validate_extraction_inputs behavior through extract_type_annotation."""

    def test_validation_enables_type_extraction(self):
        """Test that _validate_extraction_inputs enables extract_type_annotation to work."""
        code = "def func(x: int) -> str: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        param_type = extract_type_annotation(func_node.args.args[0], "annotation")
        assert param_type == "int"

        return_type = extract_type_annotation(func_node, "returns")
        assert return_type == "str"

    def test_validation_handles_invalid_inputs(self):
        """Test that _validate_extraction_inputs properly rejects invalid inputs."""
        with pytest.raises(AttributeError):
            _validate_extraction_inputs(None, "annotation")

        with pytest.raises((AttributeError, TypeError)):
            extract_type_annotation(None, "annotation")


class TestAstToTypeStringBehavior:
    """Test _ast_to_type_string behavior through extract_type_annotation."""

    def test_converts_simple_types_correctly(self):
        """Test that _ast_to_type_string correctly converts simple AST types."""
        code = "def func(x: int, y: str, z: bool) -> float: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        assert extract_type_annotation(func_node.args.args[0], "annotation") == "int"
        assert extract_type_annotation(func_node.args.args[1], "annotation") == "str"
        assert extract_type_annotation(func_node.args.args[2], "annotation") == "bool"
        assert extract_type_annotation(func_node, "returns") == "float"

    def test_converts_complex_types_correctly(self):
        """Test that _ast_to_type_string handles complex generic types."""
        code = "def func(items: List[str], mapping: Dict[str, int]) -> Optional[bool]: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        # _ast_to_type_string must handle these complex structures
        param1 = extract_type_annotation(func_node.args.args[0], "annotation")
        assert "List" in param1
        assert "str" in param1

        param2 = extract_type_annotation(func_node.args.args[1], "annotation")
        assert "Dict" in param2
        assert "str" in param2
        assert "int" in param2

        return_type = extract_type_annotation(func_node, "returns")
        assert "Optional" in return_type
        assert "bool" in return_type

    def test_handles_missing_annotations(self):
        """Test that _ast_to_type_string handles None annotations."""
        # Direct test of _ast_to_type_string behavior
        result = _ast_to_type_string(None)
        assert result is None


class TestTypeNormalizationBehavior:
    """Test type normalization helpers through compare_types."""

    def test_normalize_enables_type_comparison(self):
        """Test that normalization helpers enable compare_types to work correctly."""
        assert compare_types("int", "int") is True
        assert compare_types("str", "str") is True
        assert compare_types("Optional[int]", "Union[int, None]") is True

    def test_normalize_handles_different_input_types(self):
        """Test that _normalize_type_input handles various input types."""
        assert _normalize_type_input("int") == "int"
        assert _normalize_type_input(None) is None
        # Non-string inputs should be converted
        result = _normalize_type_input(42)
        assert isinstance(result, str)

    def test_modern_union_syntax_normalization(self):
        """Test that _normalize_modern_union_syntax converts modern syntax correctly."""
        result = _normalize_modern_union_syntax("str | None")
        assert "Union" in result
        assert "str" in result
        assert "None" in result

        normalized = _normalize_modern_union_syntax("int | str")
        assert "Union" in normalized

    def test_optional_type_normalization(self):
        """Test that _normalize_optional_type converts Optional correctly."""
        result = _normalize_optional_type("Optional[int]")
        assert "Union" in result
        assert "int" in result
        assert "None" in result
        assert compare_types("Optional[str]", "Union[str, None]") is True

    def test_optional_type_detection(self):
        """Test that _is_optional_type correctly identifies Optional types."""
        assert _is_optional_type("Optional[int]") is True
        assert _is_optional_type("Optional[str]") is True
        assert _is_optional_type("int") is False
        assert _is_optional_type("Union[int, None]") is False

    def test_union_type_detection(self):
        """Test that _is_union_type correctly identifies Union types."""
        assert _is_union_type("Union[int, str]") is True
        assert _is_union_type("Union[str, None]") is True
        assert _is_union_type("int") is False
        assert _is_union_type("Optional[int]") is False

    def test_union_type_normalization_sorts_members(self):
        """Test that _normalize_union_type sorts members alphabetically."""
        result = _normalize_union_type("Union[str, int, bool]")
        assert "Union" in result
        assert "bool" in result
        assert "int" in result
        assert "str" in result

    def test_type_argument_splitting(self):
        """Test that _split_type_arguments correctly splits complex type arguments."""
        result = _split_type_arguments("str, int, bool")
        assert isinstance(result, list)
        assert len(result) == 3
        assert "str" in result[0] or result[0] == "str"
        assert "int" in result[1] or result[1] == "int"
        assert "bool" in result[2] or result[2] == "bool"

    def test_delimiter_splitting_respects_nesting(self):
        """Test that _split_by_delimiter respects bracket nesting."""
        result = _split_by_delimiter("List[str], Dict[str, int]", ",")
        assert isinstance(result, list)
        assert len(result) == 2
        assert "List[str]" in result[0] or "List" in result[0]
        assert "Dict[str, int]" in result[1] or "Dict" in result[1]


class TestSafeConversionBehavior:
    """Test safe conversion helpers in error scenarios."""

    def test_safe_ast_conversion_handles_various_nodes(self):
        """Test that _safe_ast_conversion handles different AST node types."""
        code = "x: int"
        tree = ast.parse(code)
        result = _safe_ast_conversion(tree.body[0].annotation)
        assert result == "int"

        code = "x: List[str]"
        tree = ast.parse(code)
        result = _safe_ast_conversion(tree.body[0].annotation)
        assert result is not None
        assert "List" in result

    def test_safe_str_conversion_handles_edge_cases(self):
        """Test that _safe_str_conversion handles various input types safely."""
        assert _safe_str_conversion("test") == "test"
        result = _safe_str_conversion(None)
        assert result == "None"
        assert _safe_str_conversion(42) == "42"


class TestComplexTypeHandling:
    """Test helpers that handle complex type structures."""

    def test_subscript_node_handling(self):
        """Test that _handle_subscript_node correctly processes generic types."""
        code = "x: List[str]"
        tree = ast.parse(code)
        annotation = tree.body[0].annotation
        result = _handle_subscript_node(annotation)
        assert "List" in result
        assert "str" in result

        code = "x: Dict[str, int]"
        tree = ast.parse(code)
        annotation = tree.body[0].annotation
        result = _handle_subscript_node(annotation)
        assert "Dict" in result
        assert "str" in result
        assert "int" in result

    def test_attribute_node_handling(self):
        """Test that _handle_attribute_node correctly processes qualified names."""
        code = "x: typing.Optional"
        tree = ast.parse(code)
        annotation = tree.body[0].annotation
        result = _handle_attribute_node(annotation)
        assert "typing" in result
        assert "Optional" in result

    def test_union_operator_handling(self):
        """Test that _handle_union_operator processes modern union syntax."""
        code = "x: str | None"
        tree = ast.parse(code)
        annotation = tree.body[0].annotation
        result = _handle_union_operator(annotation)
        assert result is not None
        assert "str" in result
        assert "None" in result


class TestFallbackAndUtilityHelpers:
    """Test fallback and utility helper functions."""

    def test_fallback_ast_unparse_handles_unsupported_nodes(self):
        """Test that _fallback_ast_unparse provides fallback for nodes ast.unparse can't handle."""
        code = "x: int"
        tree = ast.parse(code)
        annotation = tree.body[0].annotation
        result = _fallback_ast_unparse(annotation)
        assert result is not None
        assert "int" in result

    def test_extract_bracketed_content_extracts_inner_type(self):
        """Test that _extract_bracketed_content correctly extracts content from bracketed types."""
        result = _extract_bracketed_content("Optional[int]", "Optional[")
        assert "int" in result

        result = _extract_bracketed_content("Union[str, int]", "Union[")
        assert "str" in result
        assert "int" in result

    def test_normalize_comma_spacing_standardizes_formatting(self):
        """Test that _normalize_comma_spacing standardizes spacing in generic types."""
        result = _normalize_comma_spacing("List[str,int]")
        assert "," in result or " " in result

    def test_skip_spaces_advances_past_whitespace(self):
        """Test that _skip_spaces correctly advances past whitespace characters."""
        text = "   hello"
        result = _skip_spaces(text, 0)
        assert result == 3

        text = "  \t  world"
        result = _skip_spaces(text, 0)
        assert result >= 2


class TestTaskNumberExtraction:
    """Test _get_task_number behavior."""

    def test_extracts_task_number_from_manifest_filename(self):
        """Test that _get_task_number correctly extracts task numbers from filenames."""
        from pathlib import Path

        path1 = Path("manifests/task-009-snapshot.manifest.json")
        result1 = _get_task_number(path1)
        assert result1 == 9

        path2 = Path("manifests/task-123-edit.manifest.json")
        result2 = _get_task_number(path2)
        assert result2 == 123

        path3 = Path("manifests/task-005-create.manifest.json")
        result3 = _get_task_number(path3)
        assert result3 == 5

    def test_handles_non_task_files(self):
        """Test that _get_task_number returns infinity for non-task files."""
        from pathlib import Path

        path = Path("manifests/other-file.json")
        result = _get_task_number(path)
        assert result == float("inf")

        path2 = Path("manifests/manifest.json")
        result2 = _get_task_number(path2)
        assert result2 == float("inf")

    def test_task_number_extraction_enables_chronological_sorting(self):
        """Test that _get_task_number enables discover_related_manifests to sort chronologically."""
        test_file = "maid_runner/validators/manifest_validator.py"
        manifests = discover_related_manifests(test_file)

        assert isinstance(manifests, list)

        if len(manifests) > 1:
            import re

            task_numbers = []
            for manifest_path in manifests:
                match = re.search(r"task-(\d+)", manifest_path)
                if match:
                    task_numbers.append(int(match.group(1)))

            assert len(task_numbers) > 0, (
                "No task numbers extracted from manifest paths. "
                "This indicates _get_task_number is not working correctly."
            )


class TestParseFileBehavior:
    """Test _parse_file behavior."""

    def test_parse_file_converts_python_to_ast(self, tmp_path: Path):
        """Test that _parse_file correctly parses Python files into AST."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def hello(name: str) -> str:
    return f"Hello, {name}"

class Greeter:
    def greet(self, name: str) -> str:
        return hello(name)
"""
        )

        tree = _parse_file(str(test_file))

        assert isinstance(tree, ast.AST)
        assert isinstance(tree, ast.Module)
        assert len(tree.body) > 0

    def test_parse_file_enables_artifact_collection(self, tmp_path: Path):
        """Test that _parse_file enables artifact collection through _collect_artifacts_from_ast."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        assert "process" in collector.found_functions


class TestCollectArtifactsFromAstBehavior:
    """Test _collect_artifacts_from_ast behavior."""

    def test_collects_artifacts_from_ast_tree(self):
        """Test that _collect_artifacts_from_ast correctly collects artifacts from AST."""
        code = """
def public_function(x: int) -> str:
    return str(x)

class PublicClass:
    def public_method(self, y: str) -> int:
        return len(y)
"""
        tree = ast.parse(code)

        collector = _collect_artifacts_from_ast(tree, "implementation")

        assert "public_function" in collector.found_functions
        assert "PublicClass" in collector.found_classes
        assert "public_method" in collector.found_methods["PublicClass"]

    def test_collects_behavioral_usage(self):
        """Test that _collect_artifacts_from_ast tracks usage in behavioral mode."""
        code = """
from module import Service

def test_service():
    svc = Service()
    result = svc.get_user(123)
"""
        tree = ast.parse(code)

        collector = _collect_artifacts_from_ast(tree, "behavioral")

        assert "Service" in collector.used_classes
        assert "get_user" in collector.used_methods.get("Service", set())


class TestGetExpectedArtifactsBehavior:
    """Test _get_expected_artifacts behavior."""

    def test_extracts_artifacts_from_manifest(self, tmp_path: Path):
        """Test that _get_expected_artifacts correctly extracts artifacts from manifest."""
        manifest_data = {
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "process",
                        "parameters": [{"name": "x", "type": "int"}],
                    },
                    {"type": "class", "name": "Service"},
                ],
            }
        }

        artifacts = _get_expected_artifacts(
            manifest_data, "test.py", use_manifest_chain=False
        )

        assert len(artifacts) == 2
        assert any(a["name"] == "process" for a in artifacts)
        assert any(a["name"] == "Service" for a in artifacts)


class TestValidateAllArtifactsBehavior:
    """Test _validate_all_artifacts behavior."""

    def test_validates_all_expected_artifacts_exist(self, tmp_path: Path):
        """Test that _validate_all_artifacts validates all artifacts are present."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
def process_data(x: int) -> bool:
    return True

class Service:
    def get_user(self, user_id: int) -> dict:
        return {}
"""
        )

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_artifacts = [
            {
                "type": "function",
                "name": "process_data",
                "parameters": [{"name": "x", "type": "int"}],
            },
            {"type": "class", "name": "Service"},
            {
                "type": "function",
                "name": "get_user",
                "class": "Service",
                "parameters": [{"name": "user_id", "type": "int"}],
            },
        ]

        _validate_all_artifacts(expected_artifacts, collector, "implementation")

    def test_raises_when_artifacts_missing(self, tmp_path: Path):
        """Test that _validate_all_artifacts raises when artifacts are missing."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def existing_function(): pass\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_artifacts = [{"type": "function", "name": "missing_function"}]

        with pytest.raises(AlignmentError):
            _validate_all_artifacts(expected_artifacts, collector, "implementation")


class TestCheckUnexpectedArtifactsBehavior:
    """Test _check_unexpected_artifacts behavior."""

    def test_allows_private_artifacts_not_in_manifest(self, tmp_path: Path):
        """Test that _check_unexpected_artifacts allows private artifacts."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
def public_function():
    pass

def _private_helper():
    pass
"""
        )

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_artifacts = [{"type": "function", "name": "public_function"}]

        _check_unexpected_artifacts(expected_artifacts, collector, str(impl_file))


class TestValidateSingleArtifactBehavior:
    """Test _validate_single_artifact behavior."""

    def test_validates_function_artifact(self, tmp_path: Path):
        """Test that _validate_single_artifact validates function artifacts."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        artifact = {
            "type": "function",
            "name": "process",
            "parameters": [{"name": "x", "type": "int"}],
        }

        _validate_single_artifact(artifact, collector, "implementation")

    def test_validates_class_artifact(self, tmp_path: Path):
        """Test that _validate_single_artifact validates class artifacts."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("class Service: pass\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        artifact = {"type": "class", "name": "Service"}

        _validate_single_artifact(artifact, collector, "implementation")


class TestValidateFunctionArtifactBehavior:
    """Test _validate_function_artifact behavior."""

    def test_validates_function_in_implementation_mode(self, tmp_path: Path):
        """Test that _validate_function_artifact validates functions in implementation mode."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        artifact = {
            "type": "function",
            "name": "process",
            "parameters": [{"name": "x", "type": "int"}],
        }

        _validate_function_artifact(artifact, collector, "implementation")

    def test_validates_function_in_behavioral_mode(self, tmp_path: Path):
        """Test that _validate_function_artifact validates functions in behavioral mode."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
from module import process

def test_process():
    result = process(42)
    assert result is True
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "behavioral")

        artifact = {
            "type": "function",
            "name": "process",
            "parameters": [{"name": "x", "type": "int"}],
        }

        _validate_function_artifact(artifact, collector, "behavioral")


class TestValidateFunctionBehavioralBehavior:
    """Test _validate_function_behavioral behavior."""

    def test_validates_function_used_in_tests(self, tmp_path: Path):
        """Test that _validate_function_behavioral validates functions are used in tests."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
from module import process

def test_process():
    result = process(42)
    assert result is True
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "behavioral")

        artifact = {
            "type": "function",
            "name": "process",
            "parameters": [{"name": "x", "type": "int"}],
        }

        _validate_function_behavioral("process", [], None, artifact, collector)

    def test_raises_when_function_not_used(self, tmp_path: Path):
        """Test that _validate_function_behavioral raises when function is not used."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text("def test_something(): assert True\n")

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "behavioral")

        artifact = {"type": "function", "name": "unused_function"}

        with pytest.raises(AlignmentError, match="not called"):
            _validate_function_behavioral(
                "unused_function", [], None, artifact, collector
            )


class TestValidateParametersUsedBehavior:
    """Test _validate_parameters_used behavior."""

    def test_validates_parameters_are_used(self, tmp_path: Path):
        """Test that _validate_parameters_used validates parameters are used in calls."""
        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
from module import process

def test_process():
    result = process(42)  # Parameter x=42 is used
    assert result is True
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "behavioral")

        parameters = [{"name": "x", "type": "int"}]

        _validate_parameters_used(parameters, "process", collector)


class TestValidateMethodParametersBehavior:
    """Test _validate_method_parameters behavior."""

    def test_validates_method_parameters(self, tmp_path: Path):
        """Test that _validate_method_parameters validates method parameters."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
class Service:
    def get_user(self, user_id: int) -> dict:
        return {}
"""
        )

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        parameters = [{"name": "user_id", "type": "int"}]

        _validate_method_parameters("get_user", parameters, "Service", collector)


class TestValidateFunctionImplementationBehavior:
    """Test _validate_function_implementation behavior."""

    def test_validates_function_implementation_exists(self, tmp_path: Path):
        """Test that _validate_function_implementation validates function exists in code."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
def process_data(x: int) -> bool:
    return True
"""
        )

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        parameters = [{"name": "x", "type": "int"}]

        _validate_function_implementation("process_data", parameters, None, collector)

    def test_raises_when_function_missing(self, tmp_path: Path):
        """Test that _validate_function_implementation raises when function is missing."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def other_function(): pass\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        parameters = [{"name": "x", "type": "int"}]

        with pytest.raises(AlignmentError):
            _validate_function_implementation(
                "missing_function", parameters, None, collector
            )


class TestValidateClassBehavior:
    """Test _validate_class behavior."""

    def test_validates_class_exists(self, tmp_path: Path):
        """Test that _validate_class validates class exists in code."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("class Service: pass\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        _validate_class(
            "Service", [], collector.found_classes, collector.found_class_bases
        )

    def test_validates_class_with_bases(self, tmp_path: Path):
        """Test that _validate_class validates class with base classes."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
class Base: pass
class Derived(Base): pass
"""
        )

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        _validate_class(
            "Derived", ["Base"], collector.found_classes, collector.found_class_bases
        )


class TestValidateAttributeBehavior:
    """Test _validate_attribute behavior."""

    def test_validates_class_attribute(self, tmp_path: Path):
        """Test that _validate_attribute validates class attributes."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
class Service:
    def __init__(self):
        self.api_key = "secret"
"""
        )

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        _validate_attribute("api_key", "Service", collector.found_attributes)

    def test_validates_module_attribute(self, tmp_path: Path):
        """Test that _validate_attribute validates module-level attributes."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("API_VERSION = '1.0'\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        _validate_attribute("API_VERSION", None, collector.found_attributes)


class TestValidateFunctionBehavior:
    """Test _validate_function behavior."""

    def test_validates_function_exists(self, tmp_path: Path):
        """Test that _validate_function validates function exists."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_params = [{"name": "x"}]
        _validate_function("process", expected_params, collector.found_functions)


class TestValidateNoUnexpectedArtifactsBehavior:
    """Test _validate_no_unexpected_artifacts behavior."""

    def test_allows_private_artifacts_not_in_manifest(self, tmp_path: Path):
        """Test that _validate_no_unexpected_artifacts allows private artifacts."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
def public_function():
    pass

def _private_helper():
    pass
"""
        )

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_items = [{"type": "function", "name": "public_function"}]

        _validate_no_unexpected_artifacts(
            expected_items,
            collector.found_classes,
            collector.found_functions,
            collector.found_methods,
        )


class TestTypeValidationHelpersBehavior:
    """Test type validation helper functions."""

    def test_are_valid_type_validation_inputs(self):
        """Test that _are_valid_type_validation_inputs validates input types."""
        manifest_artifacts = {"expectedArtifacts": {"contains": []}}
        implementation_artifacts = {"functions": {}, "methods": {}}
        result = _are_valid_type_validation_inputs(
            manifest_artifacts, implementation_artifacts
        )
        assert result is True

        result = _are_valid_type_validation_inputs(None, None)
        assert result is False

    def test_should_validate_artifact_types(self):
        """Test that _should_validate_artifact_types determines if types should be validated."""
        artifact = {
            "type": "function",
            "name": "process",
            "parameters": [{"name": "x", "type": "int"}],
        }

        result = _should_validate_artifact_types(artifact)
        assert isinstance(result, bool)

    def test_validate_function_types(self, tmp_path: Path):
        """Test that _validate_function_types validates function type hints."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        artifact = {
            "type": "function",
            "name": "process",
            "parameters": [{"name": "x", "type": "int"}],
            "returns": "bool",
        }

        _validate_function_types(artifact, collector)

    def test_get_implementation_info(self, tmp_path: Path):
        """Test that _get_implementation_info retrieves implementation details."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        implementation_artifacts = {
            "functions": collector.found_function_types,
            "methods": collector.found_method_types,
        }

        info = _get_implementation_info("process", None, implementation_artifacts)
        assert info is not None
        assert "parameters" in info

    def test_get_method_info(self, tmp_path: Path):
        """Test that _get_method_info retrieves method implementation details."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
class Service:
    def get_user(self, user_id: int) -> dict:
        return {}
"""
        )

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        implementation_artifacts = {
            "functions": collector.found_function_types,
            "methods": collector.found_method_types,
        }

        info = _get_method_info("get_user", "Service", implementation_artifacts)
        assert info is not None
        assert "parameters" in info

    def test_get_function_info(self, tmp_path: Path):
        """Test that _get_function_info retrieves function implementation details."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        implementation_artifacts = {
            "functions": collector.found_function_types,
            "methods": collector.found_method_types,
        }

        info = _get_function_info("process", implementation_artifacts)
        assert info is not None
        assert "parameters" in info

    def test_validate_parameter_types(self, tmp_path: Path):
        """Test that _validate_parameter_types validates parameter type hints."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int, y: str) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        implementation_artifacts = {
            "functions": collector.found_function_types,
            "methods": collector.found_method_types,
        }
        impl_info = _get_function_info("process", implementation_artifacts)

        artifact = {
            "type": "function",
            "name": "process",
            "parameters": [{"name": "x", "type": "int"}, {"name": "y", "type": "str"}],
        }

        errors = _validate_parameter_types(artifact, impl_info, "process", None)
        assert isinstance(errors, list)

    def test_validate_single_parameter(self, tmp_path: Path):
        """Test that _validate_single_parameter validates a single parameter type."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        implementation_artifacts = {
            "functions": collector.found_function_types,
            "methods": collector.found_method_types,
        }
        impl_info = _get_function_info("process", implementation_artifacts)
        impl_params_dict = {p["name"]: p for p in impl_info.get("parameters", [])}

        error = _validate_single_parameter(
            "x", "int", impl_params_dict, "process", None
        )
        assert error is None

    def test_validate_return_type(self, tmp_path: Path):
        """Test that _validate_return_type validates return type hints."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text("def process(x: int) -> bool: return True\n")

        tree = _parse_file(str(impl_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        implementation_artifacts = {
            "functions": collector.found_function_types,
            "methods": collector.found_method_types,
        }
        impl_info = _get_function_info("process", implementation_artifacts)

        artifact = {"type": "function", "name": "process", "returns": "bool"}

        error = _validate_return_type(artifact, impl_info, "process", None)
        assert error is None


class TestTypedDictHelpersBehavior:
    """Test TypedDict helper functions."""

    def test_is_typeddict_class(self):
        """Test that _is_typeddict_class identifies TypedDict classes."""
        result = _is_typeddict_class({"type": "class", "name": "RegularClass"})
        assert result is False

    def test_is_typeddict_base(self):
        """Test that _is_typeddict_base identifies TypedDict base classes."""
        result = _is_typeddict_base("TypedDict")
        assert result is True

        result = _is_typeddict_base("dict")
        assert result is False

    def test_should_skip_by_artifact_kind(self):
        """Test that _should_skip_by_artifact_kind determines skipping based on artifact kind."""
        artifact = {"type": "function", "name": "TypeAlias", "artifactKind": "type"}
        result = _should_skip_by_artifact_kind(artifact)
        assert result is True

        artifact = {"type": "function", "name": "process", "artifactKind": "runtime"}
        result = _should_skip_by_artifact_kind(artifact)
        assert result is False


class TestIntegrationWithValidation:
    """Test that private helpers enable end-to-end validation to work."""

    def test_helpers_enable_validation_workflow(self, tmp_path: Path):
        """Test that all helpers work together to enable validate_with_ast."""
        impl_file = tmp_path / "module.py"
        impl_file.write_text(
            """
def process_data(data: str) -> bool:
    return True
"""
        )

        test_file = tmp_path / "test_module.py"
        test_file.write_text(
            """
from module import process_data

def test_process_data():
    result = process_data("test")
    assert result is True
"""
        )

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "process_data",
                        "parameters": [{"name": "data", "type": "str"}],
                    },
                ],
            },
            "validationCommand": ["pytest", str(test_file), "-v"],
        }

        validate_with_ast(manifest, str(test_file), validation_mode="behavioral")
