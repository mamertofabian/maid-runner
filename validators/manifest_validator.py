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
    with open(schema_path, 'r') as schema_file:
        schema = json.load(schema_file)

    validate(manifest_data, schema)


class AlignmentError(Exception):
    """Raised when expected artifacts are not found in the code."""
    pass


def validate_with_ast(manifest_data, test_file_path):
    """
    Validate that artifacts listed in manifest are referenced in the test file.

    Args:
        manifest_data: Dictionary containing the manifest with expectedArtifacts
        test_file_path: Path to the Python test file to analyze

    Raises:
        AlignmentError: If any expected artifact is not found in the code
    """
    # Read and parse the test file
    with open(test_file_path, 'r') as f:
        test_code = f.read()

    tree = ast.parse(test_code)

    # Extract all classes and attributes referenced in the test
    found_classes = set()
    found_attributes = {}  # maps class_name -> set of attribute names
    variable_to_class = {}  # maps variable_name -> class_name

    class ArtifactCollector(ast.NodeVisitor):
        def visit_ImportFrom(self, node):
            # Collect imported classes
            if node.names:
                for alias in node.names:
                    if alias.name and alias.name[0].isupper():  # Likely a class
                        found_classes.add(alias.name)
            self.generic_visit(node)

        def visit_Assign(self, node):
            # Track variable assignments like user = User(...) or admin_user = User(...)
            if isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name):
                    class_name = node.value.func.id
                    if class_name in found_classes:
                        # Map each target variable to its class
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                variable_to_class[target.id] = class_name
            self.generic_visit(node)

        def visit_Attribute(self, node):
            # Collect attribute accesses like user.name or admin_user.user_id
            if isinstance(node.value, ast.Name):
                var_name = node.value.id
                attr_name = node.attr

                # Look up the actual class for this variable
                if var_name in variable_to_class:
                    class_name = variable_to_class[var_name]
                    if class_name not in found_attributes:
                        found_attributes[class_name] = set()
                    found_attributes[class_name].add(attr_name)
            self.generic_visit(node)

    collector = ArtifactCollector()
    collector.visit(tree)

    # Validate against expected artifacts
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    expected_items = expected_artifacts.get("contains", [])

    for item in expected_items:
        item_type = item.get("type")
        item_name = item.get("name")

        if item_type == "class":
            if item_name not in found_classes:
                raise AlignmentError(f"Artifact '{item_name}' not found")

        elif item_type == "attribute":
            class_name = item.get("class")
            if class_name not in found_attributes or item_name not in found_attributes[class_name]:
                raise AlignmentError(f"Artifact '{item_name}' not found")

        elif item_type == "function":
            # For functions, we'd need to check function calls
            # This is a simplified implementation
            pass