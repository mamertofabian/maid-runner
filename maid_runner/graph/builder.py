"""V2-compatible graph builder using Manifest/ManifestChain types.

Coexists with the v1 builder module - both remain importable until Phase 7.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from maid_runner.core.chain import ManifestChain
from maid_runner.core.types import (
    ArtifactSpec,
    FileMode,
    FileSpec,
    Manifest,
)
from maid_runner.graph.model import (
    ArtifactNode,
    Edge,
    EdgeType,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
    ModuleNode,
    ARTIFACT_PREFIX,
    EDGE_PREFIX,
    FILE_PREFIX,
    MANIFEST_PREFIX,
    MODULE_PREFIX,
)


class GraphBuilder:
    """Constructs a KnowledgeGraph from v2 Manifest/ManifestChain objects."""

    def build(self, chain: ManifestChain) -> KnowledgeGraph:
        """Build knowledge graph from a ManifestChain."""
        return self.build_from_manifests(chain.active_manifests())

    def build_from_manifests(self, manifests: list[Manifest]) -> KnowledgeGraph:
        """Build graph from an explicit list of Manifest objects."""
        graph = KnowledgeGraph()
        known_slugs = {m.slug for m in manifests}

        for m in manifests:
            self._process_manifest(graph, m, known_slugs)

        return graph

    def _process_manifest(
        self,
        graph: KnowledgeGraph,
        manifest: Manifest,
        known_slugs: set[str],
    ) -> None:
        manifest_id = f"{MANIFEST_PREFIX}{manifest.slug}"

        # Create manifest node
        manifest_node = ManifestNode(
            id=manifest_id,
            path=manifest.source_path,
            goal=manifest.goal,
            task_type=manifest.task_type.value if manifest.task_type else "",
            version=manifest.schema_version,
        )
        graph.add_node(manifest_node)

        # Supersession edges
        for slug in manifest.supersedes:
            target_id = f"{MANIFEST_PREFIX}{slug}"
            if slug in known_slugs:
                graph.add_edge(_edge(EdgeType.SUPERSEDES, manifest_id, target_id))

        # Create file specs
        for fs in manifest.files_create:
            self._process_file_spec(graph, manifest_id, fs, EdgeType.CREATES)

        for fs in manifest.files_edit:
            self._process_file_spec(graph, manifest_id, fs, EdgeType.EDITS)

        for fs in manifest.files_snapshot:
            self._process_file_spec(graph, manifest_id, fs, EdgeType.CREATES)

        # Read files
        for path in manifest.files_read:
            file_id = f"{FILE_PREFIX}{path}"
            _ensure_file_node(graph, file_id, path, "readonly")
            graph.add_edge(_edge(EdgeType.READS, manifest_id, file_id))

        # Delete files
        for ds in manifest.files_delete:
            file_id = f"{FILE_PREFIX}{ds.path}"
            _ensure_file_node(graph, file_id, ds.path, "deleted")
            graph.add_edge(
                _edge(EdgeType.DEFINES, manifest_id, file_id)
            )  # Could use DELETES if EdgeType supported

    def _process_file_spec(
        self,
        graph: KnowledgeGraph,
        manifest_id: str,
        fs: FileSpec,
        edge_type: EdgeType,
    ) -> None:
        file_id = f"{FILE_PREFIX}{fs.path}"
        status = "creatable" if fs.mode == FileMode.CREATE else "editable"
        _ensure_file_node(graph, file_id, fs.path, status)

        graph.add_edge(_edge(edge_type, manifest_id, file_id))

        # Module node
        _ensure_module_node(graph, fs.path)

        # Artifacts
        for artifact in fs.artifacts:
            self._process_artifact(graph, manifest_id, file_id, fs.path, artifact)

    def _process_artifact(
        self,
        graph: KnowledgeGraph,
        manifest_id: str,
        file_id: str,
        file_path: str,
        artifact: ArtifactSpec,
    ) -> None:
        art_id = f"{ARTIFACT_PREFIX}{file_path}:{artifact.name}"

        if graph.get_node(art_id) is None:
            node = ArtifactNode(
                id=art_id,
                name=artifact.name,
                artifact_type=artifact.kind.value,
                signature=_build_signature(artifact),
                parent_class=artifact.of,
            )
            graph.add_node(node)

        # DEFINES: file -> artifact
        graph.add_edge(_edge(EdgeType.DEFINES, file_id, art_id))
        # DECLARES: manifest -> artifact
        graph.add_edge(_edge(EdgeType.DECLARES, manifest_id, art_id))
        # BELONGS_TO: artifact -> file
        graph.add_edge(_edge(EdgeType.BELONGS_TO, art_id, file_id))

        # CONTAINS: parent class -> artifact (for methods/attributes)
        if artifact.of:
            parent_id = f"{ARTIFACT_PREFIX}{file_path}:{artifact.of}"
            graph.add_edge(_edge(EdgeType.CONTAINS, parent_id, art_id))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _edge(edge_type: EdgeType, source: str, target: str) -> Edge:
    return Edge(
        id=f"{EDGE_PREFIX}{uuid.uuid4()}",
        edge_type=edge_type,
        source_id=source,
        target_id=target,
    )


def _ensure_file_node(
    graph: KnowledgeGraph, file_id: str, path: str, status: str
) -> None:
    if graph.get_node(file_id) is None:
        graph.add_node(FileNode(id=file_id, path=path, status=status))


def _ensure_module_node(graph: KnowledgeGraph, file_path: str) -> None:
    p = Path(file_path)
    parts = list(p.parent.parts)
    if not parts or parts == ["."]:
        return

    module_path = str(p.parent)
    module_id = f"{MODULE_PREFIX}{module_path}"
    if graph.get_node(module_id) is None:
        graph.add_node(
            ModuleNode(
                id=module_id,
                name=p.parent.name,
                package=".".join(parts[:-1]) if len(parts) > 1 else None,
            )
        )


def _build_signature(artifact: ArtifactSpec) -> Optional[str]:
    if not artifact.args and not artifact.returns:
        return None
    arg_str = ", ".join(
        f"{a.name}: {a.type}" if a.type else a.name for a in artifact.args
    )
    sig = f"({arg_str})"
    if artifact.returns:
        sig += f" -> {artifact.returns}"
    return sig
