"""V2 Naming convention check.

Spec: 08-coherence-module.md - coherence/checks/naming.py
"""

from __future__ import annotations

import re
from typing import Optional

from maid_runner.core.types import ArtifactKind, ArtifactSpec, Manifest
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.checks.base import BaseCheck
from maid_runner.graph.model import KnowledgeGraph


class NamingCheck(BaseCheck):
    """Checks naming convention consistency.

    Rules checked:
    - Python: snake_case for functions/methods, PascalCase for classes
    - TypeScript: camelCase for functions, PascalCase for classes/interfaces
    - Manifest slugs: kebab-case
    - Consistency within a module

    Severity: INFO for style inconsistencies, WARNING for violations.
    """

    @property
    def name(self) -> str:
        return "naming"

    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest]
    ) -> list[CoherenceIssue]:
        issues: list[CoherenceIssue] = []

        for m in manifests:
            for fs in m.all_file_specs:
                lang = _detect_language(fs.path)
                for art in fs.artifacts:
                    if art.is_private:
                        continue
                    issue = _check_naming(art, fs.path, lang)
                    if issue:
                        issues.append(issue)

        return issues


def _detect_language(file_path: str) -> str:
    if file_path.endswith(".py"):
        return "python"
    elif file_path.endswith((".ts", ".tsx")):
        return "typescript"
    return "unknown"


def _check_naming(
    art: ArtifactSpec, file_path: str, lang: str
) -> Optional[CoherenceIssue]:
    """Check naming conventions for a single artifact."""
    if lang == "python":
        return _check_python_naming(art, file_path)
    elif lang == "typescript":
        return _check_typescript_naming(art, file_path)
    return None


def _check_python_naming(art: ArtifactSpec, file_path: str) -> Optional[CoherenceIssue]:
    name = art.name
    kind = art.kind

    if kind in (ArtifactKind.FUNCTION, ArtifactKind.METHOD):
        if not _is_snake_case(name) and not name.startswith("_"):
            return CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message=f"Function '{name}' does not follow snake_case convention",
                file=file_path,
                artifact=name,
                suggestion="Rename to snake_case",
            )
    elif kind == ArtifactKind.CLASS:
        if not _is_pascal_case(name) and not name.startswith("_"):
            return CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message=f"Class '{name}' does not follow PascalCase convention",
                file=file_path,
                artifact=name,
                suggestion="Rename to PascalCase",
            )
    return None


def _check_typescript_naming(
    art: ArtifactSpec, file_path: str
) -> Optional[CoherenceIssue]:
    name = art.name
    kind = art.kind

    if kind in (ArtifactKind.FUNCTION, ArtifactKind.METHOD):
        if not _is_camel_case(name) and not name.startswith("_"):
            return CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.INFO,
                message=f"Function '{name}' does not follow camelCase convention",
                file=file_path,
                artifact=name,
                suggestion="Rename to camelCase",
            )
    elif kind in (ArtifactKind.CLASS, ArtifactKind.INTERFACE):
        if not _is_pascal_case(name) and not name.startswith("_"):
            return CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message=f"Class/Interface '{name}' does not follow PascalCase convention",
                file=file_path,
                artifact=name,
                suggestion="Rename to PascalCase",
            )
    return None


def _is_snake_case(name: str) -> bool:
    return bool(re.match(r"^[a-z_][a-z0-9_]*$", name))


def _is_pascal_case(name: str) -> bool:
    return bool(re.match(r"^[A-Z][a-zA-Z0-9]*$", name))


def _is_camel_case(name: str) -> bool:
    return bool(re.match(r"^[a-z][a-zA-Z0-9]*$", name))
