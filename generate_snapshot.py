"""Snapshot Generator Tool for MAID Framework.

This tool generates consolidated snapshot manifests for existing Python files,
enabling legacy code onboarding to MAID methodology. It extracts artifacts from
code using AST analysis and creates properly structured manifests.
"""

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

# Import manifest discovery function from validators
# Note: Uses sys.path manipulation to import from validators module
# This is a known limitation that should be addressed in future refactoring
_parent_dir = str(Path(__file__).parent)
sys.path.insert(0, _parent_dir)
try:
    from validators.manifest_validator import _discover_related_manifests
except ImportError as e:
    raise RuntimeError(
        f"Failed to import validators from '{_parent_dir}'. "
        "Ensure you're running from the repository root."
    ) from e
finally:
    # Always restore sys.path, even if import fails
    try:
        sys.path.remove(_parent_dir)
    except ValueError:
        pass


def extract_artifacts_from_code(file_path: str) -> dict:
    """Extract artifacts from a Python source file using AST analysis.

    Args:
        file_path: Path to the Python file to analyze

    Returns:
        Dictionary containing extracted artifacts with structure:
        {
            "functions": [...],
            "classes": [...],
            "methods": {...},
            "attributes": {...}
        }

    Raises:
        FileNotFoundError: If the file doesn't exist
        SyntaxError: If the file contains invalid Python syntax
    """
    # Read and parse the file
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()

    # Parse the AST
    try:
        tree = ast.parse(source_code)
    except SyntaxError as e:
        raise SyntaxError(f"Invalid Python syntax in {file_path}: {e}")

    # Collect artifacts using AST visitor
    collector = _ArtifactExtractor()
    collector.visit(tree)

    # Return collected artifacts
    return {
        "functions": collector.functions,
        "classes": collector.classes,
        "methods": collector.methods,
        "attributes": collector.attributes,
        "artifacts": collector.get_manifest_artifacts(),
    }


class _ArtifactExtractor(ast.NodeVisitor):
    """AST visitor that extracts artifact definitions from Python code."""

    def __init__(self):
        self.functions = []
        self.classes = []
        self.methods = {}
        self.attributes = {}
        self.current_class = None

    def visit_FunctionDef(self, node):
        """Visit function definitions."""
        # Extract function information
        func_info = self._extract_function_info(node)

        if self.current_class is None:
            # Module-level function
            self.functions.append(func_info)
        else:
            # Method of a class
            if self.current_class not in self.methods:
                self.methods[self.current_class] = []
            self.methods[self.current_class].append(func_info)

        # Continue visiting child nodes
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        """Visit class definitions."""
        # Extract class information
        class_info = {
            "type": "class",
            "name": node.name,
        }

        # Extract base classes if present
        if node.bases:
            bases = []
            for base in node.bases:
                base_name = self._extract_base_name(base)
                if base_name:
                    bases.append(base_name)
            if bases:
                class_info["bases"] = bases

        self.classes.append(class_info)

        # Track current class for method collection
        old_class = self.current_class
        self.current_class = node.name

        # Visit class body
        self.generic_visit(node)

        # Restore previous class context
        self.current_class = old_class

    def visit_Assign(self, node):
        """Visit assignments to collect self.attribute assignments."""
        if self.current_class:
            for target in node.targets:
                if self._is_self_attribute(target):
                    # Collect class attribute
                    if self.current_class not in self.attributes:
                        self.attributes[self.current_class] = []
                    if target.attr not in self.attributes[self.current_class]:
                        self.attributes[self.current_class].append(target.attr)

        self.generic_visit(node)

    def _extract_function_info(self, node: ast.FunctionDef) -> dict:
        """Extract information from a function definition."""
        func_info = {
            "type": "function",
            "name": node.name,
        }

        # Extract parameters - collect all parameter types
        params = []

        # Combine all parameter types in order:
        # 1. Positional-only parameters (Python 3.8+)
        # 2. Standard positional/keyword parameters
        # 3. Variable-length positional (*args)
        # 4. Keyword-only parameters
        # 5. Variable-length keyword (**kwargs)
        all_args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        if node.args.vararg:
            all_args.append(node.args.vararg)
        if node.args.kwarg:
            all_args.append(node.args.kwarg)

        for arg in all_args:
            param = {"name": arg.arg}

            # Extract type annotation if present
            if arg.annotation:
                param["type"] = self._extract_type_annotation(arg.annotation)

            params.append(param)

        if params:
            func_info["parameters"] = params

        # Extract return type annotation
        if node.returns:
            func_info["returns"] = self._extract_type_annotation(node.returns)

        return func_info

    def _extract_type_annotation(self, annotation_node: ast.AST) -> str:
        """Extract type annotation as a string."""
        if isinstance(annotation_node, ast.Name):
            return annotation_node.id
        elif isinstance(annotation_node, ast.Constant):
            return str(annotation_node.value)
        elif isinstance(annotation_node, ast.Subscript):
            # Generic types like List[str], Dict[str, int]
            base = self._extract_type_annotation(annotation_node.value)
            if isinstance(annotation_node.slice, ast.Tuple):
                # Multiple type arguments
                args = [self._extract_type_annotation(elt) for elt in annotation_node.slice.elts]
                return f"{base}[{', '.join(args)}]"
            else:
                # Single type argument
                arg = self._extract_type_annotation(annotation_node.slice)
                return f"{base}[{arg}]"
        elif isinstance(annotation_node, ast.Attribute):
            # Qualified names like typing.Optional
            value = self._extract_type_annotation(annotation_node.value)
            return f"{value}.{annotation_node.attr}"
        else:
            # Fallback to unparsing
            try:
                return ast.unparse(annotation_node)
            except (AttributeError, ValueError, TypeError):
                return "Any"

    def _extract_base_name(self, base_node: ast.AST) -> Optional[str]:
        """Extract base class name from AST node."""
        if isinstance(base_node, ast.Name):
            return base_node.id
        elif isinstance(base_node, ast.Attribute):
            # Handle module.ClassName
            parts = []
            current = base_node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return None

    def _is_self_attribute(self, target: ast.AST) -> bool:
        """Check if target is a self.attribute assignment."""
        return (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        )

    def get_manifest_artifacts(self) -> List[dict]:
        """Convert collected artifacts into manifest format."""
        artifacts = []

        # Add classes
        for class_info in self.classes:
            artifacts.append(class_info)

        # Add module-level functions
        for func_info in self.functions:
            artifacts.append(func_info)

        # Add methods (with class context)
        for class_name, methods in self.methods.items():
            for method_info in methods:
                # Add class context to method
                method_with_class = method_info.copy()
                method_with_class["class"] = class_name
                artifacts.append(method_with_class)

        # Add attributes (with class context)
        for class_name, attrs in self.attributes.items():
            for attr_name in attrs:
                artifacts.append({
                    "type": "attribute",
                    "name": attr_name,
                    "class": class_name,
                })

        return artifacts


def create_snapshot_manifest(
    file_path: str,
    artifacts: Union[List[Dict[str, Any]], Dict[str, Any]],
    superseded_manifests: List[str]
) -> Dict[str, Any]:
    """Create a snapshot manifest structure.

    Args:
        file_path: Path to the file being snapshot
        artifacts: Either a list of artifacts OR the full extraction dict from
                   extract_artifacts_from_code() (with "artifacts" key)
        superseded_manifests: List of manifest paths that this snapshot supersedes

    Returns:
        Dictionary containing the complete manifest structure
    """
    # If artifacts is the full extraction dict, extract the artifact list
    if isinstance(artifacts, dict) and "artifacts" in artifacts:
        artifact_list = artifacts["artifacts"]
    else:
        artifact_list = artifacts

    # Create the manifest structure
    manifest = {
        "goal": f"Snapshot of existing code in {file_path}",
        "taskType": "snapshot",
        "supersedes": superseded_manifests,
        "creatableFiles": [],
        "editableFiles": [file_path],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": file_path,
            "contains": artifact_list,
        },
        "validationCommand": [],
    }

    return manifest


def generate_snapshot(file_path: str, output_dir: str) -> str:
    """Generate a complete snapshot manifest for a Python file.

    This function orchestrates the full snapshot generation workflow:
    1. Extract artifacts from the code
    2. Discover existing manifests that touch this file
    3. Create a snapshot manifest that supersedes them
    4. Write the manifest to the output directory

    Args:
        file_path: Path to the Python file to snapshot
        output_dir: Directory where the manifest should be written

    Returns:
        Path to the generated manifest file

    Raises:
        FileNotFoundError: If the input file doesn't exist
        SyntaxError: If the file contains invalid Python syntax
    """
    # Extract artifacts from the code
    artifacts = extract_artifacts_from_code(file_path)

    # Discover existing manifests that reference this file
    superseded_manifests = _discover_related_manifests(file_path)

    # Create the snapshot manifest
    manifest = create_snapshot_manifest(file_path, artifacts, superseded_manifests)

    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate a unique filename based on the input file
    # Use the full path to avoid overwriting manifests for files with same name
    sanitized_path = str(Path(file_path).with_suffix('')).replace('/', '_').replace('\\', '_')
    manifest_filename = f"snapshot-{sanitized_path}.manifest.json"
    manifest_path = output_path / manifest_filename

    # Check if file exists and warn user
    if manifest_path.exists():
        print(f"Warning: Overwriting existing manifest: {manifest_path}", file=sys.stderr)

    # Write the manifest to file
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return str(manifest_path)


def main() -> None:
    """CLI entry point for the snapshot generator."""
    parser = argparse.ArgumentParser(
        description="Generate MAID snapshot manifests from existing Python files"
    )
    parser.add_argument(
        "file_path",
        help="Path to the Python file to snapshot"
    )
    parser.add_argument(
        "--output-dir",
        default="manifests",
        help="Directory to write the manifest (default: manifests)"
    )

    args = parser.parse_args()

    # Validate that the file exists
    if not Path(args.file_path).exists():
        print(f"Error: File not found: {args.file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Generate the snapshot
        manifest_path = generate_snapshot(args.file_path, args.output_dir)

        # Print success message
        print(f"Snapshot manifest generated successfully: {manifest_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except SyntaxError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
