"""Behavioral tests for task-068: Idempotent CLAUDE.md Handling.

These tests verify that the marker-based section management functions
correctly identify, wrap, and replace MAID documentation sections in CLAUDE.md,
enabling idempotent updates (re-running maid init does not create duplicates).
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

# Import the artifacts that will be implemented
from maid_runner.cli.init import (
    MAID_SECTION_START,
    MAID_SECTION_END,
    has_maid_markers,
    replace_maid_section,
    wrap_with_markers,
    generate_claude_md_content,
    handle_claude_md,
)


class TestMaidSectionMarkers:
    """Tests for the MAID_SECTION_START and MAID_SECTION_END constants."""

    def test_maid_section_start_is_string(self):
        """Test that MAID_SECTION_START is a string type."""
        assert isinstance(MAID_SECTION_START, str)

    def test_maid_section_end_is_string(self):
        """Test that MAID_SECTION_END is a string type."""
        assert isinstance(MAID_SECTION_END, str)

    def test_maid_section_start_contains_html_comment(self):
        """Test that MAID_SECTION_START contains HTML comment syntax."""
        assert "<!--" in MAID_SECTION_START
        assert "-->" in MAID_SECTION_START

    def test_maid_section_end_contains_html_comment(self):
        """Test that MAID_SECTION_END contains HTML comment syntax."""
        assert "<!--" in MAID_SECTION_END
        assert "-->" in MAID_SECTION_END

    def test_start_and_end_markers_are_different(self):
        """Test that start and end markers are distinct values."""
        assert MAID_SECTION_START != MAID_SECTION_END

    def test_markers_contain_identifying_text(self):
        """Test that markers contain text to identify them as MAID markers."""
        # Both markers should reference MAID to be identifiable
        start_lower = MAID_SECTION_START.lower()
        end_lower = MAID_SECTION_END.lower()
        assert "maid" in start_lower
        assert "maid" in end_lower


class TestHasMaidMarkers:
    """Tests for the has_maid_markers function."""

    def test_returns_true_when_both_markers_present(self):
        """Test returns True when both start and end markers are present."""
        content = (
            f"Header\n{MAID_SECTION_START}\nMAID content\n{MAID_SECTION_END}\nFooter"
        )
        result = has_maid_markers(content)
        assert result is True

    def test_returns_false_when_only_start_marker_present(self):
        """Test returns False when only start marker is present."""
        content = f"Header\n{MAID_SECTION_START}\nContent without end marker"
        result = has_maid_markers(content)
        assert result is False

    def test_returns_false_when_only_end_marker_present(self):
        """Test returns False when only end marker is present."""
        content = f"Content without start marker\n{MAID_SECTION_END}\nFooter"
        result = has_maid_markers(content)
        assert result is False

    def test_returns_false_when_neither_marker_present(self):
        """Test returns False when neither marker is present."""
        content = "Just some regular content\nNo markers here"
        result = has_maid_markers(content)
        assert result is False

    def test_returns_false_for_empty_string(self):
        """Test returns False for empty string input."""
        result = has_maid_markers("")
        assert result is False

    def test_returns_true_with_markers_in_middle(self):
        """Test returns True when markers are in the middle of content."""
        content = (
            "# Project README\n\n"
            "Some existing documentation.\n\n"
            f"{MAID_SECTION_START}\n"
            "MAID docs here\n"
            f"{MAID_SECTION_END}\n\n"
            "More existing content."
        )
        result = has_maid_markers(content)
        assert result is True


class TestMalformedMarkers:
    """Tests for handling malformed MAID marker scenarios."""

    def test_reversed_markers_returns_original(self):
        """Test that reversed markers (END before START) returns original content."""
        # Malformed: END marker appears before START marker
        malformed = f"Header\n{MAID_SECTION_END}\nContent\n{MAID_SECTION_START}\nFooter"

        result = replace_maid_section(malformed, "New content")

        # Should return original unchanged - don't try to "fix" malformed content
        assert result == malformed

    def test_reversed_markers_detected_by_has_maid_markers(self):
        """Test that has_maid_markers returns True for reversed markers (both present)."""
        malformed = f"{MAID_SECTION_END}\n{MAID_SECTION_START}"

        # Both markers ARE present, so this returns True
        # The replace function handles the reversed case separately
        result = has_maid_markers(malformed)
        assert result is True

    def test_multiple_start_markers_uses_first(self):
        """Test behavior with multiple start markers."""
        content = (
            f"Header\n"
            f"{MAID_SECTION_START}\nFirst section\n{MAID_SECTION_END}\n"
            f"Middle\n"
            f"{MAID_SECTION_START}\nSecond section\n{MAID_SECTION_END}\n"
            f"Footer"
        )

        result = replace_maid_section(content, "Replaced")

        # Should replace the first complete section
        assert "Header" in result
        assert "Replaced" in result
        # Second section markers may or may not be preserved depending on implementation
        # The key is it doesn't crash and produces valid output
        assert has_maid_markers(result)

    def test_nested_markers_handled_gracefully(self):
        """Test that nested markers don't cause errors."""
        # Pathological case: markers inside markers
        nested = (
            f"Header\n"
            f"{MAID_SECTION_START}\n"
            f"Content with {MAID_SECTION_START} inside\n"
            f"{MAID_SECTION_END}\n"
            f"Footer"
        )

        # Should not raise an exception
        result = replace_maid_section(nested, "New content")

        assert isinstance(result, str)
        assert has_maid_markers(result)


class TestReplaceMaidSection:
    """Tests for the replace_maid_section function."""

    def test_replaces_content_between_markers(self):
        """Test that content between markers is replaced with new content."""
        existing = (
            f"Header\n{MAID_SECTION_START}\nOld content\n{MAID_SECTION_END}\nFooter"
        )
        new_maid_content = "New MAID content"

        result = replace_maid_section(existing, new_maid_content)

        assert "New MAID content" in result
        assert "Old content" not in result

    def test_preserves_content_before_start_marker(self):
        """Test that content before the start marker is preserved."""
        existing = f"Header content\nMore header\n{MAID_SECTION_START}\nOld\n{MAID_SECTION_END}\nFooter"
        new_maid_content = "New MAID"

        result = replace_maid_section(existing, new_maid_content)

        assert "Header content" in result
        assert "More header" in result

    def test_preserves_content_after_end_marker(self):
        """Test that content after the end marker is preserved."""
        existing = f"Header\n{MAID_SECTION_START}\nOld\n{MAID_SECTION_END}\nFooter content\nMore footer"
        new_maid_content = "New MAID"

        result = replace_maid_section(existing, new_maid_content)

        assert "Footer content" in result
        assert "More footer" in result

    def test_handles_empty_content_between_markers(self):
        """Test replacement when there is no content between markers."""
        existing = f"Header\n{MAID_SECTION_START}{MAID_SECTION_END}\nFooter"
        new_maid_content = "New content"

        result = replace_maid_section(existing, new_maid_content)

        assert "New content" in result
        assert "Header" in result
        assert "Footer" in result

    def test_returns_original_when_no_markers(self):
        """Test that original content is returned when markers not found."""
        existing = "Content without any markers"
        new_maid_content = "New MAID content"

        result = replace_maid_section(existing, new_maid_content)

        # When markers are not found, should return original unchanged
        assert result == existing

    def test_result_contains_markers_around_new_content(self):
        """Test that result contains markers wrapping the new content."""
        existing = (
            f"Header\n{MAID_SECTION_START}\nOld content\n{MAID_SECTION_END}\nFooter"
        )
        new_maid_content = "Replaced MAID docs"

        result = replace_maid_section(existing, new_maid_content)

        assert MAID_SECTION_START in result
        assert MAID_SECTION_END in result
        # Verify correct order: start -> content -> end
        start_pos = result.find(MAID_SECTION_START)
        content_pos = result.find("Replaced MAID docs")
        end_pos = result.find(MAID_SECTION_END)
        assert start_pos < content_pos < end_pos

    def test_handles_multiline_replacement(self):
        """Test replacement with multiline new content."""
        existing = f"Header\n{MAID_SECTION_START}\nOld\n{MAID_SECTION_END}\nFooter"
        new_maid_content = "Line 1\nLine 2\nLine 3"

        result = replace_maid_section(existing, new_maid_content)

        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result


class TestWrapWithMarkers:
    """Tests for the wrap_with_markers function."""

    def test_wraps_content_with_start_marker(self):
        """Test that content is wrapped with start marker at beginning."""
        content = "MAID documentation"

        result = wrap_with_markers(content)

        assert result.startswith(MAID_SECTION_START) or MAID_SECTION_START in result
        # Start marker should come before the content
        start_pos = result.find(MAID_SECTION_START)
        content_pos = result.find("MAID documentation")
        assert start_pos < content_pos

    def test_wraps_content_with_end_marker(self):
        """Test that content is wrapped with end marker at end."""
        content = "MAID documentation"

        result = wrap_with_markers(content)

        assert result.endswith(MAID_SECTION_END) or MAID_SECTION_END in result
        # End marker should come after the content
        content_pos = result.find("MAID documentation")
        end_pos = result.find(MAID_SECTION_END)
        assert content_pos < end_pos

    def test_preserves_original_content(self):
        """Test that original content is preserved between markers."""
        content = "This is the MAID docs content"

        result = wrap_with_markers(content)

        assert "This is the MAID docs content" in result

    def test_handles_empty_content(self):
        """Test wrapping empty string produces markers only."""
        result = wrap_with_markers("")

        assert MAID_SECTION_START in result
        assert MAID_SECTION_END in result
        # Verify order
        start_pos = result.find(MAID_SECTION_START)
        end_pos = result.find(MAID_SECTION_END)
        assert start_pos < end_pos

    def test_handles_content_with_newlines(self):
        """Test wrapping content that contains multiple lines."""
        content = "Line 1\nLine 2\nLine 3"

        result = wrap_with_markers(content)

        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result
        assert MAID_SECTION_START in result
        assert MAID_SECTION_END in result

    def test_wrapped_content_has_correct_structure(self):
        """Test that wrapped content has start -> content -> end structure."""
        content = "Middle content"

        result = wrap_with_markers(content)

        start_pos = result.find(MAID_SECTION_START)
        content_pos = result.find("Middle content")
        end_pos = result.find(MAID_SECTION_END)

        assert start_pos != -1, "Start marker not found"
        assert content_pos != -1, "Content not found"
        assert end_pos != -1, "End marker not found"
        assert start_pos < content_pos < end_pos

    def test_wrapped_content_can_be_detected_by_has_maid_markers(self):
        """Test that wrapped content can be detected by has_maid_markers."""
        content = "Some MAID docs"

        wrapped = wrap_with_markers(content)

        assert has_maid_markers(wrapped) is True


class TestIntegrationScenarios:
    """Integration tests for marker-based section management."""

    def test_wrap_then_replace_produces_correct_result(self):
        """Test that wrapping then replacing works correctly."""
        original_maid = "Original MAID documentation"
        wrapped = wrap_with_markers(original_maid)

        # Simulate full document with other content
        full_doc = f"# My Project\n\n{wrapped}\n\n## Other Section"

        # Replace with new content
        new_maid = "Updated MAID documentation"
        result = replace_maid_section(full_doc, new_maid)

        assert "# My Project" in result
        assert "Updated MAID documentation" in result
        assert "Original MAID documentation" not in result
        assert "## Other Section" in result

    def test_idempotent_replacement(self):
        """Test that multiple replacements produce consistent results."""
        initial_content = "# Project\n\nExisting docs."
        maid_docs = "MAID workflow documentation"

        # First wrap and add to doc
        wrapped = wrap_with_markers(maid_docs)
        doc_with_maid = f"{initial_content}\n\n{wrapped}"

        # Second replacement should produce same result
        result1 = replace_maid_section(doc_with_maid, maid_docs)
        result2 = replace_maid_section(result1, maid_docs)

        # Results should be identical (idempotent)
        assert result1 == result2

    def test_replace_preserves_surrounding_markdown(self):
        """Test that replacement preserves complex surrounding markdown."""
        header = "# My Project\n\n[![Build Status](badge-url)](link)\n\n"
        footer = "\n\n## Installation\n\n```bash\nnpm install\n```\n"
        maid_section = f"{MAID_SECTION_START}\nOld MAID docs\n{MAID_SECTION_END}"

        full_doc = f"{header}{maid_section}{footer}"

        result = replace_maid_section(full_doc, "New MAID docs")

        assert "# My Project" in result
        assert "[![Build Status](badge-url)](link)" in result
        assert "## Installation" in result
        assert "```bash" in result
        assert "npm install" in result


class TestGenerateClaudeMdContent:
    """Tests for generate_claude_md_content returning content with markers."""

    def test_python_content_includes_markers(self):
        """Test that Python CLAUDE.md content includes MAID markers."""
        content = generate_claude_md_content("python")

        assert has_maid_markers(content), "Generated content should have MAID markers"
        assert MAID_SECTION_START in content
        assert MAID_SECTION_END in content

    def test_typescript_content_includes_markers(self):
        """Test that TypeScript CLAUDE.md content includes MAID markers."""
        content = generate_claude_md_content("typescript")

        assert has_maid_markers(content), "Generated content should have MAID markers"
        assert MAID_SECTION_START in content
        assert MAID_SECTION_END in content

    def test_mixed_content_includes_markers(self):
        """Test that mixed language CLAUDE.md content includes MAID markers."""
        content = generate_claude_md_content("mixed")

        assert has_maid_markers(content), "Generated content should have MAID markers"
        assert MAID_SECTION_START in content
        assert MAID_SECTION_END in content

    def test_unknown_content_includes_markers(self):
        """Test that unknown language CLAUDE.md content includes MAID markers."""
        content = generate_claude_md_content("unknown")

        assert has_maid_markers(content), "Generated content should have MAID markers"
        assert MAID_SECTION_START in content
        assert MAID_SECTION_END in content

    def test_content_has_maid_methodology_text(self):
        """Test that generated content contains MAID methodology information."""
        content = generate_claude_md_content("python")

        assert "MAID" in content
        assert "Methodology" in content or "methodology" in content


class TestHandleClaudeMdIntegration:
    """Integration tests for handle_claude_md with marker-based section management."""

    def test_creates_new_file_with_markers(self):
        """Test that creating a new CLAUDE.md includes markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            handle_claude_md(tmpdir, force=True)

            claude_md_path = Path(tmpdir) / "CLAUDE.md"
            assert claude_md_path.exists(), "CLAUDE.md should be created"

            content = claude_md_path.read_text()
            assert has_maid_markers(content), "New CLAUDE.md should have markers"

    def test_replaces_section_when_markers_exist(self):
        """Test that handle_claude_md replaces section when markers exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_md_path = Path(tmpdir) / "CLAUDE.md"

            # Create existing file with markers and custom content
            existing_content = (
                "# My Custom Header\n\n"
                f"{MAID_SECTION_START}\n"
                "Old MAID content that should be replaced\n"
                f"{MAID_SECTION_END}\n\n"
                "## My Custom Footer"
            )
            claude_md_path.write_text(existing_content)

            # Run handle_claude_md - should auto-replace without prompting
            handle_claude_md(tmpdir, force=False)

            result = claude_md_path.read_text()

            # Custom content preserved
            assert "# My Custom Header" in result
            assert "## My Custom Footer" in result

            # Old MAID content replaced
            assert "Old MAID content that should be replaced" not in result

            # Has markers and new content
            assert has_maid_markers(result)
            assert "MAID" in result

    def test_idempotent_multiple_runs(self):
        """Test that running handle_claude_md multiple times is idempotent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First run - creates file
            handle_claude_md(tmpdir, force=True)
            claude_md_path = Path(tmpdir) / "CLAUDE.md"
            content_after_first = claude_md_path.read_text()

            # Second run - should produce identical result
            handle_claude_md(tmpdir, force=False)
            content_after_second = claude_md_path.read_text()

            # Third run - still identical
            handle_claude_md(tmpdir, force=False)
            content_after_third = claude_md_path.read_text()

            assert content_after_first == content_after_second
            assert content_after_second == content_after_third

    def test_no_duplicate_markers_after_multiple_runs(self):
        """Test that multiple runs don't create duplicate markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Run multiple times
            for _ in range(3):
                handle_claude_md(tmpdir, force=True)

            content = (Path(tmpdir) / "CLAUDE.md").read_text()

            # Should have exactly one pair of markers
            start_count = content.count(MAID_SECTION_START)
            end_count = content.count(MAID_SECTION_END)

            assert start_count == 1, f"Expected 1 start marker, found {start_count}"
            assert end_count == 1, f"Expected 1 end marker, found {end_count}"

    def test_prompts_when_no_markers_exist(self):
        """Test that handle_claude_md prompts when file exists without markers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            claude_md_path = Path(tmpdir) / "CLAUDE.md"

            # Create existing file WITHOUT markers
            existing_content = "# Existing Project Docs\n\nNo MAID markers here."
            claude_md_path.write_text(existing_content)

            # Mock input to simulate user choosing 'skip'
            with patch("builtins.input", return_value="s"):
                handle_claude_md(tmpdir, force=False)

            # File should be unchanged (user chose skip)
            result = claude_md_path.read_text()
            assert result == existing_content
