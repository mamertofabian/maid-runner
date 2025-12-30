"""Manifest validator module for MAID framework.

Provides validation of manifest files against schema and verification that
code artifacts match their declarative specifications.
"""

import ast
import json
from pathlib import Path
from typing import Optional, Any, List
from jsonschema import validate

# Import private modules using relative imports
from . import _schema_validation
from . import _type_annotation
from . import _type_normalization
from . import _artifact_validation
from . import _type_validation
from . import _manifest_utils
from . import _file_validation

# Import constants from artifact_validation for backward compatibility
# These are declared in manifests as attributes, so they must be module-level variables
from ._artifact_validation import (
    _VALIDATION_MODE_BEHAVIORAL as _VALIDATION_MODE_BEHAVIORAL_IMPL,
    _VALIDATION_MODE_IMPLEMENTATION as _VALIDATION_MODE_IMPLEMENTATION_IMPL,
    _ARTIFACT_TYPE_CLASS as _ARTIFACT_TYPE_CLASS_IMPL,
    _ARTIFACT_TYPE_FUNCTION as _ARTIFACT_TYPE_FUNCTION_IMPL,
    _ARTIFACT_TYPE_ATTRIBUTE as _ARTIFACT_TYPE_ATTRIBUTE_IMPL,
    _ARTIFACT_TYPE_INTERFACE as _ARTIFACT_TYPE_INTERFACE_IMPL,
    _ARTIFACT_TYPE_TYPE as _ARTIFACT_TYPE_TYPE_IMPL,
    _ARTIFACT_TYPE_ENUM as _ARTIFACT_TYPE_ENUM_IMPL,
    _ARTIFACT_TYPE_NAMESPACE as _ARTIFACT_TYPE_NAMESPACE_IMPL,
    _ARTIFACT_KIND_TYPE as _ARTIFACT_KIND_TYPE_IMPL,
    _ARTIFACT_KIND_RUNTIME as _ARTIFACT_KIND_RUNTIME_IMPL,
    _TYPEDDICT_INDICATOR as _TYPEDDICT_INDICATOR_IMPL,
)

# Import constants from type_annotation for backward compatibility
# These are declared in manifests as attributes, so they must be module-level variables
from ._type_annotation import (
    _OPTIONAL_PREFIX as _OPTIONAL_PREFIX_IMPL,
    _UNION_PREFIX as _UNION_PREFIX_IMPL,
    _BRACKET_OPEN as _BRACKET_OPEN_IMPL,
    _BRACKET_CLOSE as _BRACKET_CLOSE_IMPL,
)

# Import constants from type_normalization
from ._type_normalization import (
    _COMMA as _COMMA_IMPL,
    _PIPE as _PIPE_IMPL,
    _SPACE as _SPACE_IMPL,
    _NONE_TYPE as _NONE_TYPE_IMPL,
)

# Re-export as module-level constants (declared in manifests)
_VALIDATION_MODE_BEHAVIORAL = _VALIDATION_MODE_BEHAVIORAL_IMPL
_VALIDATION_MODE_IMPLEMENTATION = _VALIDATION_MODE_IMPLEMENTATION_IMPL
_ARTIFACT_TYPE_CLASS = _ARTIFACT_TYPE_CLASS_IMPL
_ARTIFACT_TYPE_FUNCTION = _ARTIFACT_TYPE_FUNCTION_IMPL
_ARTIFACT_TYPE_ATTRIBUTE = _ARTIFACT_TYPE_ATTRIBUTE_IMPL
_ARTIFACT_TYPE_INTERFACE = _ARTIFACT_TYPE_INTERFACE_IMPL
_ARTIFACT_TYPE_TYPE = _ARTIFACT_TYPE_TYPE_IMPL
_ARTIFACT_TYPE_ENUM = _ARTIFACT_TYPE_ENUM_IMPL
_ARTIFACT_TYPE_NAMESPACE = _ARTIFACT_TYPE_NAMESPACE_IMPL
_ARTIFACT_KIND_TYPE = _ARTIFACT_KIND_TYPE_IMPL
_ARTIFACT_KIND_RUNTIME = _ARTIFACT_KIND_RUNTIME_IMPL
_TYPEDDICT_INDICATOR = _TYPEDDICT_INDICATOR_IMPL
_OPTIONAL_PREFIX = _OPTIONAL_PREFIX_IMPL
_UNION_PREFIX = _UNION_PREFIX_IMPL
_BRACKET_OPEN = _BRACKET_OPEN_IMPL
_BRACKET_CLOSE = _BRACKET_CLOSE_IMPL
_COMMA = _COMMA_IMPL
_PIPE = _PIPE_IMPL
_SPACE = _SPACE_IMPL
_NONE_TYPE = _NONE_TYPE_IMPL


class AlignmentError(Exception):
    """Raised when expected artifacts are not found in the code."""

    pass


def validate_schema(manifest_data, schema_path):
    """
    Validate manifest data against a JSON schema.

    Args:
        manifest_data: Dictionary containing the manifest data to validate
        schema_path: Path to the JSON schema file

    Raises:
        jsonschema.ValidationError: If the manifest data doesn't conform to the schema
        AlignmentError: If system manifest has invalid systemArtifacts structure
    """
    with open(schema_path, "r") as schema_file:
        schema = json.load(schema_file)

    validate(manifest_data, schema)

    # Additional validation for system manifests
    # JSON schema validates basic structure, but we need deeper validation
    # of systemArtifacts blocks (file/contains fields, artifact structure, etc.)
    _validate_system_artifacts_structure(manifest_data)


def extract_type_annotation(
    node: ast.AST, annotation_attr: str = "annotation"
) -> Optional[str]:
    """
    Extract type annotation string from an AST node.

    This function extracts type annotations from various AST nodes,
    typically from function arguments or return types.

    Args:
        node: AST node to extract type annotation from
        annotation_attr: Name of the attribute containing the annotation
            (default: "annotation" for arguments, can be "returns" for functions)

    Returns:
        String representation of the type annotation, or None if not present

    Raises:
        AttributeError: If node is None (for backward compatibility)
    """
    # Validate inputs
    _validate_extraction_inputs(node, annotation_attr)

    # Extract annotation attribute
    annotation = getattr(node, annotation_attr, None)
    if annotation is None:
        return None

    # Convert AST annotation to string
    return _ast_to_type_string(annotation)


def compare_types(manifest_type: str, implementation_type: str) -> bool:
    """
    Compare two type strings for equivalence.

    Handles various forms of type representations and normalizes them
    before comparison to ensure semantic equivalence is detected.

    Args:
        manifest_type: Type string from manifest
        implementation_type: Type string from implementation

    Returns:
        True if types are equivalent, False otherwise
    """
    # Normalize inputs to strings or None
    manifest_type = _normalize_type_input(manifest_type)
    implementation_type = _normalize_type_input(implementation_type)

    # Handle None cases
    if manifest_type is None and implementation_type is None:
        return True
    if manifest_type is None or implementation_type is None:
        return False

    # Normalize and compare
    norm_manifest = normalize_type_string(manifest_type)
    norm_impl = normalize_type_string(implementation_type)

    return norm_manifest == norm_impl


def normalize_type_string(type_str: str) -> Optional[str]:
    """
    Normalize a type string for consistent comparison.

    Performs the following normalizations:
    - Removes extra whitespace
    - Converts Optional[X] to Union[X, None]
    - Converts modern union syntax (X | Y) to Union[X, Y]
    - Sorts Union members alphabetically
    - Ensures consistent comma spacing in generic types

    Args:
        type_str: Type string to normalize

    Returns:
        Normalized type string, or None if input is None
    """
    return _type_normalization.normalize_type_string(type_str)


def discover_related_manifests(target_file: str) -> List[str]:
    """
    Discover all manifests that have touched the target file.

    This is a public API function that can be used by other modules
    to find manifests related to a specific file.

    Args:
        target_file: Path to the file to check

    Returns:
        List of manifest paths in chronological order, excluding superseded manifests
    """
    from maid_runner.utils import get_superseded_manifests

    manifests = []
    manifest_dir = Path("manifests")

    if not manifest_dir.exists():
        return manifests

    # Get all JSON files and sort numerically by task number
    manifest_files = list(manifest_dir.glob("*.json"))

    # Sort manifest files numerically (supports task-1 through task-999999+)
    manifest_files.sort(key=_manifest_utils._get_task_number)

    for manifest_path in manifest_files:
        with open(manifest_path, "r") as f:
            data = json.load(f)

        # Check if this manifest touches the target file
        created_files = data.get("creatableFiles", [])
        edited_files = data.get("editableFiles", [])
        expected_file = data.get("expectedArtifacts", {}).get("file")

        # Check both the lists and the expected file
        if (
            target_file in created_files
            or target_file in edited_files
            or target_file == expected_file
        ):
            manifests.append(str(manifest_path))

    # Filter out superseded manifests
    superseded = get_superseded_manifests(manifest_dir)
    active_manifests = [m for m in manifests if Path(m) not in superseded]

    return active_manifests


def validate_with_ast(
    manifest_data, test_file_path, use_manifest_chain=False, validation_mode=None
):
    """
    Validate that artifacts listed in manifest are referenced in the test file.

    Args:
        manifest_data: Dictionary containing the manifest with expectedArtifacts
        test_file_path: Path to the file to analyze (Python, TypeScript, JavaScript, etc.)
        use_manifest_chain: If True, discovers and merges all related manifests
        validation_mode: _VALIDATION_MODE_IMPLEMENTATION or _VALIDATION_MODE_BEHAVIORAL mode, auto-detected if None

    Raises:
        AlignmentError: If any expected artifact is not found in the code
    """
    # Validate file status: absent (check that file doesn't exist)
    # This should be called early, before trying to parse the file
    _validate_absent_file(manifest_data, test_file_path)

    # Early return if file has status: "absent" - no need to parse
    expected_artifacts = manifest_data.get("expectedArtifacts")
    if expected_artifacts and isinstance(expected_artifacts, dict):
        status = expected_artifacts.get("status")
        if status == "absent":
            # File is marked as deleted - validation complete
            return

    # Get the appropriate validator for this file type
    validator = _get_validator_for_file(test_file_path)
    validation_mode = validation_mode or _VALIDATION_MODE_IMPLEMENTATION

    # Collect artifacts using the language-specific validator
    artifacts = validator.collect_artifacts(test_file_path, validation_mode)

    # Convert to collector-like object for compatibility
    class _CollectorShim:
        def __init__(self, artifacts_dict, file_path: str = ""):
            self.found_classes = artifacts_dict.get("found_classes", set())
            self.found_class_bases = artifacts_dict.get("found_class_bases", {})
            self.found_attributes = artifacts_dict.get("found_attributes", {})
            self.variable_to_class = artifacts_dict.get("variable_to_class", {})
            self.found_functions = artifacts_dict.get("found_functions", {})
            self.found_methods = artifacts_dict.get("found_methods", {})
            self.found_function_types = artifacts_dict.get("found_function_types", {})
            self.found_method_types = artifacts_dict.get("found_method_types", {})
            self.used_classes = artifacts_dict.get("used_classes", set())
            self.used_functions = artifacts_dict.get("used_functions", set())
            self.used_methods = artifacts_dict.get("used_methods", {})
            self.used_arguments = artifacts_dict.get("used_arguments", set())
            # Store file path for path-based test file detection (security fix)
            self.file_path = file_path

    collector = _CollectorShim(artifacts, test_file_path)

    # Get expected artifacts
    expected_items = _get_expected_artifacts(
        manifest_data, test_file_path, use_manifest_chain
    )

    # Validate all expected artifacts
    _validate_all_artifacts(expected_items, collector, validation_mode)

    # Check for unexpected public artifacts (strict mode)
    _check_unexpected_artifacts(expected_items, collector)

    # Type hint validation (only in implementation mode)
    if validation_mode == _VALIDATION_MODE_IMPLEMENTATION:
        # Extract type information from manifest
        manifest_artifacts = manifest_data.get("expectedArtifacts", {})

        # Format implementation type data from collector
        implementation_artifacts = {
            "functions": collector.found_function_types,
            "methods": collector.found_method_types,
        }

        # Validate type hints match manifest declarations
        type_errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        if type_errors:
            # Format errors for readability
            formatted_errors = "\n".join(f"  - {err}" for err in type_errors)
            raise AlignmentError(f"Type validation failed:\n{formatted_errors}")

    # Validate all editableFiles for undeclared public artifacts (close loophole)
    if validation_mode == _VALIDATION_MODE_IMPLEMENTATION:
        _validate_editable_files(manifest_data, validation_mode)


def collect_behavioral_artifacts(file_path: str) -> dict:
    """Collect artifacts used in a file for behavioral validation.

    This function uses the appropriate language-specific validator based on file extension.
    It analyzes the file and returns information about what classes, functions,
    and methods are used/called in the code.

    Args:
        file_path: Path to the file to analyze (Python, TypeScript, JavaScript, etc.)

    Returns:
        Dictionary containing:
        - used_classes: Set of class names that are instantiated
        - used_functions: Set of function names that are called
        - used_methods: Dict mapping class names to sets of method names called
        - used_arguments: Set of argument names used in function calls

    Raises:
        FileNotFoundError: If the file doesn't exist
        SyntaxError: If the file contains invalid syntax
    """
    # Use the appropriate validator for this file type
    validator = _get_validator_for_file(file_path)
    artifacts = validator.collect_artifacts(file_path, _VALIDATION_MODE_BEHAVIORAL)

    return {
        "used_classes": artifacts.get("used_classes", set()),
        "used_functions": artifacts.get("used_functions", set()),
        "used_methods": artifacts.get("used_methods", {}),
        "used_arguments": artifacts.get("used_arguments", set()),
    }


def validate_type_hints(
    manifest_artifacts: dict, implementation_artifacts: dict
) -> list:
    """
    Validate that implementation type hints match manifest type declarations.

    This is the main entry point for type validation, checking that all
    function and method type annotations in the implementation match
    what was declared in the manifest.

    Args:
        manifest_artifacts: Dictionary containing the manifest with expectedArtifacts
        implementation_artifacts: Dictionary with implementation type information

    Returns:
        List of error messages for type mismatches
    """
    # Validate inputs
    if not _are_valid_type_validation_inputs(
        manifest_artifacts, implementation_artifacts
    ):
        return []

    expected_items = manifest_artifacts.get("contains", [])
    if not isinstance(expected_items, list):
        return []

    # Collect all type validation errors
    errors = []

    for artifact in expected_items:
        if not _should_validate_artifact_types(artifact):
            continue

        errors.extend(_validate_function_types(artifact, implementation_artifacts))

    return errors


def should_skip_behavioral_validation(artifact: Any) -> bool:
    """
    Determine if an artifact should be skipped during behavioral validation.

    Type-only artifacts (like TypedDict classes, type aliases) are compile-time
    constructs that shouldn't be behaviorally validated as they don't have runtime
    behavior that can be tested.

    IMPORTANT: If an artifact is explicitly declared in a manifest, it should be
    validated behaviorally even if it's "private" by naming convention (starts with _).
    The manifest declaration overrides the naming convention - if it's in the manifest,
    it's part of the declared contract and should be tested.

    Args:
        artifact: Dictionary containing artifact metadata

    Returns:
        True if artifact should be skipped, False if it should be validated
    """
    if not artifact:
        return False

    # Check explicit artifact kind first (explicit intent overrides naming convention)
    skip_by_kind = _should_skip_by_artifact_kind(artifact)
    if skip_by_kind is not None:
        return skip_by_kind

    # Auto-detect type-only patterns
    if _is_typeddict_class(artifact):
        return True

    # NOTE: We do NOT skip private artifacts (starting with _) here because:
    # 1. If an artifact is in expected_items, it's explicitly declared in the manifest
    # 2. Manifest declaration overrides naming convention - it's part of the contract
    # 3. Private artifacts that are NOT in manifests are handled elsewhere (unexpected artifact checks)
    #
    # The old logic skipped all private artifacts, but this created a loophole where
    # explicitly declared private functions (like _safe_ast_conversion in task-009)
    # would not be behaviorally validated even though they're part of the declared API.

    # Default to runtime validation (validate it)
    return False


class _ArtifactCollector(ast.NodeVisitor):
    """AST visitor that collects class, function, and attribute references from Python code.

    Collects artifacts at different scopes:
    - Module-level: stored with None as key in found_attributes
    - Class-level: stored with class name as key in found_attributes
    - Functions and methods: stored separately in found_functions/found_methods
    """

    def __init__(self, validation_mode=_VALIDATION_MODE_IMPLEMENTATION):
        self.validation_mode = validation_mode  # _VALIDATION_MODE_IMPLEMENTATION or _VALIDATION_MODE_BEHAVIORAL
        self.found_classes = set()
        self.found_class_bases = {}  # class_name -> list of base class names
        self.found_attributes = {}  # {class_name|None -> set of attribute names}
        self.variable_to_class = {}  # variable_name -> class_name
        self.found_functions = {}  # function_name -> list of parameter names
        self.found_methods = (
            {}
        )  # class_name -> {method_name -> list of parameter names}
        self.current_class = None  # Track current class scope
        self.current_function = None  # Track current function scope

        # Type tracking for functions and methods
        self.found_function_types = (
            {}
        )  # function_name -> {"parameters": [...], "returns": ...}
        self.found_method_types = (
            {}
        )  # class_name -> {method_name -> {"parameters": [...], "returns": ...}}

        # For behavioral validation (tracking usage)
        self.used_classes = set()  # Classes that are instantiated
        self.used_functions = set()  # Functions that are called
        self.used_methods = {}  # class_name -> set of method names called
        self.used_arguments = set()  # Arguments used in function calls
        self.imports_pytest = False  # Track if pytest is imported

    def visit_Import(self, node):
        """Handle regular import statements."""
        # Check if pytest is imported (for auto-detection of test files)
        for alias in node.names:
            if alias.name == "pytest":
                self.imports_pytest = True
        # Don't add imports to found classes/functions
        # They are external dependencies, not artifacts of this file
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Track import statements without treating them as defined artifacts."""
        # Don't add imports to found_classes - they are dependencies, not artifacts
        # found_classes should only contain classes DEFINED via visit_ClassDef()
        self.generic_visit(node)

    def _is_local_import(self, node):
        """Check if an import is from a local module.

        Args:
            node: ImportFrom AST node

        Returns:
            True if this is a local import (relative or non-stdlib)
        """
        # Relative imports are always local
        if node.level > 0:
            return True

        # Check if module is not from standard library
        stdlib_modules = (
            "pathlib",
            "typing",
            "collections",
            "datetime",
            "json",
            "ast",
            "os",
            "sys",
            "re",
            "enum",
            "jsonschema",
        )
        return node.module and not node.module.startswith(stdlib_modules)

    def _is_class_name(self, name):
        """Check if a name follows class naming conventions.

        Args:
            name: String name to check

        Returns:
            True if name follows Python class naming conventions
        """
        if not name:
            return False

        # Standard class names start with uppercase
        if name[0].isupper():
            return True

        # Private class names like _ClassName
        if name.startswith("_") and len(name) > 1 and name[1].isupper():
            return True

        return False

    def visit_FunctionDef(self, node):
        """Collect function definitions and their parameters."""
        # Extract function signature information
        param_names = [arg.arg for arg in node.args.args]
        param_types = self._extract_parameter_types(node.args.args)
        return_type = extract_type_annotation(node, "returns")

        # Store function/method information based on scope
        if self.current_class is None:
            self._store_function_info(node.name, param_names, param_types, return_type)
        else:
            self._store_method_info(node.name, param_names, param_types, return_type)

        # Track function scope for nested definitions
        old_function = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_function

    # Alias for async function definitions - treat them the same as regular functions
    visit_AsyncFunctionDef = visit_FunctionDef

    def _extract_parameter_types(self, args):
        """Extract type information for function parameters.

        Args:
            args: List of ast.arg nodes

        Returns:
            List of parameter type information dictionaries
        """
        param_types = []
        for arg in args:
            param_info = {
                "name": arg.arg,
                "type": extract_type_annotation(arg, "annotation"),
            }
            param_types.append(param_info)
        return param_types

    def _store_function_info(self, name, param_names, param_types, return_type):
        """Store information about a module-level function."""
        self.found_functions[name] = param_names
        self.found_function_types[name] = {
            "parameters": param_types,
            "returns": return_type,
        }

    def _store_method_info(self, name, param_names, param_types, return_type):
        """Store information about a class method."""
        # Ensure dictionaries exist for this class
        if self.current_class not in self.found_methods:
            self.found_methods[self.current_class] = {}
        if self.current_class not in self.found_method_types:
            self.found_method_types[self.current_class] = {}

        # Store method information
        self.found_methods[self.current_class][name] = param_names
        self.found_method_types[self.current_class][name] = {
            "parameters": param_types,
            "returns": return_type,
        }

    def visit_ClassDef(self, node):
        """Collect class definitions and their base classes."""
        self.found_classes.add(node.name)

        # Collect base classes
        base_names = []
        for base in node.bases:
            base_name = _extract_base_class_name(base)
            if base_name:
                base_names.append(base_name)
                # In behavioral mode, track base classes as "used"
                if self.validation_mode == _VALIDATION_MODE_BEHAVIORAL:
                    self.used_classes.add(base_name)

        if base_names:
            self.found_class_bases[node.name] = base_names

        # Track that we're inside a class for nested function definitions
        old_class = self.current_class
        self.current_class = node.name

        # Visit child nodes (including methods)
        self.generic_visit(node)

        # Restore previous class context
        self.current_class = old_class

    def visit_Assign(self, node):
        """Track variable assignments to class instances, self attributes, and module-level attributes."""
        # Process based on current scope
        if self.current_class:
            self._process_class_assignments(node)
        elif not self.current_function:
            self._process_module_assignments(node)

        # Track variable-to-class mappings
        self._track_class_instantiations(node)

        # In behavioral mode, track when classes are assigned to variables
        if self.validation_mode == _VALIDATION_MODE_BEHAVIORAL:
            self._track_class_name_assignments(node)

        self.generic_visit(node)

    def _process_class_assignments(self, node):
        """Process assignments within a class scope (self.attribute = value)."""
        for target in node.targets:
            if self._is_self_attribute(target):
                self._add_class_attribute(self.current_class, target.attr)

    def _process_module_assignments(self, node):
        """Process assignments at module level."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                # Simple name assignment (e.g., CONSTANT = 5)
                self._add_module_attribute(target.id)
            elif isinstance(target, ast.Tuple):
                # Tuple unpacking (e.g., X, Y = 1, 2)
                self._process_tuple_assignment(target)

    def _process_tuple_assignment(self, target):
        """Process tuple unpacking assignments."""
        for element in target.elts:
            if isinstance(element, ast.Name):
                self._add_module_attribute(element.id)

    def _track_class_instantiations(self, node):
        """Track variable assignments to class instances."""
        if not isinstance(node.value, ast.Call):
            return

        class_name = None

        # Handle direct instantiation: service = UserService()
        if isinstance(node.value.func, ast.Name):
            class_name = node.value.func.id
        # Handle classmethod calls: service = ProductService.create_default()
        elif isinstance(node.value.func, ast.Attribute) and isinstance(
            node.value.func.value, ast.Name
        ):
            # Assume classmethod returns instance of the class
            class_name = node.value.func.value.id

        # Check if it's a known class or follows class naming conventions
        # Support both standard (UpperCase) and private (_ClassName) patterns
        if class_name and (
            class_name in self.found_classes or self._is_class_name(class_name)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.variable_to_class[target.id] = class_name

    def _track_class_name_assignments(self, node):
        """Track when a class name itself is assigned to a variable (e.g., base_ref = BaseClass)."""
        # Check if the value being assigned is a simple Name (not a Call)
        if isinstance(node.value, ast.Name):
            value_name = node.value.id
            # Check if it's a known class or follows class naming conventions
            if value_name in self.found_classes or (
                value_name and value_name[0].isupper()
            ):
                self.used_classes.add(value_name)

    def _track_method_call_with_inheritance(self, class_name: str, method_name: str):
        """Track a method call on a class and propagate to base classes.

        When a method is called on a class, it should also count as using
        the method on all parent classes (for inherited methods).
        """
        # Track for the immediate class
        if class_name not in self.used_methods:
            self.used_methods[class_name] = set()
        self.used_methods[class_name].add(method_name)

        # Also track for all base classes
        if class_name in self.found_class_bases:
            for base_class in self.found_class_bases[class_name]:
                # Recursively track for base classes
                self._track_method_call_with_inheritance(base_class, method_name)

    def _is_self_attribute(self, target):
        """Check if target is a self.attribute assignment."""
        return (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        )

    def _add_class_attribute(self, class_name, attribute_name):
        """Add an attribute to a class's attribute set."""
        if class_name not in self.found_attributes:
            self.found_attributes[class_name] = set()
        self.found_attributes[class_name].add(attribute_name)

    def _add_module_attribute(self, attribute_name):
        """Add an attribute to module-level attributes."""
        if None not in self.found_attributes:
            self.found_attributes[None] = set()
        self.found_attributes[None].add(attribute_name)

    def visit_AnnAssign(self, node):
        """Track annotated assignments including module-level type-annotated variables."""
        # Only track module-level annotated assignments
        if self._is_module_scope() and isinstance(node.target, ast.Name):
            self._add_module_attribute(node.target.id)

        self.generic_visit(node)

    def _is_module_scope(self):
        """Check if currently at module scope (not inside class or function)."""
        return not self.current_class and not self.current_function

    def visit_Attribute(self, node):
        """Collect attribute accesses on class instances."""
        if not isinstance(node.value, ast.Name):
            self.generic_visit(node)
            return

        variable_name = node.value.id
        attribute_name = node.attr

        # Map attribute to its class if we know the variable's type
        if variable_name in self.variable_to_class:
            class_name = self.variable_to_class[variable_name]
            self._add_class_attribute(class_name, attribute_name)

        self.generic_visit(node)

    def visit_Call(self, node):
        """Track function and method calls in behavioral tests."""
        if self.validation_mode == _VALIDATION_MODE_BEHAVIORAL:
            # Handle method calls (e.g., service.get_user_by_id())
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                self.used_functions.add(method_name)

                # Track the object's class if known
                if isinstance(node.func.value, ast.Name):
                    var_name = node.func.value.id

                    # Check if it's a known class being called directly (classmethod/staticmethod)
                    if var_name in self.found_classes or (
                        var_name
                        and (
                            var_name[0].isupper()
                            or (
                                var_name.startswith("_")
                                and len(var_name) > 1
                                and var_name[1].isupper()
                            )
                        )
                    ):
                        self._track_method_call_with_inheritance(var_name, method_name)
                        self.used_classes.add(var_name)
                    # Existing logic for variables
                    elif var_name in self.variable_to_class:
                        class_name = self.variable_to_class[var_name]
                        self._track_method_call_with_inheritance(
                            class_name, method_name
                        )
                # Handle direct method calls on instantiated objects
                elif isinstance(node.func.value, ast.Call) and isinstance(
                    node.func.value.func, ast.Name
                ):
                    # e.g., UserService().get_user_by_id()
                    class_name = node.func.value.func.id
                    if class_name in self.found_classes or (
                        class_name
                        and (
                            class_name[0].isupper()
                            or (
                                class_name.startswith("_")
                                and len(class_name) > 1
                                and class_name[1].isupper()
                            )
                        )
                    ):
                        self._track_method_call_with_inheritance(
                            class_name, method_name
                        )
                        self.used_classes.add(class_name)

                # For chained calls, also track intermediate methods
                current = node.func.value
                while isinstance(current, ast.Attribute):
                    self.used_functions.add(current.attr)
                    current = current.value

            # Handle direct function calls
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

                # Check if it's a class instantiation
                if func_name in self.found_classes or (
                    func_name
                    and (
                        func_name[0].isupper()
                        or (
                            func_name.startswith("_")
                            and len(func_name) > 1
                            and func_name[1].isupper()
                        )
                    )
                ):
                    self.used_classes.add(func_name)
                else:
                    self.used_functions.add(func_name)

                # Handle isinstance checks for return type validation
                if func_name == "isinstance" and len(node.args) >= 2:
                    if isinstance(node.args[1], ast.Name):
                        self.used_classes.add(node.args[1].id)

                # Handle issubclass checks
                if func_name == "issubclass" and len(node.args) >= 2:
                    # First argument is the subclass being checked
                    if isinstance(node.args[0], ast.Name):
                        self.used_classes.add(node.args[0].id)
                    # Second argument is the base class to check against
                    if isinstance(node.args[1], ast.Name):
                        self.used_classes.add(node.args[1].id)

                # Handle hasattr checks - first argument is the class
                if func_name == "hasattr" and len(node.args) >= 1:
                    if isinstance(node.args[0], ast.Name):
                        # Could be a class name or instance variable
                        arg_name = node.args[0].id
                        # Check if it's a known class
                        if arg_name in self.found_classes or (
                            arg_name and arg_name[0].isupper()
                        ):
                            self.used_classes.add(arg_name)

            # Track keyword arguments
            for keyword in node.keywords:
                if keyword.arg:
                    self.used_arguments.add(keyword.arg)

            # Track positional arguments as "used" (mark all as used for now)
            # This is a simplification - proper parameter tracking would need more context
            # For behavioral tests, we consider parameters used if the function is called
            if node.args and len(node.args) > 0:
                # Mark that positional arguments were provided
                self.used_arguments.add("__positional__")  # Marker for positional args

        self.generic_visit(node)


# Schema validation functions declared in manifests must be defined here
def _is_system_manifest(manifest_data: dict) -> bool:
    """Check if a manifest is a system manifest."""
    return _schema_validation._is_system_manifest(manifest_data)


def _validate_system_artifacts_structure(manifest_data: dict) -> None:
    """Validate the structure of systemArtifacts in a system manifest."""
    return _schema_validation._validate_system_artifacts_structure(manifest_data)


def _should_skip_behavioral_validation(manifest_data: dict) -> bool:
    """Determine if behavioral validation should be skipped for this manifest."""
    return _schema_validation._should_skip_behavioral_validation(manifest_data)


def _should_skip_implementation_validation(manifest_data: dict) -> bool:
    """Determine if implementation validation should be skipped for this manifest."""
    return _schema_validation._should_skip_implementation_validation(manifest_data)


# Functions declared in manifests must be defined here (AST validation looks for actual definitions)
# These delegate to implementations in private modules


def _extract_base_class_name(base: ast.AST) -> Optional[str]:
    """Extract base class name from various AST node types."""
    return _type_annotation._extract_base_class_name(base)


def _ast_to_type_string(node: Optional[ast.AST]) -> Optional[str]:
    """Convert an AST node to a type string representation."""
    return _type_annotation._ast_to_type_string(node)


def _validate_extraction_inputs(node: Any, annotation_attr: str) -> None:
    """Validate inputs for type annotation extraction."""
    return _type_annotation._validate_extraction_inputs(node, annotation_attr)


def _safe_ast_conversion(node: ast.AST) -> Optional[str]:
    """Safely convert AST node to string with error handling."""
    return _type_annotation._safe_ast_conversion(node)


def _handle_subscript_node(node: ast.Subscript) -> str:
    """Handle generic type subscript nodes like List[str], Dict[str, int]."""
    return _type_annotation._handle_subscript_node(node)


def _handle_attribute_node(node: ast.Attribute) -> str:
    """Handle qualified name nodes like typing.Optional."""
    return _type_annotation._handle_attribute_node(node)


def _handle_union_operator(node: ast.BinOp) -> str:
    """Handle Union types using | operator (Python 3.10+)."""
    return _type_annotation._handle_union_operator(node)


def _fallback_ast_unparse(node: ast.AST) -> Optional[str]:
    """Try to unparse AST node as fallback."""
    return _type_annotation._fallback_ast_unparse(node)


def _safe_str_conversion(node: Any) -> Optional[str]:
    """Safely convert any object to string."""
    return _type_annotation._safe_str_conversion(node)


# Normalization functions declared in manifests must be defined here
def _normalize_type_input(type_value: Any) -> Optional[str]:
    """Normalize a type input value to string or None."""
    return _type_normalization._normalize_type_input(type_value)


def _normalize_modern_union_syntax(type_str: str) -> str:
    """Convert modern union syntax (X | Y) to Union[X, Y]."""
    return _type_normalization._normalize_modern_union_syntax(type_str)


def _normalize_optional_type(type_str: str) -> str:
    """Convert Optional[X] to Union[X, None]."""
    return _type_normalization._normalize_optional_type(type_str)


def _is_optional_type(type_str: str) -> bool:
    """Check if a type string represents Optional[...] type."""
    return _type_normalization._is_optional_type(type_str)


def _extract_bracketed_content(type_str: str, prefix: str) -> str:
    """Extract content between prefix and closing bracket."""
    return _type_normalization._extract_bracketed_content(type_str, prefix)


def _normalize_union_type(type_str: str) -> str:
    """Sort Union type members alphabetically."""
    return _type_normalization._normalize_union_type(type_str)


def _is_union_type(type_str: str) -> bool:
    """Check if a type string represents Union[...] type."""
    return _type_normalization._is_union_type(type_str)


def _split_type_arguments(inner: str) -> list:
    """Split type arguments by comma, respecting nested brackets."""
    return _type_normalization._split_type_arguments(inner)


def _split_by_delimiter(text: str, delimiter: str) -> list:
    """Split text by delimiter at top level, respecting bracket nesting."""
    return _type_normalization._split_by_delimiter(text, delimiter)


def _normalize_comma_spacing(type_str: str) -> str:
    """Normalize spacing after commas in generic types."""
    return _type_normalization._normalize_comma_spacing(type_str)


def _skip_spaces(text: str, start_idx: int) -> int:
    """Skip whitespace characters starting from given index."""
    return _type_normalization._skip_spaces(text, start_idx)


# Manifest utility functions declared in manifests must be defined here
def _get_task_number(path) -> int:
    """Extract task number from filename like task-XXX-description.json."""
    return _manifest_utils._get_task_number(path)


def _get_artifact_key(artifact: dict) -> tuple:
    """Generate unique key for an artifact."""
    return _manifest_utils._get_artifact_key(artifact)


def _merge_expected_artifacts(
    manifest_paths: List[str], target_file: str
) -> List[dict]:
    """Merge expected artifacts from multiple manifests, filtering by target file."""
    return _manifest_utils._merge_expected_artifacts(manifest_paths, target_file)


def _get_expected_artifacts(
    manifest_data: dict, test_file_path: str, use_manifest_chain: bool
) -> List[dict]:
    """Get expected artifacts from manifest(s)."""
    return _manifest_utils._get_expected_artifacts(
        manifest_data, test_file_path, use_manifest_chain
    )


def _get_validator_for_file(file_path: str):
    """Get the appropriate validator for a file based on its extension."""
    return _manifest_utils._get_validator_for_file(file_path)


def _parse_file(file_path: str) -> ast.AST:
    """Parse a Python file into an AST."""
    return _manifest_utils._parse_file(file_path)


def _collect_artifacts_from_ast(
    tree: ast.AST, validation_mode: str
) -> "_ArtifactCollector":
    """Collect artifacts from an AST tree."""
    return _manifest_utils._collect_artifacts_from_ast(tree, validation_mode)


# Validation functions declared in manifests must be defined here
def _validate_all_artifacts(
    expected_items: List[dict], collector: "_ArtifactCollector", validation_mode: str
) -> None:
    """Validate all expected artifacts exist in the code."""
    return _artifact_validation._validate_all_artifacts(
        expected_items, collector, validation_mode
    )


def _check_unexpected_artifacts(
    expected_items: List[dict], collector: "_ArtifactCollector"
) -> None:
    """Check for unexpected public artifacts in strict mode."""
    return _artifact_validation._check_unexpected_artifacts(expected_items, collector)


def _validate_single_artifact(
    artifact: dict, collector: "_ArtifactCollector", validation_mode: str
) -> None:
    """Validate a single artifact."""
    return _artifact_validation._validate_single_artifact(
        artifact, collector, validation_mode
    )


def _validate_function_artifact(
    artifact: dict, collector: "_ArtifactCollector", validation_mode: str
) -> None:
    """Validate a function or method artifact."""
    return _artifact_validation._validate_function_artifact(
        artifact, collector, validation_mode
    )


def _validate_function_behavioral(
    artifact_name: str,
    parameters: List[dict],
    parent_class: Optional[str],
    artifact: dict,
    collector: "_ArtifactCollector",
) -> None:
    """Validate function/method in behavioral mode."""
    return _artifact_validation._validate_function_behavioral(
        artifact_name, parameters, parent_class, artifact, collector
    )


def _validate_parameters_used(
    parameters: List[dict], artifact_name: str, collector: "_ArtifactCollector"
) -> None:
    """Validate parameters were used in function calls."""
    return _artifact_validation._validate_parameters_used(
        parameters, artifact_name, collector
    )


def _validate_function_implementation(
    artifact_name: str,
    parameters: List[dict],
    parent_class: Optional[str],
    collector: "_ArtifactCollector",
) -> None:
    """Validate function/method in implementation mode."""
    return _artifact_validation._validate_function_implementation(
        artifact_name, parameters, parent_class, collector
    )


def _validate_method_parameters(
    method_name: str,
    parameters: List[dict],
    class_name: str,
    collector: "_ArtifactCollector",
) -> None:
    """Validate method parameters match expectations."""
    return _artifact_validation._validate_method_parameters(
        method_name, parameters, class_name, collector
    )


def _validate_class(class_name, expected_bases, found_classes, found_class_bases):
    """Validate that a class is referenced in the code with the expected base classes."""
    return _artifact_validation._validate_class(
        class_name, expected_bases, found_classes, found_class_bases
    )


def _validate_attribute(attribute_name, parent_class, found_attributes):
    """Validate that an attribute is referenced for a specific class."""
    return _artifact_validation._validate_attribute(
        attribute_name, parent_class, found_attributes
    )


def _validate_function(function_name, expected_parameters, found_functions):
    """Validate that a function exists with the expected parameters."""
    return _artifact_validation._validate_function(
        function_name, expected_parameters, found_functions
    )


def _validate_no_unexpected_artifacts(
    expected_items, found_classes, found_functions, found_methods
):
    """Validate that no unexpected public artifacts exist in the code."""
    return _artifact_validation._validate_no_unexpected_artifacts(
        expected_items, found_classes, found_functions, found_methods
    )


def _is_typeddict_class(artifact: dict) -> bool:
    """Check if an artifact represents a TypedDict class."""
    return _artifact_validation._is_typeddict_class(artifact)


def _is_typeddict_base(base_name: str) -> bool:
    """Check if a base class name indicates TypedDict."""
    return _artifact_validation._is_typeddict_base(base_name)


def _should_skip_by_artifact_kind(artifact: dict) -> Optional[bool]:
    """Check if artifact kind explicitly indicates skip behavior."""
    return _artifact_validation._should_skip_by_artifact_kind(artifact)


# Type validation functions
def _are_valid_type_validation_inputs(
    manifest_artifacts: Any, implementation_artifacts: Any
) -> bool:
    """Check if inputs are valid for type validation."""
    return _type_validation._are_valid_type_validation_inputs(
        manifest_artifacts, implementation_artifacts
    )


def _should_validate_artifact_types(artifact: Any) -> bool:
    """Check if an artifact should have its types validated."""
    return _type_validation._should_validate_artifact_types(artifact)


def _validate_function_types(artifact: dict, implementation_artifacts: dict) -> list:
    """Validate type hints for a single function or method artifact."""
    return _type_validation._validate_function_types(artifact, implementation_artifacts)


def _get_implementation_info(
    artifact_name: str, parent_class: Optional[str], implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a function or method."""
    return _type_validation._get_implementation_info(
        artifact_name, parent_class, implementation_artifacts
    )


def _get_method_info(
    method_name: str, class_name: str, implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a method."""
    return _type_validation._get_method_info(
        method_name, class_name, implementation_artifacts
    )


def _get_function_info(
    function_name: str, implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a standalone function."""
    return _type_validation._get_function_info(function_name, implementation_artifacts)


def _validate_parameter_types(
    artifact: dict, impl_info: dict, artifact_name: str, parent_class: str
) -> list:
    """Validate parameter types match between manifest and implementation."""
    return _type_validation._validate_parameter_types(
        artifact, impl_info, artifact_name, parent_class
    )


def _validate_single_parameter(
    param_name: str,
    manifest_type: str,
    impl_params_dict: dict,
    artifact_name: str,
    parent_class: Optional[str],
) -> Optional[str]:
    """Validate a single parameter's type annotation."""
    return _type_validation._validate_single_parameter(
        param_name, manifest_type, impl_params_dict, artifact_name, parent_class
    )


def _validate_return_type(
    artifact: dict, impl_info: dict, artifact_name: str, parent_class: Optional[str]
) -> Optional[str]:
    """Validate return type matches between manifest and implementation."""
    return _type_validation._validate_return_type(
        artifact, impl_info, artifact_name, parent_class
    )


# File validation functions
def _validate_absent_file(manifest_data: dict, file_path: str) -> None:
    """Validates that a file with status 'absent' does not exist."""
    return _file_validation._validate_absent_file(manifest_data, file_path)


def _validate_file_status_semantic_rules(manifest_data: dict) -> None:
    """Validates semantic rules for file status field usage."""
    return _file_validation._validate_file_status_semantic_rules(manifest_data)


def _has_undeclared_public_artifacts(file_path: str) -> bool:
    """Check if a file has any undeclared public artifacts."""
    return _file_validation._has_undeclared_public_artifacts(file_path)


def _validate_editable_files(manifest_data: dict, validation_mode: str) -> None:
    """Validate that files in editableFiles don't have undeclared public artifacts."""
    return _file_validation._validate_editable_files(manifest_data, validation_mode)
