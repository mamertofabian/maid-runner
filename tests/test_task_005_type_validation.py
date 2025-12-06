"""
Behavioral tests for Task-005: Type Validation functionality.
These tests USE the type validation functions to verify they work correctly.

This file serves as the main entry point that imports and re-exports all test classes
from the split test files. This ensures all tests run when executed via MAID manifests
that reference this file.

When pytest runs this file, it will discover all test classes defined here,
which are imported from the split files.
"""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import and re-export all test classes so pytest discovers them in this file's namespace
from tests._test_task_005_type_validation._test_task_005_type_validation_validate_type_hints import (  # noqa: F401
    TestValidateTypeHints,
)
from tests._test_task_005_type_validation._test_task_005_type_validation_extract_annotation import (  # noqa: F401
    TestExtractTypeAnnotation,
)
from tests._test_task_005_type_validation._test_task_005_type_validation_compare_types import (  # noqa: F401
    TestCompareTypes,
)
from tests._test_task_005_type_validation._test_task_005_type_validation_normalize import (  # noqa: F401
    TestNormalizeTypeString,
)
from tests._test_task_005_type_validation._test_task_005_type_validation_artifact_collector import (  # noqa: F401
    TestArtifactCollectorAttributes,
)
from tests._test_task_005_type_validation._test_task_005_type_validation_error_messages import (  # noqa: F401
    TestErrorMessageConsistency,
)
from tests._test_task_005_type_validation._test_task_005_type_validation_integration import (  # noqa: F401
    TestIntegrationScenarios,
)
