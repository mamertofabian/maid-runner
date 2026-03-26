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

# --- Core API ---
from maid_runner.core.validate import validate, validate_all, ValidationEngine
from maid_runner.core.manifest import (
    load_manifest,
    save_manifest,
    ManifestLoadError,
    ManifestSchemaError,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.snapshot import generate_snapshot
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

# --- Graph & Coherence ---
from maid_runner.graph import (
    KnowledgeGraph,
    NodeType,
    EdgeType,
)
from maid_runner.coherence import CoherenceEngine, CoherenceResult

__all__ = [
    # Version
    "__version__",
    # Convenience functions
    "validate",
    "validate_all",
    "generate_snapshot",
    # Core classes
    "ValidationEngine",
    "load_manifest",
    "save_manifest",
    "ManifestChain",
    # Types
    "ArtifactKind",
    "ArtifactSpec",
    "ArgSpec",
    "FileSpec",
    "FileMode",
    "DeleteSpec",
    "Manifest",
    "TaskType",
    "ValidationMode",
    # Results
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
    # Validators
    "ValidatorRegistry",
    "UnsupportedLanguageError",
    "BaseValidator",
    "FoundArtifact",
    "CollectionResult",
    # Exceptions
    "ManifestLoadError",
    "ManifestSchemaError",
    # Graph
    "KnowledgeGraph",
    "NodeType",
    "EdgeType",
    # Coherence
    "CoherenceEngine",
    "CoherenceResult",
]
