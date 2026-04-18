"""Tests for test_function validation in the validation engine."""

import tempfile
import pathlib
import yaml


class TestValidateTestFunctionNames:
    """Test Guard 3: test_function name validation."""

    def _write_manifest_and_test(
        self, tmpdir, manifest_yaml, test_code, test_path="tests/test_auth.py"
    ):
        """Helper to create manifest and test file."""
        p = pathlib.Path(tmpdir)
        test_file = p / test_path
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code)
        manifest_file = p / "test.manifest.yaml"
        manifest_file.write_text(manifest_yaml)
        return p, manifest_file

    def test_all_test_functions_exist(self):
        """All declared test functions exist in test file — pass."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_auth.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_success"},
                                {"kind": "test_function", "name": "test_failure"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
def test_success():
    assert True

def test_failure():
    assert False
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write_manifest_and_test(
                tmpdir, manifest_yaml, test_code
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is True
            assert len(result.errors) == 0

    def test_missing_test_function(self):
        """Declared test function not in test file — fail with E600."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_auth.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_exists"},
                                {"kind": "test_function", "name": "test_missing"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
def test_exists():
    assert True
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write_manifest_and_test(
                tmpdir, manifest_yaml, test_code
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes
            messages = [e.message for e in result.errors]
            assert any("test_missing" in m for m in messages)

    def test_test_file_not_found(self):
        """Test file doesn't exist — fail with E201."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/nonexistent.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_something"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FILE_NOT_FOUND in codes

    def test_test_function_skipped_in_usage_check(self):
        """TEST_FUNCTION artifacts are NOT flagged as 'not used in tests'."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "src/api.py",
                            "artifacts": [
                                {"kind": "function", "name": "my_func"},
                            ],
                        },
                        {
                            "path": "tests/test_api.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_my_func_works"},
                            ],
                        },
                    ],
                    "read": ["tests/test_api.py"],
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
from src.api import my_func

def test_my_func_works():
    assert my_func() is not None
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            src_file = p / "src/api.py"
            src_file.parent.mkdir(parents=True, exist_ok=True)
            src_file.write_text("def my_func(): return 42\n")
            test_file = p / "tests/test_api.py"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(test_code)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is True
            codes = [e.code for e in result.errors]
            assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS not in codes

    def test_async_test_function(self):
        """Async test functions are detected."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_async.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_async_works"},
                            ],
                        }
                    ],
                    "read": ["tests/test_async.py"],
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
async def test_async_works():
    assert True
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write_manifest_and_test(
                tmpdir, manifest_yaml, test_code, "tests/test_async.py"
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is True


class TestTestFunctionPresenceIsNotBypassable:
    """Guard 3 must distinguish test declarations from mere references."""

    def test_python_bypass_with_module_variable_fails(self):
        """A module-level variable named like a test must NOT satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_bypass.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_missing"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        # test_missing appears only as a module-level variable, not a function def.
        test_code = "test_missing = None\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(tmpdir, manifest_yaml, test_code)
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes

    def test_python_bypass_with_nested_helper_fails(self):
        """A nested helper def named like a test must NOT satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_bypass.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_missing"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
def helper():
    def test_missing():
        pass
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(tmpdir, manifest_yaml, test_code)
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes

    def test_python_class_based_test_still_passes(self):
        """A discoverable pytest class method should still satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_bypass.py",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_login"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
class TestAuth:
    def test_login(self):
        assert True
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(tmpdir, manifest_yaml, test_code)
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is True

    def test_typescript_bypass_with_import_reference_fails(self):
        """An import/variable reference must NOT satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/bypass.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_missing"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = (
            'import { test_missing } from "./helper";\nconst x = test_missing;\n'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(
                tmpdir, manifest_yaml, test_code, "tests/bypass.test.ts"
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes

    def test_typescript_bypass_with_module_level_helper_function_fails(self):
        """A plain TS helper named like a test must NOT satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/bypass.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_missing"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = "export function test_missing() { expect(true).toBe(true); }\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(
                tmpdir, manifest_yaml, test_code, "tests/bypass.test.ts"
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes

    def test_typescript_bypass_with_nested_helper_function_fails(self):
        """A nested TS helper named like a test must NOT satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/bypass.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_missing"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
describe("auth", () => {
  const helper = () => {
    const test_missing = () => {
      expect(true).toBe(true)
    }
  }
})
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(
                tmpdir, manifest_yaml, test_code, "tests/bypass.test.ts"
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes

    def test_typescript_bypass_with_nested_helper_test_call_fails(self):
        """A nested helper-scoped it()/test() call must NOT satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/bypass.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_missing"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
describe("auth", () => {
  const helper = () => {
    it("test_missing", () => {
      expect(true).toBe(true)
    })
  }
})
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(
                tmpdir, manifest_yaml, test_code, "tests/bypass.test.ts"
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes

    def test_typescript_bypass_with_suite_label_fails(self):
        """A suite label must NOT satisfy Guard 3 for a test_function artifact."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/bypass.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_missing"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = 'fdescribe("test_missing", () => {});\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(
                tmpdir, manifest_yaml, test_code, "tests/bypass.test.ts"
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes

    def test_typescript_bypass_with_test_describe_fails(self):
        """A suite wrapper like test.describe must NOT satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/bypass.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "suite_only"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = 'test.describe("suite_only", () => {});\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(
                tmpdir, manifest_yaml, test_code, "tests/bypass.test.ts"
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes

    def test_typescript_parameterized_each_still_passes(self):
        """Curried it.each/test.each declarations should satisfy Guard 3."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/bypass.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "case"},
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = 'it.each([[1]])("case", () => {});\n'
        with tempfile.TemporaryDirectory() as tmpdir:
            _, manifest_file = self._write(
                tmpdir, manifest_yaml, test_code, "tests/bypass.test.ts"
            )
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is True

    def _write(
        self, tmpdir, manifest_yaml, test_code, test_path="tests/test_bypass.py"
    ):
        p = pathlib.Path(tmpdir)
        test_file = p / test_path
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(test_code)
        manifest_file = p / "test.manifest.yaml"
        manifest_file.write_text(manifest_yaml)
        return p, manifest_file


class TestValidateTestFunctionNamesWithChain:
    """Chain-merged test_function requirements must survive across manifests."""

    def test_later_manifest_cannot_drop_historical_test(self):
        """Manifest B editing the same file cannot silently drop A's test_function."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.chain import ManifestChain
        from maid_runner.core.manifest import load_manifest
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_a = yaml.dump(
            {
                "schema": "2",
                "goal": "first",
                "type": "feature",
                "created": "2026-04-01",
                "files": {
                    "edit": [
                        {
                            "path": "tests/shared.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_old"},
                            ],
                        }
                    ]
                },
                "validate": ["echo a"],
            }
        )
        manifest_b = yaml.dump(
            {
                "schema": "2",
                "goal": "second",
                "type": "feature",
                "created": "2026-04-10",
                "files": {
                    "edit": [
                        {
                            "path": "tests/shared.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_new"},
                            ],
                        }
                    ]
                },
                "validate": ["echo b"],
            }
        )
        # Source only declares test_new; test_old has been deleted.
        test_code = 'it("test_new", () => {});\n'

        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            (p / "tests").mkdir()
            (p / "tests/shared.test.ts").write_text(test_code)
            (p / "manifests").mkdir()
            (p / "manifests/a.manifest.yaml").write_text(manifest_a)
            (p / "manifests/b.manifest.yaml").write_text(manifest_b)

            chain = ManifestChain(p / "manifests", p)
            engine = ValidationEngine(p)
            b = load_manifest(p / "manifests/b.manifest.yaml")
            result = engine.validate(
                b,
                mode=ValidationMode.IMPLEMENTATION,
                use_chain=True,
                chain=chain,
            )

            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes
            messages = [e.message for e in result.errors]
            assert any("test_old" in m for m in messages)

    def test_behavioral_mode_cannot_drop_historical_test(self):
        """Behavioral validation must enforce the same merged test history."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.chain import ManifestChain
        from maid_runner.core.manifest import load_manifest
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_a = yaml.dump(
            {
                "schema": "2",
                "goal": "first",
                "type": "feature",
                "created": "2026-04-01",
                "files": {
                    "edit": [
                        {
                            "path": "tests/shared.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_old"},
                            ],
                        }
                    ]
                },
                "validate": ["echo a"],
            }
        )
        manifest_b = yaml.dump(
            {
                "schema": "2",
                "goal": "second",
                "type": "feature",
                "created": "2026-04-10",
                "files": {
                    "edit": [
                        {
                            "path": "tests/shared.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_new"},
                            ],
                        }
                    ]
                },
                "validate": ["echo b"],
            }
        )
        test_code = 'it("test_new", () => {});\n'

        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            (p / "tests").mkdir()
            (p / "tests/shared.test.ts").write_text(test_code)
            (p / "manifests").mkdir()
            (p / "manifests/a.manifest.yaml").write_text(manifest_a)
            (p / "manifests/b.manifest.yaml").write_text(manifest_b)

            chain = ManifestChain(p / "manifests", p)
            engine = ValidationEngine(p)
            b = load_manifest(p / "manifests/b.manifest.yaml")
            result = engine.validate(
                b,
                mode=ValidationMode.BEHAVIORAL,
                use_chain=True,
                chain=chain,
            )

            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in codes
            messages = [e.message for e in result.errors]
            assert any("test_old" in m for m in messages)

    def test_behavioral_mode_preserves_historical_test_details(self):
        """Later manifests cannot erase earlier behavior requirements by omission."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.chain import ManifestChain
        from maid_runner.core.manifest import load_manifest
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_a = yaml.dump(
            {
                "schema": "2",
                "goal": "first",
                "type": "feature",
                "created": "2026-04-01",
                "files": {
                    "edit": [
                        {
                            "path": "tests/shared.test.ts",
                            "artifacts": [
                                {
                                    "kind": "test_function",
                                    "name": "test_api_call",
                                    "test_function_details": {
                                        "actions": [
                                            {
                                                "type": "api_call",
                                                "subject": {
                                                    "module": "src/api.ts",
                                                    "export": "createLogin",
                                                },
                                                "endpoint": "/api/v1/auth/login",
                                            }
                                        ]
                                    },
                                }
                            ],
                        }
                    ]
                },
                "validate": ["echo a"],
            }
        )
        manifest_b = yaml.dump(
            {
                "schema": "2",
                "goal": "second",
                "type": "feature",
                "created": "2026-04-10",
                "files": {
                    "edit": [
                        {
                            "path": "tests/shared.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "test_api_call"},
                            ],
                        }
                    ]
                },
                "validate": ["echo b"],
            }
        )
        test_code = 'it("test_api_call", () => { createLogin(); });\n'

        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            (p / "tests").mkdir()
            (p / "tests/shared.test.ts").write_text(test_code)
            (p / "manifests").mkdir()
            (p / "manifests/a.manifest.yaml").write_text(manifest_a)
            (p / "manifests/b.manifest.yaml").write_text(manifest_b)

            chain = ManifestChain(p / "manifests", p)
            engine = ValidationEngine(p)
            b = load_manifest(p / "manifests/b.manifest.yaml")
            result = engine.validate(
                b,
                mode=ValidationMode.BEHAVIORAL,
                use_chain=True,
                chain=chain,
            )

            codes = [e.code for e in result.errors + result.warnings]
            assert ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH in codes
            messages = [e.message for e in result.errors + result.warnings]
            assert any("/api/v1/auth/login" in m for m in messages)


class TestValidateTestFunctionBehavior:
    """Test behavioral alignment of test_function details."""

    def test_behavior_mismatch_runs_without_check_assertions(self):
        """Behavior metadata warnings should run in normal behavioral validation."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode
        import yaml

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_api.test.ts",
                            "artifacts": [
                                {
                                    "kind": "test_function",
                                    "name": "test_api_call",
                                    "test_function_details": {
                                        "actions": [
                                            {
                                                "type": "api_call",
                                                "subject": {
                                                    "module": "src/api.ts",
                                                    "export": "createLogin",
                                                },
                                                "endpoint": "/api/v1/auth/login",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
it("test_api_call", () => {
  expect(true).toBe(true)
})
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            test_file = p / "tests/test_api.test.ts"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(test_code)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)
            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            codes = [e.code for e in result.errors + result.warnings]
            assert ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH in codes

    def test_test_label_does_not_mask_source_coverage(self):
        """A test labeled ``it("createLogin", ...)`` must not count as a
        reference to a source artifact named ``createLogin``. Only real
        identifier/import references count as artifact usage."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "src/auth.ts",
                            "artifacts": [
                                {"kind": "function", "name": "createLogin"},
                            ],
                        },
                        {
                            "path": "tests/auth.test.ts",
                            "artifacts": [
                                {"kind": "test_function", "name": "createLogin"},
                            ],
                        },
                    ],
                    "read": ["tests/auth.test.ts"],
                },
                "validate": ["echo test"],
            }
        )
        # Test file uses the label "createLogin" but never imports or calls
        # the source artifact named createLogin.
        test_code = 'it("createLogin", () => { expect(true).toBe(true); });\n'
        src_code = "export function createLogin() { return 1; }\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            (p / "src").mkdir()
            (p / "src/auth.ts").write_text(src_code)
            (p / "tests").mkdir()
            (p / "tests/auth.test.ts").write_text(test_code)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)

            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            assert result.success is False
            codes = [e.code for e in result.errors]
            assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS in codes
            messages = [e.message for e in result.errors]
            assert any("createLogin" in m for m in messages)

    def test_behavior_mismatch_scoped_to_specific_test_body(self):
        """E610 must scope its substring check to each test's own body.
        If test_a's body mentions /api/v1/logout but test_b declares that
        endpoint with an empty body, test_b must still warn."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/api.test.ts",
                            "artifacts": [
                                {
                                    "kind": "test_function",
                                    "name": "test_login",
                                    "test_function_details": {
                                        "actions": [
                                            {
                                                "type": "api_call",
                                                "subject": {
                                                    "module": "src/api.ts",
                                                    "export": "doLogin",
                                                },
                                                "endpoint": "/api/v1/login",
                                            }
                                        ],
                                    },
                                },
                                {
                                    "kind": "test_function",
                                    "name": "test_logout",
                                    "test_function_details": {
                                        "actions": [
                                            {
                                                "type": "api_call",
                                                "subject": {
                                                    "module": "src/api.ts",
                                                    "export": "doLogout",
                                                },
                                                "endpoint": "/api/v1/logout",
                                            }
                                        ],
                                    },
                                },
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        # test_login's body mentions both endpoints and both exports; if the
        # check is whole-file, test_logout will silently pass. With per-test
        # scoping, test_logout's empty body must trigger E610 for both the
        # export (doLogout) and the endpoint (/api/v1/logout).
        test_code = (
            'it("test_login", () => {\n'
            '  doLogin("/api/v1/login");\n'
            '  doLogout("/api/v1/logout");\n'
            "});\n"
            'it("test_logout", () => {\n'
            "  expect(true).toBe(true);\n"
            "});\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            (p / "tests").mkdir()
            (p / "tests/api.test.ts").write_text(test_code)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)

            engine = ValidationEngine(tmpdir)
            result = engine.validate(manifest_file, mode=ValidationMode.BEHAVIORAL)
            all_diags = result.errors + result.warnings
            messages = [(e.code, e.message) for e in all_diags]
            mismatches = [
                m for c, m in messages if c == ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH
            ]
            # test_logout's body has neither the export nor the endpoint
            assert any(
                "test_logout" in m and "doLogout" in m for m in mismatches
            ), f"expected E610 for test_logout/doLogout; got: {mismatches}"
            assert any(
                "test_logout" in m and "/api/v1/logout" in m for m in mismatches
            ), f"expected E610 for test_logout/endpoint; got: {mismatches}"
            # test_login's body contains both — no E610 should fire for it
            assert not any(
                "test_login" in m for m in mismatches
            ), f"test_login body contains both; should not warn: {mismatches}"

    def test_behavior_mismatch_api_call(self):
        """API call export not found in test file — warning."""
        from maid_runner.core.validate import ValidationEngine
        from maid_runner.core.types import ValidationMode
        from maid_runner.core.result import ErrorCode
        import yaml

        manifest_yaml = yaml.dump(
            {
                "schema": "2",
                "goal": "test",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "tests/test_api.test.ts",
                            "artifacts": [
                                {
                                    "kind": "test_function",
                                    "name": "test_api_call",
                                    "test_function_details": {
                                        "actions": [
                                            {
                                                "type": "api_call",
                                                "subject": {
                                                    "module": "src/api.ts",
                                                    "export": "createLogin",
                                                },
                                                "endpoint": "/api/v1/auth/login",
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ]
                },
                "validate": ["echo test"],
            }
        )
        test_code = """
it("test_api_call", () => {
  expect(true).toBe(true)
})
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = pathlib.Path(tmpdir)
            test_file = p / "tests/test_api.test.ts"
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text(test_code)
            manifest_file = p / "test.manifest.yaml"
            manifest_file.write_text(manifest_yaml)
            engine = ValidationEngine(tmpdir)
            result = engine.validate(
                manifest_file,
                mode=ValidationMode.BEHAVIORAL,
                check_assertions=True,
            )
            codes = [e.code for e in result.errors + result.warnings]
            # The export and endpoint should trigger E610 warnings
            # (the test file doesn't import createLogin or have the endpoint)
            if ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH not in codes:
                print("Errors:", [(e.code.value, e.message) for e in result.errors])
                print("Warnings:", [(e.code.value, e.message) for e in result.warnings])
            assert ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH in codes
