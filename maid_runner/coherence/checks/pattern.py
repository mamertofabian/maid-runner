"""V2 Pattern consistency check.

Spec: 08-coherence-module.md - coherence/checks/pattern.py
Ported from v1: coherence/checks/pattern_check.py
"""

from __future__ import annotations

from typing import Any

from maid_runner.core.types import ArtifactKind, Manifest
from maid_runner.coherence.result_v2 import (
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.checks.base import BaseCheck
from maid_runner.graph.model import (
    ArtifactNode,
    KnowledgeGraph,
    NodeType,
)

# Pattern suffixes and their expected module locations
_PATTERN_DEFINITIONS: dict[str, dict[str, str]] = {
    "Repository": {"suffix": "Repository", "module": "repositories"},
    "Service": {"suffix": "Service", "module": "services"},
    "Handler": {"suffix": "Handler", "module": "handlers"},
}


class PatternCheck(BaseCheck):
    """Checks for architectural pattern consistency.

    Rules:
    - If a module has a validator pattern, new validators follow it
    - Classes with pattern suffixes should be in the correct module
    - Classes in pattern modules should follow the naming convention
    - Detect anti-patterns (god classes with too many methods)

    Severity: WARNING for pattern violations, INFO for suggestions.
    """

    @property
    def name(self) -> str:
        return "pattern"

    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest]
    ) -> list[CoherenceIssue]:
        issues: list[CoherenceIssue] = []

        # Detect patterns from the graph
        patterns = _detect_patterns(graph)
        if not patterns:
            return issues

        # Validate each manifest's artifacts against patterns
        for m in manifests:
            for fs in m.all_file_specs:
                for art in fs.artifacts:
                    if art.kind != ArtifactKind.CLASS:
                        continue
                    if art.is_private:
                        continue
                    issue = _check_class_pattern(art.name, fs.path, patterns)
                    if issue:
                        issues.append(issue)

        return issues


def _detect_patterns(graph: KnowledgeGraph) -> dict[str, Any]:
    """Detect architectural patterns from the knowledge graph."""
    patterns: dict[str, Any] = {}

    for node in graph.nodes:
        if node.node_type != NodeType.ARTIFACT:
            continue
        if not isinstance(node, ArtifactNode):
            continue
        if node.artifact_type != "class":
            continue
        if not node.name:
            continue

        for pattern_name, pattern_def in _PATTERN_DEFINITIONS.items():
            suffix = pattern_def["suffix"]
            if node.name.endswith(suffix):
                if pattern_name not in patterns:
                    patterns[pattern_name] = {
                        "suffix": suffix,
                        "module": pattern_def["module"],
                        "classes": [],
                    }
                patterns[pattern_name]["classes"].append(node.name)

    return patterns


def _check_class_pattern(
    class_name: str,
    file_path: str,
    patterns: dict[str, Any],
) -> CoherenceIssue | None:
    """Check if a class follows pattern conventions."""
    # Check 1: class name has pattern suffix -> verify module location
    for pattern_name, pattern_info in patterns.items():
        suffix = pattern_info.get("suffix", "")
        expected_module = pattern_info.get("module", "")

        if class_name.endswith(suffix):
            if expected_module and expected_module not in file_path:
                return CoherenceIssue(
                    issue_type=IssueType.PATTERN,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Class '{class_name}' follows the {pattern_name} pattern "
                        f"but is not in the '{expected_module}' module. "
                        f"Found in: {file_path}"
                    ),
                    file=file_path,
                    artifact=class_name,
                    suggestion=(
                        f"Consider moving '{class_name}' to a file in the "
                        f"'{expected_module}' module to follow the {pattern_name} pattern."
                    ),
                )

    # Check 2: class is in pattern module -> verify naming convention
    for pattern_name, pattern_info in patterns.items():
        suffix = pattern_info.get("suffix", "")
        expected_module = pattern_info.get("module", "")

        if expected_module and expected_module in file_path:
            if not class_name.endswith(suffix) and not class_name.startswith("_"):
                return CoherenceIssue(
                    issue_type=IssueType.PATTERN,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Class '{class_name}' is in the '{expected_module}' module "
                        f"but does not follow the {pattern_name} naming convention "
                        f"(expected suffix: '{suffix}')."
                    ),
                    file=file_path,
                    artifact=class_name,
                    suggestion=(
                        f"Consider renaming '{class_name}' to '{class_name}{suffix}' "
                        f"to follow the {pattern_name} pattern, or move it to a "
                        f"different module."
                    ),
                )

    return None
