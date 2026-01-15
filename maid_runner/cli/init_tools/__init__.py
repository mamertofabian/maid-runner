"""Tool registry for MAID init command.

This module provides a registry of dev tool setup functions and a dispatcher
to set up different AI development tools (Claude Code, Cursor, Windsurf, generic).
"""

from maid_runner.cli.init_tools import claude, cursor, generic, windsurf


def setup_tool(
    target_dir: str, tool_name: str, force: bool, dry_run: bool = False
) -> None:
    """Set up a specific dev tool in the target directory.

    Args:
        target_dir: Target directory to initialize MAID in
        tool_name: Name of the tool to set up ("claude", "cursor", "windsurf", "generic")
        force: If True, overwrite files without prompting
        dry_run: If True, show what would be done without making changes

    Raises:
        ValueError: If tool_name is not recognized
    """
    tool_registry = {
        "claude": claude.setup_claude,
        "cursor": cursor.setup_cursor,
        "windsurf": windsurf.setup_windsurf,
        "generic": generic.setup_generic,
    }

    if tool_name not in tool_registry:
        raise ValueError(
            f"Unknown tool: {tool_name}. Supported tools: {list(tool_registry.keys())}"
        )

    tool_registry[tool_name](target_dir, force, dry_run)
