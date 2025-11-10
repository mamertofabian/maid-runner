"""Context Builder - Prepares context for AI agents."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any


@dataclass
class AgentContext:
    """Context for AI agent execution."""

    manifest_data: Dict[str, Any]
    file_contents: Dict[str, str]
    goal: str


class ContextBuilder:
    """Builds context for AI agents from manifests and files."""

    def __init__(self):
        """Initialize context builder."""
        pass

    def build_from_manifest(self, manifest_path: str) -> AgentContext:
        """Build agent context from manifest file.

        Args:
            manifest_path: Path to manifest JSON file

        Returns:
            AgentContext with manifest data and loaded files
        """
        # Load manifest
        with open(manifest_path) as f:
            manifest_data = json.load(f)

        # Extract file lists
        readonly_files = manifest_data.get("readonlyFiles", [])
        editable_files = manifest_data.get("editableFiles", [])
        creatable_files = manifest_data.get("creatableFiles", [])

        # Load all referenced files
        all_files = readonly_files + editable_files + creatable_files
        file_contents = self.load_file_contents(all_files)

        return AgentContext(
            manifest_data=manifest_data,
            file_contents=file_contents,
            goal=manifest_data.get("goal", ""),
        )

    def load_file_contents(self, file_paths: list) -> dict:
        """Load contents of multiple files.

        Args:
            file_paths: List of file paths to load

        Returns:
            Dict mapping file path to content
        """
        contents = {}

        for file_path in file_paths:
            try:
                path = Path(file_path)
                if path.exists() and path.is_file():
                    with open(path) as f:
                        contents[file_path] = f.read()
                else:
                    # File doesn't exist yet (might be creatable)
                    contents[file_path] = None
            except Exception as e:
                # Handle read errors gracefully
                contents[file_path] = f"Error reading file: {e}"

        return contents
