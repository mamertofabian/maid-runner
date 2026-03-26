"""MAID Runner v2 core - validation engine, manifest loading, and result types.

Quick start:
    from maid_runner.core import validate, validate_all

    result = validate("manifests/add-auth.manifest.yaml")
    print(result.success)
"""

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

__all__ = [
    "validate",
    "validate_all",
    "ValidationEngine",
    "load_manifest",
    "save_manifest",
    "ManifestLoadError",
    "ManifestSchemaError",
    "ManifestChain",
    "ArtifactKind",
    "ArtifactSpec",
    "ArgSpec",
    "FileSpec",
    "FileMode",
    "DeleteSpec",
    "Manifest",
    "TaskType",
    "ValidationMode",
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
]
