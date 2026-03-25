"""MAID Runner - Manifest-driven AI Development validation framework.

Library API for validating code artifacts against manifest specifications.

Quick start:
    from maid_runner import validate, validate_all

    # Validate a single manifest
    result = validate("manifests/add-auth.manifest.yaml")
    print(result.success)  # True/False

    # Validate all manifests in a directory
    batch = validate_all("manifests/")
    print(f"{batch.passed}/{batch.total_manifests} passed")
"""

from maid_runner.__version__ import __version__

# --- v1 API (preserved until Phase 7) ---
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
from maid_runner import coherence

# --- v2 API ---
from maid_runner.core.validate import validate, validate_all, ValidationEngine
from maid_runner.core.manifest import (
    load_manifest,
    save_manifest,
    ManifestLoadError,
    ManifestSchemaError,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.types import (
    ArtifactKind,
    ArtifactSpec,
    ArgSpec,
    FileSpec,
    FileMode,
    DeleteSpec,
    Manifest,
    TaskType,
    ValidationMode,
)
from maid_runner.core.result import (
    ValidationResult,
    BatchValidationResult,
    ValidationError,
    ErrorCode,
    Severity,
    Location,
    FileTrackingReport,
    FileTrackingStatus,
    FileTrackingEntry,
    TestRunResult,
    BatchTestResult,
)
from maid_runner.validators.registry import ValidatorRegistry, UnsupportedLanguageError
from maid_runner.validators.base import BaseValidator, FoundArtifact, CollectionResult

# Explicit re-exports for MAID validation
KnowledgeGraph = KnowledgeGraph
KnowledgeGraphBuilder = KnowledgeGraphBuilder
NodeType = NodeType
EdgeType = EdgeType
coherence = coherence

__all__ = [
    # Version
    "__version__",
    # v1 API (preserved until Phase 7)
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
    "coherence",
    # v2 convenience functions
    "validate",
    "validate_all",
    # v2 core classes
    "ValidationEngine",
    "load_manifest",
    "save_manifest",
    "ManifestChain",
    # v2 types
    "ArtifactKind",
    "ArtifactSpec",
    "ArgSpec",
    "FileSpec",
    "FileMode",
    "DeleteSpec",
    "Manifest",
    "TaskType",
    "ValidationMode",
    # v2 results
    "ValidationResult",
    "BatchValidationResult",
    "ValidationError",
    "ErrorCode",
    "Severity",
    "Location",
    "FileTrackingReport",
    "FileTrackingStatus",
    "FileTrackingEntry",
    "TestRunResult",
    "BatchTestResult",
    # v2 validators
    "ValidatorRegistry",
    "UnsupportedLanguageError",
    "BaseValidator",
    "FoundArtifact",
    "CollectionResult",
    # v2 exceptions
    "ManifestLoadError",
    "ManifestSchemaError",
]
