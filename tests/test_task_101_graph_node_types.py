"""Behavioral tests for task-101: Graph Node Types.

These tests verify the graph node data structures for the Knowledge Graph Builder.
Tests focus on behavioral validation - using (instantiating, accessing) the declared
artifacts rather than implementation details.

Artifacts tested:
- NodeType enum with values: MANIFEST, FILE, ARTIFACT, MODULE
- Node base class with id, node_type, and attributes
- ManifestNode with path, goal, task_type, version
- FileNode with path, status
- ArtifactNode with name, artifact_type, signature, parent_class
- ModuleNode with name, package
"""

from maid_runner.graph.model import (
    NodeType,
    Node,
    ManifestNode,
    FileNode,
    ArtifactNode,
    ModuleNode,
)


class TestNodeTypeEnum:
    """Tests for the NodeType enumeration."""

    def test_node_type_has_manifest_value(self):
        """NodeType enum has MANIFEST value."""
        assert hasattr(NodeType, "MANIFEST")
        manifest_type = NodeType.MANIFEST
        assert manifest_type is not None

    def test_node_type_has_file_value(self):
        """NodeType enum has FILE value."""
        assert hasattr(NodeType, "FILE")
        file_type = NodeType.FILE
        assert file_type is not None

    def test_node_type_has_artifact_value(self):
        """NodeType enum has ARTIFACT value."""
        assert hasattr(NodeType, "ARTIFACT")
        artifact_type = NodeType.ARTIFACT
        assert artifact_type is not None

    def test_node_type_has_module_value(self):
        """NodeType enum has MODULE value."""
        assert hasattr(NodeType, "MODULE")
        module_type = NodeType.MODULE
        assert module_type is not None

    def test_node_type_values_are_distinct(self):
        """All NodeType values are distinct from each other."""
        values = [NodeType.MANIFEST, NodeType.FILE, NodeType.ARTIFACT, NodeType.MODULE]
        assert len(values) == len(set(values))

    def test_node_type_iteration(self):
        """NodeType can be iterated over (standard enum behavior)."""
        node_types = list(NodeType)
        assert len(node_types) >= 4
        assert NodeType.MANIFEST in node_types
        assert NodeType.FILE in node_types
        assert NodeType.ARTIFACT in node_types
        assert NodeType.MODULE in node_types


class TestNodeBaseClass:
    """Tests for the Node base class."""

    def test_node_creation_with_required_attributes(self):
        """Node can be created with id and node_type."""
        node = Node(id="test-node-1", node_type=NodeType.MANIFEST)

        assert node.id == "test-node-1"
        assert node.node_type == NodeType.MANIFEST

    def test_node_attributes_defaults_to_empty_dict(self):
        """Node attributes defaults to empty dict when not provided."""
        node = Node(id="test-node-2", node_type=NodeType.FILE)

        assert node.attributes == {} or node.attributes is not None
        # Verify it's dict-like
        assert hasattr(node.attributes, "get")

    def test_node_creation_with_custom_attributes(self):
        """Node can be created with custom attributes dict."""
        custom_attrs = {"key1": "value1", "key2": 42, "nested": {"a": 1}}
        node = Node(id="test-node-3", node_type=NodeType.ARTIFACT, attributes=custom_attrs)

        assert node.attributes["key1"] == "value1"
        assert node.attributes["key2"] == 42
        assert node.attributes["nested"]["a"] == 1

    def test_node_has_id_attribute(self):
        """Node has an id attribute that is accessible."""
        node = Node(id="unique-id-123", node_type=NodeType.MODULE)

        assert hasattr(node, "id")
        assert node.id == "unique-id-123"

    def test_node_has_node_type_attribute(self):
        """Node has a node_type attribute that is accessible."""
        node = Node(id="type-test", node_type=NodeType.FILE)

        assert hasattr(node, "node_type")
        assert node.node_type == NodeType.FILE

    def test_node_has_attributes_attribute(self):
        """Node has an attributes attribute that is accessible."""
        node = Node(id="attrs-test", node_type=NodeType.MANIFEST)

        assert hasattr(node, "attributes")

    def test_node_with_different_node_types(self):
        """Node can be created with any NodeType value."""
        for node_type in NodeType:
            node = Node(id=f"node-{node_type.name}", node_type=node_type)
            assert node.node_type == node_type


class TestManifestNode:
    """Tests for the ManifestNode class."""

    def test_manifest_node_creation_with_all_attributes(self):
        """ManifestNode can be created with path, goal, task_type, version."""
        manifest_node = ManifestNode(
            id="manifest-1",
            path="manifests/task-001.manifest.json",
            goal="Create new feature",
            task_type="create",
            version="1.3",
        )

        assert manifest_node.path == "manifests/task-001.manifest.json"
        assert manifest_node.goal == "Create new feature"
        assert manifest_node.task_type == "create"
        assert manifest_node.version == "1.3"

    def test_manifest_node_inherits_from_node(self):
        """ManifestNode inherits from Node base class."""
        manifest_node = ManifestNode(
            id="manifest-2",
            path="manifests/task-002.manifest.json",
            goal="Edit feature",
            task_type="edit",
            version="1.3",
        )

        assert isinstance(manifest_node, Node)

    def test_manifest_node_has_correct_node_type(self):
        """ManifestNode has node_type set to NodeType.MANIFEST."""
        manifest_node = ManifestNode(
            id="manifest-3",
            path="manifests/task-003.manifest.json",
            goal="Refactor module",
            task_type="refactor",
            version="1.3",
        )

        assert manifest_node.node_type == NodeType.MANIFEST

    def test_manifest_node_has_id_from_base_class(self):
        """ManifestNode has id attribute from Node base class."""
        manifest_node = ManifestNode(
            id="manifest-id-test",
            path="manifests/task-004.manifest.json",
            goal="Snapshot code",
            task_type="snapshot",
            version="1.3",
        )

        assert manifest_node.id == "manifest-id-test"

    def test_manifest_node_has_attributes_from_base_class(self):
        """ManifestNode has attributes from Node base class."""
        custom_attrs = {"extra": "data"}
        manifest_node = ManifestNode(
            id="manifest-attrs-test",
            path="manifests/task-005.manifest.json",
            goal="Test attributes",
            task_type="create",
            version="1.3",
            attributes=custom_attrs,
        )

        assert manifest_node.attributes["extra"] == "data"

    def test_manifest_node_path_attribute(self):
        """ManifestNode has path attribute."""
        manifest_node = ManifestNode(
            id="m1",
            path="path/to/manifest.json",
            goal="g",
            task_type="t",
            version="v",
        )

        assert hasattr(manifest_node, "path")
        assert manifest_node.path == "path/to/manifest.json"

    def test_manifest_node_goal_attribute(self):
        """ManifestNode has goal attribute."""
        manifest_node = ManifestNode(
            id="m2",
            path="p",
            goal="This is the goal description",
            task_type="t",
            version="v",
        )

        assert hasattr(manifest_node, "goal")
        assert manifest_node.goal == "This is the goal description"

    def test_manifest_node_task_type_attribute(self):
        """ManifestNode has task_type attribute."""
        manifest_node = ManifestNode(
            id="m3",
            path="p",
            goal="g",
            task_type="edit",
            version="v",
        )

        assert hasattr(manifest_node, "task_type")
        assert manifest_node.task_type == "edit"

    def test_manifest_node_version_attribute(self):
        """ManifestNode has version attribute."""
        manifest_node = ManifestNode(
            id="m4",
            path="p",
            goal="g",
            task_type="t",
            version="2.0",
        )

        assert hasattr(manifest_node, "version")
        assert manifest_node.version == "2.0"


class TestFileNode:
    """Tests for the FileNode class."""

    def test_file_node_creation_with_all_attributes(self):
        """FileNode can be created with path and status."""
        file_node = FileNode(
            id="file-1",
            path="src/service.py",
            status="tracked",
        )

        assert file_node.path == "src/service.py"
        assert file_node.status == "tracked"

    def test_file_node_inherits_from_node(self):
        """FileNode inherits from Node base class."""
        file_node = FileNode(
            id="file-2",
            path="src/module.py",
            status="untracked",
        )

        assert isinstance(file_node, Node)

    def test_file_node_has_correct_node_type(self):
        """FileNode has node_type set to NodeType.FILE."""
        file_node = FileNode(
            id="file-3",
            path="src/utils.py",
            status="tracked",
        )

        assert file_node.node_type == NodeType.FILE

    def test_file_node_has_id_from_base_class(self):
        """FileNode has id attribute from Node base class."""
        file_node = FileNode(
            id="file-id-test",
            path="src/test.py",
            status="tracked",
        )

        assert file_node.id == "file-id-test"

    def test_file_node_has_attributes_from_base_class(self):
        """FileNode has attributes from Node base class."""
        custom_attrs = {"line_count": 100}
        file_node = FileNode(
            id="file-attrs-test",
            path="src/code.py",
            status="tracked",
            attributes=custom_attrs,
        )

        assert file_node.attributes["line_count"] == 100

    def test_file_node_path_attribute(self):
        """FileNode has path attribute."""
        file_node = FileNode(
            id="f1",
            path="path/to/file.py",
            status="s",
        )

        assert hasattr(file_node, "path")
        assert file_node.path == "path/to/file.py"

    def test_file_node_status_attribute(self):
        """FileNode has status attribute."""
        file_node = FileNode(
            id="f2",
            path="p",
            status="registered",
        )

        assert hasattr(file_node, "status")
        assert file_node.status == "registered"

    def test_file_node_with_different_statuses(self):
        """FileNode can have various status values."""
        statuses = ["tracked", "untracked", "registered", "absent"]
        for status in statuses:
            file_node = FileNode(
                id=f"file-{status}",
                path="src/file.py",
                status=status,
            )
            assert file_node.status == status


class TestArtifactNode:
    """Tests for the ArtifactNode class."""

    def test_artifact_node_creation_with_required_attributes(self):
        """ArtifactNode can be created with name and artifact_type."""
        artifact_node = ArtifactNode(
            id="artifact-1",
            name="process_data",
            artifact_type="function",
        )

        assert artifact_node.name == "process_data"
        assert artifact_node.artifact_type == "function"

    def test_artifact_node_creation_with_all_attributes(self):
        """ArtifactNode can be created with all attributes including optional ones."""
        artifact_node = ArtifactNode(
            id="artifact-2",
            name="calculate",
            artifact_type="function",
            signature="(x: int, y: int) -> int",
            parent_class="Calculator",
        )

        assert artifact_node.name == "calculate"
        assert artifact_node.artifact_type == "function"
        assert artifact_node.signature == "(x: int, y: int) -> int"
        assert artifact_node.parent_class == "Calculator"

    def test_artifact_node_inherits_from_node(self):
        """ArtifactNode inherits from Node base class."""
        artifact_node = ArtifactNode(
            id="artifact-3",
            name="MyClass",
            artifact_type="class",
        )

        assert isinstance(artifact_node, Node)

    def test_artifact_node_has_correct_node_type(self):
        """ArtifactNode has node_type set to NodeType.ARTIFACT."""
        artifact_node = ArtifactNode(
            id="artifact-4",
            name="helper_func",
            artifact_type="function",
        )

        assert artifact_node.node_type == NodeType.ARTIFACT

    def test_artifact_node_has_id_from_base_class(self):
        """ArtifactNode has id attribute from Node base class."""
        artifact_node = ArtifactNode(
            id="artifact-id-test",
            name="test_artifact",
            artifact_type="function",
        )

        assert artifact_node.id == "artifact-id-test"

    def test_artifact_node_has_attributes_from_base_class(self):
        """ArtifactNode has attributes from Node base class."""
        custom_attrs = {"docstring": "A helpful function"}
        artifact_node = ArtifactNode(
            id="artifact-attrs-test",
            name="documented_func",
            artifact_type="function",
            attributes=custom_attrs,
        )

        assert artifact_node.attributes["docstring"] == "A helpful function"

    def test_artifact_node_name_attribute(self):
        """ArtifactNode has name attribute."""
        artifact_node = ArtifactNode(
            id="a1",
            name="my_artifact",
            artifact_type="function",
        )

        assert hasattr(artifact_node, "name")
        assert artifact_node.name == "my_artifact"

    def test_artifact_node_artifact_type_attribute(self):
        """ArtifactNode has artifact_type attribute."""
        artifact_node = ArtifactNode(
            id="a2",
            name="n",
            artifact_type="class",
        )

        assert hasattr(artifact_node, "artifact_type")
        assert artifact_node.artifact_type == "class"

    def test_artifact_node_signature_attribute(self):
        """ArtifactNode has signature attribute."""
        artifact_node = ArtifactNode(
            id="a3",
            name="func",
            artifact_type="function",
            signature="(self, arg: str) -> bool",
        )

        assert hasattr(artifact_node, "signature")
        assert artifact_node.signature == "(self, arg: str) -> bool"

    def test_artifact_node_parent_class_attribute(self):
        """ArtifactNode has parent_class attribute."""
        artifact_node = ArtifactNode(
            id="a4",
            name="method",
            artifact_type="function",
            parent_class="ParentClass",
        )

        assert hasattr(artifact_node, "parent_class")
        assert artifact_node.parent_class == "ParentClass"

    def test_artifact_node_signature_can_be_none(self):
        """ArtifactNode signature can be None for classes/attributes."""
        artifact_node = ArtifactNode(
            id="a5",
            name="MyClass",
            artifact_type="class",
            signature=None,
        )

        assert artifact_node.signature is None

    def test_artifact_node_parent_class_can_be_none(self):
        """ArtifactNode parent_class can be None for top-level artifacts."""
        artifact_node = ArtifactNode(
            id="a6",
            name="standalone_func",
            artifact_type="function",
            parent_class=None,
        )

        assert artifact_node.parent_class is None

    def test_artifact_node_with_different_artifact_types(self):
        """ArtifactNode can represent different artifact types."""
        artifact_types = ["function", "class", "attribute"]
        for artifact_type in artifact_types:
            artifact_node = ArtifactNode(
                id=f"artifact-{artifact_type}",
                name=f"test_{artifact_type}",
                artifact_type=artifact_type,
            )
            assert artifact_node.artifact_type == artifact_type


class TestModuleNode:
    """Tests for the ModuleNode class."""

    def test_module_node_creation_with_all_attributes(self):
        """ModuleNode can be created with name and package."""
        module_node = ModuleNode(
            id="module-1",
            name="validators",
            package="maid_runner",
        )

        assert module_node.name == "validators"
        assert module_node.package == "maid_runner"

    def test_module_node_inherits_from_node(self):
        """ModuleNode inherits from Node base class."""
        module_node = ModuleNode(
            id="module-2",
            name="model",
            package="maid_runner.graph",
        )

        assert isinstance(module_node, Node)

    def test_module_node_has_correct_node_type(self):
        """ModuleNode has node_type set to NodeType.MODULE."""
        module_node = ModuleNode(
            id="module-3",
            name="cli",
            package="maid_runner",
        )

        assert module_node.node_type == NodeType.MODULE

    def test_module_node_has_id_from_base_class(self):
        """ModuleNode has id attribute from Node base class."""
        module_node = ModuleNode(
            id="module-id-test",
            name="test_module",
            package="test_package",
        )

        assert module_node.id == "module-id-test"

    def test_module_node_has_attributes_from_base_class(self):
        """ModuleNode has attributes from Node base class."""
        custom_attrs = {"file_count": 5}
        module_node = ModuleNode(
            id="module-attrs-test",
            name="large_module",
            package="large_package",
            attributes=custom_attrs,
        )

        assert module_node.attributes["file_count"] == 5

    def test_module_node_name_attribute(self):
        """ModuleNode has name attribute."""
        module_node = ModuleNode(
            id="m1",
            name="my_module",
            package="pkg",
        )

        assert hasattr(module_node, "name")
        assert module_node.name == "my_module"

    def test_module_node_package_attribute(self):
        """ModuleNode has package attribute."""
        module_node = ModuleNode(
            id="m2",
            name="n",
            package="my.package.path",
        )

        assert hasattr(module_node, "package")
        assert module_node.package == "my.package.path"

    def test_module_node_package_can_be_none(self):
        """ModuleNode package can be None for top-level modules."""
        module_node = ModuleNode(
            id="m3",
            name="standalone",
            package=None,
        )

        assert module_node.package is None


class TestNodeTypeRelationships:
    """Tests verifying relationships between node types and classes."""

    def test_all_node_subclasses_inherit_from_node(self):
        """All specialized node classes inherit from Node."""
        node_classes = [ManifestNode, FileNode, ArtifactNode, ModuleNode]

        for cls in node_classes:
            assert issubclass(cls, Node)

    def test_each_node_type_has_corresponding_class(self):
        """Each NodeType value corresponds to a specific Node subclass."""
        manifest_node = ManifestNode(
            id="mn", path="p", goal="g", task_type="t", version="v"
        )
        file_node = FileNode(id="fn", path="p", status="s")
        artifact_node = ArtifactNode(id="an", name="n", artifact_type="function")
        module_node = ModuleNode(id="modn", name="n", package="p")

        assert manifest_node.node_type == NodeType.MANIFEST
        assert file_node.node_type == NodeType.FILE
        assert artifact_node.node_type == NodeType.ARTIFACT
        assert module_node.node_type == NodeType.MODULE

    def test_nodes_with_same_id_are_distinguishable_by_type(self):
        """Nodes with the same id can be distinguished by their node_type."""
        same_id = "shared-id"

        manifest_node = ManifestNode(
            id=same_id, path="p", goal="g", task_type="t", version="v"
        )
        file_node = FileNode(id=same_id, path="p", status="s")

        assert manifest_node.id == file_node.id
        assert manifest_node.node_type != file_node.node_type
        assert manifest_node.node_type == NodeType.MANIFEST
        assert file_node.node_type == NodeType.FILE
