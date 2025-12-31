"""Builder module for constructing knowledge graphs from MAID manifests."""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from maid_runner.cli.snapshot_system import discover_active_manifests
from maid_runner.graph.model import (
    KnowledgeGraph,
    ManifestNode,
    FileNode,
    ArtifactNode,
    ModuleNode,
    Edge,
    EdgeType,
    MANIFEST_PREFIX,
    FILE_PREFIX,
    ARTIFACT_PREFIX,
    MODULE_PREFIX,
    EDGE_PREFIX,
)


def load_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load and parse a single manifest JSON file.

    Args:
        manifest_path: Path to the manifest file

    Returns:
        Dict containing the parsed manifest data

    Raises:
        FileNotFoundError: If the manifest file doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    with open(manifest_path, "r") as f:
        return json.load(f)


def load_manifests(manifest_dir: Path) -> List[Dict[str, Any]]:
    """Load all active manifests from a directory.

    Uses discover_active_manifests to find non-superseded manifests,
    then loads and parses each one.

    Args:
        manifest_dir: Path to the manifests directory

    Returns:
        List of parsed manifest dictionaries in chronological order
    """
    active_paths = discover_active_manifests(manifest_dir)
    manifests = []
    for path in active_paths:
        try:
            manifests.append(load_manifest(path))
        except (json.JSONDecodeError, FileNotFoundError):
            # Skip invalid manifests
            continue
    return manifests


def create_manifest_node(manifest_data: Dict[str, Any], path: Path) -> ManifestNode:
    """Create a ManifestNode from manifest data.

    Args:
        manifest_data: Parsed manifest dictionary
        path: Path to the manifest file

    Returns:
        ManifestNode with extracted fields and unique ID
    """
    node_id = f"{MANIFEST_PREFIX}{path}"
    return ManifestNode(
        id=node_id,
        path=str(path),
        goal=manifest_data.get("goal", ""),
        task_type=manifest_data.get("taskType", ""),
        version=manifest_data.get("version", "1"),
    )


def create_file_node(file_path: str, status: str = "unknown") -> FileNode:
    """Create a FileNode from a file path.

    Args:
        file_path: Path to the source file
        status: File status (creatable, editable, readonly, or unknown)

    Returns:
        FileNode with unique ID derived from path
    """
    node_id = f"{FILE_PREFIX}{file_path}"
    return FileNode(
        id=node_id,
        path=file_path,
        status=status,
    )


def create_artifact_node(artifact: Dict[str, Any], file_path: str) -> ArtifactNode:
    """Create an ArtifactNode from artifact data.

    Args:
        artifact: Artifact dictionary from manifest's expectedArtifacts.contains
        file_path: Path to the file containing the artifact

    Returns:
        ArtifactNode with extracted fields and unique ID
    """
    name = artifact.get("name", "")
    artifact_type = artifact.get("type", "")
    parent_class = artifact.get("class")

    # Use signature from artifact if present, otherwise generate from args/returns
    signature = artifact.get("signature")
    if signature is None and ("args" in artifact or "returns" in artifact):
        args = artifact.get("args", [])
        arg_str = ", ".join(
            f"{a.get('name', '')}: {a.get('type', 'Any')}" for a in args
        )
        returns = artifact.get("returns", "None")
        signature = f"({arg_str}) -> {returns}"

    node_id = f"{ARTIFACT_PREFIX}{file_path}:{name}"
    return ArtifactNode(
        id=node_id,
        name=name,
        artifact_type=artifact_type,
        signature=signature,
        parent_class=parent_class,
    )


def create_module_node(file_path: str) -> ModuleNode:
    """Create a ModuleNode from a file path.

    Args:
        file_path: Path to the Python file

    Returns:
        ModuleNode with module name and package derived from path
    """
    path_obj = Path(file_path)
    module_name = path_obj.stem

    # Derive package from parent directories
    parts = path_obj.parts[:-1]
    package = ".".join(parts) if parts else None

    node_id = f"{MODULE_PREFIX}{file_path}"
    return ModuleNode(
        id=node_id,
        name=module_name,
        package=package,
    )


def create_supersedes_edges(
    manifest_data: Dict[str, Any],
    manifest_node: ManifestNode,
    known_manifest_ids: Optional[set] = None,
) -> List[Edge]:
    """Create SUPERSEDES edges from a manifest to its superseded manifests.

    Args:
        manifest_data: Parsed manifest dictionary
        manifest_node: The manifest node that supersedes others
        known_manifest_ids: Optional set of known manifest node IDs for validation.
                           If provided, edges to unknown manifests are skipped.

    Returns:
        List of Edge objects with type SUPERSEDES
    """
    edges = []
    supersedes = manifest_data.get("supersedes", [])
    for superseded_path in supersedes:
        target_id = f"{MANIFEST_PREFIX}{superseded_path}"
        # Skip edges to unknown manifests if validation is enabled
        if known_manifest_ids is not None and target_id not in known_manifest_ids:
            continue
        edge = Edge(
            id=f"{EDGE_PREFIX}{uuid.uuid4()}",
            edge_type=EdgeType.SUPERSEDES,
            source_id=manifest_node.id,
            target_id=target_id,
        )
        edges.append(edge)
    return edges


def create_file_edges(
    manifest_data: Dict[str, Any], manifest_node: ManifestNode
) -> List[Edge]:
    """Create file-related edges from a manifest.

    Creates:
    - CREATES edges for creatableFiles
    - EDITS edges for editableFiles
    - READS edges for readonlyFiles

    Args:
        manifest_data: Parsed manifest dictionary
        manifest_node: The manifest node

    Returns:
        List of Edge objects for file relationships
    """
    edges = []

    # Map file categories to edge types
    file_mappings = [
        ("creatableFiles", EdgeType.CREATES),
        ("editableFiles", EdgeType.EDITS),
        ("readonlyFiles", EdgeType.READS),
    ]

    for field, edge_type in file_mappings:
        files = manifest_data.get(field, [])
        for file_path in files:
            edge = Edge(
                id=f"{EDGE_PREFIX}{uuid.uuid4()}",
                edge_type=edge_type,
                source_id=manifest_node.id,
                target_id=f"{FILE_PREFIX}{file_path}",
            )
            edges.append(edge)

    return edges


def create_artifact_edges(
    artifact: Dict[str, Any], file_path: str, manifest_node: ManifestNode
) -> List[Edge]:
    """Create artifact-related edges.

    Creates:
    - DEFINES edge from file to artifact
    - DECLARES edge from manifest to artifact
    - CONTAINS edge if artifact has parent class

    Args:
        artifact: Artifact dictionary from manifest
        file_path: Path to the file containing the artifact
        manifest_node: The manifest node declaring the artifact

    Returns:
        List of Edge objects for artifact relationships
    """
    edges = []
    artifact_name = artifact.get("name", "")
    artifact_id = f"{ARTIFACT_PREFIX}{file_path}:{artifact_name}"
    file_id = f"{FILE_PREFIX}{file_path}"

    # DEFINES: file -> artifact
    edges.append(
        Edge(
            id=f"{EDGE_PREFIX}{uuid.uuid4()}",
            edge_type=EdgeType.DEFINES,
            source_id=file_id,
            target_id=artifact_id,
        )
    )

    # DECLARES: manifest -> artifact
    edges.append(
        Edge(
            id=f"{EDGE_PREFIX}{uuid.uuid4()}",
            edge_type=EdgeType.DECLARES,
            source_id=manifest_node.id,
            target_id=artifact_id,
        )
    )

    # CONTAINS: parent class -> artifact (if has parent class)
    parent_class = artifact.get("class")
    if parent_class:
        parent_id = f"{ARTIFACT_PREFIX}{file_path}:{parent_class}"
        edges.append(
            Edge(
                id=f"{EDGE_PREFIX}{uuid.uuid4()}",
                edge_type=EdgeType.CONTAINS,
                source_id=parent_id,
                target_id=artifact_id,
            )
        )

    return edges


class KnowledgeGraphBuilder:
    """Builder class that orchestrates knowledge graph construction from manifests."""

    def __init__(self, manifest_dir: Path) -> None:
        """Initialize the builder with a manifest directory.

        Args:
            manifest_dir: Path to the directory containing manifest files
        """
        self.manifest_dir = manifest_dir
        self._graph = KnowledgeGraph()

    def build(self) -> KnowledgeGraph:
        """Build and return the complete knowledge graph.

        Loads all active manifests, processes each one to create nodes and edges,
        and returns the populated knowledge graph.

        Returns:
            KnowledgeGraph containing all nodes and edges
        """
        # Reset graph for fresh build
        self._graph = KnowledgeGraph()

        manifests = load_manifests(self.manifest_dir)

        # Get manifest paths for correlation
        manifest_paths = discover_active_manifests(self.manifest_dir)

        # Build set of ALL manifest IDs for edge validation (including superseded)
        # This allows supersedes edges to reference superseded manifests
        all_manifest_files = list(self.manifest_dir.glob("*.manifest.json"))
        known_manifest_ids = {f"{MANIFEST_PREFIX}{path}" for path in all_manifest_files}

        for manifest_data, path in zip(manifests, manifest_paths):
            self._process_manifest(manifest_data, path, known_manifest_ids)

        return self._graph

    def _process_manifest(
        self,
        manifest_data: Dict[str, Any],
        path: Path,
        known_manifest_ids: Optional[set] = None,
    ) -> None:
        """Process a single manifest, creating nodes and edges.

        Args:
            manifest_data: Parsed manifest dictionary
            path: Path to the manifest file
            known_manifest_ids: Optional set of known manifest IDs for edge validation
        """
        # Create manifest node
        manifest_node = create_manifest_node(manifest_data, path)
        self._graph.add_node(manifest_node)

        # Create file nodes and edges
        # Map file category to status
        category_to_status = {
            "creatableFiles": "creatable",
            "editableFiles": "editable",
            "readonlyFiles": "readonly",
        }
        for file_category in ["creatableFiles", "editableFiles", "readonlyFiles"]:
            status = category_to_status[file_category]
            for file_path in manifest_data.get(file_category, []):
                file_node = create_file_node(file_path, status)
                self._graph.add_node(file_node)

                # Create module node for each file
                module_node = create_module_node(file_path)
                self._graph.add_node(module_node)

        # Create file edges
        file_edges = create_file_edges(manifest_data, manifest_node)
        for edge in file_edges:
            self._graph.add_edge(edge)

        # Create supersedes edges (with validation if known_manifest_ids provided)
        supersedes_edges = create_supersedes_edges(
            manifest_data, manifest_node, known_manifest_ids
        )
        for edge in supersedes_edges:
            self._graph.add_edge(edge)

        # Process artifacts
        for artifact, file_path in self._extract_artifacts(manifest_data):
            artifact_node = create_artifact_node(artifact, file_path)
            self._graph.add_node(artifact_node)

            artifact_edges = create_artifact_edges(artifact, file_path, manifest_node)
            for edge in artifact_edges:
                self._graph.add_edge(edge)

    def _extract_artifacts(
        self, manifest_data: Dict[str, Any]
    ) -> List[Tuple[Dict[str, Any], str]]:
        """Extract artifact data from manifest's expectedArtifacts.

        Args:
            manifest_data: Parsed manifest dictionary

        Returns:
            List of (artifact_dict, file_path) tuples
        """
        result: List[Tuple[Dict[str, Any], str]] = []
        expected = manifest_data.get("expectedArtifacts")
        if expected:
            file_path = expected.get("file", "")
            for artifact in expected.get("contains", []):
                result.append((artifact, file_path))
        return result
