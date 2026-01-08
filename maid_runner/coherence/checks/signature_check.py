"""Signature conflict detection for coherence validation.

This module checks for artifacts with the same name but different signatures
(arguments, return types) across the system. It compares artifacts from a
manifest against system_artifacts and returns CoherenceIssue with
IssueType.SIGNATURE_CONFLICT for any conflicts found.

Functions:
    check_signature_conflicts: Main function that checks for signature conflicts
    _extract_artifact_signature: Helper to extract signature string from artifact
    _compare_signatures: Helper to compare two signature strings

Usage:
    from maid_runner.coherence.checks.signature_check import check_signature_conflicts

    issues = check_signature_conflicts(
        manifest_data=manifest,
        system_artifacts=aggregated_artifacts,
    )
"""

from typing import Dict, List

from maid_runner.coherence.result import CoherenceIssue, IssueSeverity, IssueType


def check_signature_conflicts(
    manifest_data: dict,
    system_artifacts: List[Dict],
) -> List[CoherenceIssue]:
    """Check for signature conflicts between manifest artifacts and system artifacts.

    Examines the manifest's expectedArtifacts and checks if any of them
    have the same name and type as existing system artifacts but with
    different signatures (arguments or return types).

    Args:
        manifest_data: The manifest data dictionary to check.
        system_artifacts: List of artifacts aggregated from all existing manifests.
            Each artifact is a dict with "name", "type", "file", and optionally
            "args" and "returns" keys.

    Returns:
        List of CoherenceIssue instances for any signature conflicts found.
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

    # Check each artifact for signature conflicts
    for artifact in contains:
        artifact_name = artifact.get("name")
        artifact_type = artifact.get("type")

        # Skip if missing name
        if not artifact_name:
            continue

        # Find matching artifacts in system artifacts (same name and type)
        for system_artifact in system_artifacts:
            system_name = system_artifact.get("name")
            system_type = system_artifact.get("type")

            # Check if name and type match
            if system_name != artifact_name:
                continue

            # If types differ, skip (not a signature conflict, different things)
            if artifact_type and system_type and artifact_type != system_type:
                continue

            # If one has type and other doesn't, skip comparison
            if not artifact_type or not system_type:
                continue

            # Extract signatures
            new_signature = _extract_artifact_signature(artifact)
            existing_signature = _extract_artifact_signature(system_artifact)

            # Compare signatures
            if not _compare_signatures(new_signature, existing_signature):
                # Signature conflict detected
                existing_file = system_artifact.get("file", "unknown file")
                issue = CoherenceIssue(
                    issue_type=IssueType.SIGNATURE_CONFLICT,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Signature conflict for {artifact_type} '{artifact_name}': "
                        f"new signature '{new_signature}' differs from existing "
                        f"signature '{existing_signature}' in '{existing_file}'"
                    ),
                    suggestion=(
                        f"Review the signature of '{artifact_name}' and align it with "
                        f"the existing definition in '{existing_file}', or ensure this "
                        f"is an intentional override"
                    ),
                    location=existing_file,
                )
                issues.append(issue)

    return issues


def _extract_artifact_signature(artifact: dict) -> str:
    """Extract a signature string from an artifact.

    Combines the artifact's args and returns into a signature string like
    "(arg1: str, arg2: int) -> bool".

    Args:
        artifact: Dictionary containing artifact information with optional
            "args" (list of {"name": str, "type": str}) and "returns" (str).

    Returns:
        A signature string representation. Empty string if no signature info.
    """
    args = artifact.get("args", [])
    returns = artifact.get("returns", "")

    # Format args
    arg_parts = []
    for arg in args:
        arg_name = arg.get("name", "")
        arg_type = arg.get("type", "")
        if arg_name and arg_type:
            arg_parts.append(f"{arg_name}: {arg_type}")
        elif arg_name:
            arg_parts.append(arg_name)
        elif arg_type:
            arg_parts.append(f": {arg_type}")

    args_str = f"({', '.join(arg_parts)})"

    # Format return type
    if returns:
        return f"{args_str} -> {returns}"
    else:
        return args_str


def _compare_signatures(new_sig: str, existing_sig: str) -> bool:
    """Compare two signature strings for compatibility.

    Compares signatures after stripping whitespace. Returns True if signatures
    match or both are empty.

    Args:
        new_sig: The new signature string to compare.
        existing_sig: The existing signature string to compare against.

    Returns:
        True if signatures match or are compatible, False if they conflict.
    """
    # Strip whitespace from both
    new_stripped = new_sig.strip()
    existing_stripped = existing_sig.strip()

    # Both empty is considered matching
    if new_stripped == "" and existing_stripped == "":
        return True

    # One empty and one not is a mismatch
    if new_stripped == "" or existing_stripped == "":
        return False

    # Direct comparison
    return new_stripped == existing_stripped
