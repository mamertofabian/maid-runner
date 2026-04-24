"""Tests for maid_runner.core._file_discovery - source file discovery and test detection."""

from maid_runner.core._file_discovery import (
    discover_source_files,
    is_test_file,
    find_test_files_from_manifest,
)


class TestDiscoverSourceFiles:
    """Tests for discover_source_files function."""

    def test_finds_python_files(self, tmp_path):
        """Python files in subdirectories are discovered."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("print('hello')")
        (tmp_path / "src" / "utils.py").write_text("def helper(): pass")

        files = discover_source_files(tmp_path)
        assert "src/app.py" in files
        assert "src/utils.py" in files

    def test_excludes_venv_directory(self, tmp_path):
        """Files inside .venv directories are excluded."""
        (tmp_path / ".venv" / "lib").mkdir(parents=True)
        (tmp_path / ".venv" / "lib" / "site.py").write_text("# venv internals")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("print('hello')")

        files = discover_source_files(tmp_path)
        assert "src/app.py" in files
        assert not any(".venv" in f for f in files)

    def test_excludes_node_modules(self, tmp_path):
        """Files inside node_modules directories are excluded."""
        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        (tmp_path / "node_modules" / "pkg" / "index.js").write_text(
            "module.exports = {}"
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.ts").write_text("export const x = 1;")

        files = discover_source_files(tmp_path)
        assert "src/main.ts" in files
        assert not any("node_modules" in f for f in files)

    def test_custom_extensions(self, tmp_path):
        """Custom extensions parameter restricts which files are discovered."""
        (tmp_path / "data.csv").write_text("a,b,c")
        (tmp_path / "app.py").write_text("pass")
        (tmp_path / "config.yaml").write_text("key: val")

        files = discover_source_files(tmp_path, extensions={".csv", ".yaml"})
        assert "data.csv" in files
        assert "config.yaml" in files
        assert "app.py" not in files

    def test_exclude_patterns(self, tmp_path):
        """User-specified exclude patterns filter out matching files."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("pass")
        (tmp_path / "src" / "generated.py").write_text("# auto-generated")
        (tmp_path / "vendor").mkdir()
        (tmp_path / "vendor" / "lib.py").write_text("pass")

        files = discover_source_files(
            tmp_path, exclude_patterns={"vendor/*", "src/generated.py"}
        )
        assert "src/app.py" in files
        assert "vendor/lib.py" not in files
        assert "src/generated.py" not in files

    def test_empty_directory(self, tmp_path):
        """Empty directory returns an empty list."""
        files = discover_source_files(tmp_path)
        assert files == []

    def test_returns_sorted_list(self, tmp_path):
        """Returned file list is sorted alphabetically."""
        (tmp_path / "z_module.py").write_text("pass")
        (tmp_path / "a_module.py").write_text("pass")
        (tmp_path / "m_module.py").write_text("pass")

        files = discover_source_files(tmp_path)
        assert files == sorted(files)

    def test_excludes_pycache(self, tmp_path):
        """Files inside __pycache__ directories are excluded."""
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "module.cpython-311.pyc").write_text("")
        (tmp_path / "module.py").write_text("pass")

        files = discover_source_files(tmp_path)
        assert "module.py" in files
        assert not any("__pycache__" in f for f in files)

    def test_excludes_htmlcov_directory(self, tmp_path):
        """Generated coverage HTML assets are excluded."""
        (tmp_path / "htmlcov").mkdir()
        (tmp_path / "htmlcov" / "coverage_html_cb_dd2e7eb5.js").write_text("")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("pass")

        files = discover_source_files(tmp_path)
        assert "src/app.py" in files
        assert not any("htmlcov" in f for f in files)

    def test_excludes_tooling_directories(self, tmp_path):
        """Example and maintenance script directories are excluded."""
        (tmp_path / "examples").mkdir()
        (tmp_path / "examples" / "demo.py").write_text("def demo(): pass")
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "maintenance.py").write_text("def run(): pass")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("pass")

        files = discover_source_files(tmp_path)
        assert "src/app.py" in files
        assert "examples/demo.py" not in files
        assert "scripts/maintenance.py" not in files

    def test_excludes_marker_init_files(self, tmp_path):
        """Empty and docstring-only package markers are excluded."""
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text('"""Package marker."""\n')
        (tmp_path / "pkg" / "api.py").write_text("def run(): pass")

        files = discover_source_files(tmp_path)
        assert "pkg/api.py" in files
        assert "pkg/__init__.py" not in files

    def test_keeps_runtime_init_files(self, tmp_path):
        """Package init files with runtime API remain discoverable."""
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text(
            "from .api import run\n__all__ = ['run']\n"
        )
        (tmp_path / "pkg" / "api.py").write_text("def run(): pass")

        files = discover_source_files(tmp_path)
        assert "pkg/__init__.py" in files

    def test_respects_gitignore_when_requested(self, tmp_path):
        """Gitignored source files are excluded when respect_gitignore=True."""
        import subprocess

        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        (tmp_path / ".gitignore").write_text("generated.py\n")
        (tmp_path / "generated.py").write_text("pass")
        (tmp_path / "tracked.py").write_text("pass")

        files = discover_source_files(tmp_path, respect_gitignore=True)
        assert "tracked.py" in files
        assert "generated.py" not in files


class TestIsTestFile:
    """Tests for is_test_file function."""

    def test_python_test_prefix(self):
        """test_foo.py is recognized as a test file."""
        assert is_test_file("test_foo.py") is True

    def test_python_test_prefix_in_path(self):
        """tests/core/test_validate.py is recognized as a test file."""
        assert is_test_file("tests/core/test_validate.py") is True

    def test_python_test_suffix(self):
        """foo_test.py is recognized as a test file."""
        assert is_test_file("foo_test.py") is True

    def test_ts_test_file(self):
        """foo.test.ts is recognized as a test file."""
        assert is_test_file("foo.test.ts") is True

    def test_ts_spec_file(self):
        """foo.spec.tsx is recognized as a test file."""
        assert is_test_file("foo.spec.tsx") is True

    def test_js_test_file(self):
        """bar.test.js is recognized as a test file."""
        assert is_test_file("bar.test.js") is True

    def test_js_spec_file(self):
        """bar.spec.jsx is recognized as a test file."""
        assert is_test_file("bar.spec.jsx") is True

    def test_regular_python_file(self):
        """foo.py is NOT a test file."""
        assert is_test_file("foo.py") is False

    def test_regular_ts_file(self):
        """utils.ts is NOT a test file."""
        assert is_test_file("utils.ts") is False

    def test_conftest_is_test_support(self):
        """conftest.py is recognized as test support."""
        assert is_test_file("conftest.py") is True

    def test_path_with_test_directory(self):
        """conftest.py under tests/ is recognized as test support."""
        assert is_test_file("tests/conftest.py") is True


class TestFindTestFilesFromManifest:
    """Tests for find_test_files_from_manifest function."""

    def test_extracts_test_files_from_read(self):
        """Test files in files_read are extracted."""
        manifest_data = {
            "files_read": [
                "tests/test_auth.py",
                "tests/test_user.py",
            ],
        }
        result = find_test_files_from_manifest(manifest_data)
        assert "tests/test_auth.py" in result
        assert "tests/test_user.py" in result

    def test_ignores_non_test_files(self):
        """Non-test files in files_read are not included."""
        manifest_data = {
            "files_read": [
                "tests/test_auth.py",
                "src/auth.py",
                "conftest.py",
            ],
        }
        result = find_test_files_from_manifest(manifest_data)
        assert "tests/test_auth.py" in result
        assert "src/auth.py" not in result
        assert "conftest.py" in result

    def test_empty_manifest(self):
        """Manifest with no files_read returns empty list."""
        manifest_data = {}
        result = find_test_files_from_manifest(manifest_data)
        assert result == []

    def test_empty_files_read(self):
        """Manifest with empty files_read list returns empty list."""
        manifest_data = {"files_read": []}
        result = find_test_files_from_manifest(manifest_data)
        assert result == []

    def test_mixed_test_patterns(self):
        """Various test file patterns are all extracted."""
        manifest_data = {
            "files_read": [
                "tests/test_core.py",
                "tests/auth_test.py",
                "tests/login.test.ts",
                "tests/signup.spec.tsx",
                "src/utils.py",
            ],
        }
        result = find_test_files_from_manifest(manifest_data)
        assert len(result) == 4
        assert "src/utils.py" not in result
