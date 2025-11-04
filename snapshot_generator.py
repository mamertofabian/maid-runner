#!/usr/bin/env python3
"""
Snapshot Generator for MAID manifests.

This tool generates consolidated "snapshot" manifests that supersede multiple
historical manifests, providing performance optimization and enabling legacy
code onboarding.

Usage:
    # Generate snapshot for a specific file
    python snapshot_generator.py validators/manifest_validator.py

    # Generate snapshot with custom output path
    python snapshot_generator.py validators/manifest_validator.py -o manifests/task-008-snapshot.json

    # Generate snapshot from legacy code (no existing manifests)
    python snapshot_generator.py src/legacy_module.py --legacy

    # Dry-run mode (validate without saving)
    python snapshot_generator.py validators/manifest_validator.py --dry-run

    # Generate snapshots for all files with >N manifests
    python snapshot_generator.py --all --threshold 5
"""

import argparse
import ast
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from validators.manifest_validator import (
    _get_active_manifests,
    validate_with_ast,
    validate_schema,
)


class SnapshotGenerator:
    """Generates snapshot manifests that consolidate manifest history."""

    def __init__(self, target_file: str, manifests_dir: str = "manifests"):
        """
        Initialize the snapshot generator.

        Args:
            target_file: Path to the file to generate a snapshot for
            manifests_dir: Directory containing manifest files
        """
        self.target_file = Path(target_file)
        self.manifests_dir = Path(manifests_dir)

        if not self.target_file.exists():
            raise FileNotFoundError(f"Target file not found: {target_file}")

    def generate_snapshot(
        self, output_path: Optional[str] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Generate a snapshot manifest for the target file.

        Args:
            output_path: Optional path for the output manifest
            dry_run: If True, generate but don't save the snapshot

        Returns:
            Dictionary containing the snapshot manifest data
        """
        # Find all manifests for this file
        manifest_paths = self._discover_manifests_for_file()

        if not manifest_paths:
            # No existing manifests - treat as legacy code
            return self.generate_legacy_snapshot(output_path, dry_run)

        # Get active (non-superseded) manifests
        active_paths = _get_active_manifests(manifest_paths)

        # Merge artifacts from active manifests
        merged_artifacts = self._merge_artifacts(active_paths)

        # Build snapshot manifest
        snapshot = self._build_snapshot_manifest(
            active_paths, merged_artifacts, manifest_paths
        )

        # Validate snapshot against current implementation
        if not dry_run:
            self._validate_snapshot(snapshot)

        # Save snapshot if not in dry-run mode
        if not dry_run:
            output_file = output_path or self._generate_output_path()
            self._save_snapshot(snapshot, output_file)
            print(f"✓ Snapshot generated: {output_file}")
            print(f"  Supersedes {len(manifest_paths)} manifest(s)")
            print(f"  Contains {len(merged_artifacts)} artifact(s)")

        return snapshot

    def generate_legacy_snapshot(
        self, output_path: Optional[str] = None, dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Generate a snapshot for legacy code with no existing manifests.

        This analyzes the current implementation and generates a manifest
        describing its complete state.

        Args:
            output_path: Optional path for the output manifest
            dry_run: If True, generate but don't save the snapshot

        Returns:
            Dictionary containing the snapshot manifest data
        """
        print(f"Analyzing legacy code: {self.target_file}")

        # Extract artifacts from the implementation
        artifacts = self._extract_artifacts_from_code()

        # Build snapshot manifest
        snapshot = {
            "goal": f"Initial snapshot of {self.target_file} (legacy code onboarding)",
            "taskType": "snapshot",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": [str(self.target_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": str(self.target_file), "contains": artifacts},
            "validationCommand": ["pytest", f"tests/test_{self.target_file.stem}.py", "-v"],
            "snapshotMetadata": {
                "generatedAt": datetime.now(__import__('datetime').UTC).isoformat(),
                "generatedBy": "snapshot-generator",
                "commitHash": self._get_commit_hash(),
                "manifestsSuperseded": 0,
                "isLegacyOnboarding": True,
            },
        }

        # Save snapshot if not in dry-run mode
        if not dry_run:
            output_file = output_path or self._generate_output_path(is_legacy=True)
            self._save_snapshot(snapshot, output_file)
            print(f"✓ Legacy snapshot generated: {output_file}")
            print(f"  Contains {len(artifacts)} artifact(s)")
            print("\nNext steps:")
            print(f"  1. Review generated manifest: {output_file}")
            print(f"  2. Create behavioral tests: tests/test_{self.target_file.stem}.py")
            print(f"  3. Validate: python validate_manifest.py {output_file}")

        return snapshot

    def _build_snapshot_manifest(
        self,
        active_paths: List[str],
        merged_artifacts: List[Dict[str, Any]],
        all_paths: List[str],
    ) -> Dict[str, Any]:
        """
        Build a snapshot manifest from merged artifacts.

        Args:
            active_paths: List of active manifest paths
            merged_artifacts: Merged list of artifacts
            all_paths: All manifest paths (including superseded)

        Returns:
            Snapshot manifest dictionary
        """
        # Determine which manifests to supersede (all that touched this file)
        supersedes = all_paths

        # Get git commit hash
        commit_hash = self._get_commit_hash()

        snapshot = {
            "goal": f"Consolidated snapshot of {self.target_file}",
            "taskType": "snapshot",
            "supersedes": supersedes,
            "creatableFiles": [],
            "editableFiles": [str(self.target_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": str(self.target_file), "contains": merged_artifacts},
            "validationCommand": self._generate_validation_command(),
            "snapshotMetadata": {
                "generatedAt": datetime.now(__import__('datetime').UTC).isoformat(),
                "generatedBy": "snapshot-generator",
                "commitHash": commit_hash,
                "manifestsSuperseded": len(supersedes),
            },
        }

        return snapshot

    def _extract_artifacts_from_code(self) -> List[Dict[str, Any]]:
        """
        Extract artifacts from Python code using AST analysis.

        Returns:
            List of artifact dictionaries
        """
        with open(self.target_file, "r") as f:
            code = f.read()

        tree = ast.parse(code)
        extractor = ArtifactExtractor()
        extractor.visit(tree)

        return extractor.artifacts

    def _validate_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """
        Validate the snapshot manifest against current implementation.

        Args:
            snapshot: Snapshot manifest dictionary

        Raises:
            Exception: If validation fails
        """
        # Validate against schema
        schema_path = "validators/schemas/manifest.schema.json"
        validate_schema(snapshot, schema_path)

        # Validate against implementation (using permissive mode for editableFiles)
        validate_with_ast(snapshot, str(self.target_file), use_manifest_chain=False)

    def _generate_validation_command(self) -> List[str]:
        """
        Generate appropriate validation command for the target file.

        Returns:
            List of command components
        """
        # Try to find existing test file
        test_file = Path(f"tests/test_{self.target_file.stem}.py")

        if test_file.exists():
            return ["pytest", str(test_file), "-v"]
        else:
            # Generic test command
            return ["pytest", f"tests/test_{self.target_file.stem}.py", "-v"]

    def _generate_output_path(self, is_legacy: bool = False) -> str:
        """
        Generate output path for the snapshot manifest.

        Args:
            is_legacy: Whether this is a legacy code snapshot

        Returns:
            Path string for the output manifest
        """
        # Find next available task number
        existing_manifests = sorted(self.manifests_dir.glob("task-*.manifest.json"))

        if existing_manifests:
            # Extract task numbers
            task_numbers = []
            for manifest in existing_manifests:
                name = manifest.stem  # e.g., "task-007a-description"
                parts = name.split("-")
                if len(parts) >= 2:
                    # Extract numeric part (e.g., "007" or "007a")
                    task_num_str = parts[1]
                    # Remove letter suffixes for comparison
                    numeric_part = "".join(c for c in task_num_str if c.isdigit())
                    if numeric_part:
                        task_numbers.append(int(numeric_part))

            next_number = max(task_numbers) + 1 if task_numbers else 1
        else:
            next_number = 1

        # Format task number
        task_id = f"task-{next_number:03d}"

        # Generate descriptive name
        file_stem = self.target_file.stem.replace("_", "-")
        suffix = "legacy-snapshot" if is_legacy else "snapshot"

        filename = f"{task_id}-{file_stem}-{suffix}.manifest.json"
        return str(self.manifests_dir / filename)

    def _save_snapshot(self, snapshot: Dict[str, Any], output_path: str) -> None:
        """
        Save snapshot manifest to file.

        Args:
            snapshot: Snapshot manifest dictionary
            output_path: Path to save the manifest
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w") as f:
            json.dump(snapshot, f, indent=2)
            f.write("\n")  # Add trailing newline

    def _discover_manifests_for_file(self) -> List[str]:
        """
        Discover all manifests that touch the target file.

        Returns:
            List of manifest paths in chronological order
        """
        manifests = []

        if not self.manifests_dir.exists():
            return manifests

        # Get all JSON files and sort numerically by task number
        manifest_files = list(self.manifests_dir.glob("*.json"))

        def _get_task_number(path):
            """Extract task number from filename like task-XXX-description.json"""
            stem = path.stem
            # Handle .manifest.json files by removing .manifest suffix
            if stem.endswith(".manifest"):
                stem = stem[:-9]  # Remove '.manifest' suffix

            if stem.startswith("task-"):
                try:
                    # Split by '-' and get the number part (second element)
                    parts = stem.split("-")
                    if len(parts) >= 2:
                        # Extract numeric part from strings like "007a"
                        numeric_part = "".join(c for c in parts[1] if c.isdigit())
                        if numeric_part:
                            return int(numeric_part)
                except (ValueError, IndexError):
                    pass
            return float("inf")  # Put non-task files at the end

        # Sort manifest files numerically
        manifest_files.sort(key=_get_task_number)

        for manifest_path in manifest_files:
            with open(manifest_path, "r") as f:
                data = json.load(f)

            # Check if this manifest touches the target file
            created_files = data.get("creatableFiles", [])
            edited_files = data.get("editableFiles", [])
            expected_file = data.get("expectedArtifacts", {}).get("file")

            # Normalize paths for comparison
            target_str = str(self.target_file)

            # Check both the lists and the expected file
            if (
                target_str in created_files
                or target_str in edited_files
                or target_str == expected_file
            ):
                manifests.append(str(manifest_path))

        return manifests

    def _merge_artifacts(self, manifest_paths: List[str]) -> List[Dict[str, Any]]:
        """
        Merge expected artifacts from multiple manifests.

        Args:
            manifest_paths: List of paths to manifest files

        Returns:
            Merged list of expected artifacts
        """
        merged_artifacts = []
        seen_artifacts = {}  # Track (type, name, class) -> artifact

        for path in manifest_paths:
            with open(path, "r") as f:
                data = json.load(f)

            artifacts = data.get("expectedArtifacts", {}).get("contains", [])

            for artifact in artifacts:
                # Use (type, name, class) as unique key
                artifact_type = artifact.get("type")
                artifact_name = artifact.get("name")
                artifact_class = artifact.get("class")  # For methods/attributes
                key = (artifact_type, artifact_name, artifact_class)

                # Add if not seen, or always update (later manifests override earlier ones)
                seen_artifacts[key] = artifact

        # Return artifacts in a consistent order
        merged_artifacts = list(seen_artifacts.values())
        return merged_artifacts

    def _get_commit_hash(self) -> str:
        """
        Get current git commit hash.

        Returns:
            Git commit hash or "unknown" if not in a git repo
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"


class ArtifactExtractor(ast.NodeVisitor):
    """AST visitor that extracts artifacts from Python code."""

    def __init__(self):
        self.artifacts = []
        self.current_class = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition."""
        # Only track public classes
        if not node.name.startswith("_"):
            artifact = {
                "type": "class",
                "name": node.name,
            }

            # Extract base classes
            if node.bases:
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(self._get_qualified_name(base))

                if bases:
                    artifact["bases"] = bases

            self.artifacts.append(artifact)

        # Visit methods within the class
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        # Only track public functions/methods
        if not node.name.startswith("_"):
            artifact = {
                "type": "function",
                "name": node.name,
            }

            # If inside a class, it's a method
            if self.current_class:
                artifact["class"] = self.current_class

            # Extract parameters (skip self/cls)
            params = []
            for arg in node.args.args:
                if arg.arg not in ("self", "cls"):
                    param = {"name": arg.arg}
                    # Extract type annotation if present
                    if arg.annotation:
                        param["type"] = self._get_type_annotation(arg.annotation)
                    params.append(param)

            if params:
                artifact["parameters"] = params

            # Extract return type
            if node.returns:
                artifact["returns"] = self._get_type_annotation(node.returns)

            self.artifacts.append(artifact)

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit assignment (for module-level and class attributes)."""
        for target in node.targets:
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                # Module-level attribute
                if self.current_class is None:
                    self.artifacts.append({
                        "type": "attribute",
                        "name": target.id,
                    })
            elif isinstance(target, ast.Attribute) and self.current_class:
                # Class attribute
                if not target.attr.startswith("_"):
                    self.artifacts.append({
                        "type": "attribute",
                        "name": target.attr,
                        "class": self.current_class,
                    })

        self.generic_visit(node)

    def _get_type_annotation(self, node: ast.AST) -> str:
        """Convert AST type annotation to string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Attribute):
            return self._get_qualified_name(node)
        elif isinstance(node, ast.Subscript):
            value = self._get_type_annotation(node.value)
            slice_val = self._get_type_annotation(node.slice)
            return f"{value}[{slice_val}]"
        elif isinstance(node, ast.Tuple):
            elements = [self._get_type_annotation(elt) for elt in node.elts]
            return f"({', '.join(elements)})"
        elif isinstance(node, ast.List):
            elements = [self._get_type_annotation(elt) for elt in node.elts]
            return f"[{', '.join(elements)}]"
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            # Python 3.10+ union syntax (X | Y)
            left = self._get_type_annotation(node.left)
            right = self._get_type_annotation(node.right)
            return f"{left} | {right}"
        else:
            return "Any"

    def _get_qualified_name(self, node: ast.Attribute) -> str:
        """Get fully qualified name from attribute node."""
        parts = []
        current = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)

        return ".".join(reversed(parts))


def generate_all_snapshots(threshold: int = 10, dry_run: bool = False) -> None:
    """
    Generate snapshots for all files with more than threshold manifests.

    Args:
        threshold: Minimum number of manifests to trigger snapshot generation
        dry_run: If True, show what would be generated without saving
    """
    manifests_dir = Path("manifests")

    # Find all manifest files
    all_manifests = list(manifests_dir.glob("task-*.manifest.json"))

    # Group by target file
    files_to_manifests = {}
    for manifest_path in all_manifests:
        with open(manifest_path, "r") as f:
            data = json.load(f)

        # Get target file from expectedArtifacts
        target_file = data.get("expectedArtifacts", {}).get("file")
        if target_file:
            if target_file not in files_to_manifests:
                files_to_manifests[target_file] = []
            files_to_manifests[target_file].append(str(manifest_path))

    # Generate snapshots for files exceeding threshold
    for target_file, manifests in files_to_manifests.items():
        if len(manifests) >= threshold:
            print(f"\n{'='*60}")
            print(f"File: {target_file}")
            print(f"Manifests: {len(manifests)}")

            if dry_run:
                print("  [DRY RUN] Would generate snapshot")
            else:
                try:
                    generator = SnapshotGenerator(target_file)
                    generator.generate_snapshot(dry_run=False)
                except Exception as e:
                    print(f"  ✗ Error: {e}")


def main():
    """Main entry point for the snapshot generator CLI."""
    parser = argparse.ArgumentParser(
        description="Generate consolidated snapshot manifests for MAID projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "target_file",
        nargs="?",
        help="Path to the file to generate a snapshot for",
    )

    parser.add_argument(
        "-o",
        "--output",
        help="Output path for the snapshot manifest",
    )

    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Generate snapshot for legacy code (no existing manifests)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate snapshot without saving (validation only)",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate snapshots for all files with many manifests",
    )

    parser.add_argument(
        "--threshold",
        type=int,
        default=10,
        help="Minimum manifest count for --all mode (default: 10)",
    )

    args = parser.parse_args()

    # Handle --all mode
    if args.all:
        generate_all_snapshots(args.threshold, args.dry_run)
        return

    # Require target_file if not in --all mode
    if not args.target_file:
        parser.error("target_file is required unless using --all")

    # Generate snapshot for specific file
    try:
        generator = SnapshotGenerator(args.target_file)

        if args.legacy:
            generator.generate_legacy_snapshot(args.output, args.dry_run)
        else:
            generator.generate_snapshot(args.output, args.dry_run)

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
