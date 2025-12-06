"""Private module for schema validation and system manifest helpers."""

# AlignmentError will be imported lazily to avoid circular imports


def _is_system_manifest(manifest_data: dict) -> bool:
    """Check if a manifest is a system manifest.

    System manifests aggregate artifacts from multiple files and use the
    systemArtifacts field instead of expectedArtifacts. They are generated
    by the snapshot-system command and have taskType "system-snapshot".

    Args:
        manifest_data: Dictionary containing the manifest data

    Returns:
        True if the manifest has systemArtifacts field (system manifest),
        False otherwise (regular manifest)

    Example:
        >>> regular_manifest = {"expectedArtifacts": {...}}
        >>> _is_system_manifest(regular_manifest)
        False

        >>> system_manifest = {"systemArtifacts": [{...}]}
        >>> _is_system_manifest(system_manifest)
        True
    """
    return "systemArtifacts" in manifest_data


def _validate_system_artifacts_structure(manifest_data: dict) -> None:
    """Validate the structure of systemArtifacts in a system manifest.

    Performs additional validation beyond JSON schema validation to ensure
    systemArtifacts blocks are properly structured with required fields.

    Args:
        manifest_data: Dictionary containing the manifest data

    Raises:
        AlignmentError: If systemArtifacts structure is invalid

    Validates:
        - systemArtifacts is an array
        - Each artifact block has 'file' and 'contains' fields
        - 'contains' is an array
        - Each artifact has 'type' and 'name' fields

    Example:
        >>> valid_manifest = {
        ...     "systemArtifacts": [
        ...         {"file": "test.py", "contains": [{"type": "function", "name": "f"}]}
        ...     ]
        ... }
        >>> _validate_system_artifacts_structure(valid_manifest)  # No error

        >>> invalid_manifest = {"systemArtifacts": "not an array"}
        >>> _validate_system_artifacts_structure(invalid_manifest)
        AlignmentError: systemArtifacts must be an array
    """
    # Skip validation for non-system manifests
    if not _is_system_manifest(manifest_data):
        return

    system_artifacts = manifest_data.get("systemArtifacts")

    # Validate systemArtifacts is an array
    if not isinstance(system_artifacts, list):
        from maid_runner.validators.manifest_validator import AlignmentError

        raise AlignmentError(
            "systemArtifacts must be an array of artifact blocks. "
            f"Got {type(system_artifacts).__name__} instead."
        )

    # Validate each artifact block
    for i, artifact_block in enumerate(system_artifacts):
        # Validate block is a dict
        if not isinstance(artifact_block, dict):
            from maid_runner.validators.manifest_validator import AlignmentError

            raise AlignmentError(
                f"Artifact block at index {i} must be an object/dict. "
                f"Got {type(artifact_block).__name__} instead."
            )

        # Validate 'file' field exists
        if "file" not in artifact_block:
            from maid_runner.validators.manifest_validator import AlignmentError

            raise AlignmentError(
                f"Artifact block at index {i} missing required 'file' field. "
                f"Each block must specify which file it describes."
            )

        file_path = artifact_block.get("file")

        # Validate 'contains' field exists
        if "contains" not in artifact_block:
            from maid_runner.validators.manifest_validator import AlignmentError

            raise AlignmentError(
                f"Artifact block at index {i} (file: '{file_path}') missing required 'contains' field. "
                f"Each block must have a 'contains' array of artifacts."
            )

        contains = artifact_block.get("contains")

        # Validate 'contains' is an array
        if not isinstance(contains, list):
            from maid_runner.validators.manifest_validator import AlignmentError

            raise AlignmentError(
                f"Artifact block for '{file_path}': 'contains' field must be an array. "
                f"Got {type(contains).__name__} instead."
            )

        # Validate each artifact in contains
        for j, artifact in enumerate(contains):
            if not isinstance(artifact, dict):
                from maid_runner.validators.manifest_validator import AlignmentError

                raise AlignmentError(
                    f"Artifact block for '{file_path}': artifact at index {j} must be an object/dict. "
                    f"Got {type(artifact).__name__} instead."
                )

            # Validate artifact has 'type' field
            if "type" not in artifact:
                from maid_runner.validators.manifest_validator import AlignmentError

                raise AlignmentError(
                    f"Artifact block for '{file_path}': artifact at index {j} missing required 'type' field. "
                    f"Each artifact must have a type (function, class, attribute, etc.)."
                )

            # Validate artifact has 'name' field
            if "name" not in artifact:
                from maid_runner.validators.manifest_validator import AlignmentError

                raise AlignmentError(
                    f"Artifact block for '{file_path}': artifact at index {j} (type: '{artifact.get('type')}') "
                    f"missing required 'name' field. Each artifact must have a name."
                )


def _should_skip_behavioral_validation(manifest_data: dict) -> bool:
    """Determine if behavioral validation should be skipped for this manifest.

    Behavioral validation checks that test files exist and properly USE the
    declared artifacts. For system manifests, there is no single test file
    to validate - they aggregate artifacts from multiple files. Therefore,
    behavioral validation should be skipped for system manifests.

    Args:
        manifest_data: Dictionary containing the manifest data

    Returns:
        True if behavioral validation should be skipped (system manifest),
        False otherwise (regular manifest should undergo behavioral validation)

    Example:
        >>> system_manifest = {"systemArtifacts": [{...}]}
        >>> _should_skip_behavioral_validation(system_manifest)
        True

        >>> regular_manifest = {"expectedArtifacts": {...}}
        >>> _should_skip_behavioral_validation(regular_manifest)
        False
    """
    return _is_system_manifest(manifest_data)


def _should_skip_implementation_validation(manifest_data: dict) -> bool:
    """Determine if implementation validation should be skipped for this manifest.

    Implementation validation checks that code files exist and properly DEFINE
    the declared artifacts. For system manifests, there is no single implementation
    file to validate - they aggregate artifacts from multiple existing files.
    Therefore, implementation validation should be skipped for system manifests.

    Args:
        manifest_data: Dictionary containing the manifest data

    Returns:
        True if implementation validation should be skipped (system manifest),
        False otherwise (regular manifest should undergo implementation validation)

    Example:
        >>> system_manifest = {"systemArtifacts": [{...}]}
        >>> _should_skip_implementation_validation(system_manifest)
        True

        >>> regular_manifest = {"expectedArtifacts": {...}}
        >>> _should_skip_implementation_validation(regular_manifest)
        False
    """
    return _is_system_manifest(manifest_data)
