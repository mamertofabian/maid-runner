"""MAID Runner - Manifest-driven AI Development validation framework."""

from maid_runner.__version__ import __version__
from maid_runner.validators import (
    AlignmentError,
    collect_behavioral_artifacts,
    discover_related_manifests,
    validate_schema,
    validate_with_ast,
)
from maid_runner.cli.snapshot import generate_snapshot
from maid_runner.graph import (
    KnowledgeGraph,
    KnowledgeGraphBuilder,
    NodeType,
    EdgeType,
)

# Explicit re-exports for MAID validation
# These assignments make imported names visible as module-level attributes
KnowledgeGraph = KnowledgeGraph
KnowledgeGraphBuilder = KnowledgeGraphBuilder
NodeType = NodeType
EdgeType = EdgeType

__all__ = [
    "__version__",
    "AlignmentError",
    "collect_behavioral_artifacts",
    "discover_related_manifests",
    "validate_schema",
    "validate_with_ast",
    "generate_snapshot",
    "KnowledgeGraph",
    "KnowledgeGraphBuilder",
    "NodeType",
    "EdgeType",
]
