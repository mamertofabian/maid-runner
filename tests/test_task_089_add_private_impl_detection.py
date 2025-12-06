"""Behavioral tests for task-089: Add private implementation file detection.

These tests verify that private implementation files (starting with _) are
correctly detected and categorized separately from undeclared files.
"""

from maid_runner.validators.file_tracker import (
    FILE_STATUS_PRIVATE_IMPL,
    is_private_implementation_file,
    analyze_file_tracking,
    FileTrackingAnalysis,
)


class TestPrivateImplFileDetection:
    """Tests for is_private_implementation_file function."""

    def test_detects_private_python_file(self):
        """Private Python files starting with _ are detected."""
        assert is_private_implementation_file("src/_helpers.py") is True
        assert is_private_implementation_file("_validators.py") is True
        assert is_private_implementation_file("utils/_internal.py") is True

    def test_detects_private_typescript_file(self):
        """Private TypeScript files starting with _ are detected."""
        assert is_private_implementation_file("src/_utils.ts") is True
        assert is_private_implementation_file("_helpers.tsx") is True

    def test_detects_private_javascript_file(self):
        """Private JavaScript files starting with _ are detected."""
        assert is_private_implementation_file("src/_helpers.js") is True
        assert is_private_implementation_file("_utils.jsx") is True

    def test_detects_private_svelte_file(self):
        """Private Svelte files starting with _ are detected."""
        assert is_private_implementation_file("src/_Component.svelte") is True

    def test_ignores_init_file(self):
        """__init__.py is tracked normally, not considered private."""
        assert is_private_implementation_file("src/__init__.py") is False
        assert is_private_implementation_file("__init__.py") is False

    def test_ignores_public_files(self):
        """Public files (no _ prefix) are not considered private."""
        assert is_private_implementation_file("src/helpers.py") is False
        assert is_private_implementation_file("utils.ts") is False
        assert is_private_implementation_file("Component.svelte") is False

    def test_ignores_dunder_files(self):
        """Files with __ prefix that aren't __init__.py are considered private."""
        # __init__.py is special-cased
        assert is_private_implementation_file("__init__.py") is False
        # But other __ files are private (they start with _)
        assert is_private_implementation_file("__main__.py") is True

    def test_ignores_non_source_files(self):
        """Files with non-source extensions are not considered private impl."""
        assert is_private_implementation_file("_data.json") is False
        assert is_private_implementation_file("_config.yaml") is False
        assert is_private_implementation_file("_README.md") is False


class TestFileTrackingAnalysisType:
    """Tests for FileTrackingAnalysis TypedDict."""

    def test_has_private_impl_field(self):
        """FileTrackingAnalysis includes private_impl field."""
        # Verify the TypedDict class has the private_impl annotation
        assert hasattr(FileTrackingAnalysis, "__annotations__")
        assert "private_impl" in FileTrackingAnalysis.__annotations__

        # Also verify it works in practice
        analysis: FileTrackingAnalysis = {
            "undeclared": [],
            "registered": [],
            "tracked": [],
            "private_impl": [],
            "untracked_tests": [],
        }
        assert "private_impl" in analysis
        assert isinstance(analysis["private_impl"], list)


class TestAnalyzeFileTrackingWithPrivateFiles:
    """Tests for analyze_file_tracking with private implementation files."""

    def test_categorizes_private_files_separately(self, tmp_path):
        """Private implementation files are categorized as private_impl."""
        # Create source files
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        # Create a private helper file
        private_file = src_dir / "_helpers.py"
        private_file.write_text("def helper(): pass")

        # Create a public file
        public_file = src_dir / "main.py"
        public_file.write_text("def main(): pass")

        # Run analysis with no manifests
        analysis = analyze_file_tracking([], str(tmp_path))

        # Private file should be in private_impl
        assert "src/_helpers.py" in analysis["private_impl"]

        # Public file should be in undeclared
        undeclared_files = [f["file"] for f in analysis["undeclared"]]
        assert "src/main.py" in undeclared_files

    def test_private_files_not_in_undeclared(self, tmp_path):
        """Private files should NOT appear in undeclared list."""
        # Create source files
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        private_file = src_dir / "_internal.py"
        private_file.write_text("def internal(): pass")

        # Run analysis
        analysis = analyze_file_tracking([], str(tmp_path))

        # Check private file is NOT in undeclared
        undeclared_files = [f["file"] for f in analysis["undeclared"]]
        assert "src/_internal.py" not in undeclared_files

        # Check it IS in private_impl
        assert "src/_internal.py" in analysis["private_impl"]

    def test_init_file_tracked_normally(self, tmp_path):
        """__init__.py should be tracked normally, not as private."""
        # Create __init__.py
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        init_file = src_dir / "__init__.py"
        init_file.write_text("")

        # Run analysis
        analysis = analyze_file_tracking([], str(tmp_path))

        # __init__.py should be in undeclared (not private_impl)
        undeclared_files = [f["file"] for f in analysis["undeclared"]]
        assert "src/__init__.py" in undeclared_files

        # Should NOT be in private_impl
        assert "src/__init__.py" not in analysis["private_impl"]

    def test_multiple_private_file_types(self, tmp_path):
        """All source file types with _ prefix are detected as private."""
        # Create various private files
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        files = [
            "_helpers.py",
            "_utils.ts",
            "_component.tsx",
            "_lib.js",
            "_widget.jsx",
            "_Private.svelte",
        ]

        for filename in files:
            (src_dir / filename).write_text("// content")

        # Run analysis
        analysis = analyze_file_tracking([], str(tmp_path))

        # All should be in private_impl
        for filename in files:
            assert f"src/{filename}" in analysis["private_impl"]


class TestFileStatusConstant:
    """Tests for FILE_STATUS_PRIVATE_IMPL constant."""

    def test_constant_exists(self):
        """FILE_STATUS_PRIVATE_IMPL constant is defined."""
        assert FILE_STATUS_PRIVATE_IMPL is not None
        assert isinstance(FILE_STATUS_PRIVATE_IMPL, str)

    def test_constant_value(self):
        """FILE_STATUS_PRIVATE_IMPL has expected value."""
        assert FILE_STATUS_PRIVATE_IMPL == "PRIVATE_IMPL"
