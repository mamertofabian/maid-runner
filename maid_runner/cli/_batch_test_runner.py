"""Batch test runner for MAID validation.

This module provides functionality to collect test files from all active manifests
and run them in batches grouped by test runner type, eliminating the overhead of
running N separate test processes for N manifests.

Supports: pytest, vitest, jest, and other test runners.
"""

import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set

from maid_runner.utils import normalize_validation_commands


def detect_test_runner(command: List[str]) -> Optional[str]:
    """Detect the test runner type from a validation command.

    Supports: pytest, vitest, jest, npm test, pnpm test, etc.

    Args:
        command: List of command arguments

    Returns:
        Test runner name (e.g., "pytest", "vitest", "jest") or None
    """
    if not command:
        return None

    # Check for common test runners
    test_runners = ["pytest", "vitest", "jest"]

    for runner in test_runners:
        if runner in command:
            return runner

    # Check for npm/pnpm test commands
    if len(command) >= 2:
        if command[0] in ["npm", "pnpm", "yarn"] and command[1] == "test":
            return f"{command[0]}-test"

    return None


def extract_test_file_from_command(command: List[str]) -> Optional[str]:
    """Extract test file path from a validation command.

    Supports various test command formats:
    - pytest tests/test_file.py
    - python -m pytest tests/test_file.py
    - uv run pytest tests/test_file.py
    - vitest run tests/test_file.spec.ts
    - jest tests/test_file.test.js

    Args:
        command: List of command arguments

    Returns:
        Test file path if found, None otherwise
    """
    if not command:
        return None

    runner = detect_test_runner(command)
    if not runner:
        return None

    # Find the runner in the command
    try:
        runner_name = runner.split("-")[0]  # Handle npm-test -> npm
        runner_index = command.index(runner_name)
    except ValueError:
        return None

    # Look for test file after the runner command
    # Skip the next arg if it's a subcommand (like "run" or "test")
    start_index = runner_index + 1
    if start_index < len(command) and command[start_index] in ["run", "test"]:
        start_index += 1

    for arg in command[start_index:]:
        # Skip flags (start with -)
        if arg.startswith("-"):
            continue
        # Found a test file or directory (contains "test" or common test file extensions)
        if "test" in arg or arg.endswith(
            (".spec.ts", ".spec.js", ".test.ts", ".test.js")
        ):
            return arg

    return None


def is_pytest_command(command: List[str]) -> bool:
    """Check if a command is a pytest command.

    Args:
        command: List of command arguments

    Returns:
        True if command contains pytest, False otherwise
    """
    return detect_test_runner(command) == "pytest"


def collect_pytest_test_files(
    manifests_dir: Path, active_manifests: List[Path]
) -> Optional[Set[str]]:
    """Collect all pytest test files from active manifests.

    Scans all active manifests and extracts test files from their validation commands.
    Returns None if any non-pytest commands are found (indicating mixed test runners).

    Args:
        manifests_dir: Path to manifests directory
        active_manifests: List of active (non-superseded) manifest paths

    Returns:
        Set of unique test file paths, or None if mixed command types detected
    """
    test_files: Set[str] = set()

    for manifest_path in active_manifests:
        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            # Get validation commands (handles both singular and plural forms)
            validation_commands = normalize_validation_commands(manifest_data)

            if not validation_commands:
                # Skip manifests without validation commands
                continue

            # Check all commands are pytest-compatible
            for cmd in validation_commands:
                if not cmd:
                    continue

                if not is_pytest_command(cmd):
                    # Found non-pytest command, return None to signal mixed runners
                    return None

                # Extract test file
                test_file = extract_test_file_from_command(cmd)
                if test_file:
                    test_files.add(test_file)

        except (json.JSONDecodeError, IOError):
            # Skip invalid manifests
            continue

    return test_files


def collect_test_files_by_runner(
    manifests_dir: Path, active_manifests: List[Path]
) -> Dict[str, Set[str]]:
    """Collect test files grouped by test runner type.

    Scans all active manifests and groups test files by their runner type
    (pytest, vitest, jest, etc.). This allows batching per runner type.

    Args:
        manifests_dir: Path to manifests directory
        active_manifests: List of active (non-superseded) manifest paths

    Returns:
        Dictionary mapping runner type to set of test file paths
        Example: {"pytest": {"test1.py", "test2.py"}, "vitest": {"test1.spec.ts"}}
    """
    test_files_by_runner: Dict[str, Set[str]] = {}

    for manifest_path in active_manifests:
        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            # Get validation commands (handles both singular and plural forms)
            validation_commands = normalize_validation_commands(manifest_data)

            if not validation_commands:
                # Skip manifests without validation commands
                continue

            for cmd in validation_commands:
                if not cmd:
                    continue

                # Detect runner type
                runner = detect_test_runner(cmd)
                if not runner:
                    # Not a recognized test command, skip
                    continue

                # Extract test file
                test_file = extract_test_file_from_command(cmd)
                if test_file:
                    if runner not in test_files_by_runner:
                        test_files_by_runner[runner] = set()
                    test_files_by_runner[runner].add(test_file)

        except (json.JSONDecodeError, IOError):
            # Skip invalid manifests
            continue

    return test_files_by_runner


def run_batch_pytest(
    test_files: Set[str], project_root: Path, verbose: bool, timeout: int
) -> tuple:
    """Run pytest in batch mode with all test files.

    Executes a single pytest command with all test files, avoiding the overhead
    of running pytest multiple times.

    Args:
        test_files: Set of test file paths to run
        project_root: Project root directory for command execution
        verbose: Show detailed output
        timeout: Command timeout in seconds

    Returns:
        Tuple of (passed, failed, total) counts
    """
    if not test_files:
        return (0, 0, 0)

    # Check if we should auto-prefix with 'uv run'
    pyproject_path = project_root / "pyproject.toml"
    auto_prefix_uv_run = pyproject_path.exists()

    # Build pytest command
    cmd = []
    if auto_prefix_uv_run:
        cmd.extend(["uv", "run"])

    cmd.append("pytest")
    # Sort test files for consistent ordering
    cmd.extend(sorted(test_files))
    cmd.append("-v")

    # Set up environment
    import os

    env_additions = os.environ.copy()

    # Add current project root to PYTHONPATH
    current_pythonpath = env_additions.get("PYTHONPATH", "")
    pythonpath_additions = [str(project_root)]
    if current_pythonpath:
        pythonpath_additions.append(current_pythonpath)
    env_additions["PYTHONPATH"] = ":".join(pythonpath_additions)

    # Print batch execution info
    print("\n🚀 Running tests in batch mode (faster)")
    print(f"📦 Collected {len(test_files)} test file(s)")

    # Show command prefix without all the test files
    cmd_prefix = []
    for part in cmd:
        if part in sorted(test_files):
            break
        cmd_prefix.append(part)

    cmd_prefix_str = " ".join(cmd_prefix)
    print(f"🧪 Command: {cmd_prefix_str} <{len(test_files)} test files>\n")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_root,
            env=env_additions,
        )

        # Always show test runner output (contains test counts and results)
        if result.stdout:
            print(result.stdout)

        if result.returncode == 0:
            print("✅ All tests PASSED")
            return (1, 0, 1)
        else:
            print(f"❌ Tests FAILED (exit code: {result.returncode})")
            if result.stderr:
                print(result.stderr)
            return (0, 1, 1)

    except subprocess.TimeoutExpired:
        print(f"⏰ TIMEOUT (>{timeout}s)")
        return (0, 1, 1)
    except FileNotFoundError:
        print(f"❌ Command not found: {cmd[0]}")
        return (0, 1, 1)
    except Exception as e:
        print(f"❌ Error: {e}")
        return (0, 1, 1)


def run_batch_tests(
    runner: str,
    test_files: Set[str],
    project_root: Path,
    verbose: bool,
    timeout: int,
) -> tuple:
    """Run tests in batch mode for any test runner.

    Executes a single command with all test files for the given runner type,
    avoiding the overhead of running the test runner multiple times.

    Supports: pytest, vitest, jest, and other common test runners.

    Args:
        runner: Test runner type (e.g., "pytest", "vitest", "jest")
        test_files: Set of test file paths to run
        project_root: Project root directory for command execution
        verbose: Show detailed output
        timeout: Command timeout in seconds

    Returns:
        Tuple of (passed, failed, total) counts
    """
    if not test_files:
        return (0, 0, 0)

    import os

    # Build command based on runner type
    cmd = []
    env_additions = os.environ.copy()

    if runner == "pytest":
        # Check if we should auto-prefix with 'uv run'
        pyproject_path = project_root / "pyproject.toml"
        if pyproject_path.exists():
            cmd.extend(["uv", "run"])

        cmd.append("pytest")
        cmd.extend(sorted(test_files))
        cmd.append("-v")

        # Add current project root to PYTHONPATH for pytest
        current_pythonpath = env_additions.get("PYTHONPATH", "")
        pythonpath_additions = [str(project_root)]
        if current_pythonpath:
            pythonpath_additions.append(current_pythonpath)
        env_additions["PYTHONPATH"] = ":".join(pythonpath_additions)

    elif runner == "vitest":
        # Check for package manager
        package_json = project_root / "package.json"
        if package_json.exists():
            # Use pnpm/npm/yarn exec to ensure vitest is available
            if (project_root / "pnpm-lock.yaml").exists():
                cmd.extend(["pnpm", "exec", "vitest"])
            elif (project_root / "yarn.lock").exists():
                cmd.extend(["yarn", "exec", "vitest"])
            else:
                cmd.extend(["npm", "exec", "vitest"])
        else:
            cmd.append("vitest")

        cmd.append("run")
        cmd.extend(sorted(test_files))

    elif runner == "jest":
        # Similar to vitest
        package_json = project_root / "package.json"
        if package_json.exists():
            if (project_root / "pnpm-lock.yaml").exists():
                cmd.extend(["pnpm", "exec", "jest"])
            elif (project_root / "yarn.lock").exists():
                cmd.extend(["yarn", "exec", "jest"])
            else:
                cmd.extend(["npm", "exec", "jest"])
        else:
            cmd.append("jest")

        cmd.extend(sorted(test_files))

    else:
        # Generic runner - just use the runner name
        cmd.append(runner)
        cmd.extend(sorted(test_files))

    # Print batch execution info
    print(f"\n🚀 Running {runner} tests in batch mode")
    print(f"📦 Collected {len(test_files)} test file(s)")

    # Show command prefix without all the test files
    cmd_prefix = []
    for part in cmd:
        if part in sorted(test_files):
            break
        cmd_prefix.append(part)

    cmd_prefix_str = " ".join(cmd_prefix)
    print(f"🧪 Command: {cmd_prefix_str} <{len(test_files)} test files>\n")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_root,
            env=env_additions,
        )

        # Always show test runner output (contains test counts and results)
        if result.stdout:
            print(result.stdout)

        if result.returncode == 0:
            print(f"✅ {runner} tests PASSED")
            return (1, 0, 1)
        else:
            print(f"❌ {runner} tests FAILED (exit code: {result.returncode})")
            if result.stderr:
                print(result.stderr)
            return (0, 1, 1)

    except subprocess.TimeoutExpired:
        print(f"⏰ {runner} TIMEOUT (>{timeout}s)")
        return (0, 1, 1)
    except FileNotFoundError:
        print(f"❌ Command not found: {cmd[0]}")
        return (0, 1, 1)
    except Exception as e:
        print(f"❌ Error: {e}")
        return (0, 1, 1)
