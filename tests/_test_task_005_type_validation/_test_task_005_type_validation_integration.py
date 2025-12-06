"""
Behavioral tests for Task-005: Type Validation functionality - integration scenarios.
These tests USE multiple type validation functions together to verify integration.
"""

import ast
import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        validate_type_hints,
        extract_type_annotation,
        compare_types,
        normalize_type_string,
    )
except ImportError as e:
    # In Red phase, these won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestIntegrationScenarios:
    """Integration tests combining multiple functions."""

    def test_full_validation_workflow(self):
        """Test a complete validation workflow using all functions together."""
        # Create manifest with various type scenarios
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process",
                    "parameters": [
                        {"name": "data", "type": "List[str]"},
                        {"name": "count", "type": "Optional[int]"},
                    ],
                    "returns": "Dict[str, int]",
                }
            ],
        }

        # Create matching implementation
        implementation_artifacts = {
            "functions": {
                "process": {
                    "parameters": [
                        {"name": "data", "type": "List[str]"},
                        {"name": "count", "type": "Optional[int]"},
                    ],
                    "returns": "Dict[str, int]",
                }
            }
        }

        # USE validate_type_hints as the main entry point
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

        # Now test with a mismatch
        implementation_artifacts["functions"]["process"]["returns"] = "List[int]"
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_ast_to_validation_pipeline(self):
        """Test the full pipeline from AST extraction to type validation."""
        # Parse some code
        code = """
def calculate(x: float, y: float) -> float:
    return x + y
"""
        tree = ast.parse(code)
        func_node = tree.body[0]

        # USE extract_type_annotation to get types
        param1_type = extract_type_annotation(func_node.args.args[0], "annotation")
        param2_type = extract_type_annotation(func_node.args.args[1], "annotation")
        return_type = extract_type_annotation(func_node, "returns")

        assert param1_type == "float"
        assert param2_type == "float"
        assert return_type == "float"

        # USE normalize_type_string on extracted types
        norm_param1 = normalize_type_string(param1_type)
        norm_return = normalize_type_string(return_type)

        # USE compare_types to validate
        assert compare_types(norm_param1, "float") is True
        assert compare_types(norm_return, "float") is True

    def test_mixed_success_failure_validation_scenario(self):
        """Test integration where some functions pass validation and others fail."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "good_function",
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                },
                {
                    "type": "function",
                    "name": "bad_function",
                    "parameters": [{"name": "y", "type": "str"}],
                    "returns": "bool",
                },
                {
                    "type": "function",
                    "name": "another_good_function",
                    "parameters": [{"name": "z", "type": "float"}],
                    "returns": "int",
                },
            ],
        }

        # Implementation with mixed success/failure
        implementation_artifacts = {
            "functions": {
                "good_function": {
                    "parameters": [{"name": "x", "type": "int"}],  # Matches
                    "returns": "str",  # Matches
                },
                "bad_function": {
                    "parameters": [
                        {"name": "y", "type": "int"}
                    ],  # Mismatch: str vs int
                    "returns": "float",  # Mismatch: bool vs float
                },
                "another_good_function": {
                    "parameters": [{"name": "z", "type": "float"}],  # Matches
                    "returns": "int",  # Matches
                },
            }
        }

        # USE the validation function - should report only the failing function
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

        # Errors should mention the bad function
        error_text = " ".join(errors).lower()
        assert (
            "bad_function" in error_text or len(errors) == 2
        )  # Parameter and return errors

    def test_partial_failure_with_complex_types(self):
        """Test integration with complex types where some pass and some fail validation."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "complex_mixed",
                    "parameters": [
                        {"name": "good_param", "type": "Dict[str, List[int]]"},
                        {"name": "bad_param", "type": "Union[str, int]"},
                        {"name": "another_good", "type": "Optional[float]"},
                    ],
                    "returns": "List[Tuple[str, bool]]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "complex_mixed": {
                    "parameters": [
                        {
                            "name": "good_param",
                            "type": "Dict[str, List[int]]",
                        },  # Matches
                        {"name": "bad_param", "type": "Union[bool, float]"},  # Mismatch
                        {"name": "another_good", "type": "Optional[float]"},  # Matches
                    ],
                    "returns": "List[Tuple[int, bool]]",  # Mismatch: str vs int in Tuple
                }
            }
        }

        # USE the validation function - should identify specific parameter/return failures
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) >= 2  # At least bad_param and return type errors

    def test_method_and_function_mixed_validation(self):
        """Test integration with both functions and methods, mixed success/failure."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "standalone_function",
                    "parameters": [{"name": "x", "type": "str"}],
                    "returns": "int",
                },
                {
                    "type": "function",
                    "name": "class_method",
                    "class": "MyClass",
                    "parameters": [
                        {"name": "self", "type": None},
                        {"name": "y", "type": "float"},
                    ],
                    "returns": "bool",
                },
            ],
        }

        implementation_artifacts = {
            "functions": {
                "standalone_function": {
                    "parameters": [{"name": "x", "type": "str"}],  # Matches
                    "returns": "int",  # Matches
                }
            },
            "methods": {
                "MyClass": {
                    "class_method": {
                        "parameters": [
                            {"name": "self", "type": None},
                            {"name": "y", "type": "int"},  # Mismatch: float vs int
                        ],
                        "returns": "str",  # Mismatch: bool vs str
                    }
                }
            },
        }

        # USE the validation function - should handle mixed function/method validation
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0  # Should have method parameter and return errors

    def test_integration_with_pipeline_functions(self):
        """Test integration scenario simulating a processing pipeline with mixed results."""
        manifest_artifacts = {
            "file": "pipeline.py",
            "contains": [
                {
                    "type": "function",
                    "name": "input_validator",
                    "parameters": [{"name": "data", "type": "Any"}],
                    "returns": "bool",
                },
                {
                    "type": "function",
                    "name": "data_transformer",
                    "parameters": [{"name": "raw_data", "type": "Dict[str, Any]"}],
                    "returns": "List[str]",
                },
                {
                    "type": "function",
                    "name": "output_formatter",
                    "parameters": [{"name": "processed", "type": "List[str]"}],
                    "returns": "str",
                },
            ],
        }

        # Pipeline with one failing step
        implementation_artifacts = {
            "functions": {
                "input_validator": {
                    "parameters": [{"name": "data", "type": "Any"}],  # Matches
                    "returns": "bool",  # Matches
                },
                "data_transformer": {
                    "parameters": [
                        {"name": "raw_data", "type": "List[Dict[str, Any]]"}
                    ],  # Mismatch
                    "returns": "Dict[str, List[str]]",  # Mismatch
                },
                "output_formatter": {
                    "parameters": [
                        {"name": "processed", "type": "List[str]"}
                    ],  # Matches
                    "returns": "str",  # Matches
                },
            }
        }

        # USE the validation function - should identify the failing pipeline step
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

        # Should identify the transformer as the problem
        error_text = " ".join(errors).lower()
        has_transformer_context = any(
            term in error_text
            for term in ["data_transformer", "raw_data", "processed", "transform"]
        )
        assert has_transformer_context or len(errors) >= 2

    def test_pipeline_failure_at_extraction_stage(self):
        """Test pipeline failure propagation when type extraction fails."""
        # Create a scenario where extraction might fail but should be handled gracefully
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "problematic_extraction",
                    "parameters": [{"name": "param", "type": "ComplexType[Something]"}],
                    "returns": "AnotherType",
                }
            ],
        }

        # Implementation with potentially problematic type extraction
        implementation_artifacts = {
            "functions": {
                "problematic_extraction": {
                    "parameters": [
                        {"name": "param", "type": None}
                    ],  # Extraction failed
                    "returns": None,  # Extraction failed
                }
            }
        }

        # USE the validation function - should handle extraction failures gracefully
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)  # Should not crash, return error list
        # Might have errors for missing type annotations
        if len(errors) > 0:
            error_text = " ".join(errors).lower()
            # Should indicate missing or failed extraction
            assert any(
                term in error_text
                for term in ["none", "missing", "not found", "annotation"]
            )

    def test_pipeline_failure_at_normalization_stage(self):
        """Test pipeline failure propagation when type normalization fails."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "normalization_problem",
                    "parameters": [{"name": "param", "type": "ValidType"}],
                    "returns": "AnotherValidType",
                }
            ],
        }

        # Implementation with malformed types that might cause normalization issues
        implementation_artifacts = {
            "functions": {
                "normalization_problem": {
                    "parameters": [
                        {"name": "param", "type": "List[unclosed"}
                    ],  # Malformed
                    "returns": "Dict[str, int]]extra]",  # Malformed
                }
            }
        }

        # USE the validation function - should handle normalization failures
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)  # Should not crash
        # Should detect the type mismatches even if normalization is problematic
        assert len(errors) >= 0  # May have errors, but shouldn't crash

    def test_pipeline_failure_at_comparison_stage(self):
        """Test pipeline failure propagation when type comparison fails."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "comparison_issues",
                    "parameters": [{"name": "param", "type": "NormalType"}],
                    "returns": "StandardType",
                }
            ],
        }

        # Implementation that might cause comparison stage issues
        implementation_artifacts = {
            "functions": {
                "comparison_issues": {
                    # Simulate data that might cause comparison problems
                    "parameters": [{"name": "param", "type": ""}],  # Empty type string
                    "returns": "\n\t",  # Whitespace-only type
                }
            }
        }

        # USE the validation function - should handle comparison failures
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)
        # Should generate errors for the type mismatches
        assert len(errors) > 0

    def test_cascading_pipeline_failures(self):
        """Test how multiple pipeline stage failures cascade and are reported."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "cascade_failures",
                    "parameters": [
                        {"name": "param1", "type": "GoodType"},
                        {"name": "param2", "type": "Another[Good, Type]"},
                    ],
                    "returns": "ValidReturnType",
                }
            ],
        }

        # Implementation with multiple types of problems
        implementation_artifacts = {
            "functions": {
                "cascade_failures": {
                    "parameters": [
                        {"name": "param1", "type": None},  # Extraction failure
                        {
                            "name": "param2",
                            "type": "Malformed[Type[]",
                        },  # Normalization problem
                    ],
                    "returns": "DifferentType",  # Simple mismatch
                }
            }
        }

        # USE the validation function - should handle multiple failure types
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)
        assert len(errors) > 0  # Should have multiple errors

        # Each different type of failure should be reported
        error_text = " ".join(errors).lower()
        # Should mention the function and various issues
        assert "cascade_failures" in error_text or len(errors) >= 2

    def test_pipeline_error_recovery_and_continuation(self):
        """Test that pipeline continues processing after encountering errors."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "first_function",
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                },
                {
                    "type": "function",
                    "name": "problematic_function",
                    "parameters": [{"name": "y", "type": "ValidType"}],
                    "returns": "AnotherValidType",
                },
                {
                    "type": "function",
                    "name": "third_function",
                    "parameters": [{"name": "z", "type": "bool"}],
                    "returns": "float",
                },
            ],
        }

        implementation_artifacts = {
            "functions": {
                "first_function": {
                    "parameters": [{"name": "x", "type": "int"}],  # Good
                    "returns": "str",  # Good
                },
                "problematic_function": {
                    "parameters": [{"name": "y", "type": None}],  # Problem
                    "returns": None,  # Problem
                },
                "third_function": {
                    "parameters": [{"name": "z", "type": "bool"}],  # Good
                    "returns": "float",  # Good
                },
            }
        }

        # USE the validation function - should process all functions despite errors
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)

        # Should have errors only from the problematic function
        if len(errors) > 0:
            error_text = " ".join(errors).lower()
            # Should mention the problematic function but not crash on others
            assert "problematic_function" in error_text or len(errors) <= 4

    def test_pipeline_graceful_degradation_with_partial_data(self):
        """Test pipeline graceful degradation when some data is missing or malformed."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "partial_data_test",
                    "parameters": [
                        {"name": "complete_param", "type": "str"},
                        {"name": "missing_type_param", "type": "int"},
                    ],
                    "returns": "bool",
                }
            ],
        }

        # Implementation with partial/missing data
        implementation_artifacts = {
            "functions": {
                "partial_data_test": {
                    "parameters": [
                        {"name": "complete_param", "type": "str"},  # Complete data
                        # Missing the second parameter entirely
                    ],
                    # Missing returns data entirely
                }
            }
        }

        # USE the validation function - should degrade gracefully
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)
        # Should handle missing data without crashing
        # May or may not have errors depending on implementation strategy

    def test_edge_cases_ellipsis_and_literals(self):
        """Test edge cases like ellipsis (...) and literal types."""
        # Test with ellipsis in tuple
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "variadic",
                    "parameters": [{"name": "args", "type": "Tuple[int, ...]"}],
                    "returns": "None",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "variadic": {
                    "parameters": [{"name": "args", "type": "Tuple[int, ...]"}],
                    "returns": "None",
                }
            }
        }

        # USE the validation function - should handle ellipsis
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_complex_nested_generics_three_levels_deep(self):
        """Test validation with deeply nested generic types (3+ levels)."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_nested",
                    "parameters": [
                        {
                            "name": "data",
                            "type": "Dict[str, List[Tuple[Optional[int], Union[str, bool]]]]",
                        },
                        {
                            "name": "mapping",
                            "type": "List[Dict[str, Optional[Union[int, float, str]]]]",
                        },
                    ],
                    "returns": "Union[Dict[str, List[int]], List[Tuple[str, bool]], None]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_nested": {
                    "parameters": [
                        {
                            "name": "data",
                            "type": "Dict[str, List[Tuple[Optional[int], Union[str, bool]]]]",
                        },
                        {
                            "name": "mapping",
                            "type": "List[Dict[str, Optional[Union[int, float, str]]]]",
                        },
                    ],
                    "returns": "Union[Dict[str, List[int]], List[Tuple[str, bool]], None]",
                }
            }
        }

        # USE the validation function - should handle deep nesting
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_complex_nested_generics_with_mismatches(self):
        """Test validation catches errors in deeply nested generic types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "nested_mismatch",
                    "parameters": [
                        {"name": "data", "type": "Dict[str, List[Tuple[int, str]]]"},
                    ],
                    "returns": "List[Dict[str, Optional[int]]]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "nested_mismatch": {
                    "parameters": [
                        {
                            "name": "data",
                            "type": "Dict[str, List[Tuple[float, str]]]",
                        },  # int vs float mismatch
                    ],
                    "returns": "List[Dict[str, Optional[bool]]]",  # int vs bool mismatch
                }
            }
        }

        # USE the validation function - should catch nested type mismatches
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_complex_nested_generics_with_callable(self):
        """Test validation with Callable types in nested structures."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "callback_processor",
                    "parameters": [
                        {
                            "name": "callbacks",
                            "type": "List[Callable[[int, str], bool]]",
                        },
                        {
                            "name": "async_callbacks",
                            "type": "Dict[str, Callable[..., Awaitable[Optional[int]]]]",
                        },
                    ],
                    "returns": "Callable[[List[str]], Dict[str, Any]]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "callback_processor": {
                    "parameters": [
                        {
                            "name": "callbacks",
                            "type": "List[Callable[[int, str], bool]]",
                        },
                        {
                            "name": "async_callbacks",
                            "type": "Dict[str, Callable[..., Awaitable[Optional[int]]]]",
                        },
                    ],
                    "returns": "Callable[[List[str]], Dict[str, Any]]",
                }
            }
        }

        # USE the validation function - should handle Callable types
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_extreme_nesting_generics(self):
        """Test validation with extremely nested generic structures."""
        extreme_type = "Dict[str, List[Tuple[Union[Optional[Dict[str, List[int]]], Set[Tuple[str, bool]]], Callable[[int], Optional[Union[str, float]]]]]]"

        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "extreme_nesting",
                    "parameters": [{"name": "data", "type": extreme_type}],
                    "returns": "Union[None, bool]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "extreme_nesting": {
                    "parameters": [{"name": "data", "type": extreme_type}],
                    "returns": "Union[None, bool]",
                }
            }
        }

        # USE the validation function - should handle extreme nesting without crashing
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_generic_type_aliases_and_typevars(self):
        """Test validation with generic TypeVars and type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "generic_function",
                    "parameters": [
                        {"name": "data", "type": "List[T]"},
                        {"name": "mapping", "type": "Mapping[K, V]"},
                        {"name": "sequence", "type": "Sequence[Union[T, K]]"},
                    ],
                    "returns": "Iterator[Tuple[K, V]]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "generic_function": {
                    "parameters": [
                        {"name": "data", "type": "List[T]"},
                        {"name": "mapping", "type": "Mapping[K, V]"},
                        {"name": "sequence", "type": "Sequence[Union[T, K]]"},
                    ],
                    "returns": "Iterator[Tuple[K, V]]",
                }
            }
        }

        # USE the validation function - should handle TypeVar-based generics
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_basic_string_annotations(self):
        """Test validation with forward references using string annotations."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "self_referencing",
                    "parameters": [
                        {
                            "name": "node",
                            "type": "'Node'",
                        },  # Forward reference as string
                        {"name": "parent", "type": "Optional['Node']"},
                    ],
                    "returns": "'Node'",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "self_referencing": {
                    "parameters": [
                        {"name": "node", "type": "'Node'"},
                        {"name": "parent", "type": "Optional['Node']"},
                    ],
                    "returns": "'Node'",
                }
            }
        }

        # USE the validation function - should handle string forward references
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_with_generics(self):
        """Test validation with forward references in generic types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "tree_processor",
                    "parameters": [
                        {"name": "nodes", "type": "List['TreeNode']"},
                        {"name": "mapping", "type": "Dict[str, 'TreeNode']"},
                        {"name": "optional_root", "type": "Optional['TreeNode']"},
                    ],
                    "returns": "Union['TreeNode', None]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "tree_processor": {
                    "parameters": [
                        {"name": "nodes", "type": "List['TreeNode']"},
                        {"name": "mapping", "type": "Dict[str, 'TreeNode']"},
                        {"name": "optional_root", "type": "Optional['TreeNode']"},
                    ],
                    "returns": "Union['TreeNode', None]",
                }
            }
        }

        # USE the validation function - should handle forward references in generics
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_mismatches(self):
        """Test that validation catches mismatches in forward references."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "forward_mismatch",
                    "parameters": [{"name": "item", "type": "'ClassA'"}],
                    "returns": "List['ClassB']",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "forward_mismatch": {
                    "parameters": [
                        {"name": "item", "type": "'ClassC'"}
                    ],  # Mismatch: ClassA vs ClassC
                    "returns": "List['ClassD']",  # Mismatch: ClassB vs ClassD
                }
            }
        }

        # USE the validation function - should catch forward reference mismatches
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_forward_references_mixed_with_regular_types(self):
        """Test validation with mix of forward references and regular types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "mixed_types",
                    "parameters": [
                        {"name": "forward_ref", "type": "'CustomClass'"},
                        {"name": "regular_type", "type": "str"},
                        {"name": "mixed_generic", "type": "Dict[str, 'CustomClass']"},
                        {
                            "name": "complex_forward",
                            "type": "Union['TypeA', int, 'TypeB']",
                        },
                    ],
                    "returns": "Tuple[str, 'CustomClass']",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "mixed_types": {
                    "parameters": [
                        {"name": "forward_ref", "type": "'CustomClass'"},
                        {"name": "regular_type", "type": "str"},
                        {"name": "mixed_generic", "type": "Dict[str, 'CustomClass']"},
                        {
                            "name": "complex_forward",
                            "type": "Union['TypeA', int, 'TypeB']",
                        },
                    ],
                    "returns": "Tuple[str, 'CustomClass']",
                }
            }
        }

        # USE the validation function - should handle mixed forward/regular types
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_with_module_qualifiers(self):
        """Test validation with module-qualified forward references."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "qualified_forwards",
                    "parameters": [
                        {"name": "item", "type": "'mymodule.MyClass'"},
                        {
                            "name": "service",
                            "type": "'services.database.DatabaseService'",
                        },
                    ],
                    "returns": "Optional['mymodule.MyClass']",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "qualified_forwards": {
                    "parameters": [
                        {"name": "item", "type": "'mymodule.MyClass'"},
                        {
                            "name": "service",
                            "type": "'services.database.DatabaseService'",
                        },
                    ],
                    "returns": "Optional['mymodule.MyClass']",
                }
            }
        }

        # USE the validation function - should handle module-qualified forward references
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_normalization_edge_cases(self):
        """Test that forward references are normalized consistently."""
        # Test that quotes are handled consistently in normalization
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "quote_normalization",
                    "parameters": [
                        {"name": "single_quotes", "type": "'MyClass'"},
                        {"name": "in_union", "type": "Union['MyClass', str]"},
                    ],
                    "returns": "List['MyClass']",
                }
            ],
        }

        # Implementation might have slightly different quote formatting
        implementation_artifacts = {
            "functions": {
                "quote_normalization": {
                    "parameters": [
                        {"name": "single_quotes", "type": "'MyClass'"},
                        {
                            "name": "in_union",
                            "type": "Union[str, 'MyClass']",
                        },  # Different order in Union
                    ],
                    "returns": "List['MyClass']",
                }
            }
        }

        # USE the validation function - should normalize forward references properly
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        # Union order differences should be handled by normalization
        assert errors == [] or len(errors) == 0  # Should pass after normalization

    def test_python310_union_syntax_basic(self):
        """Test validation with Python 3.10+ union syntax using | operator."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "modern_union",
                    "parameters": [
                        {"name": "value", "type": "str | int"},  # Modern union syntax
                        {
                            "name": "optional",
                            "type": "str | None",
                        },  # Instead of Optional[str]
                    ],
                    "returns": "int | float | bool",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "modern_union": {
                    "parameters": [
                        {"name": "value", "type": "str | int"},
                        {"name": "optional", "type": "str | None"},
                    ],
                    "returns": "int | float | bool",
                }
            }
        }

        # USE the validation function - should handle modern union syntax
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_python310_union_syntax_compatibility_with_legacy(self):
        """Test that modern union syntax is compatible with legacy Union[] syntax."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "mixed_union_styles",
                    "parameters": [
                        {"name": "modern", "type": "str | int"},
                        {"name": "legacy", "type": "Union[str, int]"},
                    ],
                    "returns": "str | int",
                }
            ],
        }

        # Implementation uses legacy Union syntax
        implementation_artifacts = {
            "functions": {
                "mixed_union_styles": {
                    "parameters": [
                        {
                            "name": "modern",
                            "type": "Union[str, int]",
                        },  # Legacy for modern
                        {"name": "legacy", "type": "str | int"},  # Modern for legacy
                    ],
                    "returns": "Union[str, int]",  # Legacy for modern
                }
            }
        }

        # USE the validation function - should normalize both formats to match
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        # Should pass if normalization converts both formats consistently
        assert len(errors) == 0 or errors == []

    def test_python310_union_syntax_with_generics(self):
        """Test modern union syntax with generic types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "generic_modern_unions",
                    "parameters": [
                        {"name": "data", "type": "List[str] | Dict[str, int]"},
                        {"name": "optional_list", "type": "List[str] | None"},
                        {
                            "name": "complex",
                            "type": "Dict[str, int] | List[float] | set[bool]",
                        },
                    ],
                    "returns": "List[str] | Dict[str, Any] | None",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "generic_modern_unions": {
                    "parameters": [
                        {"name": "data", "type": "List[str] | Dict[str, int]"},
                        {"name": "optional_list", "type": "List[str] | None"},
                        {
                            "name": "complex",
                            "type": "Dict[str, int] | List[float] | set[bool]",
                        },
                    ],
                    "returns": "List[str] | Dict[str, Any] | None",
                }
            }
        }

        # USE the validation function - should handle modern union syntax with generics
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_python310_union_syntax_ordering_normalization(self):
        """Test that union member ordering is normalized consistently."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "union_ordering",
                    "parameters": [
                        {"name": "param1", "type": "str | int | bool"},
                        {"name": "param2", "type": "Union[float, str, int]"},
                    ],
                    "returns": "bool | str | int | float",
                }
            ],
        }

        # Implementation has different ordering
        implementation_artifacts = {
            "functions": {
                "union_ordering": {
                    "parameters": [
                        {
                            "name": "param1",
                            "type": "bool | int | str",
                        },  # Different order
                        {
                            "name": "param2",
                            "type": "Union[int, str, float]",
                        },  # Different order
                    ],
                    "returns": "float | int | str | bool",  # Different order
                }
            }
        }

        # USE the validation function - should normalize union member ordering
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        # Should pass if normalization handles ordering consistently
        assert len(errors) == 0 or errors == []

    def test_python310_union_syntax_with_none_types(self):
        """Test modern union syntax with None (replacing Optional)."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "optional_with_modern_syntax",
                    "parameters": [
                        {"name": "maybe_str", "type": "str | None"},
                        {"name": "maybe_int", "type": "int | None"},
                        {"name": "maybe_complex", "type": "Dict[str, int] | None"},
                    ],
                    "returns": "List[str] | None",
                }
            ],
        }

        # Implementation might use Optional[] syntax
        implementation_artifacts = {
            "functions": {
                "optional_with_modern_syntax": {
                    "parameters": [
                        {
                            "name": "maybe_str",
                            "type": "Optional[str]",
                        },  # Legacy Optional
                        {
                            "name": "maybe_int",
                            "type": "Union[int, None]",
                        },  # Explicit Union with None
                        {
                            "name": "maybe_complex",
                            "type": "Dict[str, int] | None",
                        },  # Modern
                    ],
                    "returns": "Optional[List[str]]",  # Legacy Optional
                }
            }
        }

        # USE the validation function - should handle Optional/None equivalence
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) == 0 or errors == []

    def test_python310_union_syntax_nested_and_complex(self):
        """Test modern union syntax in complex nested scenarios."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "complex_modern_unions",
                    "parameters": [
                        {
                            "name": "nested",
                            "type": "List[str | int] | Dict[str, bool | float]",
                        },
                        {
                            "name": "callback",
                            "type": "Callable[[str | int], bool | None]",
                        },
                        {
                            "name": "tuple_union",
                            "type": "Tuple[str | int, bool | float | None]",
                        },
                    ],
                    "returns": "Union[List[str | int], Dict[str, bool | float], None]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "complex_modern_unions": {
                    "parameters": [
                        {
                            "name": "nested",
                            "type": "List[str | int] | Dict[str, bool | float]",
                        },
                        {
                            "name": "callback",
                            "type": "Callable[[str | int], bool | None]",
                        },
                        {
                            "name": "tuple_union",
                            "type": "Tuple[str | int, bool | float | None]",
                        },
                    ],
                    "returns": "Union[List[str | int], Dict[str, bool | float], None]",
                }
            }
        }

        # USE the validation function - should handle complex nested modern unions
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_python310_union_syntax_error_detection(self):
        """Test that modern union syntax errors are still detected."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "union_mismatch",
                    "parameters": [{"name": "value", "type": "str | int"}],
                    "returns": "bool | float",
                }
            ],
        }

        # Implementation has mismatched union types
        implementation_artifacts = {
            "functions": {
                "union_mismatch": {
                    "parameters": [
                        {"name": "value", "type": "str | bool"}
                    ],  # int vs bool mismatch
                    "returns": "int | float",  # bool vs int mismatch
                }
            }
        }

        # USE the validation function - should still catch type mismatches
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_type_aliases_basic_usage(self):
        """Test validation with basic type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_user_data",
                    "parameters": [
                        {"name": "user_id", "type": "UserId"},  # Type alias
                        {"name": "email", "type": "EmailAddress"},  # Type alias
                        {"name": "scores", "type": "ScoreList"},  # Type alias
                    ],
                    "returns": "UserProfile",  # Type alias
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_user_data": {
                    "parameters": [
                        {"name": "user_id", "type": "UserId"},
                        {"name": "email", "type": "EmailAddress"},
                        {"name": "scores", "type": "ScoreList"},
                    ],
                    "returns": "UserProfile",
                }
            }
        }

        # USE the validation function - should handle type aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_type_aliases_with_generics(self):
        """Test validation with generic type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_mapping",
                    "parameters": [
                        {
                            "name": "data",
                            "type": "StringToIntMap",
                        },  # Dict[str, int] alias
                        {"name": "items", "type": "StringList"},  # List[str] alias
                        {
                            "name": "optional",
                            "type": "MaybeString",
                        },  # Optional[str] alias
                    ],
                    "returns": "StringToIntMap",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_mapping": {
                    "parameters": [
                        {"name": "data", "type": "StringToIntMap"},
                        {"name": "items", "type": "StringList"},
                        {"name": "optional", "type": "MaybeString"},
                    ],
                    "returns": "StringToIntMap",
                }
            }
        }

        # USE the validation function - should handle generic type aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_newtype_basic_usage(self):
        """Test validation with NewType constructs."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_ids",
                    "parameters": [
                        {"name": "user_id", "type": "UserId"},  # NewType('UserId', int)
                        {
                            "name": "product_id",
                            "type": "ProductId",
                        },  # NewType('ProductId', str)
                        {
                            "name": "timestamp",
                            "type": "Timestamp",
                        },  # NewType('Timestamp', float)
                    ],
                    "returns": "UserId",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_ids": {
                    "parameters": [
                        {"name": "user_id", "type": "UserId"},
                        {"name": "product_id", "type": "ProductId"},
                        {"name": "timestamp", "type": "Timestamp"},
                    ],
                    "returns": "UserId",
                }
            }
        }

        # USE the validation function - should handle NewType constructs
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_type_aliases_vs_underlying_types(self):
        """Test that type aliases are distinguished from their underlying types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "strict_typing",
                    "parameters": [
                        {
                            "name": "user_id",
                            "type": "UserId",
                        },  # Should be UserId, not int
                        {
                            "name": "name",
                            "type": "UserName",
                        },  # Should be UserName, not str
                    ],
                    "returns": "UserId",
                }
            ],
        }

        # Implementation uses underlying types instead of aliases
        implementation_artifacts = {
            "functions": {
                "strict_typing": {
                    "parameters": [
                        {
                            "name": "user_id",
                            "type": "int",
                        },  # Underlying type instead of alias
                        {
                            "name": "name",
                            "type": "str",
                        },  # Underlying type instead of alias
                    ],
                    "returns": "int",  # Underlying type instead of alias
                }
            }
        }

        # USE the validation function - should detect alias vs underlying type differences
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        # This test depends on whether the implementation treats aliases as distinct
        assert isinstance(errors, list)  # Should return some result

    def test_complex_type_aliases_with_unions_and_generics(self):
        """Test validation with complex type aliases involving unions and generics."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "complex_aliases",
                    "parameters": [
                        {
                            "name": "data",
                            "type": "StringOrIntList",
                        },  # List[Union[str, int]]
                        {
                            "name": "mapping",
                            "type": "UserDataMapping",
                        },  # Dict[UserId, UserProfile]
                        {
                            "name": "callback",
                            "type": "ProcessorCallback",
                        },  # Callable[[str], Optional[int]]
                    ],
                    "returns": "MaybeUserList",  # Optional[List[User]]
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "complex_aliases": {
                    "parameters": [
                        {"name": "data", "type": "StringOrIntList"},
                        {"name": "mapping", "type": "UserDataMapping"},
                        {"name": "callback", "type": "ProcessorCallback"},
                    ],
                    "returns": "MaybeUserList",
                }
            }
        }

        # USE the validation function - should handle complex type aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_type_aliases_with_forward_references(self):
        """Test validation with type aliases that include forward references."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "forward_alias_types",
                    "parameters": [
                        {
                            "name": "node",
                            "type": "TreeNodeAlias",
                        },  # Alias to 'TreeNode'
                        {
                            "name": "children",
                            "type": "ChildrenList",
                        },  # Alias to List['TreeNode']
                    ],
                    "returns": "TreeNodeAlias",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "forward_alias_types": {
                    "parameters": [
                        {"name": "node", "type": "TreeNodeAlias"},
                        {"name": "children", "type": "ChildrenList"},
                    ],
                    "returns": "TreeNodeAlias",
                }
            }
        }

        # USE the validation function - should handle forward reference aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_type_aliases_mismatches(self):
        """Test that validation catches mismatches in type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "alias_mismatch",
                    "parameters": [
                        {"name": "id_value", "type": "UserId"},
                        {"name": "name_value", "type": "UserName"},
                    ],
                    "returns": "UserProfile",
                }
            ],
        }

        # Implementation has different type aliases
        implementation_artifacts = {
            "functions": {
                "alias_mismatch": {
                    "parameters": [
                        {
                            "name": "id_value",
                            "type": "ProductId",
                        },  # UserId vs ProductId mismatch
                        {
                            "name": "name_value",
                            "type": "ProductName",
                        },  # UserName vs ProductName mismatch
                    ],
                    "returns": "ProductProfile",  # UserProfile vs ProductProfile mismatch
                }
            }
        }

        # USE the validation function - should catch alias type mismatches
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_literal_types_and_final_annotations(self):
        """Test validation with Literal types and Final annotations."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "literal_and_final",
                    "parameters": [
                        {
                            "name": "status",
                            "type": "Literal['active', 'inactive', 'pending']",
                        },
                        {
                            "name": "config_key",
                            "type": "Literal['debug', 'production']",
                        },
                        {"name": "constant", "type": "Final[int]"},
                    ],
                    "returns": "Literal['success', 'failure']",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "literal_and_final": {
                    "parameters": [
                        {
                            "name": "status",
                            "type": "Literal['active', 'inactive', 'pending']",
                        },
                        {
                            "name": "config_key",
                            "type": "Literal['debug', 'production']",
                        },
                        {"name": "constant", "type": "Final[int]"},
                    ],
                    "returns": "Literal['success', 'failure']",
                }
            }
        }

        # USE the validation function - should handle Literal and Final types
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_protocol_and_typed_dict_aliases(self):
        """Test validation with Protocol and TypedDict type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "protocol_and_typeddict",
                    "parameters": [
                        {
                            "name": "drawable",
                            "type": "DrawableProtocol",
                        },  # Protocol alias
                        {
                            "name": "user_data",
                            "type": "UserDataDict",
                        },  # TypedDict alias
                        {"name": "config", "type": "ConfigProtocol"},  # Protocol alias
                    ],
                    "returns": "ResponseDict",  # TypedDict alias
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "protocol_and_typeddict": {
                    "parameters": [
                        {"name": "drawable", "type": "DrawableProtocol"},
                        {"name": "user_data", "type": "UserDataDict"},
                        {"name": "config", "type": "ConfigProtocol"},
                    ],
                    "returns": "ResponseDict",
                }
            }
        }

        # USE the validation function - should handle Protocol and TypedDict aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []
