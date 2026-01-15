"""Behavioral tests for Task-152d: Create init_tools/generic.py module.

Tests verify that:
1. setup_generic() function exists and creates MAID.md file
2. create_generic_maid_doc() creates MAID.md in project root
3. The MAID.md file contains MAID methodology content and is language-aware
"""

from maid_runner.cli.init_tools.generic import create_generic_maid_doc, setup_generic


class TestSetupGeneric:
    """Test setup_generic() function."""

    def test_setup_generic_creates_maid_md(self, tmp_path):
        """Verify setup_generic creates MAID.md file."""
        setup_generic(str(tmp_path), force=True, dry_run=False)

        assert (tmp_path / "MAID.md").exists()


class TestCreateGenericMaidDoc:
    """Test create_generic_maid_doc() function."""

    def test_creates_maid_md_file(self, tmp_path):
        """Verify generic setup creates MAID.md file in project root."""
        create_generic_maid_doc(str(tmp_path), force=True, dry_run=False)

        maid_md = tmp_path / "MAID.md"
        assert maid_md.exists()

    def test_maid_md_contains_maid_content(self, tmp_path):
        """Verify generic MAID.md contains MAID methodology content."""
        create_generic_maid_doc(str(tmp_path), force=True, dry_run=False)

        maid_md = tmp_path / "MAID.md"
        content = maid_md.read_text()

        assert "MAID Methodology" in content
        assert "Manifest-driven AI Development" in content

    def test_maid_md_is_language_aware(self, tmp_path):
        """Verify generic MAID.md adapts to project language."""
        # Create Python project marker
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        create_generic_maid_doc(str(tmp_path), force=True, dry_run=False)

        maid_md = tmp_path / "MAID.md"
        content = maid_md.read_text()

        # Should contain Python-specific content
        assert "pytest" in content or "Python" in content
