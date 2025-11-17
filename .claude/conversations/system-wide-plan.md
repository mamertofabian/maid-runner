Implementation Plan: GitHub Issue #84 - System-Wide Manifest Snapshot Generator

MAID Workflow Overview

Following MAID methodology with phases: Planning Loop → Implementation → Refactoring → Integration

---
Phase 1: Schema Extension for System Manifests

Task 1.1: Extend Manifest Schema
- File: validators/schemas/manifest.schema.json
- Changes:
  - Add new optional field: systemArtifacts (array of artifact blocks)
  - Each block has file (string) and contains (array of artifacts)
  - Make expectedArtifacts optional when systemArtifacts is present
  - Add schema validation: only ONE of expectedArtifacts or systemArtifacts allowed
  - Add taskType: "system-snapshot" as new valid value

Rationale: Prevents regular manifests from using systemArtifacts for multi-file features (which must be multi-manifest per MAID specs).

---
Phase 2: Core System Snapshot Generation

Task 2.1: Manifest Discovery & Filtering
- New Module: maid_runner/cli/snapshot_system.py
- Function: discover_active_manifests(manifest_dir: Path) -> List[Path]
  - Scan all *.manifest.json files in manifest directory
  - Build supersedes graph to identify active vs superseded manifests
  - Return only active (non-superseded) manifests in chronological order
  - Reuse: get_superseded_manifests() from utils.py

Task 2.2: Artifact Aggregation
- Function: aggregate_system_artifacts(manifest_paths: List[Path]) -> List[Dict]
  - Load each active manifest
  - Extract expectedArtifacts from each
  - Group artifacts by source file
  - Create artifact blocks: [{"file": "path/to/file.py", "contains": [...]}, ...]
  - Handle manifests with multiple files (merge all into system view)

Task 2.3: Validation Command Aggregation
- Function: aggregate_validation_commands(manifest_paths: List[Path]) -> List[List[str]]
  - Collect all validation commands from active manifests
  - Normalize using normalize_validation_commands() from utils
  - Deduplicate: convert to set of tuples, back to list
  - Return deduplicated command list

Task 2.4: System Manifest Creation
- Function: create_system_manifest(artifacts: List[Dict], commands: List[List[str]]) -> Dict
  - Create manifest structure with:
      - goal: "System-wide manifest snapshot aggregated from all active manifests"
    - taskType: "system-snapshot"
    - systemArtifacts: aggregated artifact blocks
    - validationCommands: deduplicated commands
    - readonlyFiles: [] (system view has no specific readonly files)
    - supersedes: [] (system snapshot doesn't supersede anything)
  - Output follows extended schema

Task 2.5: CLI Integration
- Update: maid_runner/cli/main.py
- Add snapshot-system subcommand with arguments:
  - --output (default: system.manifest.json)
  - --manifest-dir (default: manifests/)
  - --quiet flag
- Function: run_snapshot_system(output: Path, manifest_dir: Path, quiet: bool)
  - Orchestrate: discover → aggregate artifacts → aggregate commands → create manifest → write file
  - Display summary (files processed, artifacts found, commands aggregated)

---
Phase 3: Validation Support

Task 3.1: Validator Updates
- Update: maid_runner/validators/manifest_validator.py
- Function: _validate_system_manifest_schema(manifest: Dict)
  - Check: systemArtifacts is present and expectedArtifacts is NOT
  - Validate structure of each artifact block in systemArtifacts
  - Integration with existing validate_manifest_schema()

Task 3.2: Make System Manifest Validatable
- Ensure maid validate system.manifest.json works:
  - Schema validation: ✓ (via Task 3.1)
  - Behavioral validation: SKIP for system manifests (no single file to test)
  - Implementation validation: SKIP for system manifests (aggregate view)
- Add special handling in validator for taskType: "system-snapshot"

---
Phase 4: Testing

Test Coverage >90% Required

Task 4.1: Unit Tests
- tests/test_task_XXX_snapshot_system_discovery.py
  - Test manifest discovery with supersedes chains
  - Test filtering of superseded manifests
  - Edge cases: circular supersedes, missing manifests

Task 4.2: Integration Tests
- tests/test_task_XXX_snapshot_system_aggregation.py
  - Test artifact aggregation from multiple manifests
  - Test validation command deduplication
  - Test system manifest creation with various artifact types

Task 4.3: CLI Tests
- tests/test_task_XXX_snapshot_system_cli.py
  - Test maid snapshot-system command execution
  - Test output file creation
  - Test quiet mode
  - Test custom manifest directory

Task 4.4: Validation Tests
- tests/test_task_XXX_snapshot_system_validation.py
  - Test that generated system manifest validates successfully
  - Test schema validation with systemArtifacts
  - Test error handling for invalid system manifests

---
Phase 5: Documentation

Task 5.1: Update CLI Help
- Add comprehensive help text for maid snapshot-system
- Include examples and use cases

Task 5.2: Update README/Docs
- Document system snapshot feature in main README
- Add to MAID methodology documentation
- Include example workflow

---
Implementation Order (MAID Phases)

Phase 1: Planning Loop (Iterative)
1. Create manifest for Task 1.1 (schema extension)
2. Write tests for schema extension
3. Run maid validate on manifest
4. Refine manifest + tests until validation passes
5. Repeat for Tasks 2.1-2.5, 3.1-3.2

Phase 2: Implementation
1. Implement schema extension (Task 1.1)
2. Implement core functions (Tasks 2.1-2.5)
3. Implement validator updates (Tasks 3.1-3.2)
4. Run tests, iterate until all pass

Phase 3: Refactoring
- Code quality improvements
- Performance optimization
- API refinement

Phase 4: Integration
- Full test suite execution
- Documentation updates
- Final validation

---
Key Design Decisions (Based on User Answers)

✓ Schema: New systemArtifacts array field (system-manifest only)
✓ Supersedes: Only active manifests included
✓ Validation Commands: Deduplicated only
✓ CLI: maid snapshot-system subcommand

---
Success Criteria

- maid snapshot-system command working
- Aggregates all active manifests correctly
- Output has systemArtifacts with per-file artifact blocks
- System manifest validates with maid validate
- Superseded manifests excluded
- Validation commands deduplicated
- Test coverage >90%
- Documentation complete

---
Estimated Effort

- Schema extension: 1 day
- Core implementation: 3-4 days
- Testing: 2-3 days
- Documentation: 1 day
- Total: ~7-9 days (1.5-2 weeks)

This matches the issue's 2-3 week estimate with buffer for refinement and edge cases.
