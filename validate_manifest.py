#!/usr/bin/env python3
"""
Command-line interface for MAID manifest validation.

This script provides a clean CLI for validating manifests against implementation
or behavioral test files using the enhanced AST validator.
"""

import argparse
import json
import sys
from pathlib import Path

from validators.manifest_validator import validate_with_ast, AlignmentError


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate manifest against implementation or behavioral test files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate implementation (default mode)
  %(prog)s manifests/task-001.manifest.json

  # Validate behavioral test usage
  %(prog)s manifests/task-001.manifest.json --validation-mode behavioral

  # Use manifest chain for complex validation
  %(prog)s manifests/task-001.manifest.json --use-manifest-chain

  # Combined behavioral + manifest chain
  %(prog)s manifests/task-001.manifest.json --validation-mode behavioral --use-manifest-chain

Validation Modes:
  implementation  - Validates that code DEFINES the expected artifacts (default)
  behavioral      - Validates that tests USE/CALL the expected artifacts

This enables MAID Phase 2 validation: manifest ↔ behavioral test alignment!
        """,
    )

    parser.add_argument("manifest_path", help="Path to the manifest JSON file")

    parser.add_argument(
        "--validation-mode",
        choices=["implementation", "behavioral"],
        default="implementation",
        help="Validation mode: 'implementation' (default) checks definitions, 'behavioral' checks usage",
    )

    parser.add_argument(
        "--use-manifest-chain",
        action="store_true",
        help="Use manifest chain to merge all related manifests",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only output errors (suppress success messages)",
    )

    args = parser.parse_args()

    try:
        # Validate manifest file exists
        manifest_path = Path(args.manifest_path)
        if not manifest_path.exists():
            print(f"✗ Error: Manifest file not found: {args.manifest_path}")
            sys.exit(1)

        # Load the manifest
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        # Get the file to validate from the manifest
        file_path = manifest_data.get("expectedArtifacts", {}).get("file")
        if not file_path:
            print("✗ Error: No file specified in manifest's expectedArtifacts.file")
            sys.exit(1)

        # Validate target file exists
        if not Path(file_path).exists():
            print(f"✗ Error: Target file not found: {file_path}")
            sys.exit(1)

        # Perform validation
        validate_with_ast(
            manifest_data,
            file_path,
            use_manifest_chain=args.use_manifest_chain,
            validation_mode=args.validation_mode,
        )

        # Success message
        if not args.quiet:
            print(f"✓ Validation PASSED ({args.validation_mode} mode)")
            if args.use_manifest_chain:
                print("  Used manifest chain for validation")
            print(f"  Manifest: {args.manifest_path}")
            print(f"  Target:   {file_path}")

    except AlignmentError as e:
        print(f"✗ Validation FAILED: {e}")
        if not args.quiet:
            print(f"  Manifest: {args.manifest_path}")
            print(f"  Mode:     {args.validation_mode}")
        sys.exit(1)

    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in manifest file: {e}")
        sys.exit(1)

    except FileNotFoundError as e:
        print(f"✗ Error: File not found: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        if not args.quiet:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
