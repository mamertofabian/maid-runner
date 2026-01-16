"""
Private helper module for text-mode validation logic.

This module contains the text-based validation workflow that was previously
embedded in the run_validation() function. This is private implementation
and should not be imported from outside the CLI package.
"""

import json
import sys
from pathlib import Path

import jsonschema

from maid_runner.validators.manifest_validator import (
    validate_schema,
    validate_with_ast,
    AlignmentError,
)
from maid_runner.validators.semantic_validator import (
    ManifestSemanticError,
    validate_manifest_semantics,
    validate_supersession,
)
from maid_runner.validators.file_tracker import analyze_file_tracking


def _run_behavioral_validation(
    manifest_data: dict,
    validation_commands: list,
    use_manifest_chain: bool,
    quiet: bool,
) -> None:
    """Run behavioral validation for test files.

    Args:
        manifest_data: The manifest data dictionary
        validation_commands: List of validation commands
        use_manifest_chain: Whether to use manifest chain
        quiet: Whether to suppress output
    """
    from maid_runner.cli.validate import (
        _validate_commands_exist,
        _validate_test_files_from_commands,
        extract_test_files_from_command,
        validate_behavioral_tests,
    )

    if not validation_commands:
        if not quiet:
            print("⚠ Warning: No validationCommand specified for behavioral validation")
        return

    # Validate that validation commands exist in PATH
    all_exist, missing_commands = _validate_commands_exist(manifest_data)
    if not all_exist:
        print("✗ Error: Validation command(s) not found in PATH:", file=sys.stderr)
        for _, error_msg in missing_commands:
            print(f"  - {error_msg}", file=sys.stderr)
        sys.exit(1)

    # Validate test files exist
    all_exist, missing_test_files = _validate_test_files_from_commands(
        validation_commands
    )
    if not all_exist:
        print(f"✗ Error: Test file(s) not found: {', '.join(missing_test_files)}")
        sys.exit(1)

    test_files = extract_test_files_from_command(validation_commands)
    if test_files:
        if not quiet:
            print("Running behavioral test validation...")
        validate_behavioral_tests(
            manifest_data,
            test_files,
            use_manifest_chain=use_manifest_chain,
            quiet=quiet,
        )
        if not quiet:
            print("✓ Behavioral test validation PASSED")
    else:
        if not quiet:
            print("⚠ Warning: No test files found in validationCommand")


def _check_file_existence_with_hint(
    file_path: str,
    file_status: str,
    manifest_path: str,
) -> None:
    """Check if target file exists and show helpful hint if missing.

    Args:
        file_path: Path to the file to check
        file_status: Status from expectedArtifacts ('present' or 'absent')
        manifest_path: Path to the manifest for error messages
    """
    if file_status != "absent" and not Path(file_path).exists():
        print(f"✗ Error: Target file not found: {file_path}")
        print()
        print(
            "⚠️  Hint: If you're validating a manifest before implementing the code (MAID Phase 2),"
        )
        print("   you should use behavioral validation to check the test structure:")
        print()
        print(f"   uv run maid validate {manifest_path} --validation-mode behavioral")
        print()
        print("   Implementation validation requires the target file to exist.")
        sys.exit(1)


def _display_file_tracking_analysis(
    use_manifest_chain: bool,
    validation_mode: str,
    skip_file_tracking: bool,
    quiet: bool,
) -> None:
    """Display file tracking analysis if appropriate.

    Args:
        use_manifest_chain: Whether manifest chain is being used
        validation_mode: The validation mode
        skip_file_tracking: Whether to skip file tracking
        quiet: Whether to suppress output
    """
    from maid_runner.cli.validate import _format_file_tracking_output

    if (
        not use_manifest_chain
        or validation_mode != "implementation"
        or skip_file_tracking
    ):
        return

    try:
        manifests_dir = Path("manifests")
        if not manifests_dir.exists():
            return

        manifest_chain = []
        for manifest_file in sorted(manifests_dir.glob("task-*.manifest.json")):
            with open(manifest_file, "r") as f:
                manifest_data = json.load(f)
                manifest_data["_filename"] = manifest_file.name
                manifest_chain.append(manifest_data)

        source_root = str(Path.cwd())
        analysis = analyze_file_tracking(manifest_chain, source_root)
        _format_file_tracking_output(analysis, quiet=quiet)

    except Exception as e:
        if not quiet:
            print(f"\n⚠️  File tracking analysis failed: {e}")


def _print_success_message(
    validation_mode: str,
    use_manifest_chain: bool,
    manifest_path: str,
    file_path: str,
    manifest_data: dict,
    quiet: bool,
) -> None:
    """Print validation success message and metadata.

    Args:
        validation_mode: The validation mode used
        use_manifest_chain: Whether manifest chain was used
        manifest_path: Path to the manifest
        file_path: Path to the validated file
        manifest_data: The manifest data dictionary
        quiet: Whether to suppress output
    """
    if quiet:
        return

    print(f"✓ Validation PASSED ({validation_mode} mode)")

    if use_manifest_chain:
        is_snapshot = manifest_data.get("taskType") == "snapshot"
        if is_snapshot:
            print("  Snapshot manifest (chain skipped)")
        else:
            print("  Used manifest chain for validation")

    print(f"  Manifest: {manifest_path}")
    print(f"  Target:   {file_path}")

    # Display metadata if present
    metadata = manifest_data.get("metadata")
    if metadata:
        if metadata.get("author"):
            print(f"  Author:   {metadata['author']}")
        if metadata.get("tags"):
            tags_str = ", ".join(metadata["tags"])
            print(f"  Tags:     {tags_str}")
        if metadata.get("priority"):
            print(f"  Priority: {metadata['priority']}")


def run_text_mode_validation(
    manifest_path: str,
    validation_mode: str,
    use_manifest_chain: bool,
    quiet: bool,
    skip_file_tracking: bool,
    use_cache: bool,
) -> None:
    """Run validation in text output mode.

    This is the main text-based validation workflow extracted from run_validation().
    It handles manifest loading, schema validation, semantic validation, and
    mode-specific validation logic.

    Args:
        manifest_path: Path to the manifest JSON file
        validation_mode: Validation mode ('implementation', 'behavioral', or 'schema')
        use_manifest_chain: If True, use manifest chain for validation
        quiet: If True, suppress success messages
        skip_file_tracking: If True, skip file tracking analysis
        use_cache: If True, enable manifest chain caching

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """
    from maid_runner.cli.validate import (
        _check_if_superseded,
        _build_supersede_hint,
        _build_new_manifest_hint,
        _is_latest_manifest_for_file,
        _get_latest_manifest_name,
    )
    from maid_runner.utils import validate_manifest_version
    from maid_runner.validators.manifest_validator import (
        _should_skip_behavioral_validation,
        _should_skip_implementation_validation,
    )

    try:
        # Validate manifest file exists
        manifest_path_obj = Path(manifest_path)
        if not manifest_path_obj.exists():
            print(f"✗ Error: Manifest file not found: {manifest_path}")
            sys.exit(1)

        # Check if superseded
        manifests_dir = manifest_path_obj.parent
        is_superseded, superseding_manifest = _check_if_superseded(
            manifest_path_obj, manifests_dir
        )
        if is_superseded:
            if not quiet:
                superseding_name = (
                    superseding_manifest.name
                    if superseding_manifest
                    else "another manifest"
                )
                print(
                    f"⏭️  This manifest has been superseded by {superseding_name} "
                    f"and is excluded from active validation."
                )
            return

        # Load manifest
        with open(manifest_path_obj, "r") as f:
            manifest_data = json.load(f)

        # Validate JSON schema
        schema_path = (
            Path(__file__).parent.parent
            / "validators"
            / "schemas"
            / "manifest.schema.json"
        )
        try:
            validate_schema(manifest_data, str(schema_path))
        except jsonschema.ValidationError as e:
            print("✗ Error: Manifest validation failed", file=sys.stderr)
            print(f"  {e.message}", file=sys.stderr)
            if e.path:
                path_str = ".".join(str(p) for p in e.path)
                print(f"  Location: {path_str}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print(f"✗ Error: Schema file not found at {schema_path}", file=sys.stderr)
            sys.exit(1)

        # Validate MAID semantics
        try:
            validate_manifest_semantics(manifest_data)
        except ManifestSemanticError as e:
            print("✗ Error: Manifest semantic validation failed", file=sys.stderr)
            print(f"\n{e}", file=sys.stderr)
            sys.exit(1)

        # Validate supersession
        try:
            validate_supersession(manifest_data, manifests_dir, manifest_path_obj)
        except ManifestSemanticError as e:
            print("✗ Error: Supersession validation failed", file=sys.stderr)
            print(f"\n{e}", file=sys.stderr)
            sys.exit(1)

        # Validate version field
        try:
            validate_manifest_version(manifest_data, manifest_path_obj.name)
        except ValueError as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            sys.exit(1)

        # Schema-only mode early exit
        if validation_mode == "schema":
            if not quiet:
                print("✓ Manifest validation PASSED (schema-only mode)")
                print("  Schema, semantic, and version validation completed")
            return

        # Check if system manifest
        skip_behavioral = _should_skip_behavioral_validation(manifest_data)
        skip_implementation = _should_skip_implementation_validation(manifest_data)

        if skip_behavioral and skip_implementation:
            if not quiet:
                print("✓ System manifest validation PASSED (schema validation only)")
                print(
                    "  System manifests aggregate multiple files; no single implementation to validate"
                )
            return

        # Validate snapshot manifests have validation commands
        validation_command = manifest_data.get("validationCommand", [])
        validation_commands = manifest_data.get("validationCommands", [])
        has_validation = bool(validation_command or validation_commands)

        if manifest_data.get("taskType") == "snapshot" and not has_validation:
            print(
                f"✗ Error: Snapshot manifest {manifest_path_obj.name} must have a comprehensive "
                f"validationCommand or validationCommands that tests all artifacts. Snapshot manifests document the "
                f"complete current state and must validate all artifacts."
            )
            sys.exit(1)

        # Get target file
        file_path = manifest_data.get("expectedArtifacts", {}).get("file")
        if not file_path:
            print("✗ Error: No file specified in manifest's expectedArtifacts.file")
            sys.exit(1)

        # Normalize file path
        if "/" in file_path and not Path(file_path).exists():
            project_name = Path.cwd().name
            if file_path.startswith(f"{project_name}/"):
                potential_normalized = file_path[len(project_name) + 1 :]
                if Path(potential_normalized).exists():
                    file_path = potential_normalized

        # Get validation commands
        validation_commands = manifest_data.get("validationCommands", [])
        if not validation_commands:
            validation_commands = manifest_data.get("validationCommand", [])

        # Mode-specific validation
        if validation_mode == "behavioral":
            _run_behavioral_validation(
                manifest_data, validation_commands, use_manifest_chain, quiet
            )
        else:
            # Implementation mode
            expected_artifacts = manifest_data.get("expectedArtifacts", {})
            file_status = expected_artifacts.get("status", "present")

            _check_file_existence_with_hint(file_path, file_status, manifest_path)

            # Also run behavioral validation if commands present
            _run_behavioral_validation(
                manifest_data, validation_commands, use_manifest_chain, quiet
            )

            # Run AST validation
            validate_with_ast(
                manifest_data,
                file_path,
                use_manifest_chain=use_manifest_chain,
                validation_mode=validation_mode,
                use_cache=use_cache,
            )

        # Print success message
        _print_success_message(
            validation_mode,
            use_manifest_chain,
            manifest_path,
            file_path,
            manifest_data,
            quiet,
        )

        # Display file tracking analysis
        _display_file_tracking_analysis(
            use_manifest_chain, validation_mode, skip_file_tracking, quiet
        )

    except AlignmentError as e:
        error_message = str(e)
        manifest_path_obj = Path(manifest_path)

        # Handle unexpected artifacts with manifest chain
        if "Unexpected public" in error_message and use_manifest_chain and file_path:
            is_latest = _is_latest_manifest_for_file(
                manifest_path_obj, file_path, use_cache
            )

            if not is_latest:
                latest_manifest_name = _get_latest_manifest_name(file_path, use_cache)
                print(
                    f"✗ Validation Warning: {error_message} "
                    f"in the manifest chain. "
                    f"See validation result for {latest_manifest_name} "
                    f"for more details."
                )
                if not quiet:
                    print(f"  Manifest: {manifest_path}")
                    print(f"  Mode:     {validation_mode}")
                    print("  ✅ PASSED")
                return
            else:
                hint = _build_new_manifest_hint(error_message)
                if hint:
                    error_message += hint
                print(f"✗ Validation FAILED: {error_message}")
                if not quiet:
                    print(f"  Manifest: {manifest_path}")
                    print(f"  Mode:     {validation_mode}")
                sys.exit(1)
        else:
            hint = _build_supersede_hint(
                manifest_path=manifest_path_obj,
                manifest_data=manifest_data,
                target_file=file_path,
                error_message=error_message,
            )
            if hint:
                error_message += hint
            print(f"✗ Validation FAILED: {error_message}")
            if not quiet:
                print(f"  Manifest: {manifest_path}")
                print(f"  Mode:     {validation_mode}")
            sys.exit(1)

    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in manifest file: {e}")
        sys.exit(1)

    except FileNotFoundError as e:
        print(f"✗ Error: File not found: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        if not quiet:
            import traceback

            traceback.print_exc()
        sys.exit(1)
