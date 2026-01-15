"""Private helpers for extracting test file paths from validation commands.

These helpers parse various pytest command formats to extract test file paths
for behavioral validation.
"""

from pathlib import Path
from typing import List, Any


def _is_enhanced_command_format(validation_command: List[Any]) -> bool:
    """Check if validation command uses enhanced format (array of arrays).

    Args:
        validation_command: Command to check

    Returns:
        True if enhanced format, False otherwise
    """
    return bool(validation_command and isinstance(validation_command[0], list))


def _extract_from_multiple_commands(commands: List[List[str]]) -> List[str]:
    """Extract test files from multiple command arrays (enhanced format).

    Args:
        commands: List of command arrays

    Returns:
        Combined list of test file paths from all commands
    """
    all_test_files = []
    for cmd_array in commands:
        test_files = _extract_from_single_command(cmd_array)
        all_test_files.extend(test_files)
    return all_test_files


def _extract_from_single_command(command: List[str]) -> list:
    """Extract test files from a single command array.

    Args:
        command: List of command components (e.g., ["pytest", "test.py", "-v"])

    Returns:
        List of test file paths
    """
    if not command:
        return []

    # Handle multiple pytest commands as strings
    test_files = _extract_from_string_commands(command)
    if test_files:
        return test_files

    # Otherwise, try the standard list format
    return _extract_from_list_command(command)


def _extract_from_string_commands(command: List[str]) -> List[str]:
    """Extract test files from string-based test commands.

    Handles formats like:
    - ["pytest test1.py", "pytest test2.py"]
    - ["vitest run test1.spec.ts", "vitest run test2.spec.ts"]

    Args:
        command: List of command strings

    Returns:
        List of test file paths
    """
    test_files = []
    test_runners = ["pytest", "vitest", "jest"]

    for cmd in command:
        if not isinstance(cmd, str):
            continue

        # Check if command contains any test runner
        has_runner = any(runner in cmd for runner in test_runners)
        if not has_runner:
            continue

        cmd_parts = cmd.split() if " " in cmd else [cmd]
        runner_index = _find_test_runner_index(cmd_parts)

        if runner_index != -1:
            # Skip subcommand if present
            start_index = runner_index + 1
            if start_index < len(cmd_parts) and cmd_parts[start_index] in [
                "run",
                "test",
            ]:
                start_index += 1
            test_args = cmd_parts[start_index:]
            test_files.extend(_filter_test_paths_from_args(test_args))

    return test_files


def _extract_from_list_command(command: List[str]) -> List[str]:
    """Extract test files from list-based test command.

    Handles formats like:
    - ["pytest", "test.py", "-v"]
    - ["vitest", "run", "test.spec.ts"]
    - ["pnpm", "exec", "vitest", "run", "test.spec.ts"]
    - ["jest", "test.test.js"]

    Args:
        command: List of command parts

    Returns:
        List of test file paths
    """
    if len(command) <= 1:
        return []

    runner_index = _find_test_runner_index(command)
    if runner_index == -1:
        return []

    # Skip the next arg if it's a subcommand (like "run" or "test")
    start_index = runner_index + 1
    if start_index < len(command) and command[start_index] in ["run", "test"]:
        start_index += 1

    test_args = command[start_index:]
    return _filter_test_paths_from_args(test_args)


def _find_pytest_index(command_parts: List[str]) -> int:
    """Find the index of 'pytest' in command parts.

    Args:
        command_parts: List of command components

    Returns:
        Index of 'pytest' or -1 if not found
    """
    for i, part in enumerate(command_parts):
        if part == "pytest":
            return i
    return -1


def _find_test_runner_index(command_parts: List[str]) -> int:
    """Find the index of any test runner (pytest, vitest, jest) in command parts.

    Supports common test runners and handles package manager exec patterns:
    - pytest, vitest, jest (direct)
    - pnpm exec vitest, npm exec jest, yarn exec vitest
    - python -m pytest, uv run pytest

    Args:
        command_parts: List of command components

    Returns:
        Index of test runner or -1 if not found
    """
    test_runners = ["pytest", "vitest", "jest"]

    for i, part in enumerate(command_parts):
        # Direct test runner
        if part in test_runners:
            return i
        # Handle package manager exec patterns: pnpm exec vitest, npm exec jest
        if part in ["exec"] and i + 1 < len(command_parts):
            if command_parts[i + 1] in test_runners:
                return i + 1
        # Handle python -m pytest, uv run pytest
        if part in ["-m", "run"] and i + 1 < len(command_parts):
            if command_parts[i + 1] in test_runners:
                return i + 1

    return -1


def _filter_test_paths_from_args(test_args: List[str]) -> List[str]:
    """Filter test file/directory paths from test runner arguments.

    Supports pytest, vitest, jest, and other test runners.

    Args:
        test_args: List of test runner arguments

    Returns:
        List of test file/directory paths
    """
    TEST_OPTIONS_WITH_VALUES = {
        "--tb",
        "--cov",
        "--maxfail",
        "--timeout",
        "--reporter",
        "--config",
    }
    test_files = []

    for arg in test_args:
        # Skip flags
        if arg.startswith("-"):
            continue

        # Skip common test options that take values
        if arg in TEST_OPTIONS_WITH_VALUES:
            continue

        # Extract file path from node IDs (file::class::method for pytest)
        if "::" in arg:
            file_path = arg.split("::")[0]
            test_files.append(file_path)
        else:
            # Regular file or directory path
            # Also check for common test file patterns
            if "test" in arg.lower() or arg.endswith(
                (".py", ".ts", ".js", ".spec.ts", ".spec.js", ".test.ts", ".test.js")
            ):
                test_files.append(arg)

    return test_files


def _normalize_test_file_paths(test_files: List[str]) -> List[str]:
    """Normalize test file paths by removing redundant directory prefixes.

    Args:
        test_files: List of test file paths to normalize

    Returns:
        List of normalized test file paths
    """
    normalized_test_files = []
    try:
        project_name = Path.cwd().name
    except (OSError, RuntimeError):
        # If we can't get cwd, skip normalization
        return test_files

    for test_file in test_files:
        # Only normalize if the file doesn't exist as-is
        try:
            if "/" in test_file and not Path(test_file).exists():
                if test_file.startswith(f"{project_name}/"):
                    potential_normalized = test_file[len(project_name) + 1 :]
                    if Path(potential_normalized).exists():
                        test_file = potential_normalized
        except (OSError, RuntimeError):
            # If path operations fail, use original path
            pass
        normalized_test_files.append(test_file)

    return normalized_test_files


def _validate_test_files_exist(test_files: List[str]) -> None:
    """Validate that all test files exist on disk.

    Args:
        test_files: List of test file paths to check

    Raises:
        FileNotFoundError: If any test file doesn't exist
    """
    for test_file in test_files:
        if not Path(test_file).exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")


def _find_imported_test_files(test_file: str) -> List[str]:
    """Find test files imported by a test file.

    This helps with split test files where the main entry point imports
    test classes from other test modules (e.g., _test_*.py files).

    Args:
        test_file: Path to the test file to analyze

    Returns:
        List of imported test file paths that exist
    """
    import ast

    imported_files = []
    test_file_path = Path(test_file)

    if not test_file_path.exists():
        return imported_files

    try:
        with open(test_file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=test_file)
    except (SyntaxError, UnicodeDecodeError):
        return imported_files

    # Find the tests directory
    tests_dir = test_file_path.parent
    if tests_dir.name != "tests":
        # If not in tests/, look for tests/ in parent directories
        for parent in test_file_path.parents:
            if parent.name == "tests":
                tests_dir = parent
                break

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("tests."):
                # Convert module path to file path
                # e.g., "tests._test_task_005_type_validation_validate_type_hints"
                # -> "tests/_test_task_005_type_validation_validate_type_hints.py"
                module_parts = node.module.split(".")
                if len(module_parts) >= 2 and module_parts[0] == "tests":
                    # Reconstruct file path
                    file_name = "/".join(module_parts[1:]) + ".py"
                    imported_file = tests_dir / file_name
                    if imported_file.exists():
                        imported_files.append(str(imported_file))

    return imported_files
