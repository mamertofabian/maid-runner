"""
Main orchestrator for coherence validation in MAID Runner.

This module provides the CoherenceValidator class that coordinates all
coherence validation checks. It loads system context (system snapshot and
knowledge graph), runs coherence checks, and returns a CoherenceResult
with any issues found.

Usage:
    from pathlib import Path
    from maid_runner.coherence.validator import CoherenceValidator

    validator = CoherenceValidator(manifest_dir=Path("manifests"))
    result = validator.validate(Path("manifests/task-001.manifest.json"))

    if not result.valid:
        for issue in result.issues:
            print(f"{issue.severity}: {issue.message}")
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from maid_runner.coherence.result import CoherenceResult, CoherenceIssue
from maid_runner.coherence.checks import (
    check_duplicate_artifacts,
    check_signature_conflicts,
    check_module_boundaries,
    check_naming_conventions,
    check_dependency_availability,
    check_pattern_consistency,
    check_architectural_constraints,
)
from maid_runner.cli.snapshot_system import (
    discover_active_manifests,
    aggregate_system_artifacts,
)
from maid_runner.graph.builder import KnowledgeGraphBuilder
from maid_runner.graph.model import KnowledgeGraph


class CoherenceValidator:
    """Main orchestrator for coherence validation that loads system context and runs checks.

    The CoherenceValidator coordinates architectural coherence validation by:
    1. Loading the system context (system snapshot and knowledge graph)
    2. Running all coherence checks against a given manifest
    3. Aggregating and returning any issues found

    Attributes:
        manifest_dir: Path to the directory containing manifest files

    Example:
        validator = CoherenceValidator(Path("manifests"))
        result = validator.validate(Path("manifests/task-001.manifest.json"))
        print(f"Valid: {result.valid}, Issues: {len(result.issues)}")
    """

    def __init__(self, manifest_dir: Path) -> None:
        """Initialize with manifest directory path.

        Args:
            manifest_dir: Path to the directory containing manifest files
        """
        self.manifest_dir = manifest_dir
        self._system_artifacts: Optional[List[Dict[str, Any]]] = None
        self._knowledge_graph: Optional[KnowledgeGraph] = None

    def validate(self, manifest_path: Path) -> CoherenceResult:
        """Main validation entry point that loads manifest and runs all checks.

        Loads the manifest JSON, builds system context (system snapshot and
        knowledge graph), runs all coherence checks, and returns a
        CoherenceResult with any issues found.

        Args:
            manifest_path: Path to the manifest file to validate

        Returns:
            CoherenceResult containing validation status and list of issues
        """
        # Load manifest JSON
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        # Build system context
        self._load_system_context()

        # Run all coherence checks
        issues = self._run_checks(manifest_data=manifest_data)

        # Determine validity based on issues
        # Valid if no issues or no error-level issues
        has_errors = any(issue.severity.value == "error" for issue in issues)
        valid = not has_errors

        return CoherenceResult(valid=valid, issues=issues)

    def _load_system_context(self) -> None:
        """Build system snapshot and knowledge graph from manifest directory.

        Uses snapshot_system functions to discover active manifests and
        aggregate system artifacts. Uses KnowledgeGraphBuilder to construct
        the knowledge graph from manifests.
        """
        # Discover active manifests and aggregate artifacts
        active_manifests = discover_active_manifests(self.manifest_dir)
        self._system_artifacts = aggregate_system_artifacts(active_manifests)

        # Build knowledge graph
        graph_builder = KnowledgeGraphBuilder(self.manifest_dir)
        self._knowledge_graph = graph_builder.build()

    def _run_checks(self, manifest_data: dict) -> List[CoherenceIssue]:
        """Execute all validation checks and return list of issues.

        Runs all coherence checks against the manifest data and aggregates
        any issues found.

        Args:
            manifest_data: Parsed manifest dictionary to validate

        Returns:
            List of CoherenceIssue instances representing found issues
        """
        issues: List[CoherenceIssue] = []

        # Ensure system context is loaded
        system_artifacts = self._system_artifacts or []
        graph = self._knowledge_graph

        # Run all coherence checks
        # Task 128: Duplicate artifact detection
        issues.extend(check_duplicate_artifacts(manifest_data, system_artifacts, graph))

        # Task 129: Signature conflict detection
        issues.extend(check_signature_conflicts(manifest_data, system_artifacts))

        # Task 130: Module boundary validation
        if graph:
            issues.extend(check_module_boundaries(manifest_data, graph))

        # Task 131: Naming convention compliance
        issues.extend(check_naming_conventions(manifest_data, system_artifacts))

        # Task 132: Dependency availability check
        if graph:
            issues.extend(check_dependency_availability(manifest_data, graph))

        # Task 133: Pattern consistency check
        if graph:
            issues.extend(check_pattern_consistency(manifest_data, graph))

        # Task 134: Architectural constraint validation
        if graph:
            issues.extend(check_architectural_constraints(manifest_data, graph))

        return issues
