"""Comprehensive behavioral tests for Task-053: Production-ready TypeScriptValidator.

This test suite validates all 36 expected artifacts in the manifest, ensuring complete
coverage of TypeScript/JavaScript language features using tree-sitter AST parsing.

Test Organization:
- Basic validator structure and interface compliance
- Core TypeScript declarations (classes, interfaces, type aliases, enums, namespaces)
- Functions (regular, arrow, async, generic)
- Methods (regular, static, private, async, getters/setters, abstract)
- Parameters (required, optional, rest, destructured, parameter properties)
- Advanced features (decorators, generics, abstract classes, access modifiers)
- JSX/TSX support for React
- Behavioral validation (class/function/method usage)
- Edge cases and real-world patterns
- Artifact structure consistency

This file serves as the main entry point that imports and re-exports all test classes
from the split test files. This ensures all tests run when executed via MAID manifests
that reference this file.

When pytest runs this file, it will discover all test classes defined here,
which are imported from the split files.
"""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import private test modules for task-053 private artifacts
from tests._test_task_053_private_helpers import (  # noqa: F401
    TestTypeScriptValidatorInit,
    TestParseTypeScriptFile,
    TestCollectImplementationArtifacts,
    TestCollectBehavioralArtifacts,
    TestTraverseTree,
    TestGetNodeText,
    TestExtractIdentifier,
    TestExtractClasses,
    TestExtractInterfaces,
    TestExtractTypeAliases,
    TestExtractEnums,
    TestExtractNamespaces,
    TestExtractFunctions,
    TestExtractArrowFunctions,
    TestExtractMethods,
    TestExtractParameters,
    TestExtractClassBases,
    TestIsExported,
    TestExtractClassUsage,
    TestExtractFunctionCalls,
    TestExtractMethodCalls,
    TestGetClassNameFromNode,
    TestGetFunctionNameFromNode,
    TestFindClassMethods,
    TestIsAbstractClass,
    TestIsStaticMethod,
    TestHasDecorator,
    TestIsGetterOrSetter,
    TestIsAsync,
    TestHandleOptionalParameter,
    TestHandleRestParameter,
    TestHandleDestructuredParameter,
    TestGetLanguageForFile,
)

# Import and re-export all test classes so pytest discovers them in this file's namespace
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_validator_structure import (  # noqa: F401
    TestValidatorStructure,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_file_extension_support import (  # noqa: F401
    TestFileExtensionSupport,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_parser_initialization import (  # noqa: F401
    TestParserInitialization,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_class_detection import (  # noqa: F401
    TestClassDetection,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_interface_detection import (  # noqa: F401
    TestInterfaceDetection,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_type_alias_detection import (  # noqa: F401
    TestTypeAliasDetection,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_enum_detection import (  # noqa: F401
    TestEnumDetection,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_namespace_detection import (  # noqa: F401
    TestNamespaceDetection,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_function_detection import (  # noqa: F401
    TestFunctionDetection,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_parameter_detection import (  # noqa: F401
    TestParameterDetection,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_method_detection import (  # noqa: F401
    TestMethodDetection,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_parameter_properties import (  # noqa: F401
    TestParameterProperties,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_behavioral_validation import (  # noqa: F401
    TestBehavioralValidation,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_jsx_tsx_support import (  # noqa: F401
    TestJSXTSXSupport,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_advanced_features import (  # noqa: F401
    TestAdvancedFeatures,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_edge_cases import (  # noqa: F401
    TestEdgeCases,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_artifact_structure import (  # noqa: F401
    TestArtifactStructure,
)
from tests.validators._test_task_053_typescript_validator._test_task_053_typescript_validator_framework_patterns import (  # noqa: F401
    TestFrameworkPatterns,
)
