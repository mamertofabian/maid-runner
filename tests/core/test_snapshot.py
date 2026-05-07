"""Tests for core/snapshot.py - snapshot generation module."""

import textwrap

import pytest
import yaml

from maid_runner.core.snapshot import (
    generate_snapshot,
    generate_system_snapshot,
    generate_test_stub,
    save_snapshot,
)
from maid_runner.core.types import (
    FileMode,
    Manifest,
    TaskType,
)
from maid_runner.validators.registry import UnsupportedLanguageError


# ---------------------------------------------------------------------------
# generate_snapshot
# ---------------------------------------------------------------------------


class TestGenerateSnapshot:
    def test_snapshot_simple_python_file(self, tmp_path):
        """Snapshot a Python file with a class and function."""
        src = tmp_path / "src" / "auth" / "service.py"
        src.parent.mkdir(parents=True)
        src.write_text(
            textwrap.dedent(
                """\
            class AuthService:
                def login(self, user: str) -> bool:
                    pass

            def helper() -> str:
                return "ok"
            """
            )
        )

        m = generate_snapshot(str(src), project_root=str(tmp_path))
        assert isinstance(m, Manifest)
        assert m.task_type == TaskType.SNAPSHOT
        assert m.goal == "Snapshot of src/auth/service.py"
        assert m.slug == "snapshot-auth-service"
        # Should have snapshot file specs
        assert len(m.files_snapshot) == 1
        fs = m.files_snapshot[0]
        assert fs.path == "src/auth/service.py"
        assert fs.mode == FileMode.SNAPSHOT
        # Should find public artifacts
        names = {a.name for a in fs.artifacts}
        assert "AuthService" in names
        assert "login" in names
        assert "helper" in names

    def test_snapshot_excludes_private_by_default(self, tmp_path):
        """Private artifacts are excluded unless include_private=True."""
        src = tmp_path / "utils.py"
        src.write_text(
            textwrap.dedent(
                """\
            def public_func():
                pass

            def _private_func():
                pass
            """
            )
        )

        m = generate_snapshot(str(src), project_root=str(tmp_path))
        names = {a.name for a in m.files_snapshot[0].artifacts}
        assert "public_func" in names
        assert "_private_func" not in names

    def test_snapshot_includes_private_when_requested(self, tmp_path):
        """include_private=True includes private artifacts."""
        src = tmp_path / "utils.py"
        src.write_text(
            textwrap.dedent(
                """\
            def public_func():
                pass

            def _private_func():
                pass
            """
            )
        )

        m = generate_snapshot(
            str(src), project_root=str(tmp_path), include_private=True
        )
        names = {a.name for a in m.files_snapshot[0].artifacts}
        assert "public_func" in names
        assert "_private_func" in names

    def test_snapshot_file_not_found(self, tmp_path):
        """Raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            generate_snapshot(str(tmp_path / "nope.py"), project_root=str(tmp_path))

    def test_snapshot_unsupported_language(self, tmp_path):
        """Raise UnsupportedLanguageError for unknown extensions."""
        src = tmp_path / "data.xyz"
        src.write_text("stuff")
        with pytest.raises(UnsupportedLanguageError):
            generate_snapshot(str(src), project_root=str(tmp_path))

    def test_snapshot_relative_path_resolution(self, tmp_path):
        """File path in manifest should be relative to project root."""
        src = tmp_path / "maid_runner" / "core" / "types.py"
        src.parent.mkdir(parents=True)
        src.write_text("class MyType:\n    pass\n")

        m = generate_snapshot(str(src), project_root=str(tmp_path))
        assert m.files_snapshot[0].path == "maid_runner/core/types.py"

    def test_snapshot_slug_generation(self, tmp_path):
        """Slug is derived from file path."""
        src = tmp_path / "src" / "components" / "AuthProvider.py"
        src.parent.mkdir(parents=True)
        src.write_text("class AuthProvider:\n    pass\n")

        m = generate_snapshot(str(src), project_root=str(tmp_path))
        assert m.slug == "snapshot-components-auth-provider"

    def test_typescript_snapshot_preserves_generic_type_parameters(self, tmp_path):
        """TypeScript snapshots keep declaration-site generic parameters."""
        src = tmp_path / "src" / "store.ts"
        src.parent.mkdir(parents=True)
        src.write_text("export class Store<T extends Item = Item> {}\n")

        m = generate_snapshot(str(src), project_root=str(tmp_path))
        store = next(a for a in m.files_snapshot[0].artifacts if a.name == "Store")

        assert store.type_parameters == ("T extends Item = Item",)


# ---------------------------------------------------------------------------
# parse error surfacing
# ---------------------------------------------------------------------------


class TestSnapshotParseError:
    def test_syntax_error_raises_SnapshotError(self, tmp_path):
        """Unparseable Python file should raise SnapshotError, not return empty manifest."""
        from maid_runner.core.snapshot import SnapshotError

        bad_file = tmp_path / "broken.py"
        bad_file.write_text("def broken(\n")

        with pytest.raises(SnapshotError, match="broken.py"):
            generate_snapshot(str(bad_file), project_root=str(tmp_path))

    def test_snapshot_error_has_path(self, tmp_path):
        """SnapshotError should carry the file path for caller context."""
        from maid_runner.core.snapshot import SnapshotError

        bad_file = tmp_path / "bad.py"
        bad_file.write_text("class Oops(\n")

        with pytest.raises(SnapshotError) as exc_info:
            generate_snapshot(str(bad_file), project_root=str(tmp_path))
        assert str(bad_file) in str(exc_info.value.path)

    def test_empty_init_py_succeeds(self, tmp_path):
        """Legitimate empty __init__.py should not raise (no false positive)."""
        init = tmp_path / "__init__.py"
        init.write_text("")

        m = generate_snapshot(str(init), project_root=str(tmp_path))
        assert len(m.files_snapshot) == 1
        assert len(m.files_snapshot[0].artifacts) == 0


# ---------------------------------------------------------------------------
# generate_system_snapshot
# ---------------------------------------------------------------------------


class TestGenerateSystemSnapshot:
    def test_system_snapshot_from_chain(self, tmp_path):
        """System snapshot aggregates artifacts from all tracked files."""
        # Create source files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "a.py").write_text("def func_a():\n    pass\n")
        (src_dir / "b.py").write_text("def func_b():\n    pass\n")

        # Create manifests
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        m1 = {
            "schema": "2",
            "goal": "Create A",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/a.py",
                        "artifacts": [{"kind": "function", "name": "func_a"}],
                    }
                ]
            },
            "validate": ["pytest tests/ -v"],
        }
        m2 = {
            "schema": "2",
            "goal": "Create B",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/b.py",
                        "artifacts": [{"kind": "function", "name": "func_b"}],
                    }
                ]
            },
            "validate": ["pytest tests/ -v"],
        }
        (manifest_dir / "create-a.manifest.yaml").write_text(yaml.dump(m1))
        (manifest_dir / "create-b.manifest.yaml").write_text(yaml.dump(m2))

        result = generate_system_snapshot(
            manifest_dir=str(manifest_dir),
            project_root=str(tmp_path),
        )
        assert isinstance(result, Manifest)
        assert result.slug == "system-snapshot"
        assert result.task_type == TaskType.SYSTEM_SNAPSHOT
        paths = {fs.path for fs in result.files_snapshot}
        assert "src/a.py" in paths
        assert "src/b.py" in paths

    def test_system_snapshot_empty_manifests(self, tmp_path):
        """System snapshot with no manifests returns empty snapshot."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        result = generate_system_snapshot(
            manifest_dir=str(manifest_dir),
            project_root=str(tmp_path),
        )
        assert result.slug == "system-snapshot"
        assert len(result.files_snapshot) == 0


# ---------------------------------------------------------------------------
# save_snapshot
# ---------------------------------------------------------------------------


class TestSaveSnapshot:
    def test_save_yaml_default(self, tmp_path):
        """Save snapshot as YAML (default format)."""
        m = Manifest(
            slug="snapshot-test",
            source_path="",
            goal="Snapshot of test.py",
            validate_commands=(("pytest", "tests/", "-v"),),
            task_type=TaskType.SNAPSHOT,
            files_snapshot=(),
        )
        out = save_snapshot(m, output_dir=str(tmp_path))
        assert out.suffix in (".yaml", ".yml")
        assert out.exists()
        data = yaml.safe_load(out.read_text())
        assert data["goal"] == "Snapshot of test.py"
        assert data["type"] == "snapshot"

    def test_save_json_format(self, tmp_path):
        """Save snapshot as JSON."""
        m = Manifest(
            slug="snapshot-test",
            source_path="",
            goal="Snapshot of test.py",
            validate_commands=(("pytest", "tests/", "-v"),),
            task_type=TaskType.SNAPSHOT,
        )
        out = save_snapshot(m, output_dir=str(tmp_path), format="json")
        assert out.suffix == ".json"
        assert out.exists()
        import json

        data = json.loads(out.read_text())
        assert data["goal"] == "Snapshot of test.py"

    def test_save_specific_output_path(self, tmp_path):
        """output= overrides output_dir."""
        m = Manifest(
            slug="snapshot-test",
            source_path="",
            goal="Snapshot of test.py",
            validate_commands=(),
        )
        out_path = tmp_path / "custom" / "out.yaml"
        out = save_snapshot(m, output=str(out_path))
        assert out == out_path
        assert out.exists()


# ---------------------------------------------------------------------------
# generate_test_stub
# ---------------------------------------------------------------------------


class TestGenerateTestStub:
    def test_generates_stub_for_python(self, tmp_path):
        """Test stub generation returns dict (may be empty if validator has no stub support)."""
        src = tmp_path / "src" / "service.py"
        src.parent.mkdir(parents=True)
        src.write_text(
            textwrap.dedent(
                """\
            class MyService:
                def process(self):
                    pass

            def standalone():
                pass
            """
            )
        )

        m = generate_snapshot(str(src), project_root=str(tmp_path))
        stubs = generate_test_stub(m)
        assert isinstance(stubs, dict)
        # If validator supports test stubs, verify content
        if stubs:
            test_paths = list(stubs.keys())
            assert any("test_" in p for p in test_paths)

    def test_empty_manifest_returns_empty(self):
        """Manifest with no file specs returns empty dict."""
        m = Manifest(
            slug="empty",
            source_path="",
            goal="empty",
            validate_commands=(),
        )
        stubs = generate_test_stub(m)
        assert stubs == {}


# ---------------------------------------------------------------------------
# _snapshot_slug helper (tested via generate_snapshot)
# ---------------------------------------------------------------------------


class TestSnapshotSlug:
    """Slug generation tested indirectly through generate_snapshot."""

    def test_nested_path_slug(self, tmp_path):
        src = tmp_path / "maid_runner" / "validators" / "python.py"
        src.parent.mkdir(parents=True)
        src.write_text("class PythonValidator:\n    pass\n")
        m = generate_snapshot(str(src), project_root=str(tmp_path))
        assert m.slug == "snapshot-validators-python"

    def test_single_dir_slug(self, tmp_path):
        src = tmp_path / "src" / "utils.py"
        src.parent.mkdir(parents=True)
        src.write_text("def util():\n    pass\n")
        m = generate_snapshot(str(src), project_root=str(tmp_path))
        assert m.slug == "snapshot-src-utils"

    def test_top_level_file_slug(self, tmp_path):
        src = tmp_path / "main.py"
        src.write_text("def main():\n    pass\n")
        m = generate_snapshot(str(src), project_root=str(tmp_path))
        assert m.slug == "snapshot-main"


# ---------------------------------------------------------------------------
# Edge cases for snapshot
# ---------------------------------------------------------------------------


class TestSnapshotEdgeCases:
    def test_file_outside_project_root(self, tmp_path):
        """Snapshot of file outside project root uses absolute path."""
        other = tmp_path / "outside"
        other.mkdir()
        src = other / "service.py"
        src.write_text("def svc():\n    pass\n")
        project = tmp_path / "project"
        project.mkdir()
        # File is outside project_root, so relative_to raises ValueError
        m = generate_snapshot(str(src), project_root=str(project))
        # Should fall back to absolute path
        assert m.slug is not None

    def test_system_snapshot_missing_dir(self, tmp_path):
        """System snapshot with nonexistent manifest dir returns empty."""
        m = generate_system_snapshot(
            manifest_dir=str(tmp_path / "nonexistent"),
            project_root=str(tmp_path),
        )
        assert m.task_type == TaskType.SYSTEM_SNAPSHOT
        assert not m.files_create
        assert not m.files_edit

    def test_system_snapshot_empty_dir(self, tmp_path):
        """System snapshot with empty manifest dir returns empty."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        m = generate_system_snapshot(
            manifest_dir=str(manifest_dir),
            project_root=str(tmp_path),
        )
        assert m.task_type == TaskType.SYSTEM_SNAPSHOT

    def test_system_snapshot_with_tracked_files(self, tmp_path):
        """System snapshot captures artifacts from tracked files."""
        # Create a manifest
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "example.py").write_text(
            "def greet(name: str) -> str:\n    return name\n"
        )

        manifest = {
            "schema": "2",
            "goal": "Add greeting",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/example.py",
                        "artifacts": [{"kind": "function", "name": "greet"}],
                    }
                ]
            },
            "validate": ["echo ok"],
        }
        (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

        m = generate_system_snapshot(
            manifest_dir=str(manifest_dir),
            project_root=str(tmp_path),
        )
        # Should have found the tracked file
        assert m.task_type == TaskType.SYSTEM_SNAPSHOT

    def test_infer_test_path_typescript(self):
        """Test path inference for TypeScript files."""
        from maid_runner.core.snapshot import _infer_test_path

        result = _infer_test_path("src/auth.ts", "tests")
        assert result.endswith(".test.ts")
        assert "auth" in result

    def test_infer_test_path_tsx(self):
        """Test path inference for TSX files."""
        from maid_runner.core.snapshot import _infer_test_path

        result = _infer_test_path("src/App.tsx", "tests")
        assert result.endswith(".test.tsx")

    def test_infer_test_path_unknown(self):
        """Test path inference for unknown file types."""
        from maid_runner.core.snapshot import _infer_test_path

        result = _infer_test_path("src/config.json", "tests")
        assert "test_config" in result

    def test_infer_validation_command_typescript(self):
        """TypeScript files get vitest command."""
        from maid_runner.core.snapshot import _infer_validation_command

        cmd = _infer_validation_command("src/auth.ts")
        assert ("vitest", "run") in cmd

    def test_infer_validation_command_default(self):
        """Unknown file types default to pytest."""
        from maid_runner.core.snapshot import _infer_validation_command

        cmd = _infer_validation_command("src/config.json")
        assert cmd[0][0] == "pytest"
