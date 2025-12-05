"""Snapshot Generator Tool for MAID Framework.

This tool generates consolidated snapshot manifests for existing Python or TypeScript files,
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

from maid_runner.utils import find_project_root
from maid_runner.validators.manifest_validator import discover_related_manifests


def detect_file_language(file_path: str) -> str:
    """Detect the programming language of a file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        Language identifier: "python", "typescript", "svelte", "unknown", or defaults to "python"
    """
    if file_path.endswith(".py"):
        return "python"
    elif file_path.endswith((".ts", ".tsx", ".js", ".jsx")):
        return "typescript"
    elif file_path.endswith(".svelte"):
        return "svelte"
    else:
        from pathlib import Path

        # Check if file has no extension
        if not Path(file_path).suffix:
            return "unknown"

        # Check if this might be a case variant of a known extension
        # Return "unknown" for case variants and unrecognized extensions
        lower_path = file_path.lower()
        if (
            lower_path.endswith(".py")
            or lower_path.endswith((".ts", ".tsx", ".js", ".jsx"))
            or lower_path.endswith(".svelte")
        ):
            # This is a case variant of a known extension (e.g., .PY, .SVELTE)
            return "unknown"

        # Check if it's a common non-code file extension
        non_code_extensions = (
            ".txt",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".html",
            ".css",
            ".scss",
            ".sass",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".ico",
        )
        if lower_path.endswith(non_code_extensions):
            return "unknown"

        # Default to python for backward compatibility with other unknown extensions
        # This maintains backward compatibility with existing code that might
        # pass unusual file extensions
        return "python"


def extract_typescript_artifacts(file_path: str) -> dict:
    """Extract artifacts from a TypeScript/JavaScript source file.

    Args:
        file_path: Path to the TypeScript/JavaScript file to analyze

    Returns:
        Dictionary containing extracted artifacts with structure:
        {
            "artifacts": [...]  # List of artifacts in manifest format
        }

    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    from pathlib import Path

    # Validate file exists
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Use TypeScript validator to collect artifacts
    from maid_runner.validators.typescript_validator import TypeScriptValidator

    validator = TypeScriptValidator()
    artifacts_data = validator.collect_artifacts(file_path, "implementation")

    # Convert validator output to manifest format
    manifest_artifacts = _convert_typescript_artifacts_to_manifest(
        artifacts_data, file_path
    )

    return {
        "artifacts": manifest_artifacts,
    }


def extract_svelte_artifacts(file_path: str) -> dict:
    """Extract artifacts from a Svelte source file.

    Args:
        file_path: Path to the Svelte file to analyze

    Returns:
        Dictionary containing extracted artifacts with structure:
        {
            "artifacts": [...]  # List of artifacts in manifest format
        }

    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    from pathlib import Path

    # Validate file exists
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Use Svelte validator to collect artifacts
    from maid_runner.validators.svelte_validator import SvelteValidator

    validator = SvelteValidator()
    artifacts_data = validator.collect_artifacts(file_path, "implementation")

    # Convert validator output to manifest format
    # Svelte validator extracts classes and functions from script blocks
    manifest_artifacts = []

    # Extract classes (includes interfaces, but Svelte doesn't parse TypeScript constructs separately)
    found_classes = artifacts_data.get("found_classes", set())
    for class_name in sorted(found_classes):
        manifest_artifacts.append({"type": "class", "name": class_name})

    # Extract standalone functions
    found_functions = artifacts_data.get("found_functions", {})
    for func_name, params in sorted(found_functions.items()):
        artifact = {
            "type": "function",
            "name": func_name,
        }
        if params:
            # Handle both old format (list of strings) and new format (list of dicts)
            args = []
            for param in params:
                if isinstance(param, dict):
                    # New format - already a dict with 'name' and optionally 'type'
                    args.append(param)
                else:
                    # Old format - string parameter name
                    args.append({"name": param})
            artifact["args"] = args
            # Also add 'parameters' key for backward compatibility
            artifact["parameters"] = args
        manifest_artifacts.append(artifact)

    # Extract methods
    found_methods = artifacts_data.get("found_methods", {})
    for class_name, methods_dict in sorted(found_methods.items()):
        for method_name, params in sorted(methods_dict.items()):
            artifact = {
                "type": "function",
                "name": method_name,
                "class": class_name,
            }
            if params:
                # Handle both old format (list of strings) and new format (list of dicts)
                args = []
                for param in params:
                    if isinstance(param, dict):
                        # New format - already a dict with 'name' and optionally 'type'
                        args.append(param)
                    else:
                        # Old format - string parameter name
                        args.append({"name": param})
                artifact["args"] = args
                # Also add 'parameters' key for backward compatibility
                artifact["parameters"] = args
            manifest_artifacts.append(artifact)

    return {
        "artifacts": manifest_artifacts,
    }


def _convert_typescript_artifacts_to_manifest(
    artifacts_data: dict, file_path: str
) -> list:
    """Convert TypeScript validator output to manifest artifact format.

    Args:
        artifacts_data: Output from TypeScriptValidator.collect_artifacts()
        file_path: Path to the TypeScript file (for re-parsing to differentiate types)

    Returns:
        List of artifacts in manifest format
    """
    from maid_runner.validators.typescript_validator import TypeScriptValidator

    manifest_artifacts = []

    # To differentiate between class/interface/type/enum/namespace, we need to
    # re-parse using the validator's internal methods since it combines them all
    validator = TypeScriptValidator()
    tree, source_code = validator._parse_typescript_file(file_path)

    # Extract each type separately to properly categorize
    classes = validator._extract_classes(tree, source_code)
    interfaces = validator._extract_interfaces(tree, source_code)
    type_aliases = validator._extract_type_aliases(tree, source_code)
    enums = validator._extract_enums(tree, source_code)
    namespaces = validator._extract_namespaces(tree, source_code)

    # Add classes
    for class_name in sorted(classes):
        manifest_artifacts.append({"type": "class", "name": class_name})

    # Add interfaces
    for interface_name in sorted(interfaces):
        manifest_artifacts.append({"type": "interface", "name": interface_name})

    # Add type aliases
    for type_name in sorted(type_aliases):
        manifest_artifacts.append({"type": "type", "name": type_name})

    # Add enums
    for enum_name in sorted(enums):
        manifest_artifacts.append({"type": "enum", "name": enum_name})

    # Add namespaces
    for namespace_name in sorted(namespaces):
        manifest_artifacts.append({"type": "namespace", "name": namespace_name})

    # Extract standalone functions
    found_functions = artifacts_data.get("found_functions", {})
    for func_name, params in sorted(found_functions.items()):
        artifact = {
            "type": "function",
            "name": func_name,
        }
        if params:
            # Handle both old format (list of strings) and new format (list of dicts)
            args = []
            for param in params:
                if isinstance(param, dict):
                    # New format - already a dict with 'name' and optionally 'type'
                    args.append(param)
                else:
                    # Old format - string parameter name
                    args.append({"name": param})
            artifact["args"] = args
            # Also add 'parameters' key for backward compatibility
            artifact["parameters"] = args
        manifest_artifacts.append(artifact)

    # Extract methods
    found_methods = artifacts_data.get("found_methods", {})
    for class_name, methods_dict in sorted(found_methods.items()):
        for method_name, params in sorted(methods_dict.items()):
            artifact = {
                "type": "function",
                "name": method_name,
                "class": class_name,
            }
            if params:
                # Handle both old format (list of strings) and new format (list of dicts)
                args = []
                for param in params:
                    if isinstance(param, dict):
                        # New format - already a dict with 'name' and optionally 'type'
                        args.append(param)
                    else:
                        # Old format - string parameter name
                        args.append({"name": param})
                artifact["args"] = args
                # Also add 'parameters' key for backward compatibility
                artifact["parameters"] = args
            manifest_artifacts.append(artifact)

    return manifest_artifacts


def _test_file_references_artifacts(
    test_file_path: Path, expected_artifacts: List[dict], target_file: str
) -> bool:
    """
    Check if a test file references any of the expected artifacts.

    This is used to filter out tests that reference artifacts removed during refactoring.
    Only tests that reference artifacts present in the snapshot should be included.

    Args:
        test_file_path: Path to the test file to check
        expected_artifacts: List of artifacts expected in the snapshot
        target_file: Path to the target file being tested (for import detection)

    Returns:
        True if test file references at least one expected artifact, False otherwise
    """
    if not test_file_path.exists():
        return False

    try:
        from maid_runner.validators.manifest_validator import (
            collect_behavioral_artifacts,
        )

        artifacts = collect_behavioral_artifacts(str(test_file_path))

        # Extract artifact names from expected artifacts
        expected_class_names = set()
        expected_function_names = set()
        expected_method_names = {}  # class_name -> set of method names

        for artifact in expected_artifacts:
            artifact_type = artifact.get("type")
            artifact_name = artifact.get("name")

            if artifact_type == "class":
                expected_class_names.add(artifact_name)
            elif artifact_type == "function":
                parent_class = artifact.get("class")
                if parent_class:
                    if parent_class not in expected_method_names:
                        expected_method_names[parent_class] = set()
                    expected_method_names[parent_class].add(artifact_name)
                else:
                    expected_function_names.add(artifact_name)

        # Check if test uses any expected classes
        if expected_class_names and artifacts["used_classes"].intersection(
            expected_class_names
        ):
            return True

        # Check if test uses any expected functions
        if expected_function_names and artifacts["used_functions"].intersection(
            expected_function_names
        ):
            return True

        # Check if test uses any expected methods
        for class_name, methods in expected_method_names.items():
            if class_name in artifacts["used_methods"]:
                if artifacts["used_methods"][class_name].intersection(methods):
                    return True

        # If no expected artifacts match, this test likely references removed artifacts
        return False

    except Exception:
        # If we can't parse the test file, include it to be safe
        # (better to have a test that might fail than to silently exclude it)
        # Catches SyntaxError, IOError, and other parsing/IO errors
        return True


def _aggregate_validation_commands_from_superseded(
    superseded_manifests: List[str],
    manifest_dir: Path,
    expected_artifacts: Optional[List[dict]] = None,
    target_file: Optional[str] = None,
) -> List[List[str]]:
    """
    Aggregate validation commands from superseded manifests for snapshot generation.

    Collects all validation commands from superseded manifests and returns them
    as a list of command arrays (enhanced format). Deduplicates identical commands.

    Optionally filters out tests that don't reference artifacts in the snapshot,
    which handles the case where refactoring removed artifacts tested by old tests.

    Args:
        superseded_manifests: List of manifest paths (may be relative or absolute)
        manifest_dir: Directory containing manifests (for resolving relative paths)
        expected_artifacts: Optional list of artifacts in the snapshot (for filtering)
        target_file: Optional path to target file being tested (for import detection)

    Returns:
        List of command arrays: [["pytest", "test1.py"], ["pytest", "test2.py"]]
    """
    aggregated_commands = []
    seen_commands = set()  # Deduplicate commands (as tuples for hashing)

    # Determine project root for path validation
    project_root = find_project_root(manifest_dir)

    for superseded_path_str in superseded_manifests:
        superseded_path = Path(superseded_path_str)
        # Resolve relative paths
        if not superseded_path.is_absolute():
            # If path already includes "manifests/", resolve from project root
            # Otherwise resolve relative to manifest_dir
            if str(superseded_path).startswith("manifests/"):
                # Resolve from project root
                superseded_path = project_root / superseded_path
            else:
                # Resolve relative to manifest_dir
                superseded_path = manifest_dir / superseded_path

        # Resolve to absolute path and validate it's within project root
        try:
            superseded_path = superseded_path.resolve()
            # Check if resolved path is within project root to prevent path traversal
            if not str(superseded_path).startswith(str(project_root)):
                # Path traversal detected - skip this manifest
                continue
        except (OSError, ValueError):
            # Invalid path - skip this manifest
            continue

        if not superseded_path.exists():
            continue

        try:
            with open(superseded_path, "r") as f:
                superseded_data = json.load(f)

            # Validate version field
            from maid_runner.utils import validate_manifest_version

            try:
                validate_manifest_version(superseded_data, superseded_path.name)
            except ValueError:
                # Skip invalid manifests - version validation failed
                continue

            # Normalize validation commands to consistent format
            from maid_runner.utils import normalize_validation_commands
            from maid_runner.cli.validate import extract_test_files_from_command

            cmd_list = normalize_validation_commands(superseded_data)

            if cmd_list:
                # Extract test files and filter if expected_artifacts provided
                for cmd_array in cmd_list:

                    # Create tuple for deduplication
                    # Deduplication is based on the full command array, including flags.
                    # This means commands with different flags are considered different and
                    # both will be kept. For example:
                    #   ['pytest', 'test.py', '-v'] and ['pytest', 'test.py', '-vv']
                    #   are treated as different commands and both preserved.
                    # This is intentional: different verbosity levels or flags may indicate
                    # different test scenarios or requirements.
                    cmd_tuple = tuple(cmd_array)
                    if not cmd_array or cmd_tuple in seen_commands:
                        continue

                    # Extract test files from this command
                    test_files = extract_test_files_from_command(cmd_array)

                    # Filter tests if expected_artifacts provided
                    if expected_artifacts and target_file:
                        filtered_test_files = []
                        for test_file in test_files:
                            test_path = Path(test_file)
                            if not test_path.is_absolute():
                                # Resolve relative to project root
                                test_path = project_root / test_file

                            if _test_file_references_artifacts(
                                test_path, expected_artifacts, target_file
                            ):
                                filtered_test_files.append(test_file)

                        # Only include command if it has valid test files
                        if filtered_test_files:
                            # Rebuild command preserving flags
                            pytest_index = (
                                cmd_array.index("pytest")
                                if "pytest" in cmd_array
                                else 0
                            )
                            flags = [
                                arg
                                for arg in cmd_array[pytest_index + 1 :]
                                if arg.startswith("-")
                            ]
                            new_cmd = ["pytest"] + filtered_test_files + flags
                            cmd_tuple = tuple(new_cmd)
                            seen_commands.add(cmd_tuple)
                            aggregated_commands.append(new_cmd)
                    else:
                        # No filtering - include all commands
                        seen_commands.add(cmd_tuple)
                        aggregated_commands.append(cmd_array)
        except (json.JSONDecodeError, IOError) as e:
            # Always log warnings - users should know about invalid manifests
            # This prevents one malformed manifest from breaking the entire aggregation
            print(
                f"⚠️  Skipping invalid manifest {superseded_path.name}: {e}",
                file=sys.stderr,
            )
            continue

    return aggregated_commands


def extract_artifacts_from_code(file_path: str) -> dict:
    """Extract artifacts from a source file using appropriate parser.

    Detects file type and routes to the appropriate artifact extractor:
    - Python files (.py): Uses Python AST parser
    - TypeScript/JavaScript files (.ts, .tsx, .js, .jsx): Uses TypeScript validator
    - Svelte files (.svelte): Uses Svelte validator

    Args:
        file_path: Path to the file to analyze

    Returns:
        Dictionary containing extracted artifacts with structure:
        {
            "functions": [...],
            "classes": [...],
            "methods": {...},
            "attributes": {...},
            "artifacts": [...]  # Manifest-ready artifact list
        }

    Raises:
        FileNotFoundError: If the file doesn't exist
        ValueError: If the file type is not supported
        SyntaxError: If the file contains invalid syntax
    """
    # Detect file language and route to appropriate extractor
    language = detect_file_language(file_path)

    if language == "unknown":
        # File extension is not supported
        from pathlib import Path

        ext = Path(file_path).suffix or "(no extension)"
        supported_extensions = [".py", ".ts", ".tsx", ".js", ".jsx", ".svelte"]
        raise ValueError(
            f"Unsupported file type '{ext}' for: {file_path}\n"
            f"Supported file types: {', '.join(supported_extensions)}"
        )

    if language == "typescript":
        # Use TypeScript extractor
        return extract_typescript_artifacts(file_path)
    elif language == "svelte":
        # Use Svelte extractor
        return extract_svelte_artifacts(file_path)
    else:
        # Use Python extractor (default for backward compatibility)
        return _extract_python_artifacts(file_path)


def _extract_python_artifacts(file_path: str) -> dict:
    """Extract artifacts from a Python source file using AST analysis.

    Args:
        file_path: Path to the Python file to analyze

    Returns:
        Dictionary containing extracted artifacts with structure:
        {
            "functions": [...],
            "classes": [...],
            "methods": {...},
            "attributes": {...},
            "artifacts": [...]
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
            # Output both args (enhanced) and parameters (legacy) for backward compatibility
            func_info["args"] = params
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
    # Filter out tests that reference artifacts removed during refactoring
    validation_commands = []
    if superseded_manifests and manifest_dir:
        validation_commands = _aggregate_validation_commands_from_superseded(
            superseded_manifests,
            manifest_dir,
            expected_artifacts=artifact_list,
            target_file=file_path,
        )

    # Create the manifest structure
    # Use validationCommands (enhanced format) if we have multiple commands,
    # otherwise use validationCommand (legacy format) for single command
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
    }

    # Output validation commands
    # Use validationCommand (legacy) for single command or empty, validationCommands (enhanced) for multiple
    if not validation_commands:
        # Empty - use legacy format for backward compatibility
        manifest["validationCommand"] = []
    elif len(validation_commands) == 1:
        # Single command - use legacy format for backward compatibility
        manifest["validationCommand"] = validation_commands[0]
    else:
        # Multiple commands - use enhanced format
        manifest["validationCommands"] = validation_commands

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


def generate_snapshot(
    file_path: str, output_dir: str, force: bool = False, skip_test_stub: bool = False
) -> str:
    """Generate a complete snapshot manifest for a Python or TypeScript file.

    This function orchestrates the full snapshot generation workflow:
    1. Extract artifacts from the code
    2. Discover existing manifests that touch this file
    3. Create a snapshot manifest that supersedes them
    4. Write the manifest to the output directory
    5. Optionally generate a test stub (by default)

    Args:
        file_path: Path to the Python (.py) or TypeScript (.ts, .tsx, .js, .jsx) file to snapshot
        output_dir: Directory where the manifest should be written
        force: If True, overwrite existing manifests without prompting
        skip_test_stub: If True, skip test stub generation (default: False)

    Returns:
        Path to the generated manifest file

    Raises:
        FileNotFoundError: If the input file doesn't exist
        SyntaxError: If the file contains invalid syntax
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
    # Normalize both paths to absolute for comparison, since discover_related_manifests
    # may return relative paths while manifest_path is absolute
    manifest_path_resolved = manifest_path.resolve()
    filtered_superseded = []
    for m in superseded_manifests:
        # Resolve the superseded manifest path to absolute for comparison
        superseded_path = Path(m)
        if not superseded_path.is_absolute():
            # If path already includes "manifests/", resolve from project root
            # Otherwise resolve relative to output_path
            if str(superseded_path).startswith("manifests/"):
                from maid_runner.utils import find_project_root

                project_root = find_project_root(output_path)
                superseded_path = project_root / superseded_path
            else:
                superseded_path = output_path / superseded_path
        superseded_path_resolved = superseded_path.resolve()
        # Only include if it's not the same as the manifest we're creating
        if superseded_path_resolved != manifest_path_resolved:
            filtered_superseded.append(m)
    superseded_manifests = filtered_superseded

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

    # Add test stub to validationCommand if generating stubs
    if not skip_test_stub:
        # Detect file language to determine test runner
        target_language = detect_file_language(file_path)

        # Get the stub path that will be generated (pass language since manifest not yet written)
        stub_path = get_test_stub_path(str(manifest_path), target_language)
        if target_language == "typescript":
            # Use Jest for TypeScript/JavaScript files
            test_command = ["npx", "jest", stub_path]
        else:
            # Use pytest for Python files
            test_command = ["pytest", stub_path, "-v"]

        # Add stub to validationCommand
        # Handle both single command (legacy) and multiple commands (enhanced) formats
        if "validationCommands" in manifest:
            # Enhanced format - add to the list
            manifest["validationCommands"].append(test_command)
        elif "validationCommand" in manifest and manifest["validationCommand"]:
            # Legacy format with existing command - convert to enhanced
            manifest["validationCommands"] = [
                manifest["validationCommand"],
                test_command,
            ]
            del manifest["validationCommand"]
        else:
            # No existing commands - use legacy format for simplicity
            manifest["validationCommand"] = test_command

    # Write the manifest to file
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Generate test stub unless skipped
    if not skip_test_stub:
        try:
            stub_path = generate_test_stub(manifest, str(manifest_path))
            print(f"Test stub generated: {stub_path}", file=sys.stderr)
        except Exception as e:
            # Don't fail the entire operation if stub generation fails
            print(f"Warning: Test stub generation failed: {e}", file=sys.stderr)

    return str(manifest_path)


def get_test_stub_path(
    manifest_path: str, target_language: Optional[str] = None
) -> str:
    """Derive test stub file path from manifest filename.

    Detects the target file language from the manifest and returns appropriate extension:
    - TypeScript/JavaScript files (.ts, .tsx, .js, .jsx) -> .spec.ts
    - Python files (.py) -> .py

    Args:
        manifest_path: Path to the manifest file
        target_language: Optional language override. If provided, skips manifest detection.
                        Use when manifest hasn't been written yet.

    Returns:
        Path to the test stub file in tests/ directory
    """
    manifest_file = Path(manifest_path)
    stem = manifest_file.stem

    # Remove .manifest suffix if present
    if stem.endswith(".manifest"):
        stem = stem[:-9]

    # Use provided language or detect from manifest
    if target_language is None:
        target_language = "python"  # Default
        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)
                target_file = manifest_data.get("expectedArtifacts", {}).get("file", "")
                if target_file:
                    target_language = detect_file_language(target_file)
        except (json.JSONDecodeError, IOError, KeyError):
            # If we can't read the manifest, default to Python for backward compatibility
            pass

    # Convert manifest name to test name
    # task-032-feature.manifest.json -> test_task_032_feature.py or task-032-feature.spec.ts
    # snapshot-example.manifest.json -> test_snapshot_example.py or snapshot-example.spec.ts

    if target_language == "typescript":
        # TypeScript: use .spec.ts extension with original stem (with hyphens)
        test_name = f"{stem}.spec.ts"
    else:
        # Python: use test_ prefix and .py extension (with underscores)
        # Handle edge cases: consecutive hyphens, leading/trailing hyphens
        # Replace hyphens with underscores
        test_stem = stem.replace("-", "_")
        # Sanitize: collapse multiple consecutive underscores into one
        test_stem = re.sub(r"_+", "_", test_stem)
        # Remove leading/trailing underscores
        test_stem = test_stem.strip("_")
        test_name = f"test_{test_stem}.py"

    # Place in tests directory
    return str(Path("tests") / test_name)


def generate_test_stub(manifest_data: Dict[str, Any], manifest_path: str) -> str:
    """Generate a failing test stub from manifest data.

    Detects the target file language and generates appropriate test stubs:
    - Python files: pytest syntax with .py extension
    - TypeScript/JavaScript files: Jest syntax with .spec.ts extension

    Args:
        manifest_data: The manifest dictionary
        manifest_path: Path to the manifest file (for deriving test path)

    Returns:
        Path to the generated test stub file
    """
    # Get test file path (already detects language and returns correct extension)
    stub_path = get_test_stub_path(manifest_path)

    # Detect target file language
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    target_file = expected_artifacts.get("file", "")
    target_language = detect_file_language(target_file) if target_file else "python"

    # Route to appropriate generator
    if target_language == "typescript":
        return _generate_typescript_test_stub(manifest_data, manifest_path, stub_path)
    else:
        return _generate_python_test_stub(manifest_data, manifest_path, stub_path)


def _generate_python_test_stub(
    manifest_data: Dict[str, Any], manifest_path: str, stub_path: str
) -> str:
    """Generate a Python/pytest test stub.

    Creates a test file with:
    - Import statements for artifacts
    - Test class/function shells
    - Assertion placeholders (commented examples)
    - Docstring templates
    - pytest.fail() calls to ensure tests fail until implemented

    Args:
        manifest_data: The manifest dictionary
        manifest_path: Path to the manifest file (for context)
        stub_path: Path where the stub should be written

    Returns:
        Path to the generated test stub file
    """
    stub_file = Path(stub_path)

    # Ensure tests directory exists
    stub_file.parent.mkdir(parents=True, exist_ok=True)

    # Extract information from manifest
    goal = manifest_data.get("goal", "Test implementation")
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    target_file = expected_artifacts.get("file", "")
    artifacts = expected_artifacts.get("contains", [])

    # Build import statements
    imports = ["import pytest\n"]

    if target_file and artifacts:
        # Normalize the file path using PurePosixPath for consistent handling
        # as_posix() always returns forward slashes, so backslash check is unnecessary
        normalized_path = str(Path(target_file).as_posix())
        # Remove leading ./
        if normalized_path.startswith("./"):
            normalized_path = normalized_path[2:]

        # Convert file path to module path properly
        # Handle __init__.py specially (maps to parent package)
        # Handle files with dots in names (e.g., my.config.py)
        path_obj = Path(normalized_path)

        # For __init__.py, use the parent directory as the module
        if path_obj.name == "__init__.py":
            # e.g., "maid_runner/cli/__init__.py" -> "maid_runner.cli"
            module_path = ".".join(path_obj.parent.parts)
        else:
            # Use Path.stem to properly remove .py suffix (handles my.config.py correctly)
            # e.g., "maid_runner/cli/snapshot.py" -> "maid_runner.cli.snapshot"
            # e.g., "config/my.config.py" -> "config.my.config"
            parts = list(path_obj.parent.parts) + [path_obj.stem]
            module_path = ".".join(parts)

        # Test if the module is actually importable
        is_importable = False
        try:
            # Try to import the module to verify it exists
            import importlib

            importlib.import_module(module_path)
            is_importable = True
        except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
            # Module doesn't exist or isn't importable
            is_importable = False

        # Group artifacts by type for import
        classes = [a["name"] for a in artifacts if a.get("type") == "class"]
        functions = [
            a["name"]
            for a in artifacts
            if a.get("type") == "function" and not a.get("class")
        ]

        # Generate import statement only if module is importable
        import_items = classes + functions
        if import_items and is_importable:
            if len(import_items) <= 3:
                imports.append(f"from {module_path} import {', '.join(import_items)}\n")
            else:
                # Multi-line import for readability
                imports.append(f"from {module_path} import (\n")
                for item in import_items:
                    imports.append(f"    {item},\n")
                imports.append(")\n")
        elif import_items and not is_importable:
            # Add a comment explaining why imports are skipped
            imports.append(
                f"# NOTE: Module '{module_path}' is not currently importable\n"
            )
            imports.append(
                "# This may be because the file doesn't exist yet or isn't in the Python path\n"
            )
            imports.append(
                "# Import the artifacts manually once the module is available:\n"
            )
            if len(import_items) <= 3:
                imports.append(
                    f"# from {module_path} import {', '.join(import_items)}\n"
                )
            else:
                imports.append(f"# from {module_path} import (\n")
                for item in import_items:
                    imports.append(f"#     {item},\n")
                imports.append("#  )\n")

    # Build test content
    lines = []

    # Module docstring
    lines.append('"""\n')
    lines.append(f"Behavioral tests for {Path(manifest_path).stem}\n")
    lines.append("\n")
    lines.append(f"Goal: {goal}\n")
    lines.append("\n")
    lines.append(
        "These tests verify that the implementation matches the manifest specification.\n"
    )
    lines.append("TODO: Implement the actual test logic.\n")
    lines.append('"""\n')
    lines.append("\n")

    # Add imports
    lines.extend(imports)
    lines.append("\n\n")

    # Generate test classes/functions for each artifact
    for artifact in artifacts:
        artifact_type = artifact.get("type")
        artifact_name = artifact.get("name")
        parent_class = artifact.get("class")

        if not artifact_name:
            continue

        # Create test class name
        if parent_class:
            test_class_name = (
                f"Test{parent_class}{artifact_name.title().replace('_', '')}"
            )
        else:
            test_class_name = f"Test{artifact_name.title().replace('_', '')}"

        # Generate test class
        lines.append(f"class {test_class_name}:\n")
        lines.append('    """\n')
        if artifact_type == "class":
            lines.append(f"    Test the {artifact_name} class.\n")
            lines.append("    \n")
            lines.append("    TODO: Implement tests to verify:\n")
            lines.append(f"    - {artifact_name} class is defined\n")
            lines.append("    - Class has expected methods and attributes\n")
            lines.append("    - Class behavior meets requirements\n")
        elif artifact_type == "function":
            if parent_class:
                lines.append(
                    f"    Test the {artifact_name} method of {parent_class}.\n"
                )
            else:
                lines.append(f"    Test the {artifact_name} function.\n")
            lines.append("    \n")
            lines.append("    TODO: Implement tests to verify:\n")
            lines.append(f"    - {artifact_name} is defined and callable\n")

            # Add parameter hints if available
            params = artifact.get("parameters", artifact.get("args", []))
            if params:
                param_names = ", ".join([p.get("name", "?") for p in params])
                lines.append(
                    f"    - Function accepts expected parameters: {param_names}\n"
                )

            returns = artifact.get("returns")
            if returns:
                lines.append(f"    - Function returns expected type: {returns}\n")

            lines.append("    - Function behavior meets requirements\n")
        else:
            lines.append(f"    Test the {artifact_name} {artifact_type}.\n")

        lines.append('    """\n')
        lines.append("    \n")

        # Generate test method - existence check
        lines.append(f"    def test_{artifact_name}_exists(self):\n")
        lines.append(f'        """Verify {artifact_name} is defined."""\n')
        lines.append(
            f'        pytest.fail("TODO: Implement test - verify {artifact_name} exists")\n'
        )
        lines.append("        # Example assertion:\n")
        if artifact_type == "class":
            lines.append(f"        # assert {artifact_name} is not None\n")
            lines.append(f"        # instance = {artifact_name}()\n")
            lines.append("        # assert instance is not None\n")
        else:
            lines.append(f"        # assert callable({artifact_name})\n")
        lines.append("    \n")

        # Generate test method - behavior check
        lines.append(f"    def test_{artifact_name}_behavior(self):\n")
        lines.append(f'        """Test {artifact_name} behavior with test inputs."""\n')
        lines.append(
            f'        pytest.fail("TODO: Implement test - verify {artifact_name} behavior")\n'
        )
        lines.append("        # Example assertion:\n")
        if artifact_type == "class":
            lines.append(f"        # instance = {artifact_name}()\n")
            lines.append("        # result = instance.some_method()\n")
            lines.append("        # assert result == expected_value\n")
        elif artifact_type == "function":
            params = artifact.get("parameters", artifact.get("args", []))
            if params:
                param_str = ", ".join(
                    [f"{p.get('name', 'arg')}=test_value" for p in params[:2]]
                )
                lines.append(f"        # result = {artifact_name}({param_str})\n")
            else:
                lines.append(f"        # result = {artifact_name}()\n")

            returns = artifact.get("returns")
            if returns:
                lines.append("        # assert result == expected_value\n")
            else:
                lines.append("        # assert result is not None\n")
        lines.append("\n\n")

    # Write the stub file
    content = "".join(lines)
    with open(stub_file, "w", encoding="utf-8") as f:
        f.write(content)

    return str(stub_file)


def _generate_typescript_test_stub(
    manifest_data: Dict[str, Any], manifest_path: str, stub_path: str
) -> str:
    """Generate a TypeScript/Jest test stub.

    Creates a test file with:
    - ES6 import statements for artifacts
    - Jest describe/it blocks
    - Type checking for compile-time artifacts (interfaces/types)
    - Runtime tests for classes, functions, enums, namespaces
    - expect().toBe() assertions that intentionally fail

    Args:
        manifest_data: The manifest dictionary
        manifest_path: Path to the manifest file (for context)
        stub_path: Path where the stub should be written

    Returns:
        Path to the generated test stub file
    """
    stub_file = Path(stub_path)

    # Ensure tests directory exists
    stub_file.parent.mkdir(parents=True, exist_ok=True)

    # Extract information from manifest
    goal = manifest_data.get("goal", "Test implementation")
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    target_file = expected_artifacts.get("file", "")
    artifacts = expected_artifacts.get("contains", [])

    # Build content
    lines = []

    # File header comment
    lines.append("/**\n")
    lines.append(f" * Behavioral tests for {Path(manifest_path).stem}\n")
    lines.append(" *\n")
    lines.append(f" * Goal: {goal}\n")
    lines.append(" *\n")
    lines.append(
        " * These tests verify that the implementation matches the manifest specification.\n"
    )
    lines.append(" * TODO: Implement the actual test logic.\n")
    lines.append(" */\n\n")

    # Build import statements
    if target_file and artifacts:
        # Normalize the file path
        normalized_path = str(Path(target_file).as_posix())
        # Remove leading ./
        if normalized_path.startswith("./"):
            normalized_path = normalized_path[2:]

        # Convert to relative import path from tests/ directory
        # e.g., "src/calculator.ts" -> "../src/calculator"
        path_obj = Path(normalized_path)
        # Remove extension for TypeScript imports
        import_path = str(path_obj.parent / path_obj.stem)
        # Make it a relative import
        import_path = f"../{import_path}"

        # Group artifacts by type for import
        # Runtime-testable artifacts (can be imported and tested)
        classes = [a["name"] for a in artifacts if a.get("type") == "class"]
        functions = [
            a["name"]
            for a in artifacts
            if a.get("type") == "function" and not a.get("class")
        ]
        enums = [a["name"] for a in artifacts if a.get("type") == "enum"]
        namespaces = [a["name"] for a in artifacts if a.get("type") == "namespace"]

        # Compile-time only artifacts (for type checking, not runtime testing)
        interfaces = [a["name"] for a in artifacts if a.get("type") == "interface"]
        types = [a["name"] for a in artifacts if a.get("type") == "type"]

        # Generate import statement
        import_items = classes + functions + enums + namespaces
        type_items = interfaces + types

        if import_items or type_items:
            lines.append("import { ")
            if import_items:
                lines.append(", ".join(import_items))
                if type_items:
                    lines.append(", ")
            if type_items:
                lines.append("type " + ", type ".join(type_items))
            lines.append(f" }} from '{import_path}';\n\n")

    # Generate test suites for each artifact
    for artifact in artifacts:
        artifact_type = artifact.get("type")
        artifact_name = artifact.get("name")
        parent_class = artifact.get("class")

        if not artifact_name:
            continue

        # Create describe block name
        if parent_class:
            describe_name = f"{parent_class}.{artifact_name}"
        else:
            describe_name = artifact_name

        lines.append(f"describe('{describe_name}', () => {{\n")

        # Handle different artifact types
        if artifact_type in ["interface", "type"]:
            # Interfaces and types are compile-time only
            lines.append(
                "  // NOTE: Interfaces and type aliases are compile-time constructs\n"
            )
            lines.append("  // They cannot be tested at runtime in TypeScript\n")
            lines.append("  // Type checking is performed by the TypeScript compiler\n")
            lines.append("  it('should be defined for type checking', () => {\n")
            lines.append("    // This test ensures the file compiles successfully\n")
            lines.append(
                "    expect(true).toBe(false); // TODO: Remove once implementation is complete\n"
            )
            lines.append("  });\n")

        elif artifact_type == "class":
            # Test class instantiation
            lines.append("  it('should be defined', () => {\n")
            lines.append(f"    expect({artifact_name}).toBeDefined();\n")
            lines.append("    expect(true).toBe(false); // TODO: Implement test\n")
            lines.append("  });\n\n")

            lines.append("  it('should be instantiable', () => {\n")
            lines.append("    // TODO: Provide appropriate constructor arguments\n")
            lines.append(f"    // const instance = new {artifact_name}();\n")
            lines.append(
                "    // expect(instance).toBeInstanceOf(" + artifact_name + ");\n"
            )
            lines.append("    expect(true).toBe(false); // TODO: Implement test\n")
            lines.append("  });\n")

        elif artifact_type == "function":
            # Test function existence and behavior
            if parent_class:
                # Method of a class
                lines.append(f"  it('should exist on {parent_class}', () => {{\n")
                lines.append(
                    f"    // TODO: Create instance of {parent_class} and verify method\n"
                )
                lines.append(f"    // const instance = new {parent_class}();\n")
                lines.append(
                    f"    // expect(typeof instance.{artifact_name}).toBe('function');\n"
                )
            else:
                # Standalone function
                lines.append("  it('should be defined', () => {\n")
                lines.append(f"    expect({artifact_name}).toBeDefined();\n")
                lines.append(f"    expect(typeof {artifact_name}).toBe('function');\n")

            lines.append("    expect(true).toBe(false); // TODO: Implement test\n")
            lines.append("  });\n\n")

            # Test function behavior
            params = artifact.get("parameters", artifact.get("args", []))
            lines.append("  it('should work correctly', () => {\n")
            if params:
                param_names = ", ".join([p.get("name", "arg") for p in params])
                lines.append(
                    f"    // TODO: Provide appropriate test values for: {param_names}\n"
                )
                if parent_class:
                    lines.append(f"    // const instance = new {parent_class}();\n")
                    lines.append(
                        f"    // const result = instance.{artifact_name}(/* args */);\n"
                    )
                else:
                    lines.append(
                        f"    // const result = {artifact_name}(/* args */);\n"
                    )
            else:
                if parent_class:
                    lines.append(f"    // const instance = new {parent_class}();\n")
                    lines.append(f"    // const result = instance.{artifact_name}();\n")
                else:
                    lines.append(f"    // const result = {artifact_name}();\n")
            lines.append("    // expect(result).toBe(/* expected value */);\n")
            lines.append("    expect(true).toBe(false); // TODO: Implement test\n")
            lines.append("  });\n")

        elif artifact_type == "enum":
            # Test enum values
            lines.append("  it('should have expected values', () => {\n")
            lines.append(f"    expect({artifact_name}).toBeDefined();\n")
            lines.append("    // TODO: Verify enum values\n")
            lines.append(f"    // expect({artifact_name}.SomeValue).toBeDefined();\n")
            lines.append("    expect(true).toBe(false); // TODO: Implement test\n")
            lines.append("  });\n")

        elif artifact_type == "namespace":
            # Test namespace exports
            lines.append("  it('should export expected members', () => {\n")
            lines.append(f"    expect({artifact_name}).toBeDefined();\n")
            lines.append("    // TODO: Verify namespace exports\n")
            lines.append(
                f"    // expect(typeof {artifact_name}.someFunction).toBe('function');\n"
            )
            lines.append("    expect(true).toBe(false); // TODO: Implement test\n")
            lines.append("  });\n")

        else:
            # Generic test for other artifact types
            lines.append("  it('should be defined', () => {\n")
            lines.append(f"    // TODO: Implement test for {artifact_type}\n")
            lines.append("    expect(true).toBe(false); // TODO: Implement test\n")
            lines.append("  });\n")

        lines.append("});\n\n")

    # Write the stub file
    content = "".join(lines)
    with open(stub_file, "w", encoding="utf-8") as f:
        f.write(content)

    return str(stub_file)


def run_snapshot(
    file_path: str,
    output_dir: str = "manifests",
    force: bool = False,
    skip_test_stub: bool = False,
) -> None:
    """Core snapshot generation logic accepting parsed arguments.

    Args:
        file_path: Path to the Python (.py) or TypeScript (.ts, .tsx, .js, .jsx) file to snapshot
        output_dir: Directory to write the manifest (default: manifests)
        force: If True, overwrite existing manifests without prompting
        skip_test_stub: If True, skip test stub generation (default: False)

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """
    # Validate that the file exists
    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Generate the snapshot
        manifest_path = generate_snapshot(file_path, output_dir, force, skip_test_stub)

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


def main() -> None:
    """CLI entry point for the snapshot generator."""
    parser = argparse.ArgumentParser(
        description="Generate MAID snapshot manifests from existing Python or TypeScript files"
    )
    parser.add_argument(
        "file_path",
        help="Path to the Python (.py) or TypeScript (.ts, .tsx, .js, .jsx) file to snapshot",
    )
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
    parser.add_argument(
        "--skip-test-stub",
        action="store_true",
        help="Skip test stub generation (stubs are generated by default)",
    )

    args = parser.parse_args()
    run_snapshot(args.file_path, args.output_dir, args.force, args.skip_test_stub)


if __name__ == "__main__":
    main()
