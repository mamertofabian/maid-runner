"""
Private helper module for validation orchestration logic.

This module contains internal helpers for breaking down complex validation
workflows into manageable pieces. These are private implementation details
and should not be imported from outside the CLI package.
"""

import json
from pathlib import Path
from typing import List, Optional

import jsonschema

from maid_runner.validation_result import (
    ErrorCode,
    ErrorSeverity,
    ValidationError,
)


def _load_and_validate_manifest_schema(
    manifest_path: Path,
    schema_path: Path,
    errors: List[ValidationError],
) -> Optional[dict]:
    """Load manifest and validate against JSON schema.

    Args:
        manifest_path: Path to the manifest file
        schema_path: Path to the schema file
        errors: List to append errors to

    Returns:
        Manifest data dict if successful, None if validation failed
    """
    from maid_runner.validators.manifest_validator import validate_schema

    try:
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        validate_schema(manifest_data, str(schema_path))
        return manifest_data

    except json.JSONDecodeError as e:
        errors.append(
            ValidationError(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"Invalid JSON in manifest: {e}",
                file=str(manifest_path),
                severity=ErrorSeverity.ERROR,
            )
        )
        return None

    except jsonschema.ValidationError as e:
        errors.append(
            ValidationError(
                code=ErrorCode.SCHEMA_VALIDATION_FAILED,
                message=f"Schema validation failed: {e.message}",
                file=str(manifest_path),
                severity=ErrorSeverity.ERROR,
            )
        )
        return None


def _validate_manifest_semantics(
    manifest_data: dict,
    manifest_path: Path,
    manifests_dir: Path,
    errors: List[ValidationError],
) -> bool:
    """Validate manifest semantics and supersession.

    Args:
        manifest_data: The manifest data dictionary
        manifest_path: Path to the manifest file
        manifests_dir: Path to the manifests directory
        errors: List to append errors to

    Returns:
        True if validation passed, False otherwise
    """
    from maid_runner.validators.semantic_validator import (
        ManifestSemanticError,
        validate_manifest_semantics,
        validate_supersession,
    )

    try:
        validate_manifest_semantics(manifest_data)
    except ManifestSemanticError as e:
        errors.append(
            ValidationError(
                code=ErrorCode.SEMANTIC_VALIDATION_FAILED,
                message=str(e),
                file=str(manifest_path),
                severity=ErrorSeverity.ERROR,
            )
        )
        return False

    try:
        validate_supersession(manifest_data, manifests_dir, manifest_path)
    except ManifestSemanticError as e:
        errors.append(
            ValidationError(
                code=ErrorCode.SUPERSESSION_VALIDATION_FAILED,
                message=str(e),
                file=str(manifest_path),
                severity=ErrorSeverity.ERROR,
            )
        )
        return False

    return True


def _extract_target_file(
    manifest_data: dict,
    manifest_path: Path,
    errors: List[ValidationError],
) -> Optional[str]:
    """Extract the target file path from manifest data.

    Args:
        manifest_data: The manifest data dictionary
        manifest_path: Path to the manifest file
        errors: List to append errors to

    Returns:
        Target file path if found, None otherwise
    """
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    file_path = expected_artifacts.get("file", "")

    if not file_path:
        creatable = manifest_data.get("creatableFiles", [])
        editable = manifest_data.get("editableFiles", [])
        if creatable:
            file_path = creatable[0]
        elif editable:
            file_path = editable[0]

    if not file_path:
        errors.append(
            ValidationError(
                code=ErrorCode.SEMANTIC_VALIDATION_FAILED,
                message="Manifest has no target file to validate (no expectedArtifacts.file, creatableFiles, or editableFiles)",
                file=str(manifest_path),
                severity=ErrorSeverity.ERROR,
            )
        )
        return None

    return file_path


def _check_file_existence(
    file_path: str,
    validation_mode: str,
    manifest_data: dict,
    errors: List[ValidationError],
) -> bool:
    """Check if target file exists for implementation mode.

    Args:
        file_path: Path to the file to check
        validation_mode: The validation mode being used
        manifest_data: The manifest data dictionary
        errors: List to append errors to

    Returns:
        True if check passed, False otherwise
    """
    if validation_mode != "implementation":
        return True

    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    file_status = expected_artifacts.get("status", "present")

    if file_status != "absent" and not Path(file_path).exists():
        errors.append(
            ValidationError(
                code=ErrorCode.ALIGNMENT_ERROR,
                message=f"Target file not found: {file_path}",
                file=file_path,
                severity=ErrorSeverity.ERROR,
            )
        )
        return False

    return True


def _validate_commands_and_test_files(
    manifest_data: dict,
    manifest_path: Path,
    errors: List[ValidationError],
) -> bool:
    """Validate that validation commands and test files exist.

    Args:
        manifest_data: The manifest data dictionary
        manifest_path: Path to the manifest file
        errors: List to append errors to

    Returns:
        True if validation passed, False otherwise
    """
    from maid_runner.cli.validate import (
        _validate_commands_exist,
        _validate_test_files_from_commands,
    )

    validation_commands = manifest_data.get("validationCommands", [])
    if not validation_commands:
        validation_commands = manifest_data.get("validationCommand", [])

    if not validation_commands:
        return True

    # Check commands exist
    all_exist, missing_commands = _validate_commands_exist(manifest_data)
    if not all_exist:
        error_messages = [error_msg for _, error_msg in missing_commands]
        errors.append(
            ValidationError(
                code=ErrorCode.SEMANTIC_VALIDATION_FAILED,
                message=f"Validation command(s) not found in PATH: {', '.join(error_messages)}",
                file=str(manifest_path),
                severity=ErrorSeverity.ERROR,
            )
        )
        return False

    # Check test files exist
    all_exist, missing_test_files = _validate_test_files_from_commands(
        validation_commands
    )
    if not all_exist:
        errors.append(
            ValidationError(
                code=ErrorCode.FILE_NOT_FOUND,
                message=f"Test file(s) not found: {', '.join(missing_test_files)}",
                file=str(manifest_path),
                severity=ErrorSeverity.ERROR,
            )
        )
        return False

    return True


def _perform_ast_validation(
    manifest_data: dict,
    file_path: str,
    use_manifest_chain: bool,
    validation_mode: str,
    use_cache: bool,
    errors: List[ValidationError],
    warnings: List[ValidationError],
    manifest_path: Path,
) -> bool:
    """Perform AST validation and handle alignment errors.

    Args:
        manifest_data: The manifest data dictionary
        file_path: Path to the file to validate
        use_manifest_chain: Whether to use manifest chain
        validation_mode: The validation mode
        use_cache: Whether to use caching
        errors: List to append errors to
        warnings: List to append warnings to
        manifest_path: Path to the manifest file

    Returns:
        True if validation passed, False otherwise
    """
    from maid_runner.validators.manifest_validator import (
        AlignmentError,
        validate_with_ast,
    )
    from maid_runner.cli.validate import (
        _is_latest_manifest_for_file,
        _get_latest_manifest_name,
        _build_new_manifest_hint,
        _build_supersede_hint,
    )

    try:
        validate_with_ast(
            manifest_data,
            file_path,
            use_manifest_chain=use_manifest_chain,
            validation_mode=validation_mode,
            use_cache=use_cache,
        )
        return True

    except AlignmentError as e:
        error_message = str(e)

        # Handle unexpected artifacts with manifest chain
        if "Unexpected public" in error_message and use_manifest_chain and file_path:
            is_latest = _is_latest_manifest_for_file(
                manifest_path, file_path, use_cache
            )

            if not is_latest:
                # Older manifest: Convert to warning and pass
                latest_manifest_name = _get_latest_manifest_name(file_path, use_cache)
                warnings.append(
                    ValidationError(
                        code=ErrorCode.ARTIFACT_NOT_FOUND,
                        message=(
                            f"Validation Warning: {error_message} "
                            f"in the manifest chain. "
                            f"See validation result for {latest_manifest_name} "
                            f"for more details."
                        ),
                        file=getattr(e, "file", None) or file_path,
                        line=getattr(e, "line", None),
                        column=getattr(e, "column", None),
                        severity=ErrorSeverity.WARNING,
                    )
                )
                return True  # Pass with warning
            else:
                # Latest manifest: Fail with new hint
                hint = _build_new_manifest_hint(error_message)
                if hint:
                    error_message += hint
                errors.append(
                    ValidationError(
                        code=ErrorCode.ARTIFACT_NOT_FOUND,
                        message=error_message,
                        file=getattr(e, "file", None) or file_path,
                        line=getattr(e, "line", None),
                        column=getattr(e, "column", None),
                        severity=ErrorSeverity.ERROR,
                    )
                )
                return False
        else:
            # Original behavior for other errors or when not using manifest chain
            hint = _build_supersede_hint(
                manifest_path=manifest_path,
                manifest_data=manifest_data,
                target_file=file_path,
                error_message=error_message,
            )
            if hint:
                error_message += hint
            errors.append(
                ValidationError(
                    code=ErrorCode.ARTIFACT_NOT_FOUND,
                    message=error_message,
                    file=getattr(e, "file", None) or file_path,
                    line=getattr(e, "line", None),
                    column=getattr(e, "column", None),
                    severity=ErrorSeverity.ERROR,
                )
            )
            return False
