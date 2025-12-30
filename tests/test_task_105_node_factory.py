"""Behavioral tests for Task 105: Node Factory.

Tests the factory functions that create graph nodes from raw data:
- create_manifest_node: Creates ManifestNode from manifest data and path
- create_file_node: Creates FileNode from file path string
- create_artifact_node: Creates ArtifactNode from artifact dict and file path
- create_module_node: Creates ModuleNode from file path string
"""

from pathlib import Path
from typing import Any, Dict

from maid_runner.graph.builder import (
    create_manifest_node,
    create_file_node,
    create_artifact_node,
    create_module_node,
)
from maid_runner.graph.model import (
    ManifestNode,
    FileNode,
    ArtifactNode,
    ModuleNode,
    NodeType,
)


class TestCreateManifestNode:
    """Tests for create_manifest_node factory function."""

    def test_returns_manifest_node(self, tmp_path: Path) -> None:
        """create_manifest_node returns a ManifestNode instance."""
        manifest_data: Dict[str, Any] = {
            "goal": "Test goal",
            "taskType": "create",
        }
        manifest_path = tmp_path / "task-001-test.manifest.json"

        result = create_manifest_node(manifest_data, manifest_path)

        assert isinstance(result, ManifestNode)

    def test_sets_correct_node_type(self, tmp_path: Path) -> None:
        """create_manifest_node sets node_type to NodeType.MANIFEST."""
        manifest_data: Dict[str, Any] = {
            "goal": "Test goal",
            "taskType": "edit",
        }
        manifest_path = tmp_path / "task-002-update.manifest.json"

        result = create_manifest_node(manifest_data, manifest_path)

        assert result.node_type == NodeType.MANIFEST

    def test_extracts_goal_from_manifest_data(self, tmp_path: Path) -> None:
        """create_manifest_node extracts goal from manifest_data."""
        manifest_data: Dict[str, Any] = {
            "goal": "Create new feature module",
            "taskType": "create",
        }
        manifest_path = tmp_path / "task-003-feature.manifest.json"

        result = create_manifest_node(manifest_data, manifest_path)

        assert result.goal == "Create new feature module"

    def test_extracts_task_type_from_manifest_data(self, tmp_path: Path) -> None:
        """create_manifest_node extracts taskType from manifest_data."""
        manifest_data: Dict[str, Any] = {
            "goal": "Refactor module",
            "taskType": "refactor",
        }
        manifest_path = tmp_path / "task-004-refactor.manifest.json"

        result = create_manifest_node(manifest_data, manifest_path)

        assert result.task_type == "refactor"

    def test_extracts_version_from_manifest_data(self, tmp_path: Path) -> None:
        """create_manifest_node extracts version when present in manifest_data."""
        manifest_data: Dict[str, Any] = {
            "goal": "Versioned manifest",
            "taskType": "edit",
            "version": "1.3",
        }
        manifest_path = tmp_path / "task-005-versioned.manifest.json"

        result = create_manifest_node(manifest_data, manifest_path)

        assert result.version == "1.3"

    def test_generates_unique_id_from_path(self, tmp_path: Path) -> None:
        """create_manifest_node generates unique ID from path."""
        manifest_data: Dict[str, Any] = {
            "goal": "Test",
            "taskType": "create",
        }
        manifest_path = tmp_path / "task-006-unique.manifest.json"

        result = create_manifest_node(manifest_data, manifest_path)

        assert result.id is not None
        assert len(result.id) > 0
        # ID should be derived from or include path info
        assert "task-006" in result.id or str(manifest_path) in result.id

    def test_handles_different_task_types(self, tmp_path: Path) -> None:
        """create_manifest_node handles various taskType values."""
        task_types = ["create", "edit", "refactor", "snapshot"]

        for task_type in task_types:
            manifest_data: Dict[str, Any] = {
                "goal": f"Task of type {task_type}",
                "taskType": task_type,
            }
            manifest_path = tmp_path / f"task-{task_type}.manifest.json"

            result = create_manifest_node(manifest_data, manifest_path)

            assert result.task_type == task_type

    def test_sets_path_attribute(self, tmp_path: Path) -> None:
        """create_manifest_node sets path attribute from manifest_path."""
        manifest_data: Dict[str, Any] = {
            "goal": "Test path",
            "taskType": "create",
        }
        manifest_path = tmp_path / "manifests" / "task-007-path.manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        result = create_manifest_node(manifest_data, manifest_path)

        assert str(manifest_path) in result.path or result.path == str(manifest_path)

    def test_handles_missing_optional_fields(self, tmp_path: Path) -> None:
        """create_manifest_node handles manifest without optional version field."""
        manifest_data: Dict[str, Any] = {
            "goal": "Minimal manifest",
            "taskType": "create",
        }
        manifest_path = tmp_path / "task-008-minimal.manifest.json"

        result = create_manifest_node(manifest_data, manifest_path)

        # Should not raise error, version should be empty or default
        assert result.goal == "Minimal manifest"
        assert result.task_type == "create"


class TestCreateFileNode:
    """Tests for create_file_node factory function."""

    def test_returns_file_node(self) -> None:
        """create_file_node returns a FileNode instance."""
        file_path = "src/module.py"

        result = create_file_node(file_path)

        assert isinstance(result, FileNode)

    def test_sets_correct_node_type(self) -> None:
        """create_file_node sets node_type to NodeType.FILE."""
        file_path = "src/utils/helper.py"

        result = create_file_node(file_path)

        assert result.node_type == NodeType.FILE

    def test_sets_path_attribute(self) -> None:
        """create_file_node sets path attribute from file_path."""
        file_path = "maid_runner/graph/model.py"

        result = create_file_node(file_path)

        assert result.path == file_path

    def test_generates_unique_id_from_file_path(self) -> None:
        """create_file_node generates unique ID from file_path."""
        file_path = "src/components/widget.py"

        result = create_file_node(file_path)

        assert result.id is not None
        assert len(result.id) > 0

    def test_handles_nested_directory_path(self) -> None:
        """create_file_node handles deeply nested file paths."""
        file_path = "src/components/ui/buttons/primary_button.py"

        result = create_file_node(file_path)

        assert result.path == file_path
        assert isinstance(result, FileNode)

    def test_handles_root_level_path(self) -> None:
        """create_file_node handles root-level file paths."""
        file_path = "setup.py"

        result = create_file_node(file_path)

        assert result.path == file_path
        assert result.node_type == NodeType.FILE

    def test_handles_path_with_special_characters(self) -> None:
        """create_file_node handles file paths with hyphens and underscores."""
        file_path = "src/my-module/test_utils.py"

        result = create_file_node(file_path)

        assert result.path == file_path

    def test_different_paths_produce_different_ids(self) -> None:
        """create_file_node generates different IDs for different paths."""
        path1 = "src/module_a.py"
        path2 = "src/module_b.py"

        result1 = create_file_node(path1)
        result2 = create_file_node(path2)

        assert result1.id != result2.id

    def test_same_path_produces_same_id(self) -> None:
        """create_file_node generates same ID for same path (deterministic)."""
        file_path = "src/consistent.py"

        result1 = create_file_node(file_path)
        result2 = create_file_node(file_path)

        assert result1.id == result2.id


class TestCreateArtifactNode:
    """Tests for create_artifact_node factory function."""

    def test_returns_artifact_node(self) -> None:
        """create_artifact_node returns an ArtifactNode instance."""
        artifact: Dict[str, Any] = {
            "type": "function",
            "name": "process_data",
        }
        file_path = "src/processor.py"

        result = create_artifact_node(artifact, file_path)

        assert isinstance(result, ArtifactNode)

    def test_sets_correct_node_type(self) -> None:
        """create_artifact_node sets node_type to NodeType.ARTIFACT."""
        artifact: Dict[str, Any] = {
            "type": "class",
            "name": "DataHandler",
        }
        file_path = "src/handler.py"

        result = create_artifact_node(artifact, file_path)

        assert result.node_type == NodeType.ARTIFACT

    def test_extracts_name_from_artifact_dict(self) -> None:
        """create_artifact_node extracts name from artifact dict."""
        artifact: Dict[str, Any] = {
            "type": "function",
            "name": "calculate_total",
        }
        file_path = "src/calculator.py"

        result = create_artifact_node(artifact, file_path)

        assert result.name == "calculate_total"

    def test_extracts_artifact_type_from_dict(self) -> None:
        """create_artifact_node extracts type from artifact dict."""
        artifact: Dict[str, Any] = {
            "type": "attribute",
            "name": "DEFAULT_VALUE",
        }
        file_path = "src/constants.py"

        result = create_artifact_node(artifact, file_path)

        assert result.artifact_type == "attribute"

    def test_handles_optional_signature_field(self) -> None:
        """create_artifact_node handles optional signature field."""
        artifact: Dict[str, Any] = {
            "type": "function",
            "name": "transform",
            "signature": "(data: List[int]) -> List[str]",
        }
        file_path = "src/transformer.py"

        result = create_artifact_node(artifact, file_path)

        assert result.signature == "(data: List[int]) -> List[str]"

    def test_handles_missing_signature_field(self) -> None:
        """create_artifact_node handles artifact without signature field."""
        artifact: Dict[str, Any] = {
            "type": "function",
            "name": "simple_func",
        }
        file_path = "src/simple.py"

        result = create_artifact_node(artifact, file_path)

        # Signature should be None or empty when not provided
        assert result.signature is None or result.signature == ""

    def test_handles_optional_class_field(self) -> None:
        """create_artifact_node handles optional class field (parent_class)."""
        artifact: Dict[str, Any] = {
            "type": "function",
            "name": "get_value",
            "class": "DataContainer",
        }
        file_path = "src/container.py"

        result = create_artifact_node(artifact, file_path)

        assert result.parent_class == "DataContainer"

    def test_handles_missing_class_field(self) -> None:
        """create_artifact_node handles artifact without class field."""
        artifact: Dict[str, Any] = {
            "type": "function",
            "name": "standalone_function",
        }
        file_path = "src/standalone.py"

        result = create_artifact_node(artifact, file_path)

        assert result.parent_class is None or result.parent_class == ""

    def test_generates_unique_id_combining_file_and_artifact(self) -> None:
        """create_artifact_node generates unique ID from file_path and artifact name."""
        artifact: Dict[str, Any] = {
            "type": "function",
            "name": "unique_func",
        }
        file_path = "src/unique_module.py"

        result = create_artifact_node(artifact, file_path)

        assert result.id is not None
        assert len(result.id) > 0
        # ID should include file or artifact info for uniqueness
        # Could be hash-based or path-based, just verify it exists

    def test_different_artifacts_same_file_different_ids(self) -> None:
        """create_artifact_node generates different IDs for different artifacts in same file."""
        file_path = "src/module.py"
        artifact1: Dict[str, Any] = {"type": "function", "name": "func_a"}
        artifact2: Dict[str, Any] = {"type": "function", "name": "func_b"}

        result1 = create_artifact_node(artifact1, file_path)
        result2 = create_artifact_node(artifact2, file_path)

        assert result1.id != result2.id

    def test_same_artifact_different_files_different_ids(self) -> None:
        """create_artifact_node generates different IDs for same artifact name in different files."""
        artifact: Dict[str, Any] = {"type": "function", "name": "helper"}
        file_path1 = "src/module_a.py"
        file_path2 = "src/module_b.py"

        result1 = create_artifact_node(artifact, file_path1)
        result2 = create_artifact_node(artifact, file_path2)

        assert result1.id != result2.id

    def test_handles_class_artifact_type(self) -> None:
        """create_artifact_node correctly handles class type artifacts."""
        artifact: Dict[str, Any] = {
            "type": "class",
            "name": "MyClass",
        }
        file_path = "src/myclass.py"

        result = create_artifact_node(artifact, file_path)

        assert result.artifact_type == "class"
        assert result.name == "MyClass"

    def test_handles_method_with_class_parent(self) -> None:
        """create_artifact_node handles method with class parent."""
        artifact: Dict[str, Any] = {
            "type": "function",
            "name": "__init__",
            "class": "MyClass",
            "signature": "(self, value: int)",
        }
        file_path = "src/myclass.py"

        result = create_artifact_node(artifact, file_path)

        assert result.name == "__init__"
        assert result.parent_class == "MyClass"
        assert result.signature == "(self, value: int)"


class TestCreateModuleNode:
    """Tests for create_module_node factory function."""

    def test_returns_module_node(self) -> None:
        """create_module_node returns a ModuleNode instance."""
        file_path = "maid_runner/graph/builder.py"

        result = create_module_node(file_path)

        assert isinstance(result, ModuleNode)

    def test_sets_correct_node_type(self) -> None:
        """create_module_node sets node_type to NodeType.MODULE."""
        file_path = "src/utils/helpers.py"

        result = create_module_node(file_path)

        assert result.node_type == NodeType.MODULE

    def test_derives_module_name_from_file_path(self) -> None:
        """create_module_node derives module name from file path (basename without .py)."""
        file_path = "maid_runner/graph/builder.py"

        result = create_module_node(file_path)

        assert result.name == "builder"

    def test_derives_package_from_file_path(self) -> None:
        """create_module_node derives package from file path directory structure."""
        file_path = "maid_runner/graph/builder.py"

        result = create_module_node(file_path)

        # Package should be maid_runner.graph
        assert result.package == "maid_runner.graph"

    def test_handles_top_level_module(self) -> None:
        """create_module_node handles top-level modules with no package."""
        file_path = "setup.py"

        result = create_module_node(file_path)

        assert result.name == "setup"
        # Package should be None or empty for top-level
        assert result.package is None or result.package == ""

    def test_handles_single_level_package(self) -> None:
        """create_module_node handles single-level package."""
        file_path = "src/module.py"

        result = create_module_node(file_path)

        assert result.name == "module"
        assert result.package == "src"

    def test_handles_deeply_nested_package(self) -> None:
        """create_module_node handles deeply nested package structure."""
        file_path = "src/components/ui/buttons/primary.py"

        result = create_module_node(file_path)

        assert result.name == "primary"
        assert result.package == "src.components.ui.buttons"

    def test_generates_unique_id_from_file_path(self) -> None:
        """create_module_node generates unique ID from file_path."""
        file_path = "maid_runner/validators/schema.py"

        result = create_module_node(file_path)

        assert result.id is not None
        assert len(result.id) > 0

    def test_different_paths_produce_different_ids(self) -> None:
        """create_module_node generates different IDs for different paths."""
        path1 = "src/module_a.py"
        path2 = "src/module_b.py"

        result1 = create_module_node(path1)
        result2 = create_module_node(path2)

        assert result1.id != result2.id

    def test_same_path_produces_same_id(self) -> None:
        """create_module_node generates same ID for same path (deterministic)."""
        file_path = "src/deterministic.py"

        result1 = create_module_node(file_path)
        result2 = create_module_node(file_path)

        assert result1.id == result2.id

    def test_handles_init_file(self) -> None:
        """create_module_node handles __init__.py files."""
        file_path = "maid_runner/graph/__init__.py"

        result = create_module_node(file_path)

        assert result.name == "__init__"
        assert result.package == "maid_runner.graph"

    def test_handles_path_with_hyphenated_directory(self) -> None:
        """create_module_node handles paths with hyphenated directory names."""
        file_path = "my-project/src/module.py"

        result = create_module_node(file_path)

        assert result.name == "module"
        # Package should reflect the path structure
        assert "my-project" in result.package or "src" in result.package
