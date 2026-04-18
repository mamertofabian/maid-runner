"""Tests for test function detection in behavioral artifact collectors."""


class TestPythonBehavioralTestFunctionCollection:
    """Test that Python behavioral collector detects test function definitions."""

    def test_detect_test_function_definition(self):
        from maid_runner.validators.python import PythonValidator

        v = PythonValidator()
        source = "def test_mything(): pass\n"
        result = v.collect_behavioral_artifacts(source, "test.py")
        names = [a.name for a in result.artifacts]
        assert "test_mything" in names

    def test_detect_async_test_function(self):
        from maid_runner.validators.python import PythonValidator

        v = PythonValidator()
        source = "async def test_async_works(): pass\n"
        result = v.collect_behavioral_artifacts(source, "test.py")
        names = [a.name for a in result.artifacts]
        assert "test_async_works" in names

    def test_detect_multiple_test_functions(self):
        from maid_runner.validators.python import PythonValidator

        v = PythonValidator()
        source = """
def test_one(): pass
def test_two(): pass
def not_a_test(): pass
"""
        result = v.collect_behavioral_artifacts(source, "test.py")
        names = [a.name for a in result.artifacts]
        assert "test_one" in names
        assert "test_two" in names
        assert "not_a_test" not in names

    def test_still_collects_references(self):
        from maid_runner.validators.python import PythonValidator

        v = PythonValidator()
        source = """
from src.api import createLogin

def test_call():
    result = createLogin({})
    assert result
"""
        result = v.collect_behavioral_artifacts(source, "test.py")
        names = [a.name for a in result.artifacts]
        assert "test_call" in names
        assert "createLogin" in names

    def test_nested_test_helper_is_not_collected(self):
        from maid_runner.validators.python import PythonValidator

        v = PythonValidator()
        source = """
def helper():
    def test_missing():
        pass
"""
        result = v.collect_behavioral_artifacts(source, "test.py")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "test_missing" not in test_names

    def test_class_test_method_on_discoverable_class_is_collected(self):
        from maid_runner.validators.python import PythonValidator

        v = PythonValidator()
        source = """
class TestAuth:
    def test_login(self):
        assert True
"""
        result = v.collect_behavioral_artifacts(source, "test.py")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "test_login" in test_names

    def test_class_test_method_on_non_discoverable_class_is_ignored(self):
        from maid_runner.validators.python import PythonValidator

        v = PythonValidator()
        source = """
class HelperSuite:
    def test_login(self):
        assert True
"""
        result = v.collect_behavioral_artifacts(source, "test.py")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "test_login" not in test_names


class TestTypeScriptBehavioralTestFunctionCollection:
    """Test that TypeScript behavioral collector detects test function definitions."""

    def test_plain_test_named_function_is_ignored(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = "export function test_mything() { expect(true).toBe(true) }\n"
        result = v.collect_behavioral_artifacts(source, "test.ts")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "test_mything" not in test_names

    def test_plain_test_named_arrow_function_is_ignored(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = "const test_mything = () => { expect(true).toBe(true) }\n"
        result = v.collect_behavioral_artifacts(source, "test.ts")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "test_mything" not in test_names

    def test_still_collects_references(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = (
            'import { createLogin } from "./api"\n'
            'it("test_call", () => { createLogin() })\n'
        )
        result = v.collect_behavioral_artifacts(source, "test.ts")
        names = [a.name for a in result.artifacts]
        assert "test_call" in names
        assert "createLogin" in names

    def test_detect_it_string_label(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = (
            'import { describe, it, expect } from "vitest";\n'
            'describe("Auth", () => {\n'
            '  it("test_successful_login", async () => { expect(1).toBe(1); });\n'
            "});\n"
        )
        result = v.collect_behavioral_artifacts(source, "test.ts")
        names = [a.name for a in result.artifacts]
        assert "test_successful_login" in names

    def test_detect_test_string_label(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = (
            'import { test, expect } from "vitest";\n'
            'test("test_login_blocked_with_wrong_password", async () => {\n'
            "  expect(true).toBe(false);\n"
            "});\n"
        )
        result = v.collect_behavioral_artifacts(source, "test.ts")
        names = [a.name for a in result.artifacts]
        assert "test_login_blocked_with_wrong_password" in names

    def test_detect_it_only_and_skip_variants(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = (
            'it.only("test_focused", () => {});\ntest.skip("test_skipped", () => {});\n'
        )
        result = v.collect_behavioral_artifacts(source, "test.ts")
        names = [a.name for a in result.artifacts]
        assert "test_focused" in names
        assert "test_skipped" in names

    def test_test_describe_suite_label_is_ignored(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = 'test.describe("suite_only", () => {});\n'
        result = v.collect_behavioral_artifacts(source, "test.ts")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "suite_only" not in test_names

    def test_detect_it_each_parameterized_case(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = 'it.each([[1]])("case", () => {});\n'
        result = v.collect_behavioral_artifacts(source, "test.ts")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "case" in test_names

    def test_detect_test_each_only_parameterized_case(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = 'test.each([[1]]).only("case", () => {});\n'
        result = v.collect_behavioral_artifacts(source, "test.ts")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "case" in test_names

    def test_describe_each_suite_label_is_ignored(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = 'describe.each([[1]])("suite_only", () => {});\n'
        result = v.collect_behavioral_artifacts(source, "test.ts")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "suite_only" not in test_names

    def test_template_string_without_substitution(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = "it(`test_template_label`, () => {});\n"
        result = v.collect_behavioral_artifacts(source, "test.ts")
        names = [a.name for a in result.artifacts]
        assert "test_template_label" in names

    def test_template_string_with_substitution_ignored(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = "const n = 1; it(`test_${n}`, () => {});\n"
        result = v.collect_behavioral_artifacts(source, "test.ts")
        names = [a.name for a in result.artifacts]
        # Interpolated labels cannot be matched to manifest names; must be ignored.
        assert not any(n.startswith("test_${") or n == "test_" for n in names)

    def test_non_test_callee_ignored(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = 'expect("test_not_really_a_test").toBe(true);\n'
        result = v.collect_behavioral_artifacts(source, "test.ts")
        names = [a.name for a in result.artifacts]
        assert "test_not_really_a_test" not in names

    def test_suite_labels_do_not_count_as_test_functions(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = (
            'describe("test_suite", () => {});\n'
            'fdescribe("test_focus_suite", () => {});\n'
            'xdescribe("test_skipped_suite", () => {});\n'
        )
        result = v.collect_behavioral_artifacts(source, "test.ts")
        names = [a.name for a in result.artifacts]
        assert "test_suite" not in names
        assert "test_focus_suite" not in names
        assert "test_skipped_suite" not in names

    def test_nested_helper_named_like_a_test_is_ignored(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = """
describe("auth", () => {
  const helper = () => {
    function test_missing() {
      expect(true).toBe(true)
    }
  }
})
"""
        result = v.collect_behavioral_artifacts(source, "test.ts")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "test_missing" not in test_names

    def test_nested_helper_test_call_is_ignored(self):
        from maid_runner.validators.typescript import TypeScriptValidator

        v = TypeScriptValidator()
        source = """
describe("auth", () => {
  const helper = () => {
    it("test_missing", () => {
      expect(true).toBe(true)
    })
  }
})
"""
        result = v.collect_behavioral_artifacts(source, "test.ts")
        test_names = [
            a.name for a in result.artifacts if a.kind.value == "test_function"
        ]
        assert "test_missing" not in test_names
