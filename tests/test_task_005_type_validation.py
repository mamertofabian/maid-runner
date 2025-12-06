"""
Behavioral tests for Task-005: Type Validation functionality.
These tests USE the type validation functions to verify they work correctly.

This file serves as the main entry point that imports and re-exports all test classes
from the split test files. This ensures all tests run when executed via MAID manifests
that reference this file.

When pytest runs this file, it will discover all test classes defined here,
which are imported from the split files.
"""

# Import all test modules to ensure they're loaded
# Note: Files are prefixed with _ to prevent pytest from discovering them directly
import tests._test_task_005_type_validation_validate_type_hints  # noqa: F401
import tests._test_task_005_type_validation_extract_annotation  # noqa: F401
import tests._test_task_005_type_validation_compare_types  # noqa: F401
import tests._test_task_005_type_validation_normalize  # noqa: F401
import tests._test_task_005_type_validation_artifact_collector  # noqa: F401
import tests._test_task_005_type_validation_error_messages  # noqa: F401
import tests._test_task_005_type_validation_integration  # noqa: F401

# Import and re-export all test classes so pytest discovers them in this file's namespace
from tests._test_task_005_type_validation_validate_type_hints import (  # noqa: F401
    TestValidateTypeHints,
)
from tests._test_task_005_type_validation_extract_annotation import (  # noqa: F401
    TestExtractTypeAnnotation,
)
from tests._test_task_005_type_validation_compare_types import (  # noqa: F401
    TestCompareTypes,
)
from tests._test_task_005_type_validation_normalize import (  # noqa: F401
    TestNormalizeTypeString,
)
from tests._test_task_005_type_validation_artifact_collector import (  # noqa: F401
    TestArtifactCollectorAttributes,
)
from tests._test_task_005_type_validation_error_messages import (  # noqa: F401
    TestErrorMessageConsistency,
)
from tests._test_task_005_type_validation_integration import (  # noqa: F401
    TestIntegrationScenarios,
)
