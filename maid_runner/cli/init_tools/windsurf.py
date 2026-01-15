"""Windsurf IDE tool setup for MAID init.

This module handles setting up Windsurf IDE integration by creating
.windsurf/rules/ directory with MAID methodology rule file.
"""

from pathlib import Path

from maid_runner.cli.init import (
    detect_project_language,
    generate_claude_md_content,
)


def setup_windsurf(target_dir: str, force: bool, dry_run: bool = False) -> None:
    """Set up Windsurf IDE integration in target directory.

    Args:
        target_dir: Target directory to initialize MAID in
        force: If True, overwrite files without prompting
        dry_run: If True, show what would be created without making changes
    """
    create_windsurf_rules(target_dir, force, dry_run)


def create_windsurf_rules(target_dir: str, force: bool, dry_run: bool = False) -> None:
    """Create Windsurf IDE rules directory and MAID rule file.

    Args:
        target_dir: Target directory to create rules in
        force: If True, overwrite existing files without prompting
        dry_run: If True, show what would be created without making changes
    """
    rules_dir = Path(target_dir) / ".windsurf" / "rules"
    rule_file = rules_dir / "maid-runner.md"

    if dry_run:
        action = "[UPDATE]" if rule_file.exists() else "[CREATE]"
        print(f"{action} {rule_file}")
        return

    # Create directory
    rules_dir.mkdir(parents=True, exist_ok=True)

    # Check if file exists and handle overwrite
    if rule_file.exists() and not force:
        print(f"⚠️  {rule_file} already exists. Use --force to overwrite.")
        return

    # Generate content
    language = detect_project_language(target_dir)
    maid_content = _generate_windsurf_rule_content(language)

    # Write rule file
    rule_file.write_text(maid_content)
    print(f"✓ Created Windsurf rule file: {rule_file}")


def _generate_windsurf_rule_content(language: str) -> str:
    """Generate Windsurf IDE .md rule file content.

    Args:
        language: Project language ("python", "typescript", "mixed", or "unknown")

    Returns:
        String containing .md file content with MAID documentation
    """
    # Generate MAID content (same as CLAUDE.md but without markers)
    maid_content = generate_claude_md_content(language)
    # Remove markers if present
    maid_content = maid_content.replace("<!-- MAID-SECTION-START -->", "")
    maid_content = maid_content.replace("<!-- MAID-SECTION-END -->", "")
    maid_content = maid_content.strip()

    return maid_content
