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
            Dictionary with class usage, function calls, method calls, and used arguments
        """
        # Extract variable-to-class mapping for method call resolution
        variable_to_class = self._extract_variable_to_class_mapping(tree, source_code)

        # Combine regular function calls with JSX component usage
        used_functions = self._extract_function_calls(tree, source_code)
        jsx_components = self._extract_jsx_component_usage(tree, source_code)
        used_functions.update(jsx_components)

        # Combine class instantiation with type annotation usage
        used_classes = self._extract_class_usage(tree, source_code)
        type_annotations = self._extract_type_annotation_usage(tree, source_code)
        used_classes.update(type_annotations)

        return {
            "used_classes": used_classes,
            "used_functions": used_functions,
            "used_methods": self._extract_method_calls(
                tree, source_code, variable_to_class
            ),
            "used_arguments": self._extract_used_arguments(tree, source_code),
        }

    def _extract_used_arguments(self, tree, source_code: bytes) -> set:
        """Extract used arguments from function/method calls.

        Detects when function calls have positional arguments and adds
        __positional__ marker. Also extracts named arguments from object
        literals passed to functions.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of argument identifiers, including __positional__ if any
            positional arguments are detected
        """
        used_arguments = set()
        has_positional_args = False

        def _visit(node):
            nonlocal has_positional_args

            if node.type == "call_expression":
                # Check if the call has arguments
                for child in node.children:
                    if child.type == "arguments":
                        # Check if arguments node has actual argument children
                        for arg_child in child.children:
                            # Skip parentheses and commas
                            if arg_child.type in ("(", ")", ","):
                                continue
                            # Found an actual argument
                            has_positional_args = True

                            # Extract named arguments from object literals
                            if arg_child.type == "object":
                                self._extract_object_property_names(
                                    arg_child, source_code, used_arguments
                                )

        self._traverse_tree(tree.root_node, _visit)

        if has_positional_args:
            used_arguments.add("__positional__")

        return used_arguments

    def _extract_jsx_component_usage(self, tree, source_code: bytes) -> set:
        """Extract JSX component usage from the AST.

        Detects React component usage in JSX elements like <Admin /> or <Container>...</Container>.
        Only extracts PascalCase component names (custom React components), not lowercase
        HTML elements like <div> or <span>.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of component names used in JSX elements
        """
        jsx_components = set()

        def _visit(node):
            # Handle JSX self-closing elements: <Admin />
            if node.type == "jsx_self_closing_element":
                for child in node.children:
                    if child.type == "identifier":
                        name = self._get_node_text(child, source_code)
                        # Only include PascalCase names (React components)
                        if name and name[0].isupper():
                            jsx_components.add(name)
                        break

            # Handle JSX opening elements: <Container>...</Container>
            elif node.type == "jsx_opening_element":
                for child in node.children:
                    if child.type == "identifier":
                        name = self._get_node_text(child, source_code)
                        # Only include PascalCase names (React components)
                        if name and name[0].isupper():
                            jsx_components.add(name)
                        break

        self._traverse_tree(tree.root_node, _visit)
        return jsx_components

    def _extract_type_annotation_usage(self, tree, source_code: bytes) -> set:
        """Extract type identifiers used in type annotations.

        Detects TypeScript/TSX type annotations like:
        - const x: MyType = ...
        - let items: Array<Item> = ...
        - function foo(x: ParamType): ReturnType { ... }

        This enables behavioral validation for TypeScript types and interfaces,
        where tests verify values conform to type shapes.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of type names used in type annotations
        """
        type_usage = set()

        # Built-in types to exclude (lowercase or common JS/TS types)
        builtin_types = {
            "string",
            "number",
            "boolean",
            "object",
            "any",
            "void",
            "never",
            "unknown",
            "null",
            "undefined",
            "symbol",
            "bigint",
            "Array",
            "Object",
            "String",
            "Number",
            "Boolean",
            "Function",
            "Promise",
            "Map",
            "Set",
            "WeakMap",
            "WeakSet",
            "Date",
            "RegExp",
            "Error",
            "Record",
            "Partial",
            "Required",
            "Readonly",
            "Pick",
            "Omit",
            "Exclude",
            "Extract",
            "NonNullable",
            "Parameters",
            "ReturnType",
            "InstanceType",
            "ThisType",
            "Awaited",
        }

        def _visit(node):
            # Look for type_annotation nodes
            if node.type == "type_annotation":
                self._extract_type_identifiers(
                    node, source_code, type_usage, builtin_types
                )

            # Also check return type annotations (: ReturnType after function params)
            # These appear as type_annotation children of function declarations

        self._traverse_tree(tree.root_node, _visit)
        return type_usage

    def _extract_type_identifiers(
        self, node, source_code: bytes, type_usage: set, builtin_types: set
    ) -> None:
        """Recursively extract type identifiers from a type annotation node.

        Args:
            node: AST node (type_annotation or child)
            source_code: Source code as bytes
            type_usage: Set to add type names to
            builtin_types: Set of built-in types to exclude
        """
        for child in node.children:
            if child.type == "type_identifier":
                type_name = self._get_node_text(child, source_code)
                # Only include custom types (PascalCase, not built-ins)
                if type_name and type_name not in builtin_types:
                    type_usage.add(type_name)
            # Recurse into nested types (generic_type, union_type, etc.)
            elif child.type in (
                "generic_type",
                "type_arguments",
                "union_type",
                "intersection_type",
                "array_type",
                "tuple_type",
                "parenthesized_type",
                "object_type",
                "function_type",
            ):
                self._extract_type_identifiers(
                    child, source_code, type_usage, builtin_types
                )

    def _extract_object_property_names(
        self, object_node, source_code: bytes, used_arguments: set
    ) -> None:
        """Extract property names from object literal for argument tracking.

        Args:
            object_node: AST node representing an object literal
            source_code: Source code as bytes
            used_arguments: Set to add property names to
        """
        for child in object_node.children:
            if child.type == "pair":
                for pair_child in child.children:
                    if pair_child.type == "property_identifier":
                        prop_name = self._get_node_text(pair_child, source_code)
                        used_arguments.add(prop_name)
                        break
            elif child.type == "shorthand_property_identifier":
                prop_name = self._get_node_text(child, source_code)
                used_arguments.add(prop_name)

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

    def _extract_final_property(self, node, source_code: bytes) -> str:
        """Extract final property_identifier from a member_expression chain.

        For expressions like `result.current.refetch`, this returns `refetch`.

        Args:
            node: member_expression AST node
            source_code: Source code as bytes

        Returns:
            Final property name or empty string
        """
        for child in node.children:
            if child.type == "property_identifier":
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

        Arrow functions are found in:
        - lexical_declaration -> variable_declarator (const/let variables)
        - public_field_definition (class properties)
        - pair (object properties)

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping arrow function names to parameter lists
        """
        functions = {}

        def _visit(node):
            # Handle variable declarations (const/let)
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
                                        param_name = self._get_node_text(
                                            arrow_child, source_code
                                        )
                                        # Check if there's a type annotation
                                        type_annotation = (
                                            self._find_type_annotation_in_node(
                                                subchild, source_code
                                            )
                                        )
                                        if type_annotation:
                                            params = [
                                                {
                                                    "name": param_name,
                                                    "type": type_annotation,
                                                }
                                            ]
                                        else:
                                            params = [{"name": param_name}]

                        if name and any(
                            subchild.type == "arrow_function"
                            for subchild in child.children
                        ):
                            functions[name] = params

            # Handle class property arrow functions
            elif node.type == "public_field_definition":
                name = None
                params = []

                for child in node.children:
                    if child.type == "property_identifier":
                        name = self._get_node_text(child, source_code)
                    elif child.type == "arrow_function":
                        for arrow_child in child.children:
                            if arrow_child.type == "formal_parameters":
                                params = self._extract_parameters(
                                    arrow_child, source_code
                                )
                            elif arrow_child.type == "identifier":
                                # Single parameter without parentheses
                                param_name = self._get_node_text(
                                    arrow_child, source_code
                                )
                                params = [{"name": param_name}]

                # Skip private/protected class property arrow functions
                if (
                    name
                    and any(child.type == "arrow_function" for child in node.children)
                    and not self._is_private_member(node)
                ):
                    functions[name] = params

            # NOTE: Object property arrow functions (node.type == "pair") are intentionally
            # NOT extracted. Arrow functions in object literals like { queryFn: () => {} }
            # are anonymous functions assigned to properties, not public function declarations.
            # They cannot be exported and should not appear in found_functions.

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
        """Extract parameter names and types from formal_parameters node.

        Args:
            params_node: formal_parameters AST node
            source_code: Source code as bytes

        Returns:
            List of parameter dicts with 'name' and optionally 'type' keys
        """
        params = []

        for child in params_node.children:
            if child.type == "required_parameter":
                # Check if it contains a rest_pattern
                has_rest = False
                for subchild in child.children:
                    if subchild.type == "rest_pattern":
                        param_info = self._handle_rest_parameter(subchild, source_code)
                        if param_info:
                            # Extract type annotation if present
                            type_annotation = self._find_type_annotation_in_node(
                                child, source_code
                            )
                            if type_annotation:
                                if isinstance(param_info, dict):
                                    param_info["type"] = type_annotation
                                else:
                                    param_info = {
                                        "name": param_info,
                                        "type": type_annotation,
                                    }
                            elif isinstance(param_info, str):
                                param_info = {"name": param_info}
                            params.append(param_info)
                        has_rest = True
                        break

                if not has_rest:
                    # Find the identifier (pattern child)
                    param_name = None
                    for subchild in child.children:
                        if subchild.type == "identifier":
                            param_name = self._get_node_text(subchild, source_code)
                            break
                        elif subchild.type == "pattern":
                            # Pattern contains the identifier
                            for pattern_child in subchild.children:
                                if pattern_child.type == "identifier":
                                    param_name = self._get_node_text(
                                        pattern_child, source_code
                                    )
                                    break

                    if param_name:
                        # Extract type annotation if present
                        type_annotation = self._find_type_annotation_in_node(
                            child, source_code
                        )
                        if type_annotation:
                            params.append({"name": param_name, "type": type_annotation})
                        else:
                            params.append({"name": param_name})
            elif child.type == "optional_parameter":
                param_info = self._handle_optional_parameter(child, source_code)
                if param_info:
                    # Extract type annotation if present
                    type_annotation = self._find_type_annotation_in_node(
                        child, source_code
                    )
                    if type_annotation:
                        if isinstance(param_info, dict):
                            param_info["type"] = type_annotation
                        else:
                            param_info = {"name": param_info, "type": type_annotation}
                    elif isinstance(param_info, str):
                        param_info = {"name": param_info}
                    params.append(param_info)
            elif child.type in ("object_pattern", "array_pattern"):
                # Destructured parameters
                destructured = self._handle_destructured_parameter(child, source_code)
                # Convert string names to dicts
                params.extend(
                    [
                        {"name": name} if isinstance(name, str) else name
                        for name in destructured
                    ]
                )

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

    def _extract_variable_to_class_mapping(self, tree, source_code: bytes) -> dict:
        """Extract mapping from variable names to class names.

        Combines three sources of variable-to-class mappings:
        1. Direct instantiation: const statusBar = new MaidStatusBar()
        2. Type annotations: let statusBar: MaidStatusBar;
        3. Assignment expressions: statusBar = new MaidStatusBar();

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping variable names to class names
        """
        variable_to_class = {}

        # Source 1: Direct instantiation in variable declaration
        def _get_class_from_new_expression(node):
            """Extract class name from a new_expression node."""
            for child in node.children:
                if child.type == "identifier":
                    return self._get_node_text(child, source_code)
                elif child.type == "call_expression":
                    # Handle new ClassName()
                    for call_child in child.children:
                        if call_child.type == "identifier":
                            return self._get_node_text(call_child, source_code)
            return None

        def _visit(node):
            # Match variable declarations: const/let/var name = new ClassName()
            if node.type in ("variable_declarator", "lexical_declaration"):
                # Find variable_declarator children
                declarators = []
                if node.type == "variable_declarator":
                    declarators = [node]
                else:
                    for child in node.children:
                        if child.type == "variable_declarator":
                            declarators.append(child)

                for declarator in declarators:
                    var_name = None
                    class_name = None

                    for child in declarator.children:
                        if child.type == "identifier" and var_name is None:
                            var_name = self._get_node_text(child, source_code)
                        elif child.type == "new_expression":
                            class_name = _get_class_from_new_expression(child)
                        # Source 4: Factory method patterns
                        # const service = ClassName.getInstance();
                        # const instance = Factory.create();
                        elif child.type == "call_expression":
                            for call_child in child.children:
                                if call_child.type == "member_expression":
                                    # Extract ClassName from ClassName.staticMethod()
                                    for member_child in call_child.children:
                                        if member_child.type == "identifier":
                                            potential_class = self._get_node_text(
                                                member_child, source_code
                                            )
                                            # Only consider uppercase names as classes
                                            if (
                                                potential_class
                                                and potential_class[0].isupper()
                                            ):
                                                class_name = potential_class
                                            break

                    if var_name and class_name:
                        variable_to_class[var_name] = class_name

        self._traverse_tree(tree.root_node, _visit)

        # Source 2: Type annotations (let statusBar: MaidStatusBar;)
        type_annotated = self._extract_type_annotated_variables(tree, source_code)
        for var_name, class_name in type_annotated.items():
            if var_name not in variable_to_class:
                variable_to_class[var_name] = class_name

        # Source 3: Assignment expressions (statusBar = new MaidStatusBar();)
        assignment_instantiations = self._extract_assignment_instantiations(
            tree, source_code
        )
        for var_name, class_name in assignment_instantiations.items():
            if var_name not in variable_to_class:
                variable_to_class[var_name] = class_name

        return variable_to_class

    def _extract_type_annotated_variables(self, tree, source_code: bytes) -> dict:
        """Extract variable-to-class mapping from type annotations.

        Tracks patterns like:
        - let statusBar: MaidStatusBar;
        - const service: UserService;

        Only maps to class/interface types, not primitive types.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping variable names to class/type names
        """
        variable_to_class = {}
        # Primitive types to ignore
        primitive_types = {
            "string",
            "number",
            "boolean",
            "any",
            "void",
            "null",
            "undefined",
            "never",
            "unknown",
            "object",
            "symbol",
            "bigint",
        }

        def _visit(node):
            # Match variable declarations with type annotations
            if node.type == "variable_declarator":
                var_name = None
                type_name = None

                for child in node.children:
                    if child.type == "identifier" and var_name is None:
                        var_name = self._get_node_text(child, source_code)
                    elif child.type == "type_annotation":
                        # Extract the type from the annotation
                        for type_child in child.children:
                            if type_child.type == "type_identifier":
                                type_name = self._get_node_text(type_child, source_code)
                                break

                # Only map if it's a class/interface type, not a primitive
                if var_name and type_name and type_name.lower() not in primitive_types:
                    variable_to_class[var_name] = type_name

        self._traverse_tree(tree.root_node, _visit)
        return variable_to_class

    def _extract_assignment_instantiations(self, tree, source_code: bytes) -> dict:
        """Extract variable-to-class mapping from assignment expressions.

        Tracks patterns like:
        - statusBar = new MaidStatusBar();
        - service = new UserService();

        This handles cases where variable is declared separately from instantiation,
        often seen in test setup (beforeEach) callbacks.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Dictionary mapping variable names to class names
        """
        variable_to_class = {}

        def _get_class_from_new_expression(node):
            """Extract class name from a new_expression node."""
            for child in node.children:
                if child.type == "identifier":
                    return self._get_node_text(child, source_code)
                elif child.type == "call_expression":
                    # Handle new ClassName()
                    for call_child in child.children:
                        if call_child.type == "identifier":
                            return self._get_node_text(call_child, source_code)
            return None

        def _visit(node):
            # Match assignment expressions: varName = new ClassName()
            if node.type == "assignment_expression":
                var_name = None
                class_name = None

                for child in node.children:
                    if child.type == "identifier" and var_name is None:
                        var_name = self._get_node_text(child, source_code)
                    elif child.type == "new_expression":
                        class_name = _get_class_from_new_expression(child)

                if var_name and class_name:
                    variable_to_class[var_name] = class_name

        self._traverse_tree(tree.root_node, _visit)
        return variable_to_class

    def _extract_class_usage(self, tree, source_code: bytes) -> set:
        """Extract class usage patterns.

        Detects:
        - Class instantiation: new ClassName()
        - Static method calls: ClassName.staticMethod()

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of class names being used
        """
        class_usage = set()

        # Built-in classes to exclude from static method detection
        builtin_classes = {
            "Object",
            "Array",
            "String",
            "Number",
            "Boolean",
            "Function",
            "Symbol",
            "BigInt",
            "Math",
            "Date",
            "RegExp",
            "Error",
            "Promise",
            "Map",
            "Set",
            "WeakMap",
            "WeakSet",
            "JSON",
            "Reflect",
            "Proxy",
            "Int8Array",
            "Uint8Array",
            "Uint8ClampedArray",
            "Int16Array",
            "Uint16Array",
            "Int32Array",
            "Uint32Array",
            "Float32Array",
            "Float64Array",
            "BigInt64Array",
            "BigUint64Array",
            "ArrayBuffer",
            "SharedArrayBuffer",
            "DataView",
            "Atomics",
            "Intl",
            "WebAssembly",
            "console",
            "Buffer",
            "URL",
            "URLSearchParams",
            "TextEncoder",
            "TextDecoder",
            "Headers",
            "Request",
            "Response",
            "FormData",
        }

        def _visit(node):
            # Pattern 1: new ClassName() - class instantiation
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

            # Pattern 2: ClassName.staticMethod() - static method call
            elif node.type == "call_expression":
                for child in node.children:
                    if child.type == "member_expression":
                        # Get the object part of member expression (ClassName.method -> ClassName)
                        for member_child in child.children:
                            if member_child.type == "identifier":
                                name = self._get_node_text(member_child, source_code)
                                # Only include PascalCase names (class convention)
                                # Exclude built-in JavaScript classes
                                if (
                                    name
                                    and name[0].isupper()
                                    and name not in builtin_classes
                                ):
                                    class_usage.add(name)
                                break

        self._traverse_tree(tree.root_node, _visit)
        return class_usage

    def _extract_function_calls(self, tree, source_code: bytes) -> set:
        """Extract function calls and function references used as arguments.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of function names being called or referenced
        """
        function_calls = set()
        # Track imported functions to distinguish from variables
        imported_functions = self._extract_imported_functions(tree, source_code)

        def _visit(node):
            if node.type == "call_expression":
                # Extract the function being called (direct calls like functionName())
                for child in node.children:
                    if child.type == "identifier":
                        function_calls.add(self._get_node_text(child, source_code))
                        break
                    elif child.type == "member_expression":
                        # Handle method calls - extract the method name
                        for member_child in child.children:
                            if member_child.type == "property_identifier":
                                function_calls.add(
                                    self._get_node_text(member_child, source_code)
                                )
                                break

                # Extract identifiers from arguments that are likely function references
                # This handles cases like expect(checkMaidCliInstalled).toBeDefined()
                for child in node.children:
                    if child.type == "arguments":
                        for arg_child in child.children:
                            # typeof expression (e.g., typeof functionName) - always a function reference
                            # In tree-sitter-typescript, typeof is a unary_expression with typeof child
                            if arg_child.type == "unary_expression":
                                has_typeof = any(
                                    c.type == "typeof" for c in arg_child.children
                                )
                                if has_typeof:
                                    for typeof_child in arg_child.children:
                                        if typeof_child.type == "identifier":
                                            func_name = self._get_node_text(
                                                typeof_child, source_code
                                            )
                                            function_calls.add(func_name)
                                            break
                                        # Handle typeof on member expressions
                                        # e.g., typeof result.current.refetch
                                        elif typeof_child.type == "member_expression":
                                            # Extract the final property_identifier
                                            func_name = self._extract_final_property(
                                                typeof_child, source_code
                                            )
                                            if func_name:
                                                function_calls.add(func_name)
                                            break
                            # Direct identifier argument - only if it's an imported function
                            elif arg_child.type == "identifier":
                                func_name = self._get_node_text(arg_child, source_code)
                                # Only add if it's an imported function (not a local variable)
                                if func_name in imported_functions:
                                    function_calls.add(func_name)
                            # Nested call expression (e.g., expect(functionName()))
                            elif arg_child.type == "call_expression":
                                for nested_child in arg_child.children:
                                    if nested_child.type == "identifier":
                                        func_name = self._get_node_text(
                                            nested_child, source_code
                                        )
                                        # Only add if it's an imported function
                                        if func_name in imported_functions:
                                            function_calls.add(func_name)
                                        break

        self._traverse_tree(tree.root_node, _visit)
        return function_calls

    def _extract_imported_functions(self, tree, source_code: bytes) -> set:
        """Extract function names from import statements.

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes

        Returns:
            Set of imported function names
        """
        imported_functions = set()

        def _visit(node):
            # Handle named imports: import { functionName } from "module"
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "import_clause":
                        for clause_child in child.children:
                            if clause_child.type == "named_imports":
                                for named_child in clause_child.children:
                                    if named_child.type == "import_specifier":
                                        for spec_child in named_child.children:
                                            if spec_child.type == "identifier":
                                                imported_functions.add(
                                                    self._get_node_text(
                                                        spec_child, source_code
                                                    )
                                                )
                                                break
                            # Handle default imports: import functionName from "module"
                            elif clause_child.type == "identifier":
                                imported_functions.add(
                                    self._get_node_text(clause_child, source_code)
                                )

        self._traverse_tree(tree.root_node, _visit)
        return imported_functions

    def _extract_method_calls(
        self, tree, source_code: bytes, variable_to_class: dict = None
    ) -> dict:
        """Extract method calls (object.method()).

        Args:
            tree: Parsed AST tree
            source_code: Source code as bytes
            variable_to_class: Optional mapping from variable names to class names.
                When provided, method calls on variables are mapped to their class names
                for behavioral validation.

        Returns:
            Dictionary mapping class/object names to sets of method names.
            If variable_to_class is provided, variable names are resolved to class names.
        """
        method_calls = {}
        var_to_class = variable_to_class or {}

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
                            # Map variable name to class name if mapping exists
                            key = var_to_class.get(obj_name, obj_name)
                            if key not in method_calls:
                                method_calls[key] = set()
                            method_calls[key].add(method_name)

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
                        is_arrow_function = False

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
                            elif method_child.type == "arrow_function":
                                # Class property arrow function
                                is_arrow_function = True
                                for arrow_child in method_child.children:
                                    if arrow_child.type == "formal_parameters":
                                        params = self._extract_parameters(
                                            arrow_child, source_code
                                        )
                                    elif arrow_child.type == "identifier":
                                        # Single parameter without parentheses
                                        param_name = self._get_node_text(
                                            arrow_child, source_code
                                        )
                                        params = [{"name": param_name}]

                        # Skip constructors, arrow functions, and private/protected members
                        if (
                            method_name
                            and method_name != "constructor"
                            and not is_arrow_function
                            and not self._is_private_member(body_child)
                        ):
                            methods[method_name] = params

        return methods

    def _is_private_member(self, node) -> bool:
        """Check if a class member has private or protected visibility.

        Args:
            node: Method definition or field definition node

        Returns:
            True if member has private or protected accessibility modifier
        """
        for child in node.children:
            if child.type == "accessibility_modifier":
                # Get the modifier text
                modifier_text = child.text.decode("utf-8") if child.text else ""
                if modifier_text in ("private", "protected"):
                    return True
        return False

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
            Parameter name (string, not dict - type is added by caller)
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
            Parameter name without ... prefix (string, not dict - type is added by caller)
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

    def _extract_type_from_node(self, type_node, source_code: bytes) -> str:
        """Extract type annotation text from tree-sitter AST node.

        Handles various TypeScript type constructs:
        - Simple types: string, number, boolean, any
        - Union types: string | number | null
        - Generic types: Array<T>, Promise<User>, Record<K, V>
        - Array notation: string[], number[]
        - Custom types: User, Customer

        Args:
            type_node: AST node representing the type
            source_code: Source code as bytes

        Returns:
            String representation of the type
        """
        if type_node is None:
            return ""

        # For most types, we can just extract the text directly
        # This works for:
        # - predefined_type (string, number, boolean, etc.)
        # - type_identifier (User, Customer, etc.)
        # - union_type (string | number)
        # - array_type (string[])
        # - generic_type (Array<T>, Promise<User>)
        # - intersection_type (A & B)
        # - tuple_type ([string, number])
        # - function_type ((x: number) => string)
        # - literal_type ('success' | 'error')
        # - parenthesized_type ((string | number))

        return self._get_node_text(type_node, source_code)

    def _find_type_annotation_in_node(self, param_node, source_code: bytes) -> str:
        """Find and extract type annotation from a parameter node.

        Args:
            param_node: Parameter AST node (required_parameter, optional_parameter, etc.)
            source_code: Source code as bytes

        Returns:
            Type annotation string or empty string if not found
        """
        for child in param_node.children:
            if child.type == "type_annotation":
                # type_annotation node contains colon and the actual type
                # Find the type node (skip the colon)
                for type_child in child.children:
                    if type_child.type != ":":
                        return self._extract_type_from_node(type_child, source_code)
        return ""
