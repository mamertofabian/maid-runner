"""Behavioral tests for task-065: Fix artifact merge key to include class name.

Tests that _merge_expected_artifacts properly distinguishes methods with
the same name in different classes by using (type, class, name) as the key.
"""

import json
import tempfile
from pathlib import Path
from maid_runner.validators.manifest_validator import (
    _merge_expected_artifacts,
    _get_artifact_key,
)


class TestGetArtifactKey:
    """Test the _get_artifact_key function for proper key generation."""

    def test_class_artifact_key(self):
        """Test key generation for class artifacts."""
        artifact = {"type": "class", "name": "MyClass"}
        key = _get_artifact_key(artifact)
        assert key == ("class", None, "MyClass")

    def test_function_artifact_key(self):
        """Test key generation for standalone function artifacts."""
        artifact = {"type": "function", "name": "my_function"}
        key = _get_artifact_key(artifact)
        assert key == ("function", None, "my_function")

    def test_method_artifact_key(self):
        """Test key generation for method artifacts (includes class)."""
        artifact = {"type": "function", "name": "get", "class": "LRUCache"}
        key = _get_artifact_key(artifact)
        assert key == ("function", "LRUCache", "get")

    def test_attribute_artifact_key(self):
        """Test key generation for attribute artifacts."""
        artifact = {"type": "attribute", "name": "value", "class": "MyClass"}
        key = _get_artifact_key(artifact)
        assert key == ("attribute", "MyClass", "value")

    def test_module_level_attribute_key(self):
        """Test key generation for module-level attributes."""
        artifact = {"type": "attribute", "name": "CONSTANT"}
        key = _get_artifact_key(artifact)
        assert key == ("attribute", None, "CONSTANT")


class TestMergeArtifactsWithMultipleClasses:
    """Test that _merge_expected_artifacts handles multiple classes correctly."""

    def test_methods_with_same_name_in_different_classes(self):
        """Test that methods with same name in different classes are not overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_dir = Path(tmpdir)
            target_file = "cache.py"

            # Create manifest with multiple classes having same method names
            manifest = {
                "goal": "Test cache classes",
                "taskType": "create",
                "creatableFiles": [target_file],
                "editableFiles": [],
                "readonlyFiles": [],
                "expectedArtifacts": {
                    "file": target_file,
                    "contains": [
                        {"type": "class", "name": "LRUCache"},
                        {
                            "type": "function",
                            "name": "get",
                            "class": "LRUCache",
                            "args": [{"name": "key", "type": "str"}],
                        },
                        {
                            "type": "function",
                            "name": "set",
                            "class": "LRUCache",
                            "args": [{"name": "key", "type": "str"}],
                        },
                        {"type": "class", "name": "TTLCache"},
                        {
                            "type": "function",
                            "name": "get",
                            "class": "TTLCache",
                            "args": [{"name": "key", "type": "str"}],
                        },
                        {
                            "type": "function",
                            "name": "set",
                            "class": "TTLCache",
                            "args": [{"name": "key", "type": "str"}],
                        },
                        {"type": "class", "name": "ValidationCache"},
                        {
                            "type": "function",
                            "name": "get",
                            "class": "ValidationCache",
                            "args": [{"name": "manifest_path", "type": "str"}],
                        },
                        {
                            "type": "function",
                            "name": "set",
                            "class": "ValidationCache",
                            "args": [
                                {"name": "manifest_path", "type": "str"},
                                {"name": "result", "type": "Any"},
                            ],
                        },
                    ],
                },
            }

            manifest_path = manifest_dir / "test.manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)

            # Merge artifacts
            merged = _merge_expected_artifacts([str(manifest_path)], target_file)

            # Verify all artifacts are preserved
            assert len(merged) == 9  # 3 classes + 6 methods

            # Group by class to verify
            classes = {a["name"]: a for a in merged if a["type"] == "class"}
            assert len(classes) == 3
            assert "LRUCache" in classes
            assert "TTLCache" in classes
            assert "ValidationCache" in classes

            # Check that all methods are present
            methods = [a for a in merged if a["type"] == "function"]
            assert len(methods) == 6

            # Group methods by class
            lru_methods = [m for m in methods if m.get("class") == "LRUCache"]
            ttl_methods = [m for m in methods if m.get("class") == "TTLCache"]
            val_methods = [m for m in methods if m.get("class") == "ValidationCache"]

            assert len(lru_methods) == 2
            assert len(ttl_methods) == 2
            assert len(val_methods) == 2

            # Verify method names
            assert {m["name"] for m in lru_methods} == {"get", "set"}
            assert {m["name"] for m in ttl_methods} == {"get", "set"}
            assert {m["name"] for m in val_methods} == {"get", "set"}

    def test_later_manifest_overrides_method_definition(self):
        """Test that later manifests override earlier method definitions for same class.method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_dir = Path(tmpdir)
            target_file = "cache.py"

            # First manifest
            manifest1 = {
                "goal": "Initial cache",
                "taskType": "create",
                "creatableFiles": [target_file],
                "editableFiles": [],
                "readonlyFiles": [],
                "expectedArtifacts": {
                    "file": target_file,
                    "contains": [
                        {"type": "class", "name": "Cache"},
                        {
                            "type": "function",
                            "name": "get",
                            "class": "Cache",
                            "args": [{"name": "key", "type": "str"}],
                            "returns": "str",
                        },
                    ],
                },
            }

            # Second manifest - updates the return type
            manifest2 = {
                "goal": "Update cache return type",
                "taskType": "edit",
                "creatableFiles": [],
                "editableFiles": [target_file],
                "readonlyFiles": [],
                "expectedArtifacts": {
                    "file": target_file,
                    "contains": [
                        {
                            "type": "function",
                            "name": "get",
                            "class": "Cache",
                            "args": [{"name": "key", "type": "str"}],
                            "returns": "Any | None",  # Updated return type
                        },
                    ],
                },
            }

            manifest1_path = manifest_dir / "task-001.manifest.json"
            manifest2_path = manifest_dir / "task-002.manifest.json"

            with open(manifest1_path, "w") as f:
                json.dump(manifest1, f)
            with open(manifest2_path, "w") as f:
                json.dump(manifest2, f)

            # Merge in chronological order
            merged = _merge_expected_artifacts(
                [str(manifest1_path), str(manifest2_path)], target_file
            )

            # Find the get method
            get_methods = [
                a
                for a in merged
                if a["type"] == "function"
                and a["name"] == "get"
                and a.get("class") == "Cache"
            ]

            assert len(get_methods) == 1
            # Should have the updated return type from manifest2
            assert get_methods[0]["returns"] == "Any | None"

    def test_different_classes_with_same_method_not_overwritten(self):
        """Test that different classes can have methods with the same name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_dir = Path(tmpdir)
            target_file = "models.py"

            manifest = {
                "goal": "Create models",
                "taskType": "create",
                "creatableFiles": [target_file],
                "editableFiles": [],
                "readonlyFiles": [],
                "expectedArtifacts": {
                    "file": target_file,
                    "contains": [
                        {"type": "class", "name": "User"},
                        {
                            "type": "function",
                            "name": "validate",
                            "class": "User",
                            "returns": "bool",
                        },
                        {"type": "class", "name": "Product"},
                        {
                            "type": "function",
                            "name": "validate",
                            "class": "Product",
                            "returns": "bool",
                        },
                        {"type": "class", "name": "Order"},
                        {
                            "type": "function",
                            "name": "validate",
                            "class": "Order",
                            "returns": "bool",
                        },
                    ],
                },
            }

            manifest_path = manifest_dir / "test.manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)

            merged = _merge_expected_artifacts([str(manifest_path)], target_file)

            # Should have all 3 classes and 3 validate methods
            assert len(merged) == 6

            validate_methods = [
                a for a in merged if a["type"] == "function" and a["name"] == "validate"
            ]
            assert len(validate_methods) == 3

            # Each class should have its own validate method
            classes_with_validate = {m.get("class") for m in validate_methods}
            assert classes_with_validate == {"User", "Product", "Order"}
