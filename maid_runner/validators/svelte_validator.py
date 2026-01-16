"""Svelte validator using tree-sitter AST parsing.

This validator provides production-ready validation for Svelte (.svelte) files,
supporting script blocks with JavaScript/TypeScript, reactive statements, props,
stores, event handlers, and all Svelte language features.

Supports file extension: .svelte

This validator delegates script content extraction to the TypeScript validator
to ensure consistent behavior and avoid code duplication.
"""

from maid_runner.validators.base_validator import BaseValidator
from maid_runner.validators.typescript_validator import TypeScriptValidator


class SvelteValidator(BaseValidator):
    """Validates Svelte files using tree-sitter AST parsing.

    Features:
    - Accurate AST-based parsing (not regex)
    - Script block extraction and parsing
    - TypeScript and JavaScript support
    - Svelte-specific patterns (reactive statements, props, stores)
    - Delegates to TypeScript validator for script content extraction
    """

    def __init__(self):
        """Initialize Svelte parser and TypeScript validator for script parsing."""
        from tree_sitter import Language, Parser
        import tree_sitter_svelte as ts_svelte

        # Initialize Svelte language and parser (for parsing .svelte files)
        self.svelte_language = Language(ts_svelte.language())
        self.svelte_parser = Parser(self.svelte_language)

        # Aliases for tests that expect 'parser' and 'language' attributes
        self.parser = self.svelte_parser
        self.language = self.svelte_language

        # Use TypeScript validator for script content extraction
        # This ensures all TypeScript fixes (module scope, generators, etc.)
        # automatically apply to Svelte files
        self._ts_validator = TypeScriptValidator()

    def supports_file(self, file_path: str) -> bool:
        """Check if file is a Svelte file.

        Args:
            file_path: Path to the file

        Returns:
            True if file extension is .svelte
        """
        return file_path.endswith(".svelte")

    def collect_artifacts(self, file_path: str, validation_mode: str) -> dict:
        """Collect artifacts from Svelte file.

        Args:
            file_path: Path to the Svelte file
            validation_mode: "implementation" or "behavioral"

        Returns:
            Dictionary containing found artifacts
        """
        tree, source_code = self._parse_svelte_file(file_path)

        if validation_mode == "implementation":
            return self._collect_implementation_artifacts(tree, source_code)
        else:
            return self._collect_behavioral_artifacts(tree, source_code)

    def _parse_svelte_file(self, file_path: str):
        """Parse Svelte file and return AST tree and source code.

        Args:
            file_path: Path to the Svelte file

        Returns:
            Tuple of (tree, source_code) where source_code is bytes
        """
        with open(file_path, "rb") as f:
            source_code = f.read()

        # Parse the entire Svelte file to extract script content
        svelte_tree = self.svelte_parser.parse(source_code)

        # Extract script content
        script_content = self._extract_script_content(svelte_tree, source_code)

        if script_content:
            # Parse script content with TypeScript validator's parser
            script_tree = self._ts_validator.ts_parser.parse(
                script_content.encode("utf-8")
            )
            return script_tree, script_content.encode("utf-8")
        else:
            # No script content - return empty tree
            empty_code = b""
            return self._ts_validator.ts_parser.parse(empty_code), empty_code

    def _extract_script_content(self, svelte_tree, source_code: bytes) -> str:
        """Extract script content from Svelte AST.

        Args:
            svelte_tree: Parsed Svelte AST tree
            source_code: Source code as bytes

        Returns:
            Script content as string (or empty string if no script)
        """
        script_contents = []

        def _visit(node):
            if node.type == "script_element":
                # Find the raw_text node which contains the script content
                for child in node.children:
                    if child.type == "raw_text":
                        content = self._get_node_text(child, source_code)
                        script_contents.append(content)

        self._traverse_tree(svelte_tree.root_node, _visit)

        # Combine all script blocks (supports multiple <script> tags)
        return "\n".join(script_contents)

    def _collect_implementation_artifacts(self, tree, source_code: bytes) -> dict:
        """Collect implementation artifacts (definitions).

        Delegates to TypeScript validator for script content extraction.
        This ensures all TypeScript fixes (module scope checking, generator
        functions, object property exclusion) automatically apply to Svelte.

        Args:
            tree: Parsed AST tree (of script content)
            source_code: Source code as bytes (script content)

        Returns:
            Dictionary with found classes, interfaces, functions, etc.
        """
        # Delegate to TypeScript validator for extraction
        # This reuses all the TypeScript extraction logic including:
        # - Module scope checking for nested functions
        # - Generator function detection
        # - Object property arrow function exclusion
        return self._ts_validator._collect_implementation_artifacts(tree, source_code)

    def _collect_behavioral_artifacts(self, tree, source_code: bytes) -> dict:
        """Collect behavioral artifacts (usage).

        Delegates to TypeScript validator for script content extraction.

        Args:
            tree: Parsed AST tree (of script content)
            source_code: Source code as bytes (script content)

        Returns:
            Dictionary with class usage, function calls, method calls, and used arguments
        """
        # Delegate to TypeScript validator for extraction
        return self._ts_validator._collect_behavioral_artifacts(tree, source_code)

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

    # Legacy method stubs for backward compatibility with task-086 manifest.
    # These delegate to TypeScript validator methods.

    def _get_language_for_file(self, file_path: str) -> str:
        """Determine script language from file content.

        Reads the file to check for <script lang="ts"> or similar.

        Args:
            file_path: Path to the Svelte file

        Returns:
            'typescript' or 'javascript'
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Check for TypeScript script tag
                if '<script lang="ts"' in content or "<script lang='ts'" in content:
                    return "typescript"
        except Exception:
            pass
        return "javascript"

    def _extract_functions(self, tree, source_code: bytes) -> dict:
        """Extract function declarations (delegates to TypeScript validator)."""
        return self._ts_validator._extract_functions(tree, source_code)

    def _extract_classes(self, tree, source_code: bytes) -> set:
        """Extract class and interface names (delegates to TypeScript validator).

        Note: This combines classes and interfaces for backward compatibility
        with the original Svelte validator behavior.
        """
        classes = self._ts_validator._extract_classes(tree, source_code)
        interfaces = self._ts_validator._extract_interfaces(tree, source_code)
        return classes | interfaces

    def _extract_function_calls(self, tree, source_code: bytes) -> set:
        """Extract function calls (delegates to TypeScript validator)."""
        return self._ts_validator._extract_function_calls(tree, source_code)

    def _extract_class_usage(self, tree, source_code: bytes) -> set:
        """Extract class instantiations (delegates to TypeScript validator)."""
        return self._ts_validator._extract_class_usage(tree, source_code)
