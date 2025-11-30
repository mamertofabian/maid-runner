"""TypeScript/JavaScript test runner utilities.

This module provides utilities for detecting, normalizing, and executing
TypeScript/JavaScript test commands within the MAID validation framework.
Supports common package managers (npm, pnpm, yarn) and test runners (Jest, Vitest).
"""

import json
from pathlib import Path
from typing import Optional


def detect_typescript_project(project_root: Path) -> bool:
    """Detect if a directory is a TypeScript/JavaScript project.

    Args:
        project_root: Path to the project root directory

    Returns:
        True if project has package.json, False otherwise
    """
    if not project_root.exists():
        return False

    package_json = project_root / "package.json"
    return package_json.exists()


def get_package_manager(project_root: Path) -> str:
    """Identify the package manager used by the project.

    Priority order: pnpm > yarn > npm (based on lockfile presence)

    Args:
        project_root: Path to the project root directory

    Returns:
        Package manager name: "pnpm", "yarn", or "npm"
    """
    # Check for lockfiles in priority order
    if (project_root / "pnpm-lock.yaml").exists():
        return "pnpm"
    elif (project_root / "yarn.lock").exists():
        return "yarn"
    elif (project_root / "package-lock.json").exists():
        return "npm"
    else:
        # Default to npm if no lockfile exists
        return "npm"


def is_typescript_command(cmd: list) -> bool:
    """Check if a command is TypeScript/JavaScript-related.

    Args:
        cmd: Command list (e.g., ["npm", "test"])

    Returns:
        True if command is TypeScript-related, False otherwise
    """
    if not cmd:
        return False

    first_arg = cmd[0]

    # Package managers
    if first_arg in ["npm", "pnpm", "yarn"]:
        return True

    # TypeScript tools
    if first_arg in ["tsc", "tsx", "ts-node"]:
        return True

    # Test runners
    if first_arg in ["jest", "vitest", "mocha", "ava", "tap"]:
        return True

    return False


def normalize_typescript_command(cmd: list, project_root: Path) -> list:
    """Normalize a TypeScript command for execution.

    Ensures commands are properly formatted and have necessary context.

    Args:
        cmd: Command list to normalize
        project_root: Path to the project root directory

    Returns:
        Normalized command list
    """
    if not cmd:
        return []

    # For now, just return the command as-is
    # Future enhancements could:
    # - Auto-detect and add --passWithNoTests for Jest
    # - Add --run for Vitest in CI mode
    # - Resolve relative paths
    # - Add environment variables
    return cmd


def get_test_script_from_package_json(project_root: Path) -> Optional[str]:
    """Extract the test script from package.json.

    Args:
        project_root: Path to the project root directory

    Returns:
        Test script command string, or None if not found
    """
    package_json_path = project_root / "package.json"

    if not package_json_path.exists():
        return None

    try:
        with open(package_json_path, "r") as f:
            package_data = json.load(f)

        scripts = package_data.get("scripts", {})
        return scripts.get("test")

    except (json.JSONDecodeError, IOError):
        return None


def has_typescript_installed(project_root: Path) -> bool:
    """Check if TypeScript is installed in the project.

    Args:
        project_root: Path to the project root directory

    Returns:
        True if TypeScript is in dependencies or devDependencies
    """
    package_json_path = project_root / "package.json"

    if not package_json_path.exists():
        return False

    try:
        with open(package_json_path, "r") as f:
            package_data = json.load(f)

        dependencies = package_data.get("dependencies", {})
        dev_dependencies = package_data.get("devDependencies", {})

        return "typescript" in dependencies or "typescript" in dev_dependencies

    except (json.JSONDecodeError, IOError):
        return False
