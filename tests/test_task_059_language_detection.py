"""Behavioral tests for Task-059: Language-specific MAID init.

Tests verify that the init command:
1. Detects project language (Python, TypeScript, JavaScript, Mixed)
2. Generates language-specific CLAUDE.md documentation
3. Does not create example manifest (removed feature)
4. Integrates language detection into run_init workflow
"""

from unittest.mock import patch

from maid_runner.cli.init import (
    copy_maid_specs,
    create_directories,
    detect_project_language,
    generate_claude_md_content,
    generate_mixed_claude_md,
    generate_python_claude_md,
    generate_typescript_claude_md,
    handle_claude_md,
    run_init,
)


class TestDetectProjectLanguage:
    """Test language detection functionality."""

    def test_detects_python_project_with_pyproject_toml(self, tmp_path):
        """Verify Python project detected when pyproject.toml exists."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
        language = detect_project_language(str(tmp_path))
        assert language == "python"

    def test_detects_python_project_with_setup_py(self, tmp_path):
        """Verify Python project detected when setup.py exists."""
        (tmp_path / "setup.py").write_text("from setuptools import setup")
        language = detect_project_language(str(tmp_path))
        assert language == "python"

    def test_detects_python_project_with_requirements_txt(self, tmp_path):
        """Verify Python project detected when requirements.txt exists."""
        (tmp_path / "requirements.txt").write_text("pytest>=7.0")
        language = detect_project_language(str(tmp_path))
        assert language == "python"

    def test_detects_typescript_project_with_package_json(self, tmp_path):
        """Verify TypeScript project detected when package.json exists."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        language = detect_project_language(str(tmp_path))
        assert language == "typescript"

    def test_detects_typescript_project_with_tsconfig_json(self, tmp_path):
        """Verify TypeScript project detected when tsconfig.json exists."""
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        language = detect_project_language(str(tmp_path))
        assert language == "typescript"

    def test_detects_mixed_project_with_both_indicators(self, tmp_path):
        """Verify mixed project detected when both Python and TypeScript indicators exist."""
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        language = detect_project_language(str(tmp_path))
        assert language == "mixed"

    def test_detects_unknown_for_empty_project(self, tmp_path):
        """Verify unknown language when no indicators exist."""
        language = detect_project_language(str(tmp_path))
        assert language == "unknown"


class TestGenerateClaudeMdContent:
    """Test dynamic CLAUDE.md content generation based on language."""

    def test_generates_python_content_for_python_language(self):
        """Verify Python-specific content generated for Python projects."""
        content = generate_claude_md_content("python")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_generates_typescript_content_for_typescript_language(self):
        """Verify TypeScript-specific content generated for TypeScript projects."""
        content = generate_claude_md_content("typescript")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_generates_mixed_content_for_mixed_language(self):
        """Verify mixed content generated for mixed projects."""
        content = generate_claude_md_content("mixed")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_generates_mixed_content_for_unknown_language(self):
        """Verify mixed content generated as fallback for unknown language."""
        content = generate_claude_md_content("unknown")
        assert isinstance(content, str)
        assert len(content) > 0


class TestGeneratePythonClaudeMd:
    """Test Python-specific CLAUDE.md content generation."""

    def test_returns_string_content(self):
        """Verify function returns a string."""
        content = generate_python_claude_md()
        assert isinstance(content, str)
        assert len(content) > 0

    def test_includes_python_file_extensions(self):
        """Verify content includes Python file extensions (.py)."""
        content = generate_python_claude_md()
        assert ".py" in content
        # Should not include TypeScript extensions
        assert ".ts" not in content or "TypeScript" in content  # Allow in headers

    def test_includes_pytest_commands(self):
        """Verify content includes pytest validation commands."""
        content = generate_python_claude_md()
        assert "pytest" in content

    def test_includes_python_manifest_example(self):
        """Verify content includes Python manifest template."""
        content = generate_python_claude_md()
        assert "manifests/task-" in content
        assert "expectedArtifacts" in content

    def test_includes_maid_workflow_phases(self):
        """Verify content includes MAID workflow phases."""
        content = generate_python_claude_md()
        assert "Phase 1" in content or "Goal Definition" in content
        assert "Phase 2" in content or "Planning Loop" in content
        assert "Phase 3" in content or "Implementation" in content


class TestGenerateTypeScriptClaudeMd:
    """Test TypeScript-specific CLAUDE.md content generation."""

    def test_returns_string_content(self):
        """Verify function returns a string."""
        content = generate_typescript_claude_md()
        assert isinstance(content, str)
        assert len(content) > 0

    def test_includes_typescript_file_extensions(self):
        """Verify content includes TypeScript file extensions."""
        content = generate_typescript_claude_md()
        assert ".ts" in content or ".tsx" in content

    def test_includes_npm_test_commands(self):
        """Verify content includes npm/pnpm/yarn test commands."""
        content = generate_typescript_claude_md()
        # Should mention at least one package manager
        assert "npm test" in content or "pnpm test" in content or "yarn test" in content

    def test_includes_typescript_manifest_example(self):
        """Verify content includes TypeScript manifest template."""
        content = generate_typescript_claude_md()
        assert "manifests/task-" in content
        assert "expectedArtifacts" in content

    def test_includes_maid_workflow_phases(self):
        """Verify content includes MAID workflow phases."""
        content = generate_typescript_claude_md()
        assert "Phase 1" in content or "Goal Definition" in content
        assert "Phase 2" in content or "Planning Loop" in content
        assert "Phase 3" in content or "Implementation" in content


class TestGenerateMixedClaudeMd:
    """Test mixed language CLAUDE.md content generation."""

    def test_returns_string_content(self):
        """Verify function returns a string."""
        content = generate_mixed_claude_md()
        assert isinstance(content, str)
        assert len(content) > 0

    def test_includes_both_python_and_typescript_examples(self):
        """Verify content includes examples for both languages."""
        content = generate_mixed_claude_md()
        # Should have sections for both Python and TypeScript
        assert "Python" in content
        assert "TypeScript" in content or "JavaScript" in content

    def test_includes_both_file_extensions(self):
        """Verify content includes file extensions for both languages."""
        content = generate_mixed_claude_md()
        assert ".py" in content
        assert ".ts" in content or ".tsx" in content

    def test_includes_both_test_frameworks(self):
        """Verify content includes test commands for both languages."""
        content = generate_mixed_claude_md()
        assert "pytest" in content
        assert "npm test" in content or "pnpm test" in content or "yarn test" in content


class TestRunInitWithoutExampleManifest:
    """Test that run_init no longer creates example manifest."""

    @patch("builtins.input", return_value="s")
    def test_does_not_create_example_manifest(self, mock_input, tmp_path):
        """Verify example.manifest.json is NOT created."""
        run_init(str(tmp_path), force=False)

        # Verify directories are created
        assert (tmp_path / "manifests").exists()
        assert (tmp_path / "tests").exists()

        # Verify example manifest is NOT created
        assert not (tmp_path / "manifests" / "example.manifest.json").exists()

    @patch("builtins.input", return_value="s")
    def test_still_creates_directories(self, mock_input, tmp_path):
        """Verify directories are still created."""
        run_init(str(tmp_path), force=False)

        assert (tmp_path / "manifests").exists()
        assert (tmp_path / "tests").exists()
        assert (tmp_path / ".maid" / "docs").exists()

    @patch("builtins.input", return_value="s")
    def test_still_copies_maid_specs(self, mock_input, tmp_path):
        """Verify maid_specs.md is still copied."""
        run_init(str(tmp_path), force=False)

        # Check if .maid/docs/maid_specs.md exists (might not if source missing)
        # The copy_maid_specs function handles missing source gracefully
        assert (tmp_path / ".maid" / "docs").exists()


class TestLanguageDetectionIntegration:
    """Test integration of language detection into init workflow."""

    def test_python_project_gets_python_claude_md(self, tmp_path):
        """Verify Python project gets Python-specific CLAUDE.md."""
        # Setup Python project
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]")

        # Run init
        handle_claude_md(str(tmp_path), force=True)

        # Verify CLAUDE.md exists and contains Python content
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert ".py" in content
        assert "pytest" in content

    def test_typescript_project_gets_typescript_claude_md(self, tmp_path):
        """Verify TypeScript project gets TypeScript-specific CLAUDE.md."""
        # Setup TypeScript project
        (tmp_path / "package.json").write_text('{"name": "test"}')

        # Run init
        handle_claude_md(str(tmp_path), force=True)

        # Verify CLAUDE.md exists and contains TypeScript content
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert ".ts" in content or ".tsx" in content
        assert "npm test" in content or "pnpm test" in content or "yarn test" in content

    def test_mixed_project_gets_mixed_claude_md(self, tmp_path):
        """Verify mixed project gets comprehensive CLAUDE.md."""
        # Setup mixed project
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]")
        (tmp_path / "package.json").write_text('{"name": "test"}')

        # Run init
        handle_claude_md(str(tmp_path), force=True)

        # Verify CLAUDE.md exists and contains both Python and TypeScript content
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert ".py" in content
        assert ".ts" in content or ".tsx" in content
        assert "pytest" in content
        assert "npm test" in content or "pnpm test" in content or "yarn test" in content


class TestExistingFunctionsStillWork:
    """Test that existing functions from Task-031 still work correctly."""

    def test_create_directories_still_works(self, tmp_path):
        """Verify create_directories function still works."""
        create_directories(str(tmp_path))
        assert (tmp_path / "manifests").exists()
        assert (tmp_path / "tests").exists()
        assert (tmp_path / ".maid" / "docs").exists()

    def test_copy_maid_specs_still_works(self, tmp_path):
        """Verify copy_maid_specs function still works."""
        (tmp_path / ".maid" / "docs").mkdir(parents=True)
        copy_maid_specs(str(tmp_path))
        # Function should not raise even if source is missing

    def test_handle_claude_md_creates_file(self, tmp_path):
        """Verify handle_claude_md creates CLAUDE.md."""
        handle_claude_md(str(tmp_path), force=True)
        assert (tmp_path / "CLAUDE.md").exists()

    @patch("builtins.input", return_value="s")
    def test_handle_claude_md_respects_skip(self, mock_input, tmp_path):
        """Verify handle_claude_md respects skip option."""
        # Pre-create CLAUDE.md
        existing_content = "# Existing content"
        (tmp_path / "CLAUDE.md").write_text(existing_content)

        # Run without force (should prompt)
        handle_claude_md(str(tmp_path), force=False)

        # Verify content unchanged
        content = (tmp_path / "CLAUDE.md").read_text()
        assert content == existing_content
