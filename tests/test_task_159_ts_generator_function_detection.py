"""Tests for task-159: Generator function detection in TypeScript.

Generator functions (function* and async function*) should be detected
as public functions just like regular function declarations.
"""

import os
import tempfile

from maid_runner.validators.typescript_validator import TypeScriptValidator


class TestExtractFunctionsWithGenerators:
    """Direct tests for _extract_functions method with generators."""

    def test_extract_generator_function(self):
        """_extract_functions should detect generator functions."""
        code = b"""
function* myGenerator() {
    yield 1;
    yield 2;
}
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        # Call _extract_functions directly
        functions = validator._extract_functions(tree, code)

        assert "myGenerator" in functions

    def test_extract_async_generator_function(self):
        """_extract_functions should detect async generator functions."""
        code = b"""
async function* asyncGenerator() {
    yield await Promise.resolve(1);
}
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        functions = validator._extract_functions(tree, code)

        assert "asyncGenerator" in functions

    def test_extract_generator_with_parameters(self):
        """_extract_functions should extract generator parameters."""
        code = b"""
function* generateRange(start: number, end: number) {
    for (let i = start; i <= end; i++) {
        yield i;
    }
}
"""
        validator = TypeScriptValidator()
        tree = validator.ts_parser.parse(code)

        functions = validator._extract_functions(tree, code)

        assert "generateRange" in functions
        params = functions["generateRange"]
        assert len(params) == 2
        assert params[0]["name"] == "start"
        assert params[1]["name"] == "end"


class TestGeneratorFunctionsInCollectArtifacts:
    """Test generator functions through collect_artifacts method."""

    def test_generator_function_detected(self):
        """Generator functions should be detected via collect_artifacts."""
        code = """
function* myGenerator() {
    yield 1;
    yield 2;
}

function regularFunction() {
    return 1;
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "myGenerator" in artifacts["found_functions"]
                assert "regularFunction" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_async_generator_function_detected(self):
        """Async generator functions should be detected via collect_artifacts."""
        code = """
async function* fetchPages(urls: string[]) {
    for (const url of urls) {
        yield await fetch(url);
    }
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "fetchPages" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)

    def test_exported_generator_detected(self):
        """Exported generator functions should be detected."""
        code = """
export function* exportedGenerator() {
    yield "exported";
}

export async function* exportedAsyncGenerator() {
    yield await Promise.resolve("async exported");
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "exportedGenerator" in artifacts["found_functions"]
                assert "exportedAsyncGenerator" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)


class TestMixedFunctionTypes:
    """Test detection of mixed function types together."""

    def test_all_function_types_detected(self):
        """All function types should be detected together."""
        code = """
// Regular function
function regularFunc() { return 1; }

// Arrow function
const arrowFunc = () => 2;

// Generator function
function* generatorFunc() { yield 3; }

// Async function
async function asyncFunc() { return 4; }

// Async generator
async function* asyncGenFunc() { yield 5; }
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                funcs = artifacts["found_functions"]
                assert "regularFunc" in funcs
                assert "arrowFunc" in funcs
                assert "generatorFunc" in funcs
                assert "asyncFunc" in funcs
                assert "asyncGenFunc" in funcs
            finally:
                os.unlink(f.name)

    def test_nested_generators_not_detected(self):
        """Nested generator functions should not be detected as public."""
        code = """
function* outerGenerator() {
    // This nested generator should NOT be detected
    function* innerGenerator() {
        yield "inner";
    }
    yield* innerGenerator();
}
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "outerGenerator" in artifacts["found_functions"]
                # innerGenerator is nested, should not be detected
                assert "innerGenerator" not in artifacts["found_functions"]
            finally:
                os.unlink(f.name)


class TestGeneratorInTSX:
    """Test generator detection in TSX files."""

    def test_generator_in_tsx_file(self):
        """Generator functions should be detected in TSX files."""
        code = """
import React from 'react';

function* idGenerator() {
    let id = 0;
    while (true) {
        yield id++;
    }
}

const Component = () => {
    return <div>Hello</div>;
};

export { idGenerator, Component };
"""
        validator = TypeScriptValidator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tsx", delete=False) as f:
            f.write(code)
            f.flush()
            try:
                artifacts = validator.collect_artifacts(f.name, "implementation")
                assert "idGenerator" in artifacts["found_functions"]
                assert "Component" in artifacts["found_functions"]
            finally:
                os.unlink(f.name)
