"""Tests for task-160: Svelte validator uses TypeScript extraction.

The Svelte validator should delegate script content extraction to the
TypeScript validator to ensure consistent behavior and avoid code duplication.
"""

import os
import tempfile

from maid_runner.validators.svelte_validator import SvelteValidator


class TestCollectImplementationArtifactsMethod:
    """Direct tests for _collect_implementation_artifacts method."""

    def test_collect_implementation_artifacts_returns_dict(self):
        """_collect_implementation_artifacts should return proper artifact dict."""
        code = """
<script lang="ts">
function testFunc() { return 1; }
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                tree, source_code = validator._parse_svelte_file(f.name)
                artifacts = validator._collect_implementation_artifacts(
                    tree, source_code
                )
                assert isinstance(artifacts, dict)
                assert "found_functions" in artifacts
                assert "found_classes" in artifacts
            finally:
                os.unlink(f.name)


class TestCollectBehavioralArtifactsMethod:
    """Direct tests for _collect_behavioral_artifacts method."""

    def test_collect_behavioral_artifacts_returns_dict(self):
        """_collect_behavioral_artifacts should return proper artifact dict."""
        code = """
<script lang="ts">
import { getData } from './api';
getData();
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                tree, source_code = validator._parse_svelte_file(f.name)
                artifacts = validator._collect_behavioral_artifacts(tree, source_code)
                assert isinstance(artifacts, dict)
                assert "used_functions" in artifacts
                assert "used_classes" in artifacts
            finally:
                os.unlink(f.name)


class TestSvelteUsesTypeScriptExtraction:
    """Test that Svelte validator delegates to TypeScript validator."""

    def test_module_level_functions_detected(self):
        """Module-level functions in Svelte script should be detected."""
        code = """
<script lang="ts">
function handleClick() {
    console.log('clicked');
}

const processData = () => 'processed';
</script>

<button on:click={handleClick}>Click</button>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "handleClick" in artifacts["found_functions"]
                assert "processData" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_nested_functions_not_detected(self):
        """Nested functions in Svelte script should NOT be detected."""
        code = """
<script lang="ts">
function outerFunction() {
    function nestedFunction() {
        return 'nested';
    }
    return nestedFunction();
}

const outerArrow = () => {
    const nestedArrow = () => 'nested arrow';
    return nestedArrow();
};
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Outer functions should be detected
                assert "outerFunction" in artifacts["found_functions"]
                assert "outerArrow" in artifacts["found_functions"]
                # Nested functions should NOT be detected
                assert "nestedFunction" not in artifacts["found_functions"]
                assert "nestedArrow" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_generator_functions_detected(self):
        """Generator functions in Svelte script should be detected."""
        code = """
<script lang="ts">
function* myGenerator() {
    yield 1;
    yield 2;
}

async function* asyncGenerator() {
    yield await Promise.resolve(1);
}
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "myGenerator" in artifacts["found_functions"]
                assert "asyncGenerator" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_object_property_arrows_not_detected(self):
        """Object property arrow functions should NOT be detected."""
        code = """
<script lang="ts">
const config = {
    handler: () => 'handler',
    onSuccess: () => console.log('success'),
    queryFn: async () => fetch('/api'),
};
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Object property functions should NOT be detected
                assert "handler" not in artifacts["found_functions"]
                assert "onSuccess" not in artifacts["found_functions"]
                assert "queryFn" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)


class TestSvelteClassExtraction:
    """Test class extraction in Svelte files."""

    def test_classes_detected(self):
        """Classes in Svelte script should be detected."""
        code = """
<script lang="ts">
class MyService {
    getData() {
        return 'data';
    }
}

interface MyInterface {
    value: string;
}
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "MyService" in artifacts["found_classes"]
                assert "MyInterface" in artifacts["found_classes"]
            finally:
                os.unlink(f.name)

    def test_class_methods_detected(self):
        """Class methods should be detected."""
        code = """
<script lang="ts">
class DataService {
    fetchData(id: string) {
        return fetch('/api/' + id);
    }

    processData(data: any) {
        return data;
    }
}
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "DataService" in artifacts["found_methods"]
                methods = artifacts["found_methods"]["DataService"]
                assert "fetchData" in methods
                assert "processData" in methods
            finally:
                os.unlink(f.name)


class TestSvelteBehavioralValidation:
    """Test behavioral validation for Svelte files."""

    def test_function_calls_detected(self):
        """Function calls in Svelte should be detected for behavioral validation."""
        code = """
<script lang="ts">
import { getData } from './api';

const result = getData();
console.log(result);
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "behavioral")
                assert "getData" in artifacts["used_functions"]
            finally:
                os.unlink(f.name)


class TestSvelteReactiveStatements:
    """Test handling of Svelte-specific reactive statements."""

    def test_reactive_arrow_not_detected_as_function(self):
        """Reactive statements with arrows should not create false positives."""
        code = """
<script lang="ts">
let count = 0;

// Reactive statement - not a function declaration
$: doubled = count * 2;

// Real function
function increment() {
    count++;
}
</script>
"""
        validator = SvelteValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".svelte", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                # Only the real function should be detected
                assert "increment" in artifacts["found_functions"]
                # Reactive variable should not be detected as function
                assert "doubled" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)
