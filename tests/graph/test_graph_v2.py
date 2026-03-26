"""Tests for v2 graph module - GraphBuilder and GraphQuery using v2 types."""

import pytest
import yaml

from maid_runner.core.chain import ManifestChain
from maid_runner.core.types import (
    ArtifactKind,
    ArtifactSpec,
    FileMode,
    FileSpec,
    Manifest,
    TaskType,
)
from maid_runner.graph.model import (
    EdgeType,
    NodeType,
)
from maid_runner.graph.builder import GraphBuilder
from maid_runner.graph.query import GraphQuery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(
    slug: str,
    files_create=(),
    files_edit=(),
    files_read=(),
    supersedes=(),
) -> Manifest:
    return Manifest(
        slug=slug,
        source_path=f"manifests/{slug}.manifest.yaml",
        goal=f"Goal for {slug}",
        validate_commands=(("pytest", "tests/", "-v"),),
        files_create=files_create,
        files_edit=files_edit,
        files_read=files_read,
        supersedes=supersedes,
        task_type=TaskType.FEATURE,
    )


def _make_file_spec(path, artifacts=(), mode=FileMode.CREATE):
    return FileSpec(path=path, artifacts=artifacts, mode=mode)


def _make_artifact(name, kind=ArtifactKind.FUNCTION, of=None, bases=()):
    return ArtifactSpec(kind=kind, name=name, of=of, bases=bases)


def _write_chain(tmp_path, manifests_data):
    """Write manifest YAML files and return ManifestChain."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    for slug, data in manifests_data.items():
        path = manifest_dir / f"{slug}.manifest.yaml"
        path.write_text(yaml.dump(data))
    return ManifestChain(manifest_dir, project_root=str(tmp_path))


# ---------------------------------------------------------------------------
# GraphBuilder
# ---------------------------------------------------------------------------


class TestGraphBuilder:
    def test_build_from_manifests(self):
        """Build a graph from explicit manifest list."""
        m = _make_manifest(
            "add-auth",
            files_create=(
                _make_file_spec(
                    "src/auth.py",
                    (
                        _make_artifact("AuthService", ArtifactKind.CLASS),
                        _make_artifact("login", ArtifactKind.METHOD, of="AuthService"),
                    ),
                ),
            ),
        )
        builder = GraphBuilder()
        graph = builder.build_from_manifests([m])

        assert graph.node_count > 0
        assert graph.edge_count > 0

        # Manifest node exists
        mn = graph.get_node("manifest:add-auth")
        assert mn is not None
        assert mn.node_type == NodeType.MANIFEST

        # File node
        fn = graph.get_node("file:src/auth.py")
        assert fn is not None
        assert fn.node_type == NodeType.FILE

        # Artifact nodes
        an = graph.get_node("artifact:src/auth.py:AuthService")
        assert an is not None
        assert an.node_type == NodeType.ARTIFACT

    def test_build_from_chain(self, tmp_path):
        """Build from ManifestChain."""
        data = {
            "add-feature": {
                "schema": "2",
                "goal": "Add feature",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/feature.py",
                            "artifacts": [{"kind": "function", "name": "do_it"}],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            }
        }
        chain = _write_chain(tmp_path, data)
        builder = GraphBuilder()
        graph = builder.build(chain)

        assert graph.get_node("file:src/feature.py") is not None
        assert graph.get_node("artifact:src/feature.py:do_it") is not None

    def test_supersession_edges(self):
        """Supersession relationships create SUPERSEDES edges."""
        m1 = _make_manifest("old-auth")
        m2 = _make_manifest("new-auth", supersedes=("old-auth",))

        builder = GraphBuilder()
        graph = builder.build_from_manifests([m1, m2])

        # Check for supersedes edge
        edges = graph.get_edges("manifest:new-auth", EdgeType.SUPERSEDES)
        supersedes_targets = [e.target_id for e in edges]
        assert "manifest:old-auth" in supersedes_targets

    def test_file_operation_edges(self):
        """CREATES, EDITS, READS edges are created."""
        m = _make_manifest(
            "mixed-ops",
            files_create=(_make_file_spec("src/new.py"),),
            files_edit=(_make_file_spec("src/existing.py", mode=FileMode.EDIT),),
            files_read=("src/deps.py",),
        )
        builder = GraphBuilder()
        graph = builder.build_from_manifests([m])

        creates = [e for e in graph.edges if e.edge_type == EdgeType.CREATES]
        edits = [e for e in graph.edges if e.edge_type == EdgeType.EDITS]
        reads = [e for e in graph.edges if e.edge_type == EdgeType.READS]

        assert len(creates) >= 1
        assert len(edits) >= 1
        assert len(reads) >= 1

    def test_artifact_edges(self):
        """DEFINES, DECLARES, BELONGS_TO edges for artifacts."""
        m = _make_manifest(
            "add-func",
            files_create=(_make_file_spec("src/svc.py", (_make_artifact("my_func"),)),),
        )
        builder = GraphBuilder()
        graph = builder.build_from_manifests([m])

        # DECLARES: manifest -> artifact
        declares = [e for e in graph.edges if e.edge_type == EdgeType.DECLARES]
        assert any(e.target_id == "artifact:src/svc.py:my_func" for e in declares)

        # DEFINES: file -> artifact
        defines = [e for e in graph.edges if e.edge_type == EdgeType.DEFINES]
        assert any(
            e.source_id == "file:src/svc.py"
            and e.target_id == "artifact:src/svc.py:my_func"
            for e in defines
        )

    def test_module_nodes_derived(self):
        """Module nodes are derived from file paths."""
        m = _make_manifest(
            "add-mod",
            files_create=(
                _make_file_spec("src/auth/service.py", (_make_artifact("svc"),)),
            ),
        )
        builder = GraphBuilder()
        graph = builder.build_from_manifests([m])

        module_node = graph.get_node("module:src/auth")
        assert module_node is not None
        assert module_node.node_type == NodeType.MODULE

    def test_duplicate_nodes_handled(self):
        """Same file referenced by multiple manifests doesn't crash."""
        m1 = _make_manifest(
            "m1",
            files_create=(_make_file_spec("src/shared.py", (_make_artifact("f1"),)),),
        )
        m2 = _make_manifest(
            "m2",
            files_edit=(
                _make_file_spec(
                    "src/shared.py", (_make_artifact("f2"),), mode=FileMode.EDIT
                ),
            ),
        )
        builder = GraphBuilder()
        graph = builder.build_from_manifests([m1, m2])

        # File node should exist once
        file_node = graph.get_node("file:src/shared.py")
        assert file_node is not None


# ---------------------------------------------------------------------------
# GraphQuery
# ---------------------------------------------------------------------------


class TestGraphQuery:
    @pytest.fixture
    def sample_graph(self):
        """Build a graph with multiple manifests for query testing."""
        m1 = _make_manifest(
            "add-service",
            files_create=(
                _make_file_spec(
                    "src/service.py",
                    (
                        _make_artifact("ServiceClass", ArtifactKind.CLASS),
                        _make_artifact(
                            "process", ArtifactKind.METHOD, of="ServiceClass"
                        ),
                    ),
                ),
            ),
        )
        m2 = _make_manifest(
            "add-repo",
            files_create=(
                _make_file_spec(
                    "src/repo.py", (_make_artifact("RepoClass", ArtifactKind.CLASS),)
                ),
            ),
            files_read=("src/service.py",),
        )
        builder = GraphBuilder()
        return builder.build_from_manifests([m1, m2])

    def test_find_node(self, sample_graph):
        q = GraphQuery(sample_graph)
        node = q.find_node("ServiceClass", NodeType.ARTIFACT)
        assert node is not None

    def test_find_nodes_pattern(self, sample_graph):
        q = GraphQuery(sample_graph)
        nodes = q.find_nodes("*Class", NodeType.ARTIFACT)
        assert len(nodes) >= 2

    def test_get_dependents(self, sample_graph):
        q = GraphQuery(sample_graph)
        deps = q.get_dependents("artifact:src/service.py:ServiceClass")
        # Should include manifest and file that reference it
        assert len(deps) >= 1

    def test_get_dependencies(self, sample_graph):
        q = GraphQuery(sample_graph)
        deps = q.get_dependencies("artifact:src/service.py:process")
        # Should include file and class
        assert len(deps) >= 1

    def test_find_cycles(self, sample_graph):
        """Graph may have structural cycles from bidirectional edges (DEFINES/BELONGS_TO)."""
        q = GraphQuery(sample_graph)
        # The v2 graph intentionally has DEFINES (file->artifact) and
        # BELONGS_TO (artifact->file) edges, which form structural cycles.
        # This is expected - cycle detection works correctly.
        cycles = q.find_cycles()
        assert isinstance(cycles, list)

    def test_dependency_analysis(self, sample_graph):
        q = GraphQuery(sample_graph)
        result = q.dependency_analysis("src/service.py")
        assert result["file"] == "src/service.py"
        assert "manifests" in result
        assert "artifacts" in result

    def test_impact_analysis(self, sample_graph):
        q = GraphQuery(sample_graph)
        result = q.impact_analysis("ServiceClass")
        assert "artifact" in result
        assert "manifests" in result

    def test_query_find_definition(self, sample_graph):
        """query('What defines ServiceClass?') -> finds the artifact."""
        q = GraphQuery(sample_graph)
        result = q.query("What defines ServiceClass?")
        assert result["query_type"] == "find_definition"
        assert result["results"] is not None

    def test_query_find_cycles(self, sample_graph):
        """query('Find circular dependencies') -> runs cycle detection."""
        q = GraphQuery(sample_graph)
        result = q.query("Find circular dependencies")
        assert result["query_type"] == "find_cycles"
        assert "results" in result
        assert "summary" in result

    def test_query_returns_dict_with_required_keys(self, sample_graph):
        """query() returns dict with query_type, results, summary."""
        q = GraphQuery(sample_graph)
        result = q.query("What depends on ServiceClass?")
        assert "query_type" in result
        assert "results" in result
        assert "summary" in result


# ---------------------------------------------------------------------------
# Export integration (v2 graph exports cleanly)
# ---------------------------------------------------------------------------


class TestGraphExport:
    def test_export_json_roundtrip(self):
        """Graph can be exported to JSON dict."""
        from maid_runner.graph.exporters import graph_to_dict

        m = _make_manifest(
            "test",
            files_create=(_make_file_spec("src/x.py", (_make_artifact("fn"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])
        d = graph_to_dict(graph)
        assert "nodes" in d
        assert "edges" in d
        assert len(d["nodes"]) > 0
