"""Legacy compatibility anchors for maid_runner.core.validate contracts.

Executable ValidationEngine coverage now lives in focused tests under
tests/core/validation/.
"""

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import FileSpec
from maid_runner.core.validate import (
    ValidationEngine,
    validate,
    validate_all,
)

# Historical active manifests still read this legacy file for these method
# references. Executable assertions live in focused validation suites.
_VALIDATION_ENGINE_PUBLIC_METHODS = (
    ValidationEngine.validate,
    ValidationEngine.validate_behavioral,
    ValidationEngine.validate_acceptance,
    ValidationEngine.validate_implementation,
)
_LEGACY_MANIFEST_REFERENCE_ANCHORS = (
    ManifestChain,
    ValidationEngine.run_file_tracking,
    validate,
    validate_all,
    ErrorCode.STUB_FUNCTION_DETECTED,
    ErrorCode.MISSING_REQUIRED_IMPORT,
    ErrorCode.VALIDATOR_NOT_AVAILABLE,
    ErrorCode.NO_TEST_FILES,
    FileSpec.imports,
)


class TestStubDetection:
    """Compatibility class for manifests that record retired stub tests."""
