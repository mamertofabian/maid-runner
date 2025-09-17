import ast
import json
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
        self.found_attributes = {}  # class_name -> set of attribute names
        self.variable_to_class = {}  # variable_name -> class_name

    def visit_ImportFrom(self, node):
        """Collect imported class names."""
        if node.names:
            for alias in node.names:
                # Classes typically start with uppercase
                if alias.name and alias.name[0].isupper():
                    self.found_classes.add(alias.name)
        self.generic_visit(node)

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


def validate_with_ast(manifest_data, test_file_path):
    """
    Validate that artifacts listed in manifest are referenced in the test file.

    Args:
        manifest_data: Dictionary containing the manifest with expectedArtifacts
        test_file_path: Path to the Python test file to analyze

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

    # Extract expected artifacts from manifest
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    expected_items = expected_artifacts.get("contains", [])

    # Validate each expected artifact
    for artifact in expected_items:
        artifact_type = artifact.get("type")
        artifact_name = artifact.get("name")

        if artifact_type == "class":
            _validate_class(artifact_name, collector.found_classes)

        elif artifact_type == "attribute":
            parent_class = artifact.get("class")
            _validate_attribute(artifact_name, parent_class, collector.found_attributes)

        elif artifact_type == "function":
            # Function validation not yet implemented
            pass


def _validate_class(class_name, found_classes):
    """Validate that a class is referenced in the code."""
    if class_name not in found_classes:
        raise AlignmentError(f"Artifact '{class_name}' not found")


def _validate_attribute(attribute_name, parent_class, found_attributes):
    """Validate that an attribute is referenced for a specific class."""
    class_attributes = found_attributes.get(parent_class, set())

    if attribute_name not in class_attributes:
        raise AlignmentError(f"Artifact '{attribute_name}' not found")
