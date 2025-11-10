"""Behavioral tests for Task-014: Prompt Templates."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_manifest_creation_template_exists():
    """Test manifest_creation.txt template exists."""
    template_path = Path(
        "maid_agents/maid_agents/config/templates/manifest_creation.txt"
    )
    assert template_path.exists()

    content = template_path.read_text()
    assert len(content) > 0
    assert "manifest" in content.lower() or "MAID" in content


def test_test_generation_template_exists():
    """Test test_generation.txt template exists."""
    template_path = Path("maid_agents/maid_agents/config/templates/test_generation.txt")
    assert template_path.exists()

    content = template_path.read_text()
    assert len(content) > 0
    assert "test" in content.lower()


def test_implementation_template_exists():
    """Test implementation.txt template exists."""
    template_path = Path("maid_agents/maid_agents/config/templates/implementation.txt")
    assert template_path.exists()

    content = template_path.read_text()
    assert len(content) > 0
    assert "implement" in content.lower() or "code" in content.lower()
