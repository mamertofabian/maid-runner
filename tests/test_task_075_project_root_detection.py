"""Behavioral tests for Task-075: Smart Project Root Detection.

These tests verify that the find_project_root() utility function correctly
detects project root directories by finding marker files/directories.

Test categories:
1. PROJECT_ROOT_MARKERS constant exists with expected values
2. find_project_root() function signature and behavior
3. Walking up directory tree to find markers
4. Fallback to current working directory when no marker found
5. Edge cases (file as start_path, marker in same directory, etc.)
"""

from pathlib import Path


class TestProjectRootMarkers:
    """Tests for PROJECT_ROOT_MARKERS constant."""

    def test_project_root_markers_exists(self):
        """PROJECT_ROOT_MARKERS constant is defined in utils module."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert PROJECT_ROOT_MARKERS is not None
        assert isinstance(PROJECT_ROOT_MARKERS, tuple)

    def test_project_root_markers_contains_git(self):
        """PROJECT_ROOT_MARKERS includes .git directory."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert ".git" in PROJECT_ROOT_MARKERS

    def test_project_root_markers_contains_pyproject(self):
        """PROJECT_ROOT_MARKERS includes pyproject.toml."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert "pyproject.toml" in PROJECT_ROOT_MARKERS

    def test_project_root_markers_contains_package_json(self):
        """PROJECT_ROOT_MARKERS includes package.json for JS projects."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert "package.json" in PROJECT_ROOT_MARKERS

    def test_project_root_markers_contains_maid_directory(self):
        """PROJECT_ROOT_MARKERS includes .maid directory for MAID projects."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert ".maid" in PROJECT_ROOT_MARKERS

    def test_project_root_markers_contains_setup_py(self):
        """PROJECT_ROOT_MARKERS includes setup.py for legacy Python projects."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert "setup.py" in PROJECT_ROOT_MARKERS

    def test_project_root_markers_contains_cargo_toml(self):
        """PROJECT_ROOT_MARKERS includes Cargo.toml for Rust projects."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert "Cargo.toml" in PROJECT_ROOT_MARKERS

    def test_project_root_markers_contains_go_mod(self):
        """PROJECT_ROOT_MARKERS includes go.mod for Go projects."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert "go.mod" in PROJECT_ROOT_MARKERS

    def test_project_root_markers_is_non_empty(self):
        """PROJECT_ROOT_MARKERS contains at least one marker."""
        from maid_runner.utils import PROJECT_ROOT_MARKERS

        assert len(PROJECT_ROOT_MARKERS) > 0


class TestFindProjectRoot:
    """Tests for find_project_root() function."""

    def test_find_project_root_exists(self):
        """find_project_root function is defined in utils module."""
        from maid_runner.utils import find_project_root

        assert callable(find_project_root)

    def test_find_project_root_returns_path(self):
        """find_project_root returns a Path object."""
        from maid_runner.utils import find_project_root

        result = find_project_root(Path.cwd())
        assert isinstance(result, Path)

    def test_find_project_root_finds_git_directory(self, tmp_path):
        """find_project_root finds directory containing .git."""
        from maid_runner.utils import find_project_root

        # Create a nested directory structure with .git at root
        (tmp_path / ".git").mkdir()
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)

        result = find_project_root(nested)
        assert result == tmp_path

    def test_find_project_root_finds_pyproject_toml(self, tmp_path):
        """find_project_root finds directory containing pyproject.toml."""
        from maid_runner.utils import find_project_root

        # Create a nested directory structure with pyproject.toml at root
        (tmp_path / "pyproject.toml").touch()
        nested = tmp_path / "src" / "module"
        nested.mkdir(parents=True)

        result = find_project_root(nested)
        assert result == tmp_path

    def test_find_project_root_finds_maid_directory(self, tmp_path):
        """find_project_root finds directory containing .maid directory."""
        from maid_runner.utils import find_project_root

        # Create a nested directory structure with .maid at root
        (tmp_path / ".maid").mkdir()
        nested = tmp_path / "src" / "lib"
        nested.mkdir(parents=True)

        result = find_project_root(nested)
        assert result == tmp_path

    def test_find_project_root_finds_cargo_toml(self, tmp_path):
        """find_project_root finds directory containing Cargo.toml."""
        from maid_runner.utils import find_project_root

        # Create a nested directory structure with Cargo.toml at root
        (tmp_path / "Cargo.toml").touch()
        nested = tmp_path / "src" / "bin"
        nested.mkdir(parents=True)

        result = find_project_root(nested)
        assert result == tmp_path

    def test_find_project_root_finds_go_mod(self, tmp_path):
        """find_project_root finds directory containing go.mod."""
        from maid_runner.utils import find_project_root

        # Create a nested directory structure with go.mod at root
        (tmp_path / "go.mod").touch()
        nested = tmp_path / "cmd" / "myapp"
        nested.mkdir(parents=True)

        result = find_project_root(nested)
        assert result == tmp_path

    def test_find_project_root_fallback_to_parent(self, tmp_path):
        """find_project_root falls back to start_path's parent when no marker found."""
        from maid_runner.utils import find_project_root

        # Create an isolated directory with no markers
        isolated = tmp_path / "isolated" / "deep"
        isolated.mkdir(parents=True)

        result = find_project_root(isolated)
        # Should fall back to start_path's parent since no markers found
        # This preserves original behavior of manifests_dir.parent
        assert result == isolated.parent

    def test_find_project_root_accepts_custom_markers(self, tmp_path):
        """find_project_root accepts custom markers tuple."""
        from maid_runner.utils import find_project_root

        # Create a nested directory with custom marker
        (tmp_path / "CUSTOM_MARKER").touch()
        nested = tmp_path / "subdir"
        nested.mkdir()

        result = find_project_root(nested, markers=("CUSTOM_MARKER",))
        assert result == tmp_path

    def test_find_project_root_finds_closest_marker(self, tmp_path):
        """find_project_root returns the closest directory with a marker."""
        from maid_runner.utils import find_project_root

        # Create nested structure with markers at multiple levels
        (tmp_path / "pyproject.toml").touch()  # outer marker
        inner = tmp_path / "packages" / "subpackage"
        inner.mkdir(parents=True)
        (inner / "pyproject.toml").touch()  # inner marker (closer)

        deep = inner / "src" / "lib"
        deep.mkdir(parents=True)

        result = find_project_root(deep)
        # Should find the closest marker (inner), not the outer one
        assert result == inner

    def test_find_project_root_with_file_as_start_path(self, tmp_path):
        """find_project_root works when start_path is a file, not directory."""
        from maid_runner.utils import find_project_root

        # Create project structure
        (tmp_path / ".git").mkdir()
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        test_file = src_dir / "main.py"
        test_file.touch()

        # Start from a file path
        result = find_project_root(test_file)
        assert result == tmp_path

    def test_find_project_root_marker_in_start_directory(self, tmp_path):
        """find_project_root finds marker in the starting directory itself."""
        from maid_runner.utils import find_project_root

        # Create marker in tmp_path
        (tmp_path / "pyproject.toml").touch()

        # Start from the directory containing the marker
        result = find_project_root(tmp_path)
        assert result == tmp_path

    def test_find_project_root_returns_resolved_path(self, tmp_path):
        """find_project_root returns an absolute/resolved path."""
        from maid_runner.utils import find_project_root

        (tmp_path / ".git").mkdir()
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)

        result = find_project_root(nested)
        assert result.is_absolute()

    def test_find_project_root_uses_default_markers(self, tmp_path):
        """find_project_root uses PROJECT_ROOT_MARKERS by default."""
        from maid_runner.utils import find_project_root, PROJECT_ROOT_MARKERS

        # Create one of the default markers
        marker = PROJECT_ROOT_MARKERS[0]  # Use the first default marker
        if (
            marker.endswith(".toml")
            or marker.endswith(".json")
            or "." in marker
            and not marker.startswith(".")
        ):
            (tmp_path / marker).touch()
        else:
            (tmp_path / marker).mkdir()

        nested = tmp_path / "subdir"
        nested.mkdir()

        # Call without specifying markers (should use default)
        result = find_project_root(nested)
        assert result == tmp_path

    def test_find_project_root_empty_markers_fallback(self, tmp_path):
        """find_project_root with empty markers tuple falls back to start_path's parent."""
        from maid_runner.utils import find_project_root

        # Create project structure (but use empty markers)
        (tmp_path / ".git").mkdir()
        nested = tmp_path / "subdir"
        nested.mkdir()

        # With empty markers, nothing should match, so fallback to parent
        result = find_project_root(nested, markers=())
        assert result == nested.parent
