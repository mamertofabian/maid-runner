"""Utility functions for MAID Runner."""

from typing import List


def normalize_validation_commands(manifest_data: dict) -> List[List[str]]:
    """Normalize validation commands from manifest to a consistent format.

    Converts various validation command formats to a standard format:
    List[List[str]] where each inner list is a command array.

    Supported formats:
    - Enhanced: validationCommands = [["pytest", "test1.py"], ["pytest", "test2.py"]]
    - Legacy single: validationCommand = ["pytest", "test.py", "-v"]
    - Legacy multiple strings: validationCommand = ["pytest test1.py", "pytest test2.py"]
    - Legacy single string: validationCommand = "pytest test.py"

    Args:
        manifest_data: Dictionary containing manifest data

    Returns:
        List of command arrays, where each command is a list of strings.
        Returns empty list if no validation commands found.
    """
    # Support both validationCommand (legacy) and validationCommands (enhanced)
    validation_commands = manifest_data.get("validationCommands", [])
    if validation_commands:
        # Enhanced format: array of command arrays
        return validation_commands

    validation_command = manifest_data.get("validationCommand", [])
    if not validation_command:
        return []

    # Handle different legacy formats
    if isinstance(validation_command, str):
        # Single string command: "pytest tests/test.py"
        return [validation_command.split()]

    if isinstance(validation_command, list):
        if len(validation_command) > 1 and all(
            isinstance(cmd, str) and " " in cmd for cmd in validation_command
        ):
            # Multiple string commands: ["pytest test1.py", "pytest test2.py"]
            # Convert each string to a command array
            return [cmd.split() for cmd in validation_command]
        elif len(validation_command) > 0 and isinstance(validation_command[0], str):
            # Check if first element is a string with spaces (single string command)
            if " " in validation_command[0]:
                # Single string command in array: ["pytest tests/test.py"]
                return [validation_command[0].split()]
            else:
                # Single command array: ["pytest", "test.py", "-v"]
                return [validation_command]
        else:
            # Single command array: ["pytest", "test.py", "-v"]
            return [validation_command]

    return []
