# tests/test_task_072_file_tracking_multi_language.py
"""Tests for multi-language file tracking support."""
from pathlib import Path
from maid_runner.validators.file_tracker import (
    DEFAULT_EXCLUDE_PATTERNS,
    DEFAULT_SOURCE_EXTENSIONS,
    find_source_files,
)


# ============================================================================
# Test Default Constants
# ============================================================================


def test_default_exclude_patterns_includes_node_modules():
    """Test that DEFAULT_EXCLUDE_PATTERNS includes node_modules."""
    assert any("node_modules" in pattern for pattern in DEFAULT_EXCLUDE_PATTERNS)


def test_default_exclude_patterns_includes_common_patterns():
    """Test that DEFAULT_EXCLUDE_PATTERNS includes common dev directories."""
    patterns_str = str(DEFAULT_EXCLUDE_PATTERNS)
    assert "__pycache__" in patterns_str
    assert ".venv" in patterns_str or "venv" in patterns_str
    assert ".git" in patterns_str


def test_default_source_extensions_includes_python():
    """Test that DEFAULT_SOURCE_EXTENSIONS includes Python files."""
    assert ".py" in DEFAULT_SOURCE_EXTENSIONS


def test_default_source_extensions_includes_typescript():
    """Test that DEFAULT_SOURCE_EXTENSIONS includes TypeScript files."""
    assert ".ts" in DEFAULT_SOURCE_EXTENSIONS
    assert ".tsx" in DEFAULT_SOURCE_EXTENSIONS


def test_default_source_extensions_includes_javascript():
    """Test that DEFAULT_SOURCE_EXTENSIONS includes JavaScript files."""
    assert ".js" in DEFAULT_SOURCE_EXTENSIONS
    assert ".jsx" in DEFAULT_SOURCE_EXTENSIONS


# ============================================================================
# Test find_source_files with Multiple Extensions
# ============================================================================


def test_find_source_files_discovers_typescript_files(tmp_path: Path):
    """Test that find_source_files discovers TypeScript files."""
    # Create test files
    (tmp_path / "component.ts").write_text("// typescript")
    (tmp_path / "component.tsx").write_text("// tsx component")
    (tmp_path / "module.py").write_text("# python")

    files = find_source_files(str(tmp_path), exclude_patterns=[])

    assert "component.ts" in files
    assert "component.tsx" in files
    assert "module.py" in files


def test_find_source_files_discovers_javascript_files(tmp_path: Path):
    """Test that find_source_files discovers JavaScript files."""
    # Create test files
    (tmp_path / "app.js").write_text("// javascript")
    (tmp_path / "component.jsx").write_text("// jsx component")

    files = find_source_files(str(tmp_path), exclude_patterns=[])

    assert "app.js" in files
    assert "component.jsx" in files


def test_find_source_files_excludes_node_modules(tmp_path: Path):
    """Test that find_source_files excludes node_modules by default."""
    # Create test structure
    (tmp_path / "app.ts").write_text("// app")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lodash").mkdir(parents=True)
    (tmp_path / "node_modules" / "lodash" / "index.js").write_text("// lodash")
    # Nested node_modules (like in pnpm)
    (tmp_path / "node_modules" / ".pnpm").mkdir()
    (tmp_path / "node_modules" / ".pnpm" / "flatted@3.3.3").mkdir(parents=True)
    (tmp_path / "node_modules" / ".pnpm" / "flatted@3.3.3" / "flatted.py").write_text(
        "# py"
    )

    files = find_source_files(str(tmp_path), exclude_patterns=["node_modules/**"])

    assert "app.ts" in files
    assert "node_modules/lodash/index.js" not in files
    assert "node_modules/.pnpm/flatted@3.3.3/flatted.py" not in files


def test_find_source_files_with_custom_extensions(tmp_path: Path):
    """Test that find_source_files can use custom extensions."""
    # Create test files
    (tmp_path / "script.py").write_text("# python")
    (tmp_path / "app.ts").write_text("// typescript")
    (tmp_path / "style.css").write_text("/* css */")

    # Only search for Python files
    files = find_source_files(str(tmp_path), exclude_patterns=[], extensions=[".py"])

    assert "script.py" in files
    assert "app.ts" not in files
    assert "style.css" not in files


def test_find_source_files_uses_default_extensions_when_none(tmp_path: Path):
    """Test that find_source_files uses DEFAULT_SOURCE_EXTENSIONS when extensions=None."""
    # Create test files of various types
    (tmp_path / "module.py").write_text("# python")
    (tmp_path / "component.tsx").write_text("// tsx")
    (tmp_path / "config.json").write_text("{}")

    files = find_source_files(str(tmp_path), exclude_patterns=[], extensions=None)

    assert "module.py" in files
    assert "component.tsx" in files
    assert "config.json" not in files  # JSON not in default extensions


def test_find_source_files_nested_typescript_project(tmp_path: Path):
    """Test file discovery in a nested TypeScript project structure."""
    # Create a typical React/TypeScript project structure
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.tsx").write_text("// entry")
    (src / "App.tsx").write_text("// app")
    components = src / "components"
    components.mkdir()
    (components / "Button.tsx").write_text("// button")
    (components / "Button.test.tsx").write_text("// test")

    files = find_source_files(str(tmp_path), exclude_patterns=[])

    assert "src/index.tsx" in files
    assert "src/App.tsx" in files
    assert "src/components/Button.tsx" in files
    assert "src/components/Button.test.tsx" in files
