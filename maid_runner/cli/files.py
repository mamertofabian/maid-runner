#!/usr/bin/env python3
"""CLI module for 'maid files' command.

This module provides file-level tracking status without requiring full validation.
It shows which files are UNDECLARED, REGISTERED, or TRACKED in the manifest chain.
"""

import json
from pathlib import Path
from typing import Optional, List

from maid_runner.validators.file_tracker import (
    FileTrackingAnalysis,
    analyze_file_tracking,
)


def format_files_output(
    analysis: FileTrackingAnalysis,
    issues_only: bool,
    status_filter: Optional[str],
    quiet: bool,
) -> None:
    """Format file tracking results for human-readable output.

    Args:
        analysis: FileTrackingAnalysis dictionary with file status data
        issues_only: If True, only show undeclared and registered files
        status_filter: If set, only show files with this status (undeclared, registered, tracked)
        quiet: If True, produce machine-readable output without decorative elements
    """
    undeclared = analysis.get("undeclared", [])
    registered = analysis.get("registered", [])
    tracked = analysis.get("tracked", [])

    # Apply status filter if specified
    if status_filter:
        status_lower = status_filter.lower()
        if status_lower == "undeclared":
            registered = []
            tracked = []
        elif status_lower == "registered":
            undeclared = []
            tracked = []
        elif status_lower == "tracked":
            undeclared = []
            registered = []

    # Apply issues_only filter
    if issues_only:
        tracked = []

    # Output
    if quiet:
        # Machine-readable output - simple format without decorations
        for file_info in undeclared:
            print(f"UNDECLARED\t{file_info['file']}")
        for file_info in registered:
            print(f"REGISTERED\t{file_info['file']}")
        for file_path in tracked:
            print(f"TRACKED\t{file_path}")
    else:
        # Human-readable output with decorations
        if undeclared:
            print()
            print("=" * 60)
            print(f"UNDECLARED FILES ({len(undeclared)} files)")
            print("=" * 60)
            for file_info in undeclared:
                print(f"  {file_info['file']}")
                for issue in file_info.get("issues", []):
                    print(f"    - {issue}")

        if registered:
            print()
            print("=" * 60)
            print(f"REGISTERED FILES ({len(registered)} files)")
            print("=" * 60)
            for file_info in registered:
                print(f"  {file_info['file']}")
                for issue in file_info.get("issues", []):
                    print(f"    - {issue}")
                manifests = file_info.get("manifests", [])
                if manifests:
                    print(f"    Manifests: {', '.join(manifests[:3])}")

        if tracked:
            print()
            print("=" * 60)
            print(f"TRACKED FILES ({len(tracked)} files)")
            print("=" * 60)
            for file_path in tracked:
                print(f"  {file_path}")

        # Summary
        total = len(undeclared) + len(registered) + len(tracked)
        if total > 0:
            print()
            print(
                f"Summary: {len(undeclared)} undeclared, {len(registered)} registered, {len(tracked)} tracked"
            )


def format_files_json(
    analysis: FileTrackingAnalysis,
    issues_only: bool,
    status_filter: Optional[str],
) -> str:
    """Format file tracking results as JSON output.

    Args:
        analysis: FileTrackingAnalysis dictionary with file status data
        issues_only: If True, only include undeclared and registered files
        status_filter: If set, only include files with this status

    Returns:
        JSON string with filtered file tracking data
    """
    result = {}

    undeclared = analysis.get("undeclared", [])
    registered = analysis.get("registered", [])
    tracked = analysis.get("tracked", [])

    # Apply status filter if specified
    if status_filter:
        status_lower = status_filter.lower()
        if status_lower == "undeclared":
            result["undeclared"] = undeclared
        elif status_lower == "registered":
            result["registered"] = registered
        elif status_lower == "tracked":
            result["tracked"] = tracked
    else:
        # Apply issues_only filter
        if issues_only:
            result["undeclared"] = undeclared
            result["registered"] = registered
            # Don't include tracked when issues_only is True
        else:
            result["undeclared"] = undeclared
            result["registered"] = registered
            result["tracked"] = tracked

    return json.dumps(result, indent=2)


def run_files(
    manifest_dir: str,
    issues_only: bool,
    status_filter: Optional[str],
    quiet: bool,
    json_output: bool,
) -> None:
    """Main entry point for the 'maid files' command.

    Args:
        manifest_dir: Directory containing manifest files
        issues_only: If True, only show undeclared and registered files
        status_filter: If set, only show files with this status
        quiet: If True, produce machine-readable output
        json_output: If True, output as JSON
    """
    manifests_path = Path(manifest_dir)

    # Load manifests
    manifest_chain: List[dict] = []
    if manifests_path.exists():
        for manifest_file in sorted(manifests_path.glob("task-*.manifest.json")):
            try:
                with open(manifest_file, "r") as f:
                    manifest_data = json.load(f)
                    manifest_data["_filename"] = manifest_file.name
                    manifest_chain.append(manifest_data)
            except (json.JSONDecodeError, IOError):
                # Skip invalid manifests
                continue

    # Determine source root (parent of manifest dir or current dir)
    if manifests_path.exists():
        source_root = str(manifests_path.parent.resolve())
    else:
        source_root = str(Path.cwd())

    # Analyze file tracking
    analysis = analyze_file_tracking(manifest_chain, source_root)

    # Output results
    if json_output:
        output = format_files_json(analysis, issues_only, status_filter)
        print(output)
    else:
        format_files_output(analysis, issues_only, status_filter, quiet)
