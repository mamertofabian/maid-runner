"""Comprehensive behavioral tests for Task-086: Production-ready SvelteValidator.

This test suite validates all expected artifacts in the manifest, ensuring complete
coverage of Svelte (.svelte) language features using tree-sitter-svelte parser.

Test Organization:
- Basic validator structure and interface compliance
- File extension support for .svelte files
- Parser initialization and language selection
- Script tag parsing (JavaScript/TypeScript in <script> blocks)
- Component structure detection (classes, functions, reactive statements)
- Behavioral validation (class/function usage)
- Edge cases and real-world Svelte patterns
- Artifact structure consistency
"""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_runner.validators.svelte_validator import SvelteValidator
from maid_runner.validators.base_validator import BaseValidator

# Import private test modules for task-086 private artifacts
from tests._test_task_086_private_helpers import (  # noqa: F401
    TestSvelteValidatorInit,
    TestParseSvelteFile,
    TestCollectImplementationArtifacts,
    TestCollectBehavioralArtifacts,
    TestTraverseTree,
    TestGetNodeText,
    TestExtractFunctions,
    TestExtractClasses,
    TestExtractFunctionCalls,
    TestExtractClassUsage,
)


# =============================================================================
# SECTION 1: Validator Structure and Interface Compliance
# =============================================================================


class TestValidatorStructure:
    """Test SvelteValidator class structure and BaseValidator compliance."""

    def test_validator_class_exists(self):
        """SvelteValidator class must exist."""
        assert SvelteValidator is not None

    def test_validator_inherits_from_base(self):
        """SvelteValidator must inherit from BaseValidator."""
        assert issubclass(SvelteValidator, BaseValidator)

    def test_validator_can_be_instantiated(self):
        """SvelteValidator must be instantiable."""
        validator = SvelteValidator()
        assert validator is not None
        assert isinstance(validator, BaseValidator)

    def test_supports_file_method_exists(self):
        """supports_file method must exist and return bool."""
        validator = SvelteValidator()
        result = validator.supports_file("test.svelte")
        assert isinstance(result, bool)

    def test_collect_artifacts_method_exists(self, tmp_path):
        """collect_artifacts method must exist and return dict."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let count = 0;</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)


# =============================================================================
# SECTION 2: File Extension Support
# =============================================================================


class TestFileExtensionSupport:
    """Test supports_file for .svelte file extensions."""

    def test_supports_svelte_files(self):
        """Must support .svelte files."""
        validator = SvelteValidator()
        assert validator.supports_file("Component.svelte") is True
        assert validator.supports_file("/path/to/App.svelte") is True
        assert validator.supports_file("/src/components/Button.svelte") is True

    def test_rejects_non_svelte_files(self):
        """Must reject non-Svelte files."""
        validator = SvelteValidator()
        assert validator.supports_file("test.py") is False
        assert validator.supports_file("test.js") is False
        assert validator.supports_file("test.ts") is False
        assert validator.supports_file("test.tsx") is False
        assert validator.supports_file("test.vue") is False
        assert validator.supports_file("README.md") is False
        assert validator.supports_file("config.json") is False


# =============================================================================
# SECTION 3: Parser Initialization (__init__)
# =============================================================================


class TestParserInitialization:
    """Test parser initialization and language selection."""

    def test_validator_initializes_parser(self):
        """Must initialize Svelte parser on instantiation."""
        validator = SvelteValidator()
        assert hasattr(validator, "parser"), "Must have parser attribute"
        assert validator.parser is not None

    def test_validator_initializes_language(self):
        """Must initialize Svelte language object."""
        validator = SvelteValidator()
        assert hasattr(validator, "language"), "Must have language attribute"
        assert validator.language is not None

    def test_parses_valid_svelte_component(self, tmp_path):
        """Must successfully parse valid Svelte component without errors."""
        test_file = tmp_path / "valid.svelte"
        test_file.write_text(
            """
<script>
let name = 'World';
</script>

<h1>Hello {name}!</h1>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)

    def test_handles_empty_file(self, tmp_path):
        """Must handle empty Svelte files without errors."""
        test_file = tmp_path / "empty.svelte"
        test_file.write_text("")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)
        # Empty file should have no artifacts
        assert len(result.get("found_classes", set())) == 0
        assert len(result.get("found_functions", {})) == 0

    def test_handles_markup_only_file(self, tmp_path):
        """Must handle Svelte files with only markup (no script)."""
        test_file = tmp_path / "markup.svelte"
        test_file.write_text(
            """
<div>
    <h1>Hello World</h1>
    <p>This is a simple component.</p>
</div>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)


# =============================================================================
# SECTION 4: Language Selection (_get_language_for_file)
# =============================================================================


class TestLanguageSelection:
    """Test _get_language_for_file method for script tag language detection."""

    def test_detects_javascript_in_script_tag(self, tmp_path):
        """Must detect JavaScript (default) in <script> tag."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
let count = 0;
</script>
"""
        )
        validator = SvelteValidator()
        lang = validator._get_language_for_file(str(test_file))
        # Default script language is JavaScript
        assert lang in ["javascript", "typescript"]

    def test_detects_typescript_in_script_tag(self, tmp_path):
        """Must detect TypeScript in <script lang="ts"> tag."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script lang="ts">
let count: number = 0;
</script>
"""
        )
        validator = SvelteValidator()
        lang = validator._get_language_for_file(str(test_file))
        assert lang == "typescript"

    def test_handles_missing_script_tag(self, tmp_path):
        """Must handle Svelte files without <script> tag."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<div>Hello</div>")
        validator = SvelteValidator()
        # Should not crash when detecting language
        lang = validator._get_language_for_file(str(test_file))
        # Default to JavaScript when no script tag present
        assert lang in ["javascript", "typescript", None]


# =============================================================================
# SECTION 5: Svelte File Parsing (_parse_svelte_file)
# =============================================================================


class TestSvelteFileParsing:
    """Test _parse_svelte_file for parsing .svelte files."""

    def test_parses_complete_svelte_component(self, tmp_path):
        """Must parse complete Svelte component with script, style, and markup."""
        test_file = tmp_path / "complete.svelte"
        test_file.write_text(
            """
<script>
export let name = 'World';

function greet() {
    alert('Hello!');
}
</script>

<style>
h1 { color: red; }
</style>

<h1>Hello {name}!</h1>
<button on:click={greet}>Greet</button>
"""
        )
        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        assert tree is not None
        assert source_code is not None
        assert isinstance(source_code, bytes)

    def test_parses_typescript_script(self, tmp_path):
        """Must parse Svelte component with TypeScript script."""
        test_file = tmp_path / "typescript.svelte"
        test_file.write_text(
            """
<script lang="ts">
let count: number = 0;

function increment(): void {
    count += 1;
}
</script>

<button on:click={increment}>{count}</button>
"""
        )
        validator = SvelteValidator()
        tree, source_code = validator._parse_svelte_file(str(test_file))
        assert tree is not None
        assert source_code is not None


# =============================================================================
# SECTION 6: Function Detection (_extract_functions)
# =============================================================================


class TestFunctionDetection:
    """Test _extract_functions for detecting functions in Svelte scripts."""

    def test_detects_simple_function(self, tmp_path):
        """Must detect simple function declarations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function greet(name) {
    return `Hello ${name}`;
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "greet" in result["found_functions"]

    def test_detects_arrow_function(self, tmp_path):
        """Must detect arrow function expressions."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
const increment = () => {
    count += 1;
};
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "increment" in result["found_functions"]

    def test_detects_async_function(self, tmp_path):
        """Must detect async functions."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
async function fetchData(url) {
    const response = await fetch(url);
    return await response.json();
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "fetchData" in result["found_functions"]

    def test_detects_multiple_functions(self, tmp_path):
        """Must detect multiple functions in one component."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function foo() {}
function bar() {}
function baz() {}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "foo" in result["found_functions"]
        assert "bar" in result["found_functions"]
        assert "baz" in result["found_functions"]


# =============================================================================
# SECTION 7: Class Detection (_extract_classes)
# =============================================================================


class TestClassDetection:
    """Test _extract_classes for detecting classes in Svelte scripts."""

    def test_detects_simple_class(self, tmp_path):
        """Must detect simple class declarations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class UserService {
    constructor() {
        this.users = [];
    }
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "UserService" in result["found_classes"]

    def test_detects_exported_class(self, tmp_path):
        """Must detect exported classes."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
export class DataStore {
    load() {}
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "DataStore" in result["found_classes"]

    def test_detects_class_with_inheritance(self, tmp_path):
        """Must detect classes with inheritance."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class BaseService {}
class UserService extends BaseService {}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "BaseService" in result["found_classes"]
        assert "UserService" in result["found_classes"]


# =============================================================================
# SECTION 8: Implementation Mode (_collect_implementation_artifacts)
# =============================================================================


class TestImplementationArtifacts:
    """Test _collect_implementation_artifacts for implementation mode."""

    def test_collects_implementation_artifacts(self, tmp_path):
        """Must collect all implementation artifacts (classes, functions, methods)."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Counter {
    increment() {}
}

function reset() {}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Counter" in result["found_classes"]
        assert "reset" in result["found_functions"]
        assert "Counter" in result["found_methods"]
        assert "increment" in result["found_methods"]["Counter"]

    def test_implementation_mode_has_required_keys(self, tmp_path):
        """Implementation mode must return all required artifact keys."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        required_keys = [
            "found_classes",
            "found_functions",
            "found_methods",
            "found_class_bases",
            "found_attributes",
            "variable_to_class",
            "found_function_types",
            "found_method_types",
            "used_classes",
            "used_functions",
            "used_methods",
            "used_arguments",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"


# =============================================================================
# SECTION 9: Behavioral Mode (_collect_behavioral_artifacts)
# =============================================================================


class TestBehavioralArtifacts:
    """Test _collect_behavioral_artifacts for behavioral mode."""

    def test_detects_function_calls(self, tmp_path):
        """Must detect function calls in behavioral mode."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function greet() {}

greet();
greet();
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "greet" in result["used_functions"]

    def test_detects_class_instantiation(self, tmp_path):
        """Must detect class instantiations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Service {}

const service = new Service();
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "Service" in result["used_classes"]

    def test_detects_method_calls(self, tmp_path):
        """Must detect method calls on objects."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
const obj = getObject();
obj.method1();
obj.method2();
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "obj" in result["used_methods"]
        assert "method1" in result["used_methods"]["obj"]
        assert "method2" in result["used_methods"]["obj"]

    def test_behavioral_mode_has_required_keys(self, tmp_path):
        """Behavioral mode must return all required usage keys."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>let x = 1;</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")

        required_keys = ["used_classes", "used_functions", "used_methods"]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"


# =============================================================================
# SECTION 10: Helper Methods (_extract_function_calls, _extract_class_usage)
# =============================================================================


class TestHelperMethods:
    """Test helper methods for extracting usage patterns."""

    def test_extract_function_calls(self, tmp_path):
        """Must extract function calls correctly."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
doSomething();
processData(x, y);
formatString('test');
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "doSomething" in result["used_functions"]
        assert "processData" in result["used_functions"]
        assert "formatString" in result["used_functions"]

    def test_extract_class_usage(self, tmp_path):
        """Must extract class usage (instantiation) correctly."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
const service = new UserService();
const store = new DataStore();
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "UserService" in result["used_classes"]
        assert "DataStore" in result["used_classes"]

    def test_extract_method_calls(self, tmp_path):
        """Must extract method calls correctly."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
const user = getUser();
user.save();
user.delete();
user.update({ name: 'John' });
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "user" in result["used_methods"]
        assert "save" in result["used_methods"]["user"]
        assert "delete" in result["used_methods"]["user"]
        assert "update" in result["used_methods"]["user"]


# =============================================================================
# SECTION 11: Tree Traversal (_traverse_tree)
# =============================================================================


class TestTreeTraversal:
    """Test _traverse_tree method for AST traversal."""

    def test_traverses_entire_tree(self, tmp_path):
        """Must traverse entire AST tree and find all artifacts."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function outer() {
    function inner() {
        return 42;
    }
    return inner();
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should find outer function (inner might be nested)
        assert "outer" in result["found_functions"]

    def test_visits_nested_structures(self, tmp_path):
        """Must visit nested structures in the AST."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Outer {
    method() {
        const nested = () => {
            return 42;
        };
    }
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Outer" in result["found_classes"]
        assert "Outer" in result["found_methods"]
        assert "method" in result["found_methods"]["Outer"]


# =============================================================================
# SECTION 12: Node Text Extraction (_get_node_text)
# =============================================================================


class TestNodeTextExtraction:
    """Test _get_node_text method for extracting text from AST nodes."""

    def test_extracts_function_names(self, tmp_path):
        """Must extract function names correctly from AST nodes."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
function myFunction() {}
function anotherFunction() {}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "myFunction" in result["found_functions"]
        assert "anotherFunction" in result["found_functions"]

    def test_extracts_class_names(self, tmp_path):
        """Must extract class names correctly from AST nodes."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class MyClass {}
class AnotherClass {}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "MyClass" in result["found_classes"]
        assert "AnotherClass" in result["found_classes"]


# =============================================================================
# SECTION 13: Svelte-Specific Features
# =============================================================================


class TestSvelteSpecificFeatures:
    """Test Svelte-specific patterns and features."""

    def test_handles_reactive_statements(self, tmp_path):
        """Must handle Svelte reactive statements ($:)."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
let count = 0;
$: doubled = count * 2;
$: {
    console.log(`Count is ${count}`);
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should parse without errors
        assert isinstance(result, dict)

    def test_handles_component_props(self, tmp_path):
        """Must handle Svelte component props (export let)."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
export let name = 'World';
export let count = 0;
</script>

<h1>Hello {name}!</h1>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should parse without errors
        assert isinstance(result, dict)

    def test_handles_stores_import(self, tmp_path):
        """Must handle Svelte stores (writable, readable)."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
import { writable } from 'svelte/store';

const count = writable(0);

function increment() {
    count.update(n => n + 1);
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "increment" in result["found_functions"]

    def test_handles_event_handlers(self, tmp_path):
        """Must handle inline event handlers in markup."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
let count = 0;

function increment() {
    count += 1;
}
</script>

<button on:click={increment}>
    Count: {count}
</button>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "increment" in result["found_functions"]


# =============================================================================
# SECTION 14: TypeScript in Svelte
# =============================================================================


class TestTypeScriptSupport:
    """Test TypeScript support in Svelte components."""

    def test_parses_typescript_functions(self, tmp_path):
        """Must parse TypeScript functions with type annotations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script lang="ts">
function greet(name: string): string {
    return `Hello ${name}`;
}

function add(a: number, b: number): number {
    return a + b;
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "greet" in result["found_functions"]
        assert "add" in result["found_functions"]

    def test_parses_typescript_classes(self, tmp_path):
        """Must parse TypeScript classes with type annotations."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script lang="ts">
class User {
    name: string;
    age: number;

    constructor(name: string, age: number) {
        this.name = name;
        this.age = age;
    }

    greet(): string {
        return `Hello, I'm ${this.name}`;
    }
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "User" in result["found_classes"]
        assert "User" in result["found_methods"]
        assert "greet" in result["found_methods"]["User"]

    def test_parses_typescript_interfaces(self, tmp_path):
        """Must parse TypeScript interfaces."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script lang="ts">
interface User {
    name: string;
    age: number;
}

interface Product {
    id: number;
    title: string;
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Interfaces should be detected as classes (type-like declarations)
        assert "User" in result["found_classes"]
        assert "Product" in result["found_classes"]


# =============================================================================
# SECTION 15: Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_empty_script_tag(self, tmp_path):
        """Must handle empty <script> tag."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
</script>

<h1>Hello</h1>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)
        assert len(result["found_functions"]) == 0

    def test_handles_multiple_script_tags(self, tmp_path):
        """Must handle components with multiple <script> tags."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
let count = 0;
</script>

<script context="module">
export function helper() {
    return 42;
}
</script>

<button>{count}</button>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should parse both script tags
        assert isinstance(result, dict)

    def test_handles_syntax_errors_gracefully(self, tmp_path):
        """Must handle files with syntax errors without crashing."""
        test_file = tmp_path / "invalid.svelte"
        test_file.write_text(
            """
<script>
function broken() {
    // Missing closing brace
</script>
"""
        )
        validator = SvelteValidator()
        # Should not crash
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)

    def test_handles_file_with_only_comments(self, tmp_path):
        """Must handle files with only comments in script."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
// This is a comment
/* This is a block comment */
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)
        assert len(result["found_functions"]) == 0

    def test_handles_large_component(self, tmp_path):
        """Must handle large components efficiently."""
        test_file = tmp_path / "large.svelte"
        # Generate a component with many functions
        functions = "\n".join([f"function func{i}() {{}}" for i in range(50)])
        test_file.write_text(f"<script>\n{functions}\n</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert len(result["found_functions"]) == 50


# =============================================================================
# SECTION 16: Artifact Structure Consistency
# =============================================================================


class TestArtifactStructure:
    """Test that collected artifacts have consistent structure."""

    def test_found_classes_is_set(self, tmp_path):
        """found_classes must be a set."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>class Test {}</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result["found_classes"], set)

    def test_found_functions_is_dict(self, tmp_path):
        """found_functions must be a dict."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>function test() {}</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result["found_functions"], dict)

    def test_found_methods_is_dict_of_dicts(self, tmp_path):
        """found_methods must be a dict of dicts."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text(
            """
<script>
class Test {
    method() {}
}
</script>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result["found_methods"], dict)
        if "Test" in result["found_methods"]:
            assert isinstance(result["found_methods"]["Test"], dict)

    def test_used_classes_is_set(self, tmp_path):
        """used_classes must be a set."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>const x = new Test();</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert isinstance(result["used_classes"], set)

    def test_used_functions_is_set(self, tmp_path):
        """used_functions must be a set."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>test();</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert isinstance(result["used_functions"], set)

    def test_used_methods_is_dict_of_sets(self, tmp_path):
        """used_methods must be a dict of sets."""
        test_file = tmp_path / "test.svelte"
        test_file.write_text("<script>obj.method();</script>")
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert isinstance(result["used_methods"], dict)


# =============================================================================
# SECTION 17: Real-World Svelte Patterns
# =============================================================================


class TestRealWorldPatterns:
    """Test patterns from real-world Svelte components."""

    def test_counter_component_pattern(self, tmp_path):
        """Must handle classic Svelte counter component."""
        test_file = tmp_path / "Counter.svelte"
        test_file.write_text(
            """
<script>
let count = 0;

function increment() {
    count += 1;
}

function decrement() {
    count -= 1;
}

function reset() {
    count = 0;
}
</script>

<div>
    <button on:click={decrement}>-</button>
    <span>{count}</span>
    <button on:click={increment}>+</button>
    <button on:click={reset}>Reset</button>
</div>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "increment" in result["found_functions"]
        assert "decrement" in result["found_functions"]
        assert "reset" in result["found_functions"]

    def test_form_component_pattern(self, tmp_path):
        """Must handle form component with validation."""
        test_file = tmp_path / "LoginForm.svelte"
        test_file.write_text(
            """
<script>
let email = '';
let password = '';
let errors = {};

function validateEmail(email) {
    return email.includes('@');
}

function validatePassword(password) {
    return password.length >= 8;
}

async function handleSubmit() {
    errors = {};

    if (!validateEmail(email)) {
        errors.email = 'Invalid email';
    }

    if (!validatePassword(password)) {
        errors.password = 'Password too short';
    }

    if (Object.keys(errors).length === 0) {
        await submitForm({ email, password });
    }
}
</script>

<form on:submit|preventDefault={handleSubmit}>
    <input bind:value={email} type="email" />
    <input bind:value={password} type="password" />
    <button type="submit">Login</button>
</form>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "validateEmail" in result["found_functions"]
        assert "validatePassword" in result["found_functions"]
        assert "handleSubmit" in result["found_functions"]

    def test_store_subscription_pattern(self, tmp_path):
        """Must handle Svelte store subscription pattern."""
        test_file = tmp_path / "UserProfile.svelte"
        test_file.write_text(
            """
<script>
import { userStore } from './stores.js';

let user;
const unsubscribe = userStore.subscribe(value => {
    user = value;
});

function updateProfile(data) {
    userStore.update(u => ({ ...u, ...data }));
}

function logout() {
    userStore.set(null);
}
</script>

<div>
    <h1>{user?.name}</h1>
    <button on:click={logout}>Logout</button>
</div>
"""
        )
        validator = SvelteValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "updateProfile" in result["found_functions"]
        assert "logout" in result["found_functions"]
