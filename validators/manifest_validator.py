"""Manifest validator module for MAID framework.

Provides validation of manifest files against schema and verification that
code artifacts match their declarative specifications.
"""

import ast
import json
from pathlib import Path
from typing import Optional, Any, List
from jsonschema import validate


def validate_schema(manifest_data, schema_path):
    """
    Validate manifest data against a JSON schema.

    Args:
        manifest_data: Dictionary containing the manifest data to validate
        schema_path: Path to the JSON schema file

    Raises:
        jsonschema.ValidationError: If the manifest data doesn't conform to the schema
    """
    with open(schema_path, "r") as schema_file:
        schema = json.load(schema_file)

    validate(manifest_data, schema)


class AlignmentError(Exception):
    """Raised when expected artifacts are not found in the code."""

    pass


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


def _validate_extraction_inputs(node: Any, annotation_attr: str) -> None:
    """Validate inputs for type annotation extraction.

    Args:
        node: Node to validate
        annotation_attr: Attribute name to validate

    Raises:
        AttributeError: If node is None (for backward compatibility)
    """
    if node is None:
        raise AttributeError("Cannot extract type annotation from None node")

    if not isinstance(node, ast.AST):
        return  # Will return None from main function

    if not annotation_attr:
        return  # Will return None from main function


def _ast_to_type_string(node: Optional[ast.AST]) -> Optional[str]:
    """
    Convert an AST node to a type string representation.

    Handles various Python type hint syntaxes including:
    - Simple types (int, str, etc.)
    - Generic types (List[str], Dict[str, int])
    - Qualified names (typing.Optional)
    - Union types (str | None in Python 3.10+)
    - Forward references (string literals)

    Args:
        node: AST node representing a type annotation

    Returns:
        String representation of the type, or None if node is None
    """
    if node is None:
        return None

    # Use safe wrapper to handle any exceptions
    return _safe_ast_conversion(node)


def _safe_ast_conversion(node: ast.AST) -> Optional[str]:
    """Safely convert AST node to string with error handling.

    Args:
        node: AST node to convert

    Returns:
        String representation or None if conversion fails
    """
    try:
        # Dispatch based on node type
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Constant):
            return str(node.value)

        if isinstance(node, ast.Subscript):
            return _handle_subscript_node(node)

        if isinstance(node, ast.Attribute):
            return _handle_attribute_node(node)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return _handle_union_operator(node)

        if isinstance(node, ast.Ellipsis):
            return "..."

        # Fallback to AST unparsing if available
        return _fallback_ast_unparse(node)

    except Exception:
        # Final safety net
        return _safe_str_conversion(node)


def _handle_subscript_node(node: ast.Subscript) -> str:
    """Handle generic type subscript nodes like List[str], Dict[str, int].

    Args:
        node: Subscript AST node

    Returns:
        String representation of the generic type
    """
    base = _ast_to_type_string(node.value)

    if isinstance(node.slice, ast.Tuple):
        # Multiple type arguments like Dict[str, int]
        args = [_ast_to_type_string(elt) for elt in node.slice.elts]
        return f"{base}{_BRACKET_OPEN}{', '.join(args)}{_BRACKET_CLOSE}"
    else:
        # Single type argument like List[str]
        arg = _ast_to_type_string(node.slice)
        return f"{base}{_BRACKET_OPEN}{arg}{_BRACKET_CLOSE}"


def _handle_attribute_node(node: ast.Attribute) -> str:
    """Handle qualified name nodes like typing.Optional.

    Args:
        node: Attribute AST node

    Returns:
        String representation of the qualified name
    """
    value = _ast_to_type_string(node.value)
    return f"{value}.{node.attr}" if value else node.attr


def _handle_union_operator(node: ast.BinOp) -> str:
    """Handle Union types using | operator (Python 3.10+).

    Args:
        node: BinOp AST node with BitOr operator

    Returns:
        String representation in Union[...] format
    """
    left = _ast_to_type_string(node.left)
    right = _ast_to_type_string(node.right)
    return f"{_UNION_PREFIX}{left}, {right}{_BRACKET_CLOSE}"


def _fallback_ast_unparse(node: ast.AST) -> Optional[str]:
    """Try to unparse AST node as fallback.

    Args:
        node: AST node to unparse

    Returns:
        Unparsed string or None if unparsing fails
    """
    try:
        return ast.unparse(node)
    except (AttributeError, TypeError):
        return str(node)


def _safe_str_conversion(node: Any) -> Optional[str]:
    """Safely convert any object to string.

    Args:
        node: Object to convert

    Returns:
        String representation or None if conversion fails
    """
    try:
        return str(node)
    except Exception:
        return None


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


def _normalize_type_input(type_value: Any) -> Optional[str]:
    """Normalize a type input value to string or None.

    Args:
        type_value: Any value that represents a type

    Returns:
        String representation or None
    """
    if type_value is None:
        return None
    if isinstance(type_value, str):
        return type_value
    return str(type_value)


# ============================================================================
# CONSTANTS
# ============================================================================

# Type string constants for parsing and normalization
_OPTIONAL_PREFIX = "Optional["
_UNION_PREFIX = "Union["
_BRACKET_OPEN = "["
_BRACKET_CLOSE = "]"
_COMMA = ","
_PIPE = "|"
_SPACE = " "
_NONE_TYPE = "None"

# Artifact kind constants - determines validation behavior
_ARTIFACT_KIND_TYPE = "type"  # Compile-time only artifacts
_ARTIFACT_KIND_RUNTIME = "runtime"  # Runtime behavioral artifacts
_TYPEDDICT_INDICATOR = "TypedDict"  # Marker for TypedDict classes

# Artifact type constants - categorization of code elements
_ARTIFACT_TYPE_CLASS = "class"
_ARTIFACT_TYPE_FUNCTION = "function"
_ARTIFACT_TYPE_ATTRIBUTE = "attribute"

# Validation mode constants - how validation is performed
_VALIDATION_MODE_BEHAVIORAL = "behavioral"  # Test usage validation
_VALIDATION_MODE_IMPLEMENTATION = "implementation"  # Code definition validation


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
    if type_str is None:
        return None

    # Clean and prepare the string
    type_str = type_str.strip()
    if not type_str:
        return type_str

    # Apply normalization pipeline
    normalized = type_str.replace(_SPACE, "")  # Remove all spaces first
    normalized = _normalize_modern_union_syntax(normalized)
    normalized = _normalize_optional_type(normalized)
    normalized = _normalize_union_type(normalized)
    normalized = _normalize_comma_spacing(normalized)

    return normalized


def _normalize_modern_union_syntax(type_str: str) -> str:
    """Convert modern union syntax (X | Y) to Union[X, Y].

    Args:
        type_str: Type string that may contain pipe union operators

    Returns:
        Type string with Union[...] syntax instead of pipes
    """
    if _PIPE not in type_str:
        return type_str

    # Split by pipe at top level only (respecting bracket nesting)
    parts = _split_by_delimiter(type_str, _PIPE)

    # Convert to Union syntax if multiple parts found
    if len(parts) > 1:
        return f"{_UNION_PREFIX}{_COMMA.join(parts)}{_BRACKET_CLOSE}"

    return type_str


def _normalize_optional_type(type_str: str) -> str:
    """Convert Optional[X] to Union[X, None].

    Args:
        type_str: Type string that may contain Optional[...]

    Returns:
        Type string with Union[X, None] instead of Optional[X]
    """
    if not _is_optional_type(type_str):
        return type_str

    inner_type = _extract_bracketed_content(type_str, _OPTIONAL_PREFIX)
    return f"{_UNION_PREFIX}{inner_type},{_NONE_TYPE}{_BRACKET_CLOSE}"


def _is_optional_type(type_str: str) -> bool:
    """Check if a type string represents Optional[...] type."""
    return type_str.startswith(_OPTIONAL_PREFIX) and type_str.endswith(_BRACKET_CLOSE)


def _extract_bracketed_content(type_str: str, prefix: str) -> str:
    """Extract content between prefix and closing bracket.

    Args:
        type_str: Full type string
        prefix: Prefix to remove (e.g., 'Optional[', 'Union[')

    Returns:
        Content between prefix and closing bracket
    """
    return type_str[len(prefix) : -1]


def _normalize_union_type(type_str: str) -> str:
    """Sort Union type members alphabetically.

    Args:
        type_str: Type string that may contain Union[...]

    Returns:
        Type string with Union members sorted alphabetically
    """
    if not _is_union_type(type_str):
        return type_str

    inner = _extract_bracketed_content(type_str, _UNION_PREFIX)
    members = _split_type_arguments(inner)
    members.sort()
    return f"{_UNION_PREFIX}{_COMMA.join(members)}{_BRACKET_CLOSE}"


def _is_union_type(type_str: str) -> bool:
    """Check if a type string represents Union[...] type."""
    return type_str.startswith(_UNION_PREFIX) and type_str.endswith(_BRACKET_CLOSE)


def _split_type_arguments(inner: str) -> list:
    """Split type arguments by comma, respecting nested brackets.

    Args:
        inner: String containing comma-separated type arguments

    Returns:
        List of individual type argument strings
    """
    return _split_by_delimiter(inner, _COMMA)


def _split_by_delimiter(text: str, delimiter: str) -> list:
    """Split text by delimiter at top level, respecting bracket nesting.

    This utility function handles splitting strings that contain nested
    brackets, ensuring we only split at the top level.

    Args:
        text: String to split
        delimiter: Character(s) to split by

    Returns:
        List of split parts with whitespace trimmed
    """
    if not text:
        return []

    parts = []
    current = ""
    bracket_depth = 0

    for char in text:
        if char == _BRACKET_OPEN:
            bracket_depth += 1
        elif char == _BRACKET_CLOSE:
            bracket_depth -= 1
        elif char == delimiter and bracket_depth == 0:
            parts.append(current.strip())
            current = ""
            continue

        current += char

    if current:
        parts.append(current.strip())

    return parts


def _normalize_comma_spacing(type_str: str) -> str:
    """Normalize spacing after commas in generic types.

    Ensures consistent formatting like Dict[str, int] instead of
    Dict[str,int] or Dict[str,  int].

    Args:
        type_str: Type string to normalize

    Returns:
        Type string with normalized comma spacing
    """
    if _COMMA not in type_str:
        return type_str

    result = []
    bracket_depth = 0
    i = 0

    while i < len(type_str):
        char = type_str[i]

        if char == _BRACKET_OPEN:
            bracket_depth += 1
            result.append(char)
        elif char == _BRACKET_CLOSE:
            bracket_depth -= 1
            result.append(char)
        elif char == _COMMA and bracket_depth > 0:
            # Add comma with single space
            result.append(_COMMA)
            result.append(_SPACE)
            # Skip any following spaces
            i = _skip_spaces(type_str, i + 1) - 1
        else:
            result.append(char)

        i += 1

    return "".join(result)


def _skip_spaces(text: str, start_idx: int) -> int:
    """Skip whitespace characters starting from given index.

    Args:
        text: String to process
        start_idx: Starting index

    Returns:
        Index of first non-space character or end of string
    """
    idx = start_idx
    while idx < len(text) and text[idx] == _SPACE:
        idx += 1
    return idx


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
        """Collect imported class names from local modules only."""
        if not node.names:
            self.generic_visit(node)
            return

        # Determine if this is a local import
        is_local = self._is_local_import(node)

        # Process each imported name
        for alias in node.names:
            if is_local and self._is_class_name(alias.name):
                self.found_classes.add(alias.name)

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
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                # Handle cases like module.ClassName (e.g., ast.NodeVisitor)
                # Build the full qualified name
                parts = []
                current = base
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                # Reconstruct in correct order (reversed)
                full_name = ".".join(reversed(parts))
                base_names.append(full_name)

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
        if not (
            isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
        ):
            return

        class_name = node.value.func.id
        if class_name in self.found_classes:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.variable_to_class[target.id] = class_name

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
                    if var_name in self.variable_to_class:
                        class_name = self.variable_to_class[var_name]
                        if class_name not in self.used_methods:
                            self.used_methods[class_name] = set()
                        self.used_methods[class_name].add(method_name)
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
                        if class_name not in self.used_methods:
                            self.used_methods[class_name] = set()
                        self.used_methods[class_name].add(method_name)
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


def discover_related_manifests(target_file):
    """
    Discover all manifests that have touched the target file.

    This is a public API function that can be used by other modules
    to find manifests related to a specific file.

    Args:
        target_file: Path to the file to check

    Returns:
        List of manifest paths in chronological order
    """
    manifests = []
    manifest_dir = Path("manifests")

    if not manifest_dir.exists():
        return manifests

    # Get all JSON files and sort numerically by task number
    manifest_files = list(manifest_dir.glob("*.json"))

    def _get_task_number(path):
        """Extract task number from filename like task-XXX-description.json"""
        stem = path.stem
        # Handle .manifest.json files by removing .manifest suffix
        if stem.endswith(".manifest"):
            stem = stem[:-9]  # Remove '.manifest' suffix

        if stem.startswith("task-"):
            try:
                # Split by '-' and get the number part (second element)
                parts = stem.split("-")
                if len(parts) >= 2:
                    return int(parts[1])
            except (ValueError, IndexError):
                pass
        return float("inf")  # Put non-task files at the end

    # Sort manifest files numerically (supports task-1 through task-999999+)
    manifest_files.sort(key=_get_task_number)

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

    return manifests


def _merge_expected_artifacts(manifest_paths):
    """
    Merge expected artifacts from multiple manifests.

    Args:
        manifest_paths: List of paths to manifest files

    Returns:
        Merged list of expected artifacts
    """
    merged_artifacts = []
    seen_artifacts = {}  # Track (type, name) -> artifact

    for path in manifest_paths:
        with open(path, "r") as f:
            data = json.load(f)

        artifacts = data.get("expectedArtifacts", {}).get("contains", [])

        for artifact in artifacts:
            # Use (type, name) as unique key
            artifact_type = artifact.get("type")
            artifact_name = artifact.get("name")
            key = (artifact_type, artifact_name)

            # Add if not seen, or always update (later manifests override earlier ones)
            # This ensures that modifications in later tasks override earlier definitions
            seen_artifacts[key] = artifact

    # Return artifacts in a consistent order
    merged_artifacts = list(seen_artifacts.values())
    return merged_artifacts


def validate_with_ast(
    manifest_data, test_file_path, use_manifest_chain=False, validation_mode=None
):
    """
    Validate that artifacts listed in manifest are referenced in the test file.

    Args:
        manifest_data: Dictionary containing the manifest with expectedArtifacts
        test_file_path: Path to the Python test file to analyze
        use_manifest_chain: If True, discovers and merges all related manifests
        validation_mode: _VALIDATION_MODE_IMPLEMENTATION or _VALIDATION_MODE_BEHAVIORAL mode, auto-detected if None

    Raises:
        AlignmentError: If any expected artifact is not found in the code
    """
    # Parse and collect artifacts from the code
    tree = _parse_file(test_file_path)
    validation_mode = validation_mode or _VALIDATION_MODE_IMPLEMENTATION
    collector = _collect_artifacts_from_ast(tree, validation_mode)

    # Get expected artifacts
    expected_items = _get_expected_artifacts(
        manifest_data, test_file_path, use_manifest_chain
    )

    # Validate all expected artifacts
    _validate_all_artifacts(expected_items, collector, validation_mode)

    # Check for unexpected public artifacts (strict mode)
    _check_unexpected_artifacts(expected_items, collector)


def _parse_file(file_path: str) -> ast.AST:
    """Parse a Python file into an AST.

    Args:
        file_path: Path to the Python file

    Returns:
        Parsed AST tree
    """
    with open(file_path, "r") as f:
        code = f.read()
    return ast.parse(code)


def _collect_artifacts_from_ast(
    tree: ast.AST, validation_mode: str
) -> "_ArtifactCollector":
    """Collect artifacts from an AST tree.

    Args:
        tree: Parsed AST tree
        validation_mode: Mode for validation

    Returns:
        Collector with discovered artifacts
    """
    collector = _ArtifactCollector(validation_mode=validation_mode)
    collector.visit(tree)
    return collector


def _get_expected_artifacts(
    manifest_data: dict, test_file_path: str, use_manifest_chain: bool
) -> List[dict]:
    """Get expected artifacts from manifest(s).

    Args:
        manifest_data: Manifest data dictionary
        test_file_path: Path to file being validated
        use_manifest_chain: Whether to use manifest chain

    Returns:
        List of expected artifact definitions
    """
    if use_manifest_chain:
        target_file = manifest_data.get("expectedArtifacts", {}).get(
            "file", test_file_path
        )
        related_manifests = discover_related_manifests(target_file)
        return _merge_expected_artifacts(related_manifests)
    else:
        expected_artifacts = manifest_data.get("expectedArtifacts", {})
        return expected_artifacts.get("contains", [])


def _validate_all_artifacts(
    expected_items: List[dict], collector: "_ArtifactCollector", validation_mode: str
) -> None:
    """Validate all expected artifacts exist in the code.

    Args:
        expected_items: List of expected artifacts
        collector: Artifact collector with discovered artifacts
        validation_mode: Validation mode

    Raises:
        AlignmentError: If any expected artifact is not found
    """
    for artifact in expected_items:
        # Skip type-only artifacts in behavioral validation
        if (
            validation_mode == _VALIDATION_MODE_BEHAVIORAL
            and should_skip_behavioral_validation(artifact)
        ):
            continue

        _validate_single_artifact(artifact, collector, validation_mode)


def _check_unexpected_artifacts(
    expected_items: List[dict], collector: "_ArtifactCollector"
) -> None:
    """Check for unexpected public artifacts in strict mode.

    Args:
        expected_items: List of expected artifacts
        collector: Artifact collector with discovered artifacts

    Raises:
        AlignmentError: If unexpected public artifacts are found
    """
    # Skip strict validation for test files
    is_test_file = any(func.startswith("test_") for func in collector.found_functions)

    if expected_items and not is_test_file:
        _validate_no_unexpected_artifacts(
            expected_items, collector.found_classes, collector.found_functions
        )


def _validate_single_artifact(
    artifact: dict, collector: "_ArtifactCollector", validation_mode: str
) -> None:
    """Validate a single artifact.

    Args:
        artifact: Artifact definition
        collector: Artifact collector
        validation_mode: Validation mode

    Raises:
        AlignmentError: If artifact is not found or invalid
    """
    artifact_type = artifact.get("type")
    artifact_name = artifact.get("name")

    if artifact_type == _ARTIFACT_TYPE_CLASS:
        expected_bases = artifact.get("bases", [])
        if validation_mode == _VALIDATION_MODE_BEHAVIORAL:
            # In behavioral mode, check if class was used
            if artifact_name not in collector.used_classes:
                raise AlignmentError(
                    f"Class '{artifact_name}' not used in behavioral test"
                )
        else:
            # In implementation mode, check definitions
            _validate_class(
                artifact_name,
                expected_bases,
                collector.found_classes,
                collector.found_class_bases,
            )

    elif artifact_type == _ARTIFACT_TYPE_ATTRIBUTE:
        parent_class = artifact.get("class")
        _validate_attribute(artifact_name, parent_class, collector.found_attributes)

    elif artifact_type == _ARTIFACT_TYPE_FUNCTION:
        _validate_function_artifact(artifact, collector, validation_mode)


def _validate_function_artifact(
    artifact: dict, collector: "_ArtifactCollector", validation_mode: str
) -> None:
    """Validate a function or method artifact.

    Args:
        artifact: Function/method artifact definition
        collector: Artifact collector
        validation_mode: Validation mode

    Raises:
        AlignmentError: If function/method is not found or invalid
    """
    artifact_name = artifact.get("name")
    parameters = artifact.get("parameters", [])
    parent_class = artifact.get("class")

    if validation_mode == _VALIDATION_MODE_BEHAVIORAL:
        _validate_function_behavioral(
            artifact_name, parameters, parent_class, artifact, collector
        )
    else:
        _validate_function_implementation(
            artifact_name, parameters, parent_class, collector
        )


def _validate_function_behavioral(
    artifact_name: str,
    parameters: List[dict],
    parent_class: Optional[str],
    artifact: dict,
    collector: "_ArtifactCollector",
) -> None:
    """Validate function/method in behavioral mode."""
    if parent_class:
        # It's a method
        if parent_class not in collector.used_methods:
            raise AlignmentError(
                f"Class '{parent_class}' not used or method '{artifact_name}' not called"
            )
        if artifact_name not in collector.used_methods[parent_class]:
            raise AlignmentError(
                f"Method '{artifact_name}' not called on class '{parent_class}'"
            )
    else:
        # It's a standalone function
        if artifact_name not in collector.used_functions:
            raise AlignmentError(
                f"Function '{artifact_name}' not called in behavioral test"
            )

    # Validate parameters were used
    _validate_parameters_used(parameters, artifact_name, collector)

    # Validate return type if specified
    returns = artifact.get("returns")
    if returns and returns not in collector.used_classes:
        raise AlignmentError(
            f"Return type '{returns}' not validated for '{artifact_name}'"
        )


def _validate_parameters_used(
    parameters: List[dict], artifact_name: str, collector: "_ArtifactCollector"
) -> None:
    """Validate parameters were used in function calls."""
    if not parameters:
        return

    # If we have positional arguments, we can't reliably check parameter names
    # Only check keyword arguments
    for param in parameters:
        param_name = param.get("name")
        if param_name:
            # Skip checking if positional args were used
            if "__positional__" not in collector.used_arguments:
                if param_name not in collector.used_arguments:
                    raise AlignmentError(
                        f"Parameter '{param_name}' not used in call to '{artifact_name}'"
                    )


def _validate_function_implementation(
    artifact_name: str,
    parameters: List[dict],
    parent_class: Optional[str],
    collector: "_ArtifactCollector",
) -> None:
    """Validate function/method in implementation mode."""
    if parent_class:
        # It's a method
        if parent_class not in collector.found_methods:
            raise AlignmentError(
                f"Class '{parent_class}' not found for method '{artifact_name}'"
            )
        if artifact_name not in collector.found_methods[parent_class]:
            raise AlignmentError(
                f"Method '{artifact_name}' not found in class '{parent_class}'"
            )

        # Validate method parameters
        if parameters:
            _validate_method_parameters(
                artifact_name, parameters, parent_class, collector
            )
    else:
        # It's a standalone function
        _validate_function(artifact_name, parameters, collector.found_functions)


def _validate_method_parameters(
    method_name: str,
    parameters: List[dict],
    class_name: str,
    collector: "_ArtifactCollector",
) -> None:
    """Validate method parameters match expectations."""
    actual_parameters = collector.found_methods[class_name][method_name]

    # Skip 'self' parameter for methods
    if "self" in actual_parameters:
        actual_parameters = [p for p in actual_parameters if p != "self"]

    expected_param_names = [p["name"] for p in parameters]

    # Check all expected parameters are present
    for param_name in expected_param_names:
        if param_name not in actual_parameters:
            raise AlignmentError(
                f"Parameter '{param_name}' not found in method '{method_name}'"
            )


def _validate_class(class_name, expected_bases, found_classes, found_class_bases):
    """Validate that a class is referenced in the code with the expected base classes."""
    if class_name not in found_classes:
        raise AlignmentError(f"Artifact '{class_name}' not found")

    # Check base classes if specified
    if expected_bases:
        actual_bases = found_class_bases.get(class_name, [])
        for expected_base in expected_bases:
            # Check if expected base matches either the full name or just the class name part
            found = False
            for actual_base in actual_bases:
                # Match exact name or match the last component (for qualified names)
                if (
                    actual_base == expected_base
                    or actual_base.split(".")[-1] == expected_base
                ):
                    found = True
                    break
            if not found:
                raise AlignmentError(
                    f"Class '{class_name}' does not inherit from '{expected_base}'"
                )


def _validate_attribute(attribute_name, parent_class, found_attributes):
    """Validate that an attribute is referenced for a specific class."""
    class_attributes = found_attributes.get(parent_class, set())

    if attribute_name not in class_attributes:
        raise AlignmentError(f"Artifact '{attribute_name}' not found")


def _validate_function(function_name, expected_parameters, found_functions):
    """Validate that a function exists with the expected parameters."""
    if function_name not in found_functions:
        raise AlignmentError(f"Artifact '{function_name}' not found")

    # Check parameters if specified
    if expected_parameters:
        actual_parameters = found_functions[function_name]

        expected_param_names = [p["name"] for p in expected_parameters]

        # Check all expected parameters are present
        for param_name in expected_param_names:
            if param_name not in actual_parameters:
                raise AlignmentError(
                    f"Parameter '{param_name}' not found in function '{function_name}'"
                )

        # Check for unexpected parameters (strict validation)
        unexpected_params = set(actual_parameters) - set(expected_param_names)
        if unexpected_params:
            raise AlignmentError(
                f"Unexpected parameter(s) in function '{function_name}': {', '.join(sorted(unexpected_params))}"
            )


def _validate_no_unexpected_artifacts(expected_items, found_classes, found_functions):
    """Validate that no unexpected public artifacts exist in the code."""
    # Build sets of expected names
    expected_classes = {
        item["name"] for item in expected_items if item.get("type") == "class"
    }
    expected_functions = {
        item["name"] for item in expected_items if item.get("type") == "function"
    }

    # Check for unexpected public classes (exclude private ones starting with _)
    public_classes = {cls for cls in found_classes if not cls.startswith("_")}
    unexpected_classes = public_classes - expected_classes
    if unexpected_classes:
        raise AlignmentError(
            f"Unexpected public class(es) found: {', '.join(sorted(unexpected_classes))}"
        )

    # Check for unexpected public functions (exclude private ones starting with _)
    public_functions = {func for func in found_functions if not func.startswith("_")}
    unexpected_functions = public_functions - expected_functions
    if unexpected_functions:
        raise AlignmentError(
            f"Unexpected public function(s) found: {', '.join(sorted(unexpected_functions))}"
        )


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


def _are_valid_type_validation_inputs(
    manifest_artifacts: Any, implementation_artifacts: Any
) -> bool:
    """Check if inputs are valid for type validation.

    Args:
        manifest_artifacts: Potentially a dict with manifest data
        implementation_artifacts: Potentially a dict with implementation data

    Returns:
        True if both inputs are valid dictionaries
    """
    return (
        manifest_artifacts is not None
        and isinstance(manifest_artifacts, dict)
        and implementation_artifacts is not None
        and isinstance(implementation_artifacts, dict)
    )


def _should_validate_artifact_types(artifact: Any) -> bool:
    """Check if an artifact should have its types validated.

    Args:
        artifact: Artifact definition from manifest

    Returns:
        True if artifact is a function/method that should be validated
    """
    return (
        isinstance(artifact, dict) and artifact.get("type") == _ARTIFACT_TYPE_FUNCTION
    )


def _validate_function_types(artifact: dict, implementation_artifacts: dict) -> list:
    """Validate type hints for a single function or method artifact.

    Args:
        artifact: Manifest artifact definition
        implementation_artifacts: Collected implementation type information

    Returns:
        List of validation error messages
    """
    # Early return for invalid inputs
    if not isinstance(artifact, dict):
        return []

    artifact_name = artifact.get("name")
    if not artifact_name:
        return []

    parent_class = artifact.get("class")

    # Get implementation info
    impl_info = _get_implementation_info(
        artifact_name, parent_class, implementation_artifacts
    )

    if not impl_info:
        return []  # No implementation to validate against

    # Collect all validation errors
    errors = []

    # Validate parameters
    errors.extend(
        _validate_parameter_types(artifact, impl_info, artifact_name, parent_class)
    )

    # Validate return type
    return_error = _validate_return_type(
        artifact, impl_info, artifact_name, parent_class
    )
    if return_error:
        errors.append(return_error)

    return errors


def _get_implementation_info(
    artifact_name: str, parent_class: Optional[str], implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a function or method.

    Args:
        artifact_name: Name of the function or method
        parent_class: Parent class name if method, None if function
        implementation_artifacts: Collected implementation information

    Returns:
        Dictionary with type information, or None if not found
    """
    if not isinstance(implementation_artifacts, dict):
        return None

    if parent_class:
        return _get_method_info(artifact_name, parent_class, implementation_artifacts)
    else:
        return _get_function_info(artifact_name, implementation_artifacts)


def _get_method_info(
    method_name: str, class_name: str, implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a method.

    Args:
        method_name: Name of the method
        class_name: Name of the parent class
        implementation_artifacts: Collected implementation information

    Returns:
        Dictionary with method type information, or None if not found
    """
    methods = implementation_artifacts.get("methods", {})
    if not isinstance(methods, dict):
        return None

    class_methods = methods.get(class_name)
    if not isinstance(class_methods, dict):
        return None

    return class_methods.get(method_name, {})


def _get_function_info(
    function_name: str, implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a standalone function.

    Args:
        function_name: Name of the function
        implementation_artifacts: Collected implementation information

    Returns:
        Dictionary with function type information, or None if not found
    """
    functions = implementation_artifacts.get("functions", {})
    if not isinstance(functions, dict):
        return None

    func_info = functions.get(function_name, {})
    if not isinstance(func_info, dict):
        return None

    return func_info


def _validate_parameter_types(
    artifact: dict, impl_info: dict, artifact_name: str, parent_class: str
) -> list:
    """Validate parameter types match between manifest and implementation.

    Args:
        artifact: Manifest artifact definition
        impl_info: Implementation type information
        artifact_name: Name of the function/method
        parent_class: Parent class name if method, None if function

    Returns:
        List of validation error messages
    """
    errors = []
    manifest_params = artifact.get("parameters", [])
    impl_params = impl_info.get("parameters", [])

    # Create lookup for implementation parameters
    impl_params_dict = {p.get("name"): p for p in impl_params}

    for manifest_param in manifest_params:
        param_name = manifest_param.get("name")
        manifest_type = manifest_param.get("type")

        if not manifest_type:
            continue  # No type to validate

        error = _validate_single_parameter(
            param_name, manifest_type, impl_params_dict, artifact_name, parent_class
        )
        if error:
            errors.append(error)

    return errors


def _validate_single_parameter(
    param_name: str,
    manifest_type: str,
    impl_params_dict: dict,
    artifact_name: str,
    parent_class: Optional[str],
) -> Optional[str]:
    """Validate a single parameter's type annotation.

    Args:
        param_name: Parameter name
        manifest_type: Expected type from manifest
        impl_params_dict: Implementation parameters by name
        artifact_name: Function/method name
        parent_class: Parent class or None

    Returns:
        Error message if validation fails, None otherwise
    """
    entity_type = "method" if parent_class else "function"

    impl_param = impl_params_dict.get(param_name)
    if not impl_param:
        return (
            f"Missing type annotation for parameter '{param_name}' "
            f"in {entity_type} '{artifact_name}'"
        )

    impl_type = impl_param.get("type")
    if not compare_types(manifest_type, impl_type):
        return (
            f"Type mismatch for parameter '{param_name}' in {entity_type} "
            f"'{artifact_name}': expected '{manifest_type}', got '{impl_type}'"
        )

    return None


def _validate_return_type(
    artifact: dict, impl_info: dict, artifact_name: str, parent_class: Optional[str]
) -> Optional[str]:
    """Validate return type matches between manifest and implementation.

    Args:
        artifact: Manifest artifact definition
        impl_info: Implementation type information
        artifact_name: Name of the function/method
        parent_class: Parent class name if method, None if function

    Returns:
        Error message if validation fails, None otherwise
    """
    manifest_return = artifact.get("returns")
    if not manifest_return:
        return None

    impl_return = impl_info.get("returns")
    if not compare_types(manifest_return, impl_return):
        entity_type = "method" if parent_class else "function"
        return (
            f"Type mismatch for return type in {entity_type} '{artifact_name}': "
            f"expected '{manifest_return}', got '{impl_return}'"
        )

    return None


def _is_typeddict_class(artifact: dict) -> bool:
    """
    Check if an artifact represents a TypedDict class.

    TypedDict classes are special type-only constructs that don't
    have runtime behavior and should be skipped during behavioral
    validation.

    Args:
        artifact: Dictionary containing artifact metadata

    Returns:
        True if artifact is a TypedDict class, False otherwise
    """
    if artifact.get("type") != _ARTIFACT_TYPE_CLASS:
        return False

    bases = artifact.get("bases")
    if not bases:
        return False

    # Check if any base class indicates TypedDict
    return any(_is_typeddict_base(base) for base in bases if base)


def _is_typeddict_base(base_name: str) -> bool:
    """Check if a base class name indicates TypedDict.

    Args:
        base_name: Name of the base class

    Returns:
        True if base class is TypedDict
    """
    return base_name and _TYPEDDICT_INDICATOR in base_name


def should_skip_behavioral_validation(artifact: Any) -> bool:
    """
    Determine if an artifact should be skipped during behavioral validation.

    Type-only artifacts (like TypedDict classes, type aliases) are compile-time
    constructs that shouldn't be behaviorally validated as they don't have runtime
    behavior that can be tested.

    Args:
        artifact: Dictionary containing artifact metadata

    Returns:
        True if artifact should be skipped, False if it should be validated
    """
    if not artifact:
        return False

    # Check explicit artifact kind first
    skip_by_kind = _should_skip_by_artifact_kind(artifact)
    if skip_by_kind is not None:
        return skip_by_kind

    # Auto-detect type-only patterns
    if _is_typeddict_class(artifact):
        return True

    # Default to runtime validation
    return False


def _should_skip_by_artifact_kind(artifact: dict) -> Optional[bool]:
    """Check if artifact kind explicitly indicates skip behavior.

    Args:
        artifact: Artifact metadata dictionary

    Returns:
        True to skip, False to validate, None if not explicitly specified
    """
    artifact_kind = artifact.get("artifactKind")

    if artifact_kind == _ARTIFACT_KIND_TYPE:
        return True
    elif artifact_kind == _ARTIFACT_KIND_RUNTIME:
        return False
    elif artifact_kind is not None:
        # Invalid values default to runtime (validate)
        return False

    return None  # No explicit specification
