"""TypeScript/JavaScript validator using tree-sitter AST parsing.

This validator provides production-ready validation for TypeScript and JavaScript files,
supporting all language constructs including classes, interfaces, functions, type aliases,
enums, namespaces, decorators, and JSX/TSX syntax.

Supports file extensions: .ts, .tsx, .js, .jsx
"""

from maid_runner.validators.base_validator import BaseValidator


class TypeScriptValidator(BaseValidator):
    """Validates TypeScript/JavaScript files using tree-sitter AST parsing.

    Features:
    - Accurate AST-based parsing (not regex)
    - Dual grammar support (TypeScript and TSX)
    - Complete TypeScript language coverage
    - Framework support (Angular, React, NestJS, Vue)
    """

    def __init__(self):
        """Initialize TypeScript and TSX parsers."""
        from tree_sitter import Language, Parser
        import tree_sitter_typescript as ts_ts

        # Initialize TypeScript language and parser
        self.ts_language = Language(ts_ts.language_typescript())
        self.ts_parser = Parser(self.ts_language)

        # Initialize TSX language and parser
        self.tsx_language = Language(ts_ts.language_tsx())
        self.tsx_parser = Parser(self.tsx_language)

    def supports_file(self, file_path: str) -> bool:
        """Check if file is a TypeScript/JavaScript file.

        Args:
            file_path: Path to the file

        Returns:
            True if file extension is .ts, .tsx, .js, or .jsx
        """
        return file_path.endswith((".ts", ".tsx", ".js", ".jsx"))

    def collect_artifacts(self, file_path: str, validation_mode: str) -> dict:
        """Collect artifacts from TypeScript/JavaScript file.

        Args:
            file_path: Path to the TypeScript/JavaScript file
            validation_mode: "implementation" or "behavioral"

        Returns:
            Dictionary containing found artifacts
        """
        tree, source_code = self._parse_typescript_file(file_path)

        if validation_mode == "implementation":
            return self._collect_implementation_artifacts(tree, source_code)
        else:
            return self._collect_behavioral_artifacts(tree, source_code)

    def _parse_typescript_file(self, file_path: str):
        """Parse TypeScript file and return AST tree and source code.

        Args:
            file_path: Path to the TypeScript file

        Returns:
            Tuple of (tree, source_code) where source_code is bytes
        """
        with open(file_path, "rb") as f:
            source_code = f.read()

        lang = self._get_language_for_file(file_path)
        parser = self.tsx_parser if lang == "tsx" else self.ts_parser

        return parser.parse(source_code), source_code

    def _collect_implementation_artifacts(self, tree, source_code: bytes) -> dict:
        """Collect implementation artifacts (definitions).

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary with found classes, interfaces, functions, etc.
        """
        # Combine all type declarations into found_classes
        classes = self._extract_classes(tree, source_code)
        interfaces = self._extract_interfaces(tree, source_code)
        type_aliases = self._extract_type_aliases(tree, source_code)
        enums = self._extract_enums(tree, source_code)
        namespaces = self._extract_namespaces(tree, source_code)
        all_classes = classes | interfaces | type_aliases | enums | namespaces

        # Extract other artifacts
        functions = self._extract_functions(tree, source_code)
        methods = self._extract_methods(tree, source_code)
        class_bases = self._extract_all_class_bases(tree, source_code)

        # Extract behavioral artifacts too (for implementation mode)
        used_classes = self._extract_class_usage(tree, source_code)
        used_functions = self._extract_function_calls(tree, source_code)
        used_methods = self._extract_method_calls(tree, source_code)

        return {
            "found_classes": all_classes,
            "found_functions": functions,
            "found_methods": methods,
            "found_class_bases": class_bases,
            "found_attributes": {},  # Not extracting attributes for TypeScript
            "variable_to_class": {},  # Not tracking variable to class mapping
            "found_function_types": {},  # Not extracting function types
            "found_method_types": {},  # Not extracting method types
            "used_classes": used_classes,
            "used_functions": used_functions,
            "used_methods": used_methods,
            "used_arguments": {},  # Not tracking used arguments
        }

    def _collect_behavioral_artifacts(self, tree, source_code: bytes) -> dict:
        """Collect behavioral artifacts (usage).

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary with class usage, function calls, method calls
        """
        return {
            "used_classes": self._extract_class_usage(tree, source_code),
            "used_functions": self._extract_function_calls(tree, source_code),
            "used_methods": self._extract_method_calls(tree, source_code),
        }

    def _traverse_tree(self, node, callback):
        """Recursively traverse AST nodes.

        Args:
            node: Current AST node
            callback: Function to call for each node
        """
        callback(node)
        for child in node.children:
            self._traverse_tree(child, callback)

    def _get_node_text(self, node, source_code: bytes) -> str:
        """Extract text from AST node.

        Args:
            node: AST node
            source_code: Source code as bytes

        Returns:
            Text content of the node
        """
        return source_code[node.start_byte : node.end_byte].decode("utf-8")

    def _extract_identifier(self, node, source_code: bytes) -> str:
        """Extract identifier name from node.

        Args:
            node: AST node
            source_code: Source code as bytes

        Returns:
            Identifier name or empty string
        """
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return self._get_node_text(child, source_code)
        return ""

    def _extract_classes(self, tree, source_code: bytes) -> set:
        """Extract class names from AST.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of class names
        """
        classes = set()

        def _visit(node):
            if node.type in ("class_declaration", "abstract_class_declaration"):
                for child in node.children:
                    if child.type == "type_identifier":
                        name = self._get_node_text(child, source_code)
                        classes.add(name)
                        break

        self._traverse_tree(tree.root_node, _visit)
        return classes

    def _extract_interfaces(self, tree, source_code: bytes) -> set:
        """Extract interface names from AST.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of interface names
        """
        interfaces = set()

        def _visit(node):
            if node.type == "interface_declaration":
                for child in node.children:
                    if child.type == "type_identifier":
                        name = self._get_node_text(child, source_code)
                        interfaces.add(name)
                        break

        self._traverse_tree(tree.root_node, _visit)
        return interfaces

    def _extract_type_aliases(self, tree, source_code: bytes) -> set:
        """Extract type alias names from AST.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of type alias names
        """
        type_aliases = set()

        def _visit(node):
            if node.type == "type_alias_declaration":
                for child in node.children:
                    if child.type == "type_identifier":
                        name = self._get_node_text(child, source_code)
                        type_aliases.add(name)
                        break

        self._traverse_tree(tree.root_node, _visit)
        return type_aliases

    def _extract_enums(self, tree, source_code: bytes) -> set:
        """Extract enum names from AST.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of enum names
        """
        enums = set()

        def _visit(node):
            if node.type == "enum_declaration":
                for child in node.children:
                    if child.type == "identifier":
                        name = self._get_node_text(child, source_code)
                        enums.add(name)
                        break

        self._traverse_tree(tree.root_node, _visit)
        return enums

    def _extract_namespaces(self, tree, source_code: bytes) -> set:
        """Extract namespace names from AST.

        Note: TypeScript namespaces use 'internal_module' node type.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of namespace names
        """
        namespaces = set()

        def _visit(node):
            if node.type == "internal_module":
                for child in node.children:
                    if child.type == "identifier":
                        name = self._get_node_text(child, source_code)
                        namespaces.add(name)
                        break

        self._traverse_tree(tree.root_node, _visit)
        return namespaces

    def _extract_functions(self, tree, source_code: bytes) -> dict:
        """Extract function declarations with their parameters.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping function names to parameter lists
        """
        functions = {}

        def _visit(node):
            # Handle both regular function declarations and ambient function signatures
            if node.type in ("function_declaration", "function_signature"):
                name = None
                params = []

                for child in node.children:
                    if child.type == "identifier":
                        name = self._get_node_text(child, source_code)
                    elif child.type == "formal_parameters":
                        params = self._extract_parameters(child, source_code)

                if name:
                    functions[name] = params

        self._traverse_tree(tree.root_node, _visit)

        # Also extract arrow functions
        arrow_functions = self._extract_arrow_functions(tree, source_code)
        functions.update(arrow_functions)

        return functions

    def _extract_arrow_functions(self, tree, source_code: bytes) -> dict:
        """Extract arrow function declarations with their parameters.

        Arrow functions are found under lexical_declaration -> variable_declarator.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping arrow function names to parameter lists
        """
        functions = {}

        def _visit(node):
            if node.type == "lexical_declaration":
                for child in node.children:
                    if child.type == "variable_declarator":
                        name = None
                        params = []

                        for subchild in child.children:
                            if subchild.type == "identifier":
                                name = self._get_node_text(subchild, source_code)
                            elif subchild.type == "arrow_function":
                                for arrow_child in subchild.children:
                                    if arrow_child.type == "formal_parameters":
                                        params = self._extract_parameters(
                                            arrow_child, source_code
                                        )
                                    elif arrow_child.type == "identifier":
                                        # Single parameter without parentheses
                                        params = [
                                            self._get_node_text(
                                                arrow_child, source_code
                                            )
                                        ]

                        if name and any(
                            subchild.type == "arrow_function"
                            for subchild in child.children
                        ):
                            functions[name] = params

        self._traverse_tree(tree.root_node, _visit)
        return functions

    def _extract_methods(self, tree, source_code: bytes) -> dict:
        """Extract class methods with their parameters.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping ClassName to dict of methodName: parameter lists
            Format: {ClassName: {methodName: [params]}}
        """
        methods = {}

        def _visit(node):
            if node.type in ("class_declaration", "abstract_class_declaration"):
                class_name = self._get_class_name_from_node(node, source_code)
                if class_name:
                    class_methods = self._find_class_methods(node, source_code)
                    if class_methods:
                        methods[class_name] = class_methods

        self._traverse_tree(tree.root_node, _visit)
        return methods

    def _extract_parameters(self, params_node, source_code: bytes) -> list:
        """Extract parameter names from formal_parameters node.

        Args:
            params_node: formal_parameters AST node
            source_code: Source code as bytes

        Returns:
            List of parameter names
        """
        params = []

        for child in params_node.children:
            if child.type == "required_parameter":
                # Check if it contains a rest_pattern
                has_rest = False
                for subchild in child.children:
                    if subchild.type == "rest_pattern":
                        param_name = self._handle_rest_parameter(subchild, source_code)
                        if param_name:
                            params.append(param_name)
                        has_rest = True
                        break

                if not has_rest:
                    # Find the identifier (pattern child)
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            params.append(self._get_node_text(subchild, source_code))
                            break
                        elif subchild.type == "pattern":
                            # Pattern contains the identifier
                            for pattern_child in subchild.children:
                                if pattern_child.type == "identifier":
                                    params.append(
                                        self._get_node_text(pattern_child, source_code)
                                    )
                                    break
            elif child.type == "optional_parameter":
                param_name = self._handle_optional_parameter(child, source_code)
                if param_name:
                    params.append(param_name)
            elif child.type in ("object_pattern", "array_pattern"):
                # Destructured parameters
                destructured = self._handle_destructured_parameter(child, source_code)
                params.extend(destructured)

        return params

    def _extract_class_bases(self, class_node, source_code: bytes) -> list:
        """Extract base classes from class declaration.

        Args:
            class_node: Class declaration AST node
            source_code: Source code as bytes

        Returns:
            List of base class names
        """
        bases = []

        for child in class_node.children:
            if child.type == "class_heritage":
                for heritage_child in child.children:
                    if heritage_child.type == "extends_clause":
                        for extends_child in heritage_child.children:
                            if extends_child.type in ("identifier", "type_identifier"):
                                bases.append(
                                    self._get_node_text(extends_child, source_code)
                                )

        return bases

    def _extract_all_class_bases(self, tree, source_code: bytes) -> dict:
        """Extract base classes for all classes in the file.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping class names to lists of base class names
        """
        class_bases = {}

        def _visit(node):
            if node.type in ("class_declaration", "abstract_class_declaration"):
                class_name = self._get_class_name_from_node(node, source_code)
                if class_name:
                    bases = self._extract_class_bases(node, source_code)
                    if bases:
                        class_bases[class_name] = bases

        self._traverse_tree(tree.root_node, _visit)
        return class_bases

    def _is_exported(self, node) -> bool:
        """Check if node is exported.

        Args:
            node: AST node

        Returns:
            True if node is wrapped in export_statement
        """
        if node.parent and node.parent.type == "export_statement":
            return True
        return False

    def _extract_class_usage(self, tree, source_code: bytes) -> set:
        """Extract class instantiations (new ClassName).

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of class names being instantiated
        """
        class_usage = set()

        def _visit(node):
            if node.type == "new_expression":
                for child in node.children:
                    if child.type == "identifier":
                        class_usage.add(self._get_node_text(child, source_code))
                        break
                    elif child.type == "call_expression":
                        # Handle new ClassName()
                        for call_child in child.children:
                            if call_child.type == "identifier":
                                class_usage.add(
                                    self._get_node_text(call_child, source_code)
                                )
                                break

        self._traverse_tree(tree.root_node, _visit)
        return class_usage

    def _extract_function_calls(self, tree, source_code: bytes) -> set:
        """Extract function calls.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of function names being called
        """
        function_calls = set()

        def _visit(node):
            if node.type == "call_expression":
                for child in node.children:
                    if child.type == "identifier":
                        function_calls.add(self._get_node_text(child, source_code))
                        break

        self._traverse_tree(tree.root_node, _visit)
        return function_calls

    def _extract_method_calls(self, tree, source_code: bytes) -> dict:
        """Extract method calls (object.method()).

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping object names to sets of method names
        """
        method_calls = {}

        def _visit(node):
            if node.type == "call_expression":
                for child in node.children:
                    if child.type == "member_expression":
                        obj_name = None
                        method_name = None

                        for member_child in child.children:
                            if (
                                member_child.type in ("identifier", "this")
                                and obj_name is None
                            ):
                                obj_name = self._get_node_text(
                                    member_child, source_code
                                )
                            elif member_child.type == "property_identifier":
                                method_name = self._get_node_text(
                                    member_child, source_code
                                )

                        if obj_name and method_name:
                            if obj_name not in method_calls:
                                method_calls[obj_name] = set()
                            method_calls[obj_name].add(method_name)

        self._traverse_tree(tree.root_node, _visit)
        return method_calls

    def _get_class_name_from_node(self, node, source_code: bytes) -> str:
        """Extract class name from class declaration node.

        Args:
            node: Class declaration node
            source_code: Source code as bytes

        Returns:
            Class name or empty string
        """
        for child in node.children:
            if child.type == "type_identifier":
                return self._get_node_text(child, source_code)
        return ""

    def _get_function_name_from_node(self, node, source_code: bytes) -> str:
        """Extract function name from function declaration node.

        Args:
            node: Function declaration node
            source_code: Source code as bytes

        Returns:
            Function name or empty string
        """
        for child in node.children:
            if child.type == "identifier":
                return self._get_node_text(child, source_code)
        return ""

    def _find_class_methods(self, class_node, source_code: bytes) -> dict:
        """Find all methods in a class.

        Args:
            class_node: Class declaration node
            source_code: Source code as bytes

        Returns:
            Dictionary mapping method names to parameter lists
        """
        methods = {}

        for child in class_node.children:
            if child.type == "class_body":
                for body_child in child.children:
                    if body_child.type in (
                        "method_definition",
                        "public_field_definition",
                        "abstract_method_signature",
                    ):
                        method_name = None
                        params = []

                        for method_child in body_child.children:
                            if method_child.type in (
                                "property_identifier",
                                "identifier",
                            ):
                                method_name = self._get_node_text(
                                    method_child, source_code
                                )
                            elif method_child.type == "formal_parameters":
                                params = self._extract_parameters(
                                    method_child, source_code
                                )

                        # Skip constructors
                        if method_name and method_name != "constructor":
                            methods[method_name] = params

        return methods

    def _is_abstract_class(self, node) -> bool:
        """Check if class is abstract.

        Args:
            node: Class declaration node

        Returns:
            True if class is abstract
        """
        return node.type == "abstract_class_declaration"

    def _is_static_method(self, node) -> bool:
        """Check if method is static.

        Args:
            node: Method definition node

        Returns:
            True if method has static modifier
        """
        for child in node.children:
            if child.type == "static":
                return True
        return False

    def _has_decorator(self, node) -> bool:
        """Check if node has decorator.

        Args:
            node: AST node

        Returns:
            True if node has decorator
        """
        if node.parent:
            for sibling in node.parent.children:
                if sibling.type == "decorator":
                    return True
        return False

    def _is_getter_or_setter(self, node) -> bool:
        """Check if method is getter or setter.

        Args:
            node: Method definition node

        Returns:
            True if method is getter or setter
        """
        for child in node.children:
            if child.type in ("get", "set"):
                return True
        return False

    def _is_async(self, node) -> bool:
        """Check if function/method is async.

        Args:
            node: Function or method node

        Returns:
            True if async
        """
        for child in node.children:
            if child.type == "async":
                return True
        return False

    def _handle_optional_parameter(self, param_node, source_code: bytes) -> str:
        """Extract name from optional parameter.

        Args:
            param_node: optional_parameter node
            source_code: Source code as bytes

        Returns:
            Parameter name
        """
        for child in param_node.children:
            if child.type == "identifier":
                return self._get_node_text(child, source_code)
            elif child.type == "pattern":
                for pattern_child in child.children:
                    if pattern_child.type == "identifier":
                        return self._get_node_text(pattern_child, source_code)
        return ""

    def _handle_rest_parameter(self, param_node, source_code: bytes) -> str:
        """Extract name from rest parameter (...args).

        Args:
            param_node: rest_pattern node
            source_code: Source code as bytes

        Returns:
            Parameter name without ... prefix
        """
        for child in param_node.children:
            if child.type == "identifier":
                return self._get_node_text(child, source_code)
        return ""

    def _handle_destructured_parameter(self, param_node, source_code: bytes) -> list:
        """Extract names from destructured parameter.

        Args:
            param_node: object_pattern or array_pattern node
            source_code: Source code as bytes

        Returns:
            List of destructured parameter names
        """
        params = []

        def _extract_from_pattern(node):
            if node.type == "identifier":
                params.append(self._get_node_text(node, source_code))
            elif node.type in (
                "shorthand_property_identifier_pattern",
                "shorthand_property_identifier",
            ):
                params.append(self._get_node_text(node, source_code))
            else:
                for child in node.children:
                    _extract_from_pattern(child)

        _extract_from_pattern(param_node)
        return params

    def _get_language_for_file(self, file_path: str) -> str:
        """Determine which grammar to use for file.

        Args:
            file_path: Path to the file

        Returns:
            'tsx' for .tsx/.jsx files, 'typescript' for .ts/.js files
        """
        if file_path.endswith((".tsx", ".jsx")):
            return "tsx"
        return "typescript"
