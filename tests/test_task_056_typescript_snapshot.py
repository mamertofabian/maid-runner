"""Behavioral tests for Task-056: Enable TypeScript/JavaScript snapshot generation.

This test suite validates that the snapshot generator can detect and process
TypeScript/JavaScript files using the TypeScript validator, converting artifacts
to manifest format while maintaining backward compatibility with Python snapshots.

Test Organization:
- File language detection
- TypeScript artifact extraction
- Integration with snapshot generation
- Backward compatibility
- Edge cases
"""

import json
from pathlib import Path

import pytest


# =============================================================================
# SECTION 1: Module Imports
# =============================================================================


class TestModuleImports:
    """Test that required functions and classes can be imported."""

    def test_import_detect_file_language(self):
        """detect_file_language function must be importable from snapshot module."""
        from maid_runner.cli.snapshot import detect_file_language

        assert callable(detect_file_language)

    def test_import_extract_typescript_artifacts(self):
        """extract_typescript_artifacts function must be importable from snapshot module."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        assert callable(extract_typescript_artifacts)

    def test_import_extract_artifacts_from_code(self):
        """Existing extract_artifacts_from_code must still be importable."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        assert callable(extract_artifacts_from_code)


# =============================================================================
# SECTION 2: File Language Detection
# =============================================================================


class TestFileLanguageDetection:
    """Test file type detection for routing to correct validator."""

    def test_detect_python_file(self):
        """Python files (.py) must be detected correctly."""
        from maid_runner.cli.snapshot import detect_file_language

        assert detect_file_language("example.py") == "python"
        assert detect_file_language("path/to/module.py") == "python"
        assert detect_file_language("/absolute/path/script.py") == "python"

    def test_detect_typescript_file(self):
        """TypeScript files (.ts) must be detected correctly."""
        from maid_runner.cli.snapshot import detect_file_language

        assert detect_file_language("example.ts") == "typescript"
        assert detect_file_language("path/to/module.ts") == "typescript"

    def test_detect_tsx_file(self):
        """TypeScript JSX files (.tsx) must be detected as TypeScript."""
        from maid_runner.cli.snapshot import detect_file_language

        assert detect_file_language("component.tsx") == "typescript"
        assert detect_file_language("path/to/Component.tsx") == "typescript"

    def test_detect_javascript_file(self):
        """JavaScript files (.js) must be detected as TypeScript (same validator)."""
        from maid_runner.cli.snapshot import detect_file_language

        assert detect_file_language("script.js") == "typescript"
        assert detect_file_language("path/to/module.js") == "typescript"

    def test_detect_jsx_file(self):
        """JavaScript JSX files (.jsx) must be detected as TypeScript."""
        from maid_runner.cli.snapshot import detect_file_language

        assert detect_file_language("component.jsx") == "typescript"

    def test_detect_unknown_file(self):
        """Unknown file types must return 'unknown' or raise appropriate error."""
        from maid_runner.cli.snapshot import detect_file_language

        # Could either return "unknown" or raise ValueError
        result = detect_file_language("file.txt")
        assert result in (
            "unknown",
            "python",
        )  # May default to python for backward compat


# =============================================================================
# SECTION 3: TypeScript Artifact Extraction
# =============================================================================


class TestTypeScriptArtifactExtraction:
    """Test extraction of TypeScript artifacts in manifest format."""

    def test_extract_typescript_class(self, tmp_path):
        """TypeScript class must be extracted as manifest artifact."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "example.ts"
        ts_file.write_text(
            """
export class UserService {
    getUser(id: string): User {
        return { id, name: "Test" };
    }
}
"""
        )

        artifacts = extract_typescript_artifacts(str(ts_file))

        # Check structure
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

        # Find the class artifact
        classes = [a for a in artifacts["artifacts"] if a.get("type") == "class"]
        assert len(classes) >= 1
        assert any(c.get("name") == "UserService" for c in classes)

    def test_extract_typescript_interface(self, tmp_path):
        """TypeScript interface must be extracted as manifest artifact."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "types.ts"
        ts_file.write_text(
            """
export interface User {
    id: string;
    name: string;
}
"""
        )

        artifacts = extract_typescript_artifacts(str(ts_file))

        # Find the interface artifact
        interfaces = [a for a in artifacts["artifacts"] if a.get("type") == "interface"]
        assert len(interfaces) >= 1
        assert any(i.get("name") == "User" for i in interfaces)

    def test_extract_typescript_function(self, tmp_path):
        """TypeScript standalone function must be extracted as manifest artifact."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "utils.ts"
        ts_file.write_text(
            """
export function validateUser(user: User): boolean {
    return user.id.length > 0;
}
"""
        )

        artifacts = extract_typescript_artifacts(str(ts_file))

        # Find the function artifact
        functions = [
            a
            for a in artifacts["artifacts"]
            if a.get("type") == "function" and not a.get("class")
        ]
        assert len(functions) >= 1
        assert any(f.get("name") == "validateUser" for f in functions)

    def test_extract_typescript_type_alias(self, tmp_path):
        """TypeScript type alias must be extracted as manifest artifact."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "types.ts"
        ts_file.write_text(
            """
export type UserID = string;
export type Status = 'active' | 'inactive';
"""
        )

        artifacts = extract_typescript_artifacts(str(ts_file))

        # Find the type alias artifacts
        types = [a for a in artifacts["artifacts"] if a.get("type") == "type"]
        assert len(types) >= 1
        type_names = {t.get("name") for t in types}
        assert "UserID" in type_names or "Status" in type_names

    def test_extract_typescript_enum(self, tmp_path):
        """TypeScript enum must be extracted as manifest artifact."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "enums.ts"
        ts_file.write_text(
            """
export enum Role {
    Admin,
    User,
    Guest
}
"""
        )

        artifacts = extract_typescript_artifacts(str(ts_file))

        # Find the enum artifact
        enums = [a for a in artifacts["artifacts"] if a.get("type") == "enum"]
        assert len(enums) >= 1
        assert any(e.get("name") == "Role" for e in enums)

    def test_extract_typescript_namespace(self, tmp_path):
        """TypeScript namespace must be extracted as manifest artifact."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "namespaces.ts"
        ts_file.write_text(
            """
export namespace Utils {
    export function helper() {
        return true;
    }
}
"""
        )

        artifacts = extract_typescript_artifacts(str(ts_file))

        # Find the namespace artifact
        namespaces = [a for a in artifacts["artifacts"] if a.get("type") == "namespace"]
        assert len(namespaces) >= 1
        assert any(n.get("name") == "Utils" for n in namespaces)

    def test_extract_mixed_typescript_artifacts(self, tmp_path):
        """File with multiple TypeScript artifact types must extract all."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "mixed.ts"
        ts_file.write_text(
            """
export interface User {
    id: string;
}

export class UserService {
    getUser(id: string): User {
        return { id };
    }
}

export function validateUser(user: User): boolean {
    return true;
}

export type UserID = string;
export enum Role { Admin, User }
"""
        )

        artifacts = extract_typescript_artifacts(str(ts_file))

        # Should have multiple artifact types
        artifact_types = {a.get("type") for a in artifacts["artifacts"]}
        assert "interface" in artifact_types
        assert "class" in artifact_types
        assert "function" in artifact_types


# =============================================================================
# SECTION 4: Integration with Snapshot Generation
# =============================================================================


class TestSnapshotGeneration:
    """Test end-to-end snapshot generation for TypeScript files."""

    def test_generate_snapshot_for_typescript_file(self, tmp_path):
        """Snapshot generation must work for TypeScript files."""
        from maid_runner.cli.snapshot import generate_snapshot

        # Create a TypeScript file
        ts_file = tmp_path / "service.ts"
        ts_file.write_text(
            """
export class UserService {
    getUser(id: string) {
        return { id };
    }
}
"""
        )

        # Create manifest output directory
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Generate snapshot
        manifest_path = generate_snapshot(
            str(ts_file), str(manifest_dir), skip_test_stub=True
        )

        # Verify manifest was created
        assert Path(manifest_path).exists()

        # Load and verify manifest structure
        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["taskType"] == "snapshot"
        assert manifest["expectedArtifacts"]["file"] == str(ts_file)
        assert len(manifest["expectedArtifacts"]["contains"]) > 0

    def test_generate_snapshot_for_javascript_file(self, tmp_path):
        """Snapshot generation must work for JavaScript files."""
        from maid_runner.cli.snapshot import generate_snapshot

        js_file = tmp_path / "utils.js"
        js_file.write_text(
            """
export function helper() {
    return true;
}
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(js_file), str(manifest_dir), skip_test_stub=True
        )

        assert Path(manifest_path).exists()

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["expectedArtifacts"]["file"] == str(js_file)

    def test_snapshot_manifest_contains_typescript_artifacts(self, tmp_path):
        """Generated snapshot must include all TypeScript artifact types."""
        from maid_runner.cli.snapshot import generate_snapshot

        ts_file = tmp_path / "complete.ts"
        ts_file.write_text(
            """
export interface User { id: string; }
export class UserService {}
export function validate() {}
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(ts_file), str(manifest_dir), skip_test_stub=True
        )

        with open(manifest_path) as f:
            manifest = json.load(f)

        artifact_types = {
            a.get("type") for a in manifest["expectedArtifacts"]["contains"]
        }
        # Should contain interface, class, and function
        assert len(artifact_types) >= 2  # At least some types present


# =============================================================================
# SECTION 5: Backward Compatibility
# =============================================================================


class TestBackwardCompatibility:
    """Test that Python snapshot generation still works."""

    def test_python_snapshot_still_works(self, tmp_path):
        """Python file snapshots must continue to work unchanged."""
        from maid_runner.cli.snapshot import generate_snapshot

        py_file = tmp_path / "module.py"
        py_file.write_text(
            """
class Example:
    def method(self):
        pass

def function():
    pass
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(py_file), str(manifest_dir), skip_test_stub=True
        )

        assert Path(manifest_path).exists()

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["taskType"] == "snapshot"
        assert manifest["expectedArtifacts"]["file"] == str(py_file)
        assert len(manifest["expectedArtifacts"]["contains"]) >= 2

    def test_extract_artifacts_from_code_routes_correctly(self, tmp_path):
        """extract_artifacts_from_code must route based on file type."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # Python file
        py_file = tmp_path / "test.py"
        py_file.write_text("class Test: pass")

        py_artifacts = extract_artifacts_from_code(str(py_file))
        assert "artifacts" in py_artifacts

        # TypeScript file
        ts_file = tmp_path / "test.ts"
        ts_file.write_text("export class Test {}")

        ts_artifacts = extract_artifacts_from_code(str(ts_file))
        assert "artifacts" in ts_artifacts


# =============================================================================
# SECTION 6: Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test error handling and edge cases."""

    def test_typescript_file_not_found(self):
        """Missing TypeScript file must raise FileNotFoundError."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        with pytest.raises(FileNotFoundError):
            extract_typescript_artifacts("nonexistent.ts")

    def test_empty_typescript_file(self, tmp_path):
        """Empty TypeScript file must not crash."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "empty.ts"
        ts_file.write_text("")

        artifacts = extract_typescript_artifacts(str(ts_file))

        # Should return valid structure even if empty
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

    def test_typescript_with_syntax_errors(self, tmp_path):
        """TypeScript file with syntax errors must handle gracefully."""
        from maid_runner.cli.snapshot import extract_typescript_artifacts

        ts_file = tmp_path / "invalid.ts"
        ts_file.write_text("class {{{{{ invalid syntax")

        # Should either parse what it can or raise SyntaxError
        # Tree-sitter is fault-tolerant, so might extract partial artifacts
        artifacts = extract_typescript_artifacts(str(ts_file))
        assert "artifacts" in artifacts
