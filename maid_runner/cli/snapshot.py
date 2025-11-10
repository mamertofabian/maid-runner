"""Snapshot Generator Tool for MAID Framework.

This tool generates consolidated snapshot manifests for existing Python files,
enabling legacy code onboarding to MAID methodology. It extracts artifacts from
code using AST analysis and creates properly structured manifests.
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

from maid_runner.validators.manifest_validator import discover_related_manifests


def _aggregate_validation_commands_from_superseded(
    superseded_manifests: List[str], manifest_dir: Path
) -> List[str]:
    """
    Aggregate validation commands from superseded manifests for snapshot generation.
    
    Collects all validation commands from superseded manifests and returns them
    as a list of command strings. Deduplicates identical commands.
    
    Args:
        superseded_manifests: List of manifest paths (may be relative or absolute)
        manifest_dir: Directory containing manifests (for resolving relative paths)
        
    Returns:
        List of aggregated validation command strings
    """
    aggregated_commands = []
    seen_commands = set()  # Deduplicate commands
    
    for superseded_path_str in superseded_manifests:
        superseded_path = Path(superseded_path_str)
        # Resolve relative paths
        if not superseded_path.is_absolute():
            # If path already includes "manifests/", resolve from manifest_dir's parent
            # Otherwise resolve relative to manifest_dir
            if str(superseded_path).startswith("manifests/"):
                # Resolve from manifest_dir's parent (project root)
                superseded_path = manifest_dir.parent / superseded_path
            else:
                # Resolve relative to manifest_dir
                superseded_path = manifest_dir / superseded_path
        
        if not superseded_path.exists():
            continue
        
        try:
            with open(superseded_path, "r") as f:
                superseded_data = json.load(f)
            
            superseded_cmd = superseded_data.get("validationCommand", [])
            if superseded_cmd:
                if isinstance(superseded_cmd, list):
                    # Check if it's a single command as list: ["pytest", "test.py", "-v"]
                    # vs multiple commands: ["pytest test1.py", "pytest test2.py"]
                    if len(superseded_cmd) > 0 and superseded_cmd[0] == "pytest" and len(superseded_cmd) > 1:
                        # Single command: join into one string
                        cmd_str = " ".join(superseded_cmd)
                        if cmd_str not in seen_commands:
                            seen_commands.add(cmd_str)
                            aggregated_commands.append(cmd_str)
                    else:
                        # Multiple commands: add each one
                        for cmd_item in superseded_cmd:
                            cmd_str = str(cmd_item)
                            if cmd_str and cmd_str not in seen_commands:
                                seen_commands.add(cmd_str)
                                aggregated_commands.append(cmd_str)
                else:
                    # Single command as string
                    cmd_str = str(superseded_cmd)
                    if cmd_str and cmd_str not in seen_commands:
                        seen_commands.add(cmd_str)
                        aggregated_commands.append(cmd_str)
        except (json.JSONDecodeError, IOError):
            continue
    
    return aggregated_commands


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
        self.current_function = None  # Track when inside a function body

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

        # Track that we're entering a function body
        old_function = self.current_function
        self.current_function = node.name

        # Continue visiting child nodes
        self.generic_visit(node)

        # Restore previous function context
        self.current_function = old_function

    # Support async functions by reusing the same logic
    visit_AsyncFunctionDef = visit_FunctionDef

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
        """Visit assignments to collect self.attribute and module-level assignments."""
        if self.current_class:
            # Class scope: collect self.attribute assignments
            for target in node.targets:
                if self._is_self_attribute(target):
                    # Collect class attribute
                    if self.current_class not in self.attributes:
                        self.attributes[self.current_class] = []
                    if target.attr not in self.attributes[self.current_class]:
                        self.attributes[self.current_class].append(target.attr)
        elif self.current_function is None:
            # True module scope (not inside a function): collect module-level variables
            # Skip if we're inside a function body (local variables shouldn't be collected)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # Module-level simple assignment (e.g., CONSTANT = 5)
                    if None not in self.attributes:
                        self.attributes[None] = []
                    if target.id not in self.attributes[None]:
                        self.attributes[None].append(target.id)

        self.generic_visit(node)

    def _extract_function_info(self, node: ast.FunctionDef) -> dict:
        """Extract information from a function definition."""
        func_info = {
            "type": "function",
            "name": node.name,
        }

        # Extract decorators if present
        if node.decorator_list:
            decorators = []
            for decorator in node.decorator_list:
                decorator_name = self._extract_decorator_name(decorator)
                if decorator_name:
                    decorators.append(decorator_name)
            if decorators:
                func_info["decorators"] = decorators

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
            # Skip 'self' parameter for methods (implicit in Python)
            if self.current_class is not None and arg.arg == "self":
                continue

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
                args = [
                    self._extract_type_annotation(elt)
                    for elt in annotation_node.slice.elts
                ]
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

    def _extract_decorator_name(self, decorator_node: ast.AST) -> Optional[str]:
        """Extract decorator name from AST node.

        Note: For decorators with arguments (e.g., @decorator(arg1, arg2)),
        only the decorator name is extracted; arguments are discarded.

        Args:
            decorator_node: AST node representing a decorator

        Returns:
            Decorator name as a string, or None if extraction fails
        """
        if isinstance(decorator_node, ast.Name):
            # Simple decorator: @decorator
            return decorator_node.id
        elif isinstance(decorator_node, ast.Attribute):
            # Qualified decorator: @module.decorator
            value = self._extract_type_annotation(decorator_node.value)
            return f"{value}.{decorator_node.attr}"
        elif isinstance(decorator_node, ast.Call):
            # Decorator with arguments: @decorator(args)
            # Extract the function name being called (arguments are discarded)
            if isinstance(decorator_node.func, ast.Name):
                return decorator_node.func.id
            elif isinstance(decorator_node.func, ast.Attribute):
                value = self._extract_type_annotation(decorator_node.func.value)
                return f"{value}.{decorator_node.func.attr}"
        return None

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

        # Add attributes (with class context or module-level)
        for class_name, attrs in self.attributes.items():
            for attr_name in attrs:
                artifact = {
                    "type": "attribute",
                    "name": attr_name,
                }
                # Only add class field if not module-level (None)
                if class_name is not None:
                    artifact["class"] = class_name
                artifacts.append(artifact)

        return artifacts


def create_snapshot_manifest(
    file_path: str,
    artifacts: Union[List[Dict[str, Any]], Dict[str, Any]],
    superseded_manifests: List[str],
    manifest_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create a snapshot manifest structure.

    Args:
        file_path: Path to the file being snapshot
        artifacts: Either a list of artifacts OR the full extraction dict from
                   extract_artifacts_from_code() (with "artifacts" key)
        superseded_manifests: List of manifest paths that this snapshot supersedes
        manifest_dir: Directory containing manifests (for resolving relative paths)

    Returns:
        Dictionary containing the complete manifest structure
    """
    # If artifacts is the full extraction dict, extract the artifact list
    if isinstance(artifacts, dict) and "artifacts" in artifacts:
        artifact_list = artifacts["artifacts"]
    else:
        artifact_list = artifacts

    # Aggregate validation commands from superseded manifests
    validation_command = []
    if superseded_manifests and manifest_dir:
        validation_command = _aggregate_validation_commands_from_superseded(
            superseded_manifests, manifest_dir
        )

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
        "validationCommand": validation_command,
    }

    return manifest


def _get_next_manifest_number(manifest_dir: Path) -> int:
    """Find the next available manifest number.

    Scans the manifest directory for task-XXX files (including snapshots)
    and returns the next sequential number.

    Args:
        manifest_dir: Path to the manifest directory

    Returns:
        Next available manifest number
    """
    max_number = 0

    if not manifest_dir.exists():
        return 1

    # Look for task-XXX pattern (covers both regular tasks and snapshots)
    for manifest_file in manifest_dir.glob("*.manifest.json"):
        stem = manifest_file.stem
        # Remove .manifest suffix if present
        if stem.endswith(".manifest"):
            stem = stem[:-9]

        # Check for task-XXX pattern
        if stem.startswith("task-"):
            try:
                parts = stem.split("-")
                if len(parts) >= 2:
                    number = int(parts[1])
                    max_number = max(max_number, number)
            except (ValueError, IndexError):
                pass

    return max_number + 1


def generate_snapshot(file_path: str, output_dir: str, force: bool = False) -> str:
    """Generate a complete snapshot manifest for a Python file.

    This function orchestrates the full snapshot generation workflow:
    1. Extract artifacts from the code
    2. Discover existing manifests that touch this file
    3. Create a snapshot manifest that supersedes them
    4. Write the manifest to the output directory

    Args:
        file_path: Path to the Python file to snapshot
        output_dir: Directory where the manifest should be written
        force: If True, overwrite existing manifests without prompting

    Returns:
        Path to the generated manifest file

    Raises:
        FileNotFoundError: If the input file doesn't exist
        SyntaxError: If the file contains invalid Python syntax
    """
    # Extract artifacts from the code
    artifacts = extract_artifacts_from_code(file_path)

    # Discover existing manifests that reference this file
    superseded_manifests = discover_related_manifests(file_path)

    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Find the next sequential number by looking at existing manifests
    next_number = _get_next_manifest_number(output_path)

    # Generate a descriptive name based on the input file
    # Use just the filename (not full path) for readability
    sanitized_path = Path(file_path).stem  # Get filename without extension
    # Replace special characters with hyphens, preserving underscores and Unicode word characters
    # This handles files like: manifest_validator.py, café_utils.py, test_數據.py
    sanitized_path = re.sub(r"[^\w-]+", "-", sanitized_path)
    # Remove leading/trailing hyphens
    sanitized_path = sanitized_path.strip("-")
    # Ensure we have something after sanitization
    if not sanitized_path:
        sanitized_path = "unnamed"

    # Use task prefix with sequential numbering for natural sorting
    manifest_filename = (
        f"task-{next_number:03d}-snapshot-{sanitized_path}.manifest.json"
    )
    manifest_path = output_path / manifest_filename

    # Filter out the snapshot itself from supersedes to avoid circular reference
    # (This handles the case where we're regenerating with --force)
    snapshot_path_str = str(manifest_path)
    superseded_manifests = [m for m in superseded_manifests if m != snapshot_path_str]

    # Create the snapshot manifest
    manifest = create_snapshot_manifest(
        file_path, artifacts, superseded_manifests, manifest_dir=output_path
    )

    # Check if file exists (unlikely with sequential numbering, but safety check)
    if manifest_path.exists() and not force:
        # This shouldn't happen with sequential numbering, but handle it anyway
        response = input(
            f"Manifest already exists: {manifest_path}\nOverwrite? (y/N): "
        )
        if response.lower() not in ("y", "yes"):
            print("Operation cancelled.", file=sys.stderr)
            sys.exit(1)

    # Write the manifest to file
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return str(manifest_path)


def main() -> None:
    """CLI entry point for the snapshot generator."""
    parser = argparse.ArgumentParser(
        description="Generate MAID snapshot manifests from existing Python files"
    )
    parser.add_argument("file_path", help="Path to the Python file to snapshot")
    parser.add_argument(
        "--output-dir",
        default="manifests",
        help="Directory to write the manifest (default: manifests)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing manifests without prompting",
    )

    args = parser.parse_args()

    # Validate that the file exists
    if not Path(args.file_path).exists():
        print(f"Error: File not found: {args.file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Generate the snapshot
        manifest_path = generate_snapshot(args.file_path, args.output_dir, args.force)

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
