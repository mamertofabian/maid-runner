# MAID Validate Hardening Backlog

## Purpose

This document records confirmed `maid validate` loopholes that can let an AI agent claim MAID compliance without satisfying the real validation intent. The goal is to make the validator fail closed, produce automation-safe exit codes, and resist selective reporting of only the green parts of the workflow.

MAID's core contract is:

1. The manifest declares the intended file and artifact boundary.
2. Behavioral tests prove the declared artifacts are exercised.
3. Implementation validation proves the code defines the declared artifacts.
4. The chain, coherence checks, file tracking, and validation commands make the result hard to game.

The findings below focus on places where that contract can currently be weakened.

## Confirmed Loopholes

### 1. Empty Manifest Discovery Exits Green

**Scenario:** Running `maid validate --quiet` in a project with no `manifests/` directory returned exit code `0`.

**Why this matters:** An agent can validate the wrong working directory, omit manifests entirely, or point `--manifest-dir` at a missing path and still report success.

**Code path:** `maid_runner/core/validate.py` returns an empty successful `BatchValidationResult` when the manifest directory does not exist.

**Closure shape:** Make missing or empty manifest discovery fail closed by default. Add an explicit `--allow-empty` or library option for bootstrap-only workflows that intentionally validate an empty manifest set.

### 2. `maid validate` Does Not Execute `validate:` Commands

**Scenario:** A manifest with `validate: python -c "raise SystemExit(42)"` passed `maid validate`, while `maid test --manifest ...` failed.

**Why this matters:** `maid validate` can prove structural alignment while the actual behavioral command is red. An agent can report `maid validate` as the done gate and omit `maid test`.

**Code path:** `validate:` commands are used for test file discovery, but command execution is owned by `maid test`.

**Closure shape:** Add a combined strict gate command, or add `maid validate --run-tests` / `maid verify` that runs schema, behavioral, implementation, coherence, file tracking, and manifest test commands as one automation-safe gate.

### 3. Behavioral Validation Accepts Tests With No Assertions

**Scenario:** A test that only called the artifact, with no assertion, passed `maid validate --mode behavioral`.

**Why this matters:** This satisfies "artifact is referenced" without proving observable behavior. It is a low-effort way for an agent to make behavioral validation green with weak tests.

**Code path:** Assertion checking exists as `check_assertions=True` in the engine, but the CLI does not expose it and the default path does not enforce it.

**Closure shape:** Add a CLI flag for assertion checks, include it in strict mode, and consider making assertion presence mandatory for feature/fix/refactor manifests.

### 4. Untested Artifacts Are Warnings in Implementation Mode

**Scenario:** A manifest passed implementation validation with `E200 Artifact 'greet' not referenced in any test file` as a warning.

**Why this matters:** A public artifact can be declared and implemented while missing behavioral coverage, yet the command still exits `0`.

**Code path:** `_check_test_coverage` emits `ARTIFACT_NOT_USED_IN_TESTS` as `Severity.WARNING`.

**Closure shape:** Promote E200 to an error for non-snapshot feature, fix, and refactor manifests. If warning behavior is still useful interactively, put it behind a permissive or advisory mode.

### 5. File Paths Can Escape the Project Root

**Scenario:** A manifest with `path: ../outside.py` passed implementation validation against a file outside the project root.

**Why this matters:** A manifest can validate files outside the repository, bypassing the intended project boundary and weakening auditability.

**Code path:** Normal `files.create`, `files.edit`, `files.snapshot`, `files.read`, and `files.delete` paths are joined with `project_root` without the containment checks already used by `removed_artifacts`.

**Closure shape:** Add a shared project-relative path validator for every manifest path field. Reject absolute paths, parent-relative escapes, and normalized paths outside the project root.

### 6. Duplicate YAML Keys Are Silently Overwritten

**Scenario:** A manifest with two top-level `files:` keys passed schema validation; YAML loading kept only the later key.

**Why this matters:** A manifest can appear to declare one contract to a reviewer while the parser validates a different contract. This is a direct review and audit-integrity risk.

**Code path:** `load_manifest_raw` uses `yaml.safe_load`, which does not reject duplicate mapping keys.

**Closure shape:** Use a YAML loader that rejects duplicate keys with a manifest parse error. Add tests for duplicate top-level and nested keys.

### 7. Undeclared Production Files Do Not Fail `maid validate`

**Scenario:** A project with `src/backdoor.py` outside all manifests passed `maid validate`; `maid files --json` reported the file as undeclared but exited `0`.

**Why this matters:** An agent can add unmanifested production code and still pass the primary validation command.

**Code path:** File tracking is separate from `maid validate`; `run_file_tracking` reports undeclared files but does not act as a failing validation gate.

**Closure shape:** Add `maid validate --file-tracking` or include file tracking in strict mode. Make `maid files --fail-on undeclared` available for CI and agent workflows.

### 8. `maid validate --coherence` Does Not Affect Exit Status

**Scenario:** A forced coherence error printed `Coherence: FAIL`, but `maid validate --coherence` still exited `0`.

**Why this matters:** Automation sees success even when architectural coherence fails. An agent can quote the green structural status and ignore the printed coherence failure.

**Code path:** `cmd_validate` prints coherence after structural success but returns only the structural validation result. `_print_coherence` also swallows coherence exceptions.

**Closure shape:** Make `--coherence` participate in the exit code. Stop swallowing coherence exceptions; represent them as structured validation failures or command errors.

## Gradual Closure Backlog

1. Fail closed on missing or empty manifest discovery unless explicitly allowed.
2. Make `--coherence` affect `maid validate` exit status and stop swallowing coherence exceptions.
3. Enforce project-root containment for every manifest path field.
4. Reject duplicate YAML mapping keys during manifest loading.
5. Add strict mode that turns validator warnings into failures.
6. Promote E200 test-coverage misses to errors for feature, fix, and refactor manifests.
7. Expose assertion and stub checks in the CLI and include them in strict mode.
8. Add a worktree scope gate: changed production files must be declared in `files.create`, `files.edit`, or `files.delete`.
9. Add failing file-tracking options for undeclared and read-only-only production files.
10. Add a combined `maid verify` or equivalent done gate that runs structural validation, behavioral validation, implementation validation, coherence, file tracking, and manifest test commands together.

## Suggested Acceptance Criteria

For each closure item, include adversarial tests that prove the old gaming path fails:

- The command exits non-zero.
- JSON output reports a structured error code.
- Text output names the exact file, manifest, or command that caused failure.
- The failure cannot be bypassed by selecting only one validation mode unless the user explicitly chooses an advisory/permissive mode.

## Verification Notes

The scenarios were exercised with throwaway projects under `/tmp` using the local CLI entry point. Repo schema validation was also checked with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run maid validate --mode schema --quiet
```

That command passed.
