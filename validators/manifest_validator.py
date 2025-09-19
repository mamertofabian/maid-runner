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


class _ArtifactCollector(ast.NodeVisitor):
    """AST visitor that collects class and attribute references from Python code."""

    def __init__(self):
        self.found_classes = set()
        self.found_class_bases = {}  # class_name -> list of base class names
        self.found_attributes = {}  # class_name -> set of attribute names
        self.variable_to_class = {}  # variable_name -> class_name
        self.found_functions = {}  # function_name -> list of parameter names
        self.current_class = None  # Track if we're inside a class definition

    def visit_Import(self, node):
        """Handle regular import statements."""
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
        # Only collect module-level functions (not methods inside classes)
        if self.current_class is None:
            param_names = [arg.arg for arg in node.args.args]
            self.found_functions[node.name] = param_names

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
                # Handle cases like module.ClassName
                base_names.append(base.attr)

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
        """Track variable assignments to class instances."""
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


def validate_with_ast(manifest_data, test_file_path, use_manifest_chain=False):
    """
    Validate that artifacts listed in manifest are referenced in the test file.

    Args:
        manifest_data: Dictionary containing the manifest with expectedArtifacts
        test_file_path: Path to the Python test file to analyze
        use_manifest_chain: If True, discovers and merges all related manifests

    Raises:
        AlignmentError: If any expected artifact is not found in the code
    """
    # Parse the test file into an AST
    with open(test_file_path, "r") as f:
        test_code = f.read()

    tree = ast.parse(test_code)

    # Collect artifacts from the test code
    collector = _ArtifactCollector()
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
            _validate_function(artifact_name, parameters, collector.found_functions)

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
            if expected_base not in actual_bases:
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
