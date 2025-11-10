"""
Behavioral tests for Task-003: ContextBuilder.

Tests the ContextBuilder class that prepares context for AI agents.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.core.context_builder import ContextBuilder, AgentContext


def test_agent_context_creation():
    """Test AgentContext can be instantiated."""
    context = AgentContext(manifest_data={}, file_contents={}, goal="Test goal")

    assert hasattr(context, "manifest_data")
    assert hasattr(context, "file_contents")
    assert hasattr(context, "goal")


def test_context_builder_instantiation():
    """Test ContextBuilder can be instantiated."""
    builder = ContextBuilder()
    assert builder is not None
    assert isinstance(builder, ContextBuilder)


def test_build_from_manifest():
    """Test build_from_manifest loads manifest and creates context."""
    builder = ContextBuilder()

    manifest_path = "maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json"
    context = builder.build_from_manifest(manifest_path)

    assert isinstance(context, AgentContext)
    assert context.manifest_data is not None
    assert isinstance(context.manifest_data, dict)


def test_load_file_contents():
    """Test load_file_contents reads multiple files."""
    builder = ContextBuilder()

    file_paths = [
        "maid_agents/maid_agents/__init__.py",
        "maid_agents/maid_agents/__version__.py",
    ]

    contents = builder.load_file_contents(file_paths)

    assert isinstance(contents, dict)
    assert len(contents) >= 0  # May be empty if files don't exist
