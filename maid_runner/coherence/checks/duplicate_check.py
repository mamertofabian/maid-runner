"""Duplicate artifact detection for coherence validation.

This module checks for artifacts that are declared in multiple manifests
without proper supersession. It queries the system snapshot (aggregated
artifacts from all manifests) and returns CoherenceIssue with IssueType.DUPLICATE
for any duplicates found.

Functions:
    check_duplicate_artifacts: Main function that checks for duplicate declarations
    _find_existing_artifact: Helper to find if an artifact exists in system artifacts
    _is_valid_supersession: Helper to check if supersession is properly declared

Usage:
    from maid_runner.coherence.checks.duplicate_check import check_duplicate_artifacts
    from maid_runner.graph.model import KnowledgeGraph

    issues = check_duplicate_artifacts(
        manifest_data=manifest,
        system_artifacts=aggregated_artifacts,
        graph=knowledge_graph,
    )
"""

from typing import Dict, List, Optional

from maid_runner.coherence.result import CoherenceIssue, IssueSeverity, IssueType
from maid_runner.graph.model import KnowledgeGraph


def check_duplicate_artifacts(
    manifest_data: dict,
    system_artifacts: List[Dict],
    graph: KnowledgeGraph,
) -> List[CoherenceIssue]:
    """Check for duplicate artifact declarations.

    Examines the manifest's expectedArtifacts and checks if any of them
    already exist in the system_artifacts (aggregated from all manifests).
    If a duplicate is found and no valid supersession exists, returns a
    CoherenceIssue with IssueType.DUPLICATE.

    Args:
        manifest_data: The manifest data dictionary to check.
        system_artifacts: List of artifacts aggregated from all existing manifests.
            Each artifact is a dict with "name", "type", and "file" keys.
        graph: The KnowledgeGraph for additional context (reserved for future use).

    Returns:
        List of CoherenceIssue instances for any duplicates found.
    """
    issues: List[CoherenceIssue] = []

    # Get expectedArtifacts from manifest
    expected_artifacts = manifest_data.get("expectedArtifacts")
    if expected_artifacts is None:
        return issues

    # Get the contains list
    contains = expected_artifacts.get("contains", [])
    if not contains:
        return issues

    # Check each artifact for duplicates
    for artifact in contains:
        artifact_name = artifact.get("name")
        artifact_type = artifact.get("type")

        # Skip if missing name or type
        if not artifact_name:
            continue

        # If type is missing, we cannot reliably check for duplicates
        if not artifact_type:
            continue

        # Check if this artifact already exists in system artifacts
        existing_file = _find_existing_artifact(
            artifact_name=artifact_name,
            artifact_type=artifact_type,
            system_artifacts=system_artifacts,
        )

        if existing_file is not None:
            # Check if manifest properly supersedes or edits the existing file
            if not _is_valid_supersession(manifest_data, existing_file):
                # This is a duplicate without valid supersession
                issue = CoherenceIssue(
                    issue_type=IssueType.DUPLICATE,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"Duplicate {artifact_type} '{artifact_name}' "
                        f"already defined in '{existing_file}'"
                    ),
                    suggestion=(
                        f"Use 'supersedes' to reference the manifest that created "
                        f"'{existing_file}', or add '{existing_file}' to 'editableFiles' "
                        f"if you intend to modify it"
                    ),
                    location=existing_file,
                )
                issues.append(issue)

    return issues


def _find_existing_artifact(
    artifact_name: str,
    artifact_type: str,
    system_artifacts: List[Dict],
) -> Optional[str]:
    """Find if an artifact already exists in system artifacts.

    Searches through the system_artifacts list for an artifact matching
    both the name AND type.

    Args:
        artifact_name: The name of the artifact to search for.
        artifact_type: The type of the artifact (function, class, etc.).
        system_artifacts: List of existing artifacts, each with "name",
            "type", and "file" keys.

    Returns:
        The file path where the artifact is defined, or None if not found.
    """
    for artifact in system_artifacts:
        if (
            artifact.get("name") == artifact_name
            and artifact.get("type") == artifact_type
        ):
            return artifact.get("file")

    return None


def _is_valid_supersession(
    manifest_data: dict,
    existing_file: str,
) -> bool:
    """Check if the manifest properly supersedes the existing file.

    A supersession is valid if:
    - The existing_file is in the manifest's editableFiles list, OR
    - The existing_file is covered by a supersedes declaration

    Args:
        manifest_data: The manifest data dictionary.
        existing_file: The file path where the duplicate artifact exists.

    Returns:
        True if the supersession is valid, False otherwise.
    """
    # Check if existing_file is in editableFiles
    editable_files = manifest_data.get("editableFiles", [])
    if existing_file in editable_files:
        return True

    # Check if existing_file is in supersedes
    # Note: supersedes typically contains manifest paths, not file paths,
    # but we check if the file is listed there for flexibility
    supersedes = manifest_data.get("supersedes", [])
    if existing_file in supersedes:
        return True

    return False
