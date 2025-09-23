import ast
import json
from pathlib import Path
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


def extract_type_annotation(node: ast.AST, annotation_attr: str = "annotation") -> str:
    """
    Extract type annotation string from an AST node.

    Args:
        node: AST node to extract type annotation from
        annotation_attr: Name of the attribute containing the annotation

    Returns:
        String representation of the type annotation, or None if not present
    """
    annotation = getattr(node, annotation_attr, None)

    if annotation is None:
        return None

    return _ast_to_type_string(annotation)


def _ast_to_type_string(node):
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

    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Constant):
        # Handle string constants (for forward references)
        return str(node.value)

    if isinstance(node, ast.Subscript):
        # Handle generic types like List[str], Dict[str, int]
        base = _ast_to_type_string(node.value)

        # Handle the subscript part (what's inside the brackets)
        if isinstance(node.slice, ast.Tuple):
            # Multiple type arguments like Dict[str, int]
            args = [_ast_to_type_string(elt) for elt in node.slice.elts]
            return f"{base}[{', '.join(args)}]"
        else:
            # Single type argument like List[str]
            arg = _ast_to_type_string(node.slice)
            return f"{base}[{arg}]"

    if isinstance(node, ast.Attribute):
        # Handle qualified names like typing.Optional
        value = _ast_to_type_string(node.value)
        return f"{value}.{node.attr}" if value else node.attr

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # Handle Union types using | operator (Python 3.10+)
        left = _ast_to_type_string(node.left)
        right = _ast_to_type_string(node.right)
        return f"Union[{left}, {right}]"

    if isinstance(node, ast.Ellipsis):
        return "..."

    # Fallback: try to get the source representation
    try:
        return ast.unparse(node)
    except (AttributeError, TypeError):
        return str(node)


def compare_types(manifest_type: str, implementation_type: str) -> bool:
    """
    Compare two type strings for equivalence.

    Args:
        manifest_type: Type string from manifest
        implementation_type: Type string from implementation

    Returns:
        True if types are equivalent, False otherwise
    """
    # Handle None cases
    if manifest_type is None and implementation_type is None:
        return True
    if manifest_type is None or implementation_type is None:
        return False

    # Normalize both types
    norm_manifest = normalize_type_string(manifest_type)
    norm_impl = normalize_type_string(implementation_type)

    return norm_manifest == norm_impl


# Type string constants
_OPTIONAL_PREFIX = "Optional["
_UNION_PREFIX = "Union["
_BRACKET_OPEN = "["
_BRACKET_CLOSE = "]"
_COMMA = ","


def normalize_type_string(type_str: str) -> str:
    """
    Normalize a type string for consistent comparison.

    Performs the following normalizations:
    - Removes extra whitespace
    - Converts Optional[X] to Union[X, None]
    - Sorts Union members alphabetically
    - Ensures consistent comma spacing in generic types

    Args:
        type_str: Type string to normalize

    Returns:
        Normalized type string
    """
    if type_str is None:
        return None

    # Remove extra spaces
    normalized = type_str.strip().replace(" ", "")

    # Convert Optional[X] to Union[X, None]
    normalized = _normalize_optional_type(normalized)

    # Handle Union types - sort members alphabetically
    normalized = _normalize_union_type(normalized)

    # Normalize spacing after commas in generic types
    return _normalize_comma_spacing(normalized)


def _normalize_optional_type(type_str: str) -> str:
    """Convert Optional[X] to Union[X, None]."""
    if not (
        type_str.startswith(_OPTIONAL_PREFIX) and type_str.endswith(_BRACKET_CLOSE)
    ):
        return type_str

    optional_len = len(_OPTIONAL_PREFIX)
    inner_type = type_str[optional_len:-1]
    return f"Union[{inner_type},None]"


def _normalize_union_type(type_str: str) -> str:
    """Sort Union type members alphabetically."""
    if not (type_str.startswith(_UNION_PREFIX) and type_str.endswith(_BRACKET_CLOSE)):
        return type_str

    union_len = len(_UNION_PREFIX)
    inner = type_str[union_len:-1]

    # Split by comma, handling nested types
    members = _split_type_arguments(inner)
    members.sort()
    return f"Union[{','.join(members)}]"


def _split_type_arguments(inner: str) -> list:
    """Split type arguments by comma, respecting nested brackets."""
    members = []
    current = ""
    bracket_depth = 0

    for char in inner:
        if char == _BRACKET_OPEN:
            bracket_depth += 1
        elif char == _BRACKET_CLOSE:
            bracket_depth -= 1
        elif char == _COMMA and bracket_depth == 0:
            members.append(current.strip())
            current = ""
            continue

        current += char

    if current:
        members.append(current.strip())

    return members


def _normalize_comma_spacing(type_str: str) -> str:
    """
    Normalize spacing after commas in generic types.
    This handles Dict[str,int] vs Dict[str, int].
    """
    result = ""
    bracket_depth = 0
    i = 0

    while i < len(type_str):
        char = type_str[i]

        if char == _BRACKET_OPEN:
            bracket_depth += 1
            result += char
        elif char == _BRACKET_CLOSE:
            bracket_depth -= 1
            result += char
        elif char == _COMMA and bracket_depth > 0:
            # Add comma with consistent spacing
            result += ", "
            # Skip any spaces after the comma in the original
            i += 1
            while i < len(type_str) and type_str[i] == " ":
                i += 1
            i -= 1  # Back up one since the loop will increment
        else:
            result += char

        i += 1

    return result


class _ArtifactCollector(ast.NodeVisitor):
    """AST visitor that collects class and attribute references from Python code."""

    def __init__(self, validation_mode="implementation"):
        self.validation_mode = validation_mode  # "implementation" or "behavioral"
        self.found_classes = set()
        self.found_class_bases = {}  # class_name -> list of base class names
        self.found_attributes = {}  # class_name -> set of attribute names
        self.variable_to_class = {}  # variable_name -> class_name
        self.found_functions = {}  # function_name -> list of parameter names
        self.found_methods = (
            {}
        )  # class_name -> {method_name -> list of parameter names}
        self.current_class = None  # Track if we're inside a class definition

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
        if node.names:
            # Check if this is importing from a local module (relative import or local package)
            is_local = node.level > 0 or (
                node.module
                and not node.module.startswith(
                    (
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
                )
            )

            for alias in node.names:
                # Classes typically start with uppercase
                if alias.name and alias.name[0].isupper() and is_local:
                    self.found_classes.add(alias.name)
                # Don't track imported functions as they're external dependencies
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        """Collect function definitions and their parameters."""
        param_names = [arg.arg for arg in node.args.args]

        # Extract parameter types
        param_types = []
        for arg in node.args.args:
            param_info = {
                "name": arg.arg,
                "type": extract_type_annotation(arg, "annotation"),
            }
            param_types.append(param_info)

        # Extract return type
        return_type = extract_type_annotation(node, "returns")

        if self.current_class is None:
            # Module-level function
            self.found_functions[node.name] = param_names
            self.found_function_types[node.name] = {
                "parameters": param_types,
                "returns": return_type,
            }
        else:
            # Method inside a class
            if self.current_class not in self.found_methods:
                self.found_methods[self.current_class] = {}
            self.found_methods[self.current_class][node.name] = param_names

            if self.current_class not in self.found_method_types:
                self.found_method_types[self.current_class] = {}
            self.found_method_types[self.current_class][node.name] = {
                "parameters": param_types,
                "returns": return_type,
            }

        # Continue visiting child nodes
        self.generic_visit(node)

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
        """Track variable assignments to class instances and self attributes."""
        # Track self.attribute = value assignments inside classes
        if self.current_class:
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(
                    target.value, ast.Name
                ):
                    if target.value.id == "self":
                        # Track as an attribute of the current class
                        if self.current_class not in self.found_attributes:
                            self.found_attributes[self.current_class] = set()
                        self.found_attributes[self.current_class].add(target.attr)

        # Track variable assignments to class instances
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            class_name = node.value.func.id

            # Only track if this is a known class
            if class_name in self.found_classes:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.variable_to_class[target.id] = class_name

        self.generic_visit(node)

    def visit_Attribute(self, node):
        """Collect attribute accesses on class instances."""
        if isinstance(node.value, ast.Name):
            variable_name = node.value.id
            attribute_name = node.attr

            # Map attribute to its class if we know the variable's type
            if variable_name in self.variable_to_class:
                class_name = self.variable_to_class[variable_name]

                if class_name not in self.found_attributes:
                    self.found_attributes[class_name] = set()

                self.found_attributes[class_name].add(attribute_name)

        self.generic_visit(node)

    def visit_Call(self, node):
        """Track function and method calls in behavioral tests."""
        if self.validation_mode == "behavioral":
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
                        class_name and class_name[0].isupper()
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
                    func_name and func_name[0].isupper()
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


def _discover_related_manifests(target_file):
    """
    Discover all manifests that have touched the target file.

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
        validation_mode: "implementation" or "behavioral" mode, auto-detected if None

    Raises:
        AlignmentError: If any expected artifact is not found in the code
    """
    # Parse the test file into an AST
    with open(test_file_path, "r") as f:
        test_code = f.read()

    tree = ast.parse(test_code)

    # Auto-detect validation mode if not specified
    if validation_mode is None:
        # Default to implementation mode
        # Behavioral mode should be explicitly requested for now
        # This ensures backward compatibility with existing tests
        validation_mode = "implementation"

    # Collect artifacts from the test code
    collector = _ArtifactCollector(validation_mode=validation_mode)
    collector.visit(tree)

    # Determine expected artifacts based on mode
    if use_manifest_chain:
        # Discover all manifests that touched this file
        target_file = manifest_data.get("expectedArtifacts", {}).get(
            "file", test_file_path
        )
        related_manifests = _discover_related_manifests(target_file)

        # Merge artifacts from all related manifests
        expected_items = _merge_expected_artifacts(related_manifests)
    else:
        # Use single manifest mode (current behavior)
        expected_artifacts = manifest_data.get("expectedArtifacts", {})
        expected_items = expected_artifacts.get("contains", [])

    # Validate each expected artifact exists
    for artifact in expected_items:
        artifact_type = artifact.get("type")
        artifact_name = artifact.get("name")

        if artifact_type == "class":
            expected_bases = artifact.get("bases", [])
            if validation_mode == "behavioral":
                # In behavioral mode, check if class was used
                if artifact_name not in collector.used_classes:
                    raise AlignmentError(
                        f"Class '{artifact_name}' not used in behavioral test"
                    )
                # Note: Base class validation doesn't apply to usage
            else:
                # In implementation mode, check definitions
                _validate_class(
                    artifact_name,
                    expected_bases,
                    collector.found_classes,
                    collector.found_class_bases,
                )

        elif artifact_type == "attribute":
            parent_class = artifact.get("class")
            _validate_attribute(artifact_name, parent_class, collector.found_attributes)

        elif artifact_type == "function":
            parameters = artifact.get("parameters", [])
            parent_class = artifact.get("class")

            if validation_mode == "behavioral":
                # In behavioral mode, check if function/method was called
                if parent_class:
                    # It's a method
                    if parent_class in collector.used_methods:
                        if artifact_name not in collector.used_methods[parent_class]:
                            raise AlignmentError(
                                f"Method '{artifact_name}' not called on class '{parent_class}'"
                            )
                    else:
                        raise AlignmentError(
                            f"Class '{parent_class}' not used or method '{artifact_name}' not called"
                        )
                else:
                    # It's a standalone function
                    if artifact_name not in collector.used_functions:
                        raise AlignmentError(
                            f"Function '{artifact_name}' not called in behavioral test"
                        )

                # Validate parameters were used
                if parameters:
                    # If we have positional arguments, we can't reliably check parameter names
                    # Only check keyword arguments
                    for param in parameters:
                        param_name = param.get("name")
                        if param_name:
                            # Check if this specific parameter was used as a keyword argument
                            # We skip checking if positional args were used since we can't map them
                            if "__positional__" not in collector.used_arguments:
                                if param_name not in collector.used_arguments:
                                    raise AlignmentError(
                                        f"Parameter '{param_name}' not used in call to '{artifact_name}'"
                                    )

                # Validate return type if specified
                returns = artifact.get("returns")
                if returns and returns not in collector.used_classes:
                    # Return type should be validated via isinstance or type annotation
                    raise AlignmentError(
                        f"Return type '{returns}' not validated for '{artifact_name}'"
                    )
            else:
                # In implementation mode, check definitions
                if parent_class:
                    # It's a method - check in found_methods
                    if parent_class not in collector.found_methods:
                        raise AlignmentError(
                            f"Class '{parent_class}' not found for method '{artifact_name}'"
                        )
                    if artifact_name not in collector.found_methods[parent_class]:
                        raise AlignmentError(
                            f"Method '{artifact_name}' not found in class '{parent_class}'"
                        )

                    # Validate parameters if specified
                    if parameters:
                        actual_parameters = collector.found_methods[parent_class][
                            artifact_name
                        ]
                        # Skip 'self' parameter for methods
                        if "self" in actual_parameters:
                            actual_parameters = [
                                p for p in actual_parameters if p != "self"
                            ]

                        expected_param_names = [p["name"] for p in parameters]

                        # Check all expected parameters are present
                        for param_name in expected_param_names:
                            if param_name not in actual_parameters:
                                raise AlignmentError(
                                    f"Parameter '{param_name}' not found in method '{artifact_name}'"
                                )
                else:
                    # It's a standalone function
                    _validate_function(
                        artifact_name, parameters, collector.found_functions
                    )

    # Check for unexpected public artifacts (strict mode)
    # Only validate if we're checking an implementation file (not a test file)
    # Skip strict validation for test files (files with test functions)
    is_test_file = any(func.startswith("test_") for func in collector.found_functions)

    if (
        expected_items and not is_test_file
    ):  # Only enforce for non-test files with expectations
        _validate_no_unexpected_artifacts(
            expected_items, collector.found_classes, collector.found_functions
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

    Args:
        manifest_artifacts: Dictionary containing the manifest with expectedArtifacts
        implementation_artifacts: Dictionary with implementation type information

    Returns:
        List of error messages for type mismatches
    """
    errors = []
    expected_items = manifest_artifacts.get("contains", [])

    for artifact in expected_items:
        if artifact.get("type") != "function":
            continue

        artifact_errors = _validate_function_types(artifact, implementation_artifacts)
        errors.extend(artifact_errors)

    return errors


def _validate_function_types(artifact: dict, implementation_artifacts: dict) -> list:
    """Validate type hints for a single function or method artifact."""
    errors = []
    artifact_name = artifact.get("name")
    parent_class = artifact.get("class")

    # Get implementation info based on whether it's a method or function
    impl_info = _get_implementation_info(
        artifact_name, parent_class, implementation_artifacts
    )

    if not impl_info:
        return errors  # No implementation found to validate

    # Validate parameter types
    param_errors = _validate_parameter_types(
        artifact, impl_info, artifact_name, parent_class
    )
    errors.extend(param_errors)

    # Validate return type
    return_error = _validate_return_type(
        artifact, impl_info, artifact_name, parent_class
    )
    if return_error:
        errors.append(return_error)

    return errors


def _get_implementation_info(
    artifact_name: str, parent_class: str, implementation_artifacts: dict
) -> dict:
    """Get implementation info for a function or method."""
    if parent_class:
        # It's a method
        methods = implementation_artifacts.get("methods", {})
        if parent_class in methods:
            return methods[parent_class].get(artifact_name, {})
    else:
        # It's a standalone function
        functions = implementation_artifacts.get("functions", {})
        return functions.get(artifact_name, {})

    return None


def _validate_parameter_types(
    artifact: dict, impl_info: dict, artifact_name: str, parent_class: str
) -> list:
    """Validate parameter types match between manifest and implementation."""
    errors = []
    manifest_params = artifact.get("parameters", [])
    impl_params = impl_info.get("parameters", [])

    for manifest_param in manifest_params:
        param_name = manifest_param.get("name")
        manifest_type = manifest_param.get("type")

        if not manifest_type:
            continue  # No type specified in manifest, nothing to validate

        # Find matching parameter in implementation
        impl_param = next((p for p in impl_params if p.get("name") == param_name), None)

        if not impl_param:
            entity_type = "method" if parent_class else "function"
            errors.append(
                f"Missing type annotation for parameter '{param_name}' "
                f"in {entity_type} '{artifact_name}'"
            )
        else:
            impl_type = impl_param.get("type")
            if not compare_types(manifest_type, impl_type):
                entity_type = "method" if parent_class else "function"
                errors.append(
                    f"Type mismatch for parameter '{param_name}' in {entity_type} "
                    f"'{artifact_name}': expected '{manifest_type}', got '{impl_type}'"
                )

    return errors


def _validate_return_type(
    artifact: dict, impl_info: dict, artifact_name: str, parent_class: str
) -> str:
    """Validate return type matches between manifest and implementation."""
    manifest_return = artifact.get("returns")
    if not manifest_return:
        return None  # No return type specified in manifest

    impl_return = impl_info.get("returns")
    if not compare_types(manifest_return, impl_return):
        entity_type = "method" if parent_class else "function"
        return (
            f"Type mismatch for return type in {entity_type} '{artifact_name}': "
            f"expected '{manifest_return}', got '{impl_return}'"
        )

    return None
