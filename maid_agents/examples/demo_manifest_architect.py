#!/usr/bin/env python3
"""
Demo: Using ManifestArchitect to generate MAID manifests

This demonstrates how to use the ManifestArchitect agent to generate
MAID v1.2 manifests from high-level goal descriptions using Claude Code's
headless CLI.
"""

import sys
import json
from pathlib import Path

# Add maid_agents to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.manifest_architect import ManifestArchitect
from maid_agents.claude.cli_wrapper import ClaudeWrapper


def generate_manifest(goal: str, task_number: int, save: bool = True):
    """Generate a MAID manifest from a goal description.

    Args:
        goal: High-level goal description
        task_number: Task number for the manifest
        save: Whether to save the manifest to a file

    Returns:
        dict: Result containing success status and manifest data
    """
    # Create Claude wrapper (mock_mode=False for real Claude invocation)
    claude = ClaudeWrapper(mock_mode=False)

    # Create ManifestArchitect agent
    architect = ManifestArchitect(claude)

    print(f"Generating manifest for task-{task_number:03d}...")
    print(f"Goal: {goal}")
    print()

    # Generate manifest
    result = architect.create_manifest(goal=goal, task_number=task_number)

    if result["success"]:
        print("✅ Manifest generated successfully!")
        print(json.dumps(result["manifest_data"], indent=2))

        if save and result["manifest_path"]:
            # Save to file
            save_path = Path(__file__).parent.parent / result["manifest_path"]
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "w") as f:
                json.dump(result["manifest_data"], f, indent=2)

            print(f"\n✅ Saved to: {save_path}")
    else:
        print(f"❌ Failed to generate manifest: {result['error']}")

    return result


if __name__ == "__main__":
    # Example usage
    examples = [
        ("Create a utility function to format dates as ISO 8601", 100),
        ("Add validation for email addresses in user registration", 101),
        ("Implement caching for database queries", 102),
    ]

    print("ManifestArchitect Demo")
    print("=" * 70)
    print()

    for goal, task_num in examples:
        print(f"\nExample {task_num}:")
        print("-" * 70)
        result = generate_manifest(goal, task_num, save=False)
        print()
        print("=" * 70)
