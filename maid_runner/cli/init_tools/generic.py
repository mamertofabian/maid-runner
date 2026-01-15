"""Generic tool setup for MAID init.

This module handles creating a generic MAID.md file for projects
that don't use a specific AI dev tool.
"""

from pathlib import Path

from maid_runner.cli.init import (
    detect_project_language,
    generate_claude_md_content,
)


def setup_generic(target_dir: str, force: bool, dry_run: bool = False) -> None:
    """Set up generic MAID.md file in target directory.

    Args:
        target_dir: Target directory to initialize MAID in
        force: If True, overwrite files without prompting
        dry_run: If True, show what would be created without making changes
    """
    create_generic_maid_doc(target_dir, force, dry_run)


def create_generic_maid_doc(
    target_dir: str, force: bool, dry_run: bool = False
) -> None:
    """Create generic MAID.md documentation file.

    Args:
        target_dir: Target directory to create MAID.md in
        force: If True, overwrite existing file without prompting
        dry_run: If True, show what would be created without making changes
    """
    maid_md = Path(target_dir) / "MAID.md"

    if dry_run:
        action = "[UPDATE]" if maid_md.exists() else "[CREATE]"
        print(f"{action} {maid_md}")
        return

    # Check if file exists and handle overwrite
    if maid_md.exists() and not force:
        print(f"⚠️  {maid_md} already exists. Use --force to overwrite.")
        return

    # Generate content
    language = detect_project_language(target_dir)
    maid_content = _generate_generic_maid_content(language)

    # Write file
    maid_md.write_text(maid_content)
    print(f"✓ Created generic MAID.md: {maid_md}")


def _generate_generic_maid_content(language: str) -> str:
    """Generate generic MAID.md file content.

    Args:
        language: Project language ("python", "typescript", "mixed", or "unknown")

    Returns:
        String containing MAID.md file content with MAID documentation
    """
    # Generate MAID content (same as CLAUDE.md but without markers)
    maid_content = generate_claude_md_content(language)
    # Remove markers if present
    maid_content = maid_content.replace("<!-- MAID-SECTION-START -->", "")
    maid_content = maid_content.replace("<!-- MAID-SECTION-END -->", "")
    maid_content = maid_content.strip()

    return maid_content
