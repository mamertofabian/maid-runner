"""TypeScript/JavaScript validator implementation.

This module provides basic TypeScript and JavaScript artifact collection.
Currently uses regex-based parsing. Can be enhanced with tree-sitter for
more accurate AST-based parsing.
"""

import re
from typing import Set, Dict, List
from maid_runner.validators.base_validator import BaseValidator


class TypeScriptValidator(BaseValidator):
    """Validator for TypeScript and JavaScript source files.

    Handles .ts, .tsx, .js, .jsx files. Provides basic artifact collection
    for classes, functions, and interfaces using regex-based parsing.

    Note: This is a basic implementation. For production use, consider
    enhancing with tree-sitter-typescript for proper AST parsing.
    """

    def supports_file(self, file_path: str) -> bool:
        """Check if this validator supports TypeScript/JavaScript files.

        Args:
            file_path: Path to the file to check

        Returns:
            True if file has .ts, .tsx, .js, or .jsx extension
        """
        return file_path.endswith((".ts", ".tsx", ".js", ".jsx"))

    def collect_artifacts(self, file_path: str, validation_mode: str) -> dict:
        """Collect artifacts from a TypeScript/JavaScript file.

        Args:
            file_path: Path to the TypeScript/JavaScript file to parse
            validation_mode: Either "implementation" or "behavioral"

        Returns:
            Dictionary containing collected artifacts compatible with
            the validation infrastructure
        """
        with open(file_path, "r") as f:
            content = f.read()

        if validation_mode == "implementation":
            return self._collect_implementation_artifacts(content)
        else:
            return self._collect_behavioral_artifacts(content)

    def _collect_implementation_artifacts(self, content: str) -> dict:
        """Collect artifacts from TypeScript implementation code.

        Args:
            content: Source code content

        Returns:
            Dictionary with found classes, functions, etc.
        """
        found_classes = self._extract_classes(content)
        found_functions = self._extract_functions(content)
        found_interfaces = self._extract_interfaces(content)
        found_methods = self._extract_methods(content)

        return {
            "found_classes": found_classes
            | found_interfaces,  # Combine classes and interfaces
            "found_class_bases": {},
            "found_attributes": {},
            "variable_to_class": {},
            "found_functions": found_functions,
            "found_methods": found_methods,
            "found_function_types": {},
            "found_method_types": {},
            "used_classes": set(),
            "used_functions": set(),
            "used_methods": {},
            "used_arguments": set(),
        }

    def _collect_behavioral_artifacts(self, content: str) -> dict:
        """Collect usage artifacts from TypeScript test code.

        Args:
            content: Test code content

        Returns:
            Dictionary with used classes, functions, etc.
        """
        # Detect class instantiations (new ClassName())
        used_classes = self._extract_class_instantiations(content)

        # Detect method calls (object.method())
        used_methods = self._extract_method_calls(content)

        # Detect standalone function calls
        all_calls = self._extract_function_calls(content)

        # Filter out method names from function calls
        method_names = set()
        for methods in used_methods.values():
            method_names.update(methods)

        used_functions = all_calls - method_names - used_classes

        return {
            "found_classes": set(),
            "found_class_bases": {},
            "found_attributes": {},
            "variable_to_class": {},
            "found_functions": {},
            "found_methods": {},
            "found_function_types": {},
            "found_method_types": {},
            "used_classes": used_classes,
            "used_functions": used_functions,
            "used_methods": used_methods,
            "used_arguments": set(),
        }

    def _extract_classes(self, content: str) -> Set[str]:
        """Extract class names from TypeScript/JavaScript code.

        Args:
            content: Source code content

        Returns:
            Set of class names
        """
        # Match: class ClassName, export class ClassName, etc.
        class_pattern = r"\bclass\s+([A-Z][a-zA-Z0-9_]*)"
        matches = re.findall(class_pattern, content)
        return set(matches)

    def _extract_interfaces(self, content: str) -> Set[str]:
        """Extract interface names from TypeScript code.

        Args:
            content: Source code content

        Returns:
            Set of interface names
        """
        # Match: interface InterfaceName, export interface InterfaceName
        interface_pattern = r"\binterface\s+([A-Z][a-zA-Z0-9_]*)"
        matches = re.findall(interface_pattern, content)
        return set(matches)

    def _extract_functions(self, content: str) -> Dict[str, List[str]]:
        """Extract function names and parameters from code.

        Args:
            content: Source code content

        Returns:
            Dictionary mapping function names to parameter lists
        """
        functions = {}

        # Match: function functionName(params), export function functionName(params)
        function_pattern = r"\bfunction\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)"
        matches = re.findall(function_pattern, content)

        for func_name, params_str in matches:
            # Parse parameters (basic parsing, doesn't handle complex types)
            params = []
            if params_str.strip():
                param_list = params_str.split(",")
                for param in param_list:
                    param = param.strip()
                    if param:
                        # Extract parameter name (before : or =)
                        param_name = re.split(r"[:\s=]", param)[0].strip()
                        if param_name:
                            params.append(param_name)
            functions[func_name] = params

        # Also match arrow functions: const funcName = (params) => ...
        arrow_pattern = r"\bconst\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\((.*?)\)\s*=>"
        arrow_matches = re.findall(arrow_pattern, content)

        for func_name, params_str in arrow_matches:
            params = []
            if params_str.strip():
                param_list = params_str.split(",")
                for param in param_list:
                    param = param.strip()
                    if param:
                        param_name = re.split(r"[:\s=]", param)[0].strip()
                        if param_name:
                            params.append(param_name)
            functions[func_name] = params

        return functions

    def _extract_function_calls(self, content: str) -> Set[str]:
        """Extract function calls from code (for behavioral validation).

        Args:
            content: Source code content

        Returns:
            Set of function names that are called
        """
        # Match: functionName(...)
        call_pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
        matches = re.findall(call_pattern, content)
        return set(matches)

    def _extract_methods(self, content: str) -> Dict[str, Dict[str, List[str]]]:
        """Extract methods from TypeScript/JavaScript classes.

        Args:
            content: Source code content

        Returns:
            Dictionary mapping class names to their methods
        """
        methods = {}

        # Find class declarations and their bodies using brace matching
        lines = content.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # Check if this line declares a class
            class_match = re.match(r"\s*class\s+([A-Z][a-zA-Z0-9_]*)", line)
            if class_match:
                class_name = class_match.group(1)

                # Find the opening brace
                if "{" in line:
                    start_line = i
                else:
                    # Look for opening brace in next lines
                    i += 1
                    while i < len(lines) and "{" not in lines[i]:
                        i += 1
                    start_line = i

                # Extract class body by matching braces
                brace_count = 0
                class_body_lines = []
                j = start_line
                while j < len(lines):
                    current_line = lines[j]
                    for char in current_line:
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1

                    class_body_lines.append(current_line)

                    if brace_count == 0 and "{" in lines[start_line]:
                        break
                    j += 1

                # Extract methods from class body
                # Match: methodName(params) or async methodName(params)
                method_pattern = (
                    r"^\s*(?:async\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*[:{\[]"
                )
                class_methods = {}

                for body_line in class_body_lines:
                    method_match = re.match(method_pattern, body_line)
                    if method_match:
                        method_name = method_match.group(1)
                        params_str = method_match.group(2)

                        # Skip constructor
                        if method_name == "constructor":
                            continue

                        # Parse parameters
                        params = []
                        if params_str.strip():
                            param_list = params_str.split(",")
                            for param in param_list:
                                param = param.strip()
                                if param:
                                    param_name = re.split(r"[:\s=]", param)[0].strip()
                                    if param_name:
                                        params.append(param_name)

                        class_methods[method_name] = params

                if class_methods:
                    methods[class_name] = class_methods

            i += 1

        return methods

    def _extract_class_instantiations(self, content: str) -> Set[str]:
        """Extract class names that are instantiated with 'new'.

        Args:
            content: Source code content

        Returns:
            Set of class names that are instantiated
        """
        # Match: new ClassName(...)
        pattern = r"\bnew\s+([A-Z][a-zA-Z0-9_]*)\s*\("
        matches = re.findall(pattern, content)
        return set(matches)

    def _extract_method_calls(self, content: str) -> Dict[str, Set[str]]:
        """Extract method calls from code (object.method()).

        Args:
            content: Source code content

        Returns:
            Dictionary mapping variable names to sets of methods called on them
        """
        methods = {}

        # Match: variableName.methodName(...)
        # This is a simplified pattern - doesn't handle chaining perfectly
        pattern = r"\b([a-z][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\("
        matches = re.findall(pattern, content)

        for var_name, method_name in matches:
            if var_name not in methods:
                methods[var_name] = set()
            methods[var_name].add(method_name)

        return methods
