# CLAUDE.md

**⚠️ CRITICAL: This project dogfoods MAID v1.3. Every code change MUST follow the MAID workflow.**

**Note on Documentation Changes:** Pure documentation changes (modifying only `.md` files with no code artifacts) may be exempt from the full MAID workflow, but should still be reviewed for accuracy and consistency. When in doubt, create a manifest.

## MAID Workflow (Required for ALL changes)

### Phase 1: Goal Definition
Confirm the high-level goal with user before proceeding.

### Phase 2: Planning Loop
**Before ANY implementation - iterative refinement:**
1. Draft manifest (`manifests/task-XXX.manifest.json`) - **PRIMARY CONTRACT**
2. Draft behavioral tests (`tests/test_task_XXX_*.py`) to support and verify the manifest
3. Run behavioral validation (checks that tests USE declared artifacts):
   `uv run maid validate manifests/task-XXX.manifest.json --validation-mode behavioral --use-manifest-chain`
4. Refine BOTH tests & manifest together until validation passes

### Phase 3: Implementation
1. Load ONLY files from manifest (`editableFiles` + `readonlyFiles`)
2. Implement code to pass tests
3. Run implementation validation (checks that code DEFINES declared artifacts):
   `uv run maid validate manifests/task-XXX.manifest.json --validation-mode implementation --use-manifest-chain`
4. Run behavioral tests (from `validationCommand`)
5. Iterate until all validations and tests pass

### Phase 3.5: Refactoring
1. After tests pass, improve code quality
2. Maintain public API and manifest compliance
3. Apply clean code principles and patterns
4. Validate tests still pass after each change

### Phase 4: Integration
1. Verify all manifests: `uv run maid validate`
2. Run all MAID tests: `uv run maid test`
3. Run full test suite: `uv run python -m pytest tests/ -v`

## External MAID Automation Examples

**Note:** MAID Runner is a validation-only tool. The automation examples below are external tools that use MAID Runner for validation. They are NOT part of MAID Runner itself.

Example Claude Code configurations demonstrating MAID automation are available in `docs/future/claude-code-integration/`. These show how external tools can build automation on top of MAID Runner:

### Example Automation Agents (External):
1. **maid-manifest-architect** - Phase 1: Creates and validates manifests
2. **maid-test-designer** - Phase 2: Creates behavioral tests from manifests
3. **maid-developer** - Phase 3: Implements code to pass tests
4. **maid-refactorer** - Phase 3.5: Improves code quality (completes TDD cycle)
5. **maid-auditor** - Cross-cutting: Enforces strict MAID compliance across all phases

**These are examples only.** MAID Runner itself provides validation tools via the `maid` CLI (`maid validate`, `maid snapshot`). External tools (Claude Code, custom agents, IDEs) use these CLI commands to build automation workflows.

See `docs/future/claude-code-integration/README.md` for details on building your own automation.

**Note:** The MAID workflow embodies TDD at two levels:
- **Planning Loop**: Iterative test-manifest refinement (micro TDD)
- **Overall Workflow**: Red (failing tests) → Green (passing implementation) → Refactor (quality improvement)

## Project Overview

MAID Runner implements and enforces the Manifest-driven AI Development (MAID) methodology from `docs/maid_specs.md`. It validates that code artifacts match their declarative manifests, ensuring AI-generated code aligns with architectural specifications through strict chronological tracking.

## Architecture

### Core Components

1. **Manifest Validator** (CLI: `maid validate`)
   - Validates manifest JSON against schema
   - Behavioral test validation: Verifies tests USE declared artifacts
   - Implementation validation: Verifies code DEFINES artifacts
   - Enforces manifest chain chronology

2. **Manifest Schema** (`validators/schemas/manifest.schema.json`)
   - Defines the required structure for task manifests
   - Artifact types: class, function, attribute, parameter

3. **Manifest Files** (`manifests/`)
   - Chronologically ordered task records
   - Current task's manifest can be modified during active development; all prior tasks' manifests are immutable
   - Sequential naming: task-001, task-002, task-003, etc.
   - Each represents a single atomic change

4. **Development Tools**
   - `Makefile`: Convenience commands for development workflow
   - `maid test`: TDD runner with watch mode support
   - Enables building MAID tools using MAID methodology

### Key MAID Principles in This Codebase

- **Explicitness**: Every task context is explicitly defined in manifests
- **Extreme Isolation**: Tasks touch minimal files, specified in manifest
- **Test-Driven Validation**: Tests define success, not subjective assessment
- **Verifiable Chronology**: Current state = sequential manifest application

## Key Rules

**NEVER:** Modify code without manifest | Skip validation | Access unlisted files
**ALWAYS:** Manifest first → Tests → Implementation → Validate

## Refactoring Private Implementation

MAID provides flexibility for refactoring private implementation details without requiring new manifests:

- **Private code** (functions, classes, variables with `_` prefix) can be refactored freely
- **Internal logic changes** that don't affect the public API are allowed
- **Code quality improvements** (splitting functions, extracting helpers, renaming privates) are permitted

**Requirements:**
- All tests must continue to pass (`make test`, `uv run maid test`)
- All validations must pass (`uv run maid validate`)
- Public API must remain unchanged (no changes to public functions, classes, or signatures)
- No MAID rules are violated

This breathing room allows practical development without bureaucracy while maintaining accountability for public interface changes.

**For complete methodology details**, see `docs/maid_specs.md`.

## Testing Standards

All tests must follow the unit testing rules defined in `docs/unit-testing-rules.md`. Key principles:
- Test behavior, not implementation details
- Minimize mocking to essential dependencies
- Make tests deterministic and independent
- Test for failure conditions, not just happy paths
- Keep tests simple, readable, and maintainable

See `docs/unit-testing-rules.md` for complete guidelines on writing effective unit tests.

## Documentation Standards

**Focus on current state, not temporal comparisons:**

**NEVER use in documentation or code:**
- ❌ Temporal markers: "NEW", "⭐", "UPDATED", "ADDED", "LATEST"
- ❌ Temporal comparisons: "Before/After", "What's Missing", "What We Currently Have"
- ❌ Marketing language: "Exciting new feature", "Now available", "Just released"
- ❌ Date-based qualifiers: "As of today", "Recently added", "Coming soon"

**ALWAYS:**
- ✅ State facts clearly: "System supports X", "Feature Y validates Z"
- ✅ Use present tense: "This validates", not "This will validate"
- ✅ Document current capabilities: "The system provides", not "We've added"
- ✅ Let git history track changes

**Rationale:** Git history handles temporal tracking. Documentation should describe the current state objectively. We're building technical documentation, not marketing pages.

**If temporal context is needed:** User will explicitly request it. Otherwise, omit it.

## Validation Flow

The `maid validate` command supports two validation modes:

### Behavioral Mode (`--validation-mode behavioral`)
**Use during Phase 2 (Planning Loop) when writing tests**

1. **Schema Validation**: Ensures manifest follows the JSON schema
2. **Behavioral Test Validation**: Verifies test files USE the declared artifacts (AST-based)

Note: Behavioral validation only checks artifacts from the current manifest, not the merged chain.

### Implementation Mode (`--validation-mode implementation`, default)
**Use during Phase 3 (Implementation) when writing code**

1. **Schema Validation**: Ensures manifest follows the JSON schema
2. **Implementation Validation**: Verifies code DEFINES the declared artifacts
3. **File Tracking Analysis** (when using `--use-manifest-chain`): Detects undeclared and partially compliant files

### File Tracking Analysis

When using `--use-manifest-chain` in implementation mode, MAID Runner performs automatic file tracking analysis with a two-level warning system:

- **🔴 UNDECLARED** (High Priority): Files exist in codebase but not in any manifest
  - No audit trail of when/why created
  - **Action**: Add to `creatableFiles` or `editableFiles` in a manifest

- **🟡 REGISTERED** (Medium Priority): Files in manifests but incomplete compliance
  - Issues: Missing `expectedArtifacts`, no tests, or only in `readonlyFiles`
  - **Action**: Add `expectedArtifacts` and `validationCommand` for full compliance

- **✓ TRACKED** (Clean): Files with full MAID compliance
  - Properly documented with artifacts and behavioral tests

This progressive compliance system helps identify accountability gaps and supports gradual migration to MAID.

## Validation Modes (MAID v1.3)

- **Strict Mode** (`creatableFiles`): Implementation must EXACTLY match `expectedArtifacts`
- **Permissive Mode** (`editableFiles`): Implementation must CONTAIN `expectedArtifacts` (allows existing code)

## Manifest Template

**⚠️ CRITICAL: `expectedArtifacts` is an OBJECT, not an array!**

- `expectedArtifacts` defines artifacts for **ONE file only**
- For multi-file tasks: Create **separate manifests** for each file
- Structure: `{"file": "...", "contains": [...]}`
- **NOT** an array of file objects

```json
{
  "goal": "Clear task description",
  "taskType": "edit|create|refactor",
  "supersedes": [],  // Optional: paths to obsolete manifests
  "creatableFiles": [],  // New files (Strict Mode)
  "editableFiles": [],   // Existing files (Permissive Mode)
  "readonlyFiles": [],   // Dependencies and tests
  "expectedArtifacts": {
    "file": "path/to/file.py",  // ← Single file path
    "contains": [                // ← Array of artifacts for THIS file
      {
        "type": "function|class|attribute",
        "name": "artifact_name",
        "class": "ParentClass",  // For methods/attributes
        "args": [{"name": "arg1", "type": "str"}],  // For functions
        "returns": "ReturnType"  // Optional
      }
    ]
  },
  "validationCommand": ["pytest tests/test_file.py -v"]
}
```

## MAID CLI Commands

**IMPORTANT: Always use the `maid` CLI for validation and snapshots, NOT direct Python scripts.**

### Whole-Codebase Validation (Recommended)

```bash
# Validate ALL active manifests with proper chaining
# Automatically excludes superseded manifests and uses manifest chain
uv run maid validate

# Run ALL validation commands from all active manifests
# Intelligent enough to exclude inactive manifests
uv run maid test
```

**These commands are the primary way to verify complete MAID compliance across the entire codebase.**

### Individual Commands

```bash
# Validate a specific manifest (with optional manifest chain)
uv run maid validate <manifest-path> [--use-manifest-chain] [--quiet]

# Generate a snapshot manifest from existing code
uv run maid snapshot <file-path> [--output-dir <dir>]

# Generate system-wide manifest aggregating all active manifests
uv run maid snapshot-system [--output <file>] [--manifest-dir <dir>] [--quiet]

# List manifests that reference a file
uv run maid manifests <file-path> [--manifest-dir <dir>] [--quiet]

# Run validation commands from specific manifests
uv run maid test [--manifest-dir <dir>] [--fail-fast] [--verbose]

# Watch mode: Single-manifest watch (re-run tests on file changes)
uv run maid test --manifest <manifest-path> --watch

# Watch mode: Multi-manifest watch (run affected tests on changes)
uv run maid test --watch-all

# Get help
uv run maid --help
uv run maid validate --help
uv run maid snapshot --help
uv run maid snapshot-system --help
uv run maid manifests --help
uv run maid test --help
```

## Quick Commands

```bash
# Whole-Codebase Validation (Primary Commands)
uv run maid validate     # Validate ALL active manifests with proper chaining
uv run maid test         # Run ALL validation commands from active manifests
make test                # Run full pytest suite

# Watch Mode (Live TDD workflow)
uv run maid test --manifest manifests/task-XXX.manifest.json --watch  # Single-manifest watch
uv run maid test --watch-all                                          # Multi-manifest watch

# Development Shortcuts (Makefile)
make dev TASK=005        # Run tests once for task-005
make watch TASK=005      # Watch mode with auto-test for task-005
make validate            # Validate all manifests with chain

# Find next manifest number
ls manifests/task-*.manifest.json | tail -1

# Individual Task Validation Flow
# 1. During Planning: Behavioral validation (checks tests USE artifacts)
uv run maid validate manifests/task-XXX.manifest.json --validation-mode behavioral --use-manifest-chain

# 2. During Implementation: Implementation validation (checks code DEFINES artifacts)
uv run maid validate manifests/task-XXX.manifest.json --validation-mode implementation --use-manifest-chain

# 3. Behavioral test execution (run actual tests)
uv run python -m pytest tests/test_task_XXX_*.py -v

# Note: Each validation mode runs schema validation first, then:
#   - behavioral mode: Verifies test files USE the declared artifacts
#   - implementation mode: Verifies code DEFINES the artifacts + file tracking analysis

# Code quality
make lint        # Run black formatter
make type-check  # Run mypy type checking
make format      # Auto-fix formatting issues
```

## Artifact Rules

- **Public** (no `_` prefix): MUST be in manifest
- **Private** (`_` prefix): Optional in manifest
- **creatableFiles**: Strict validation (exact match)
- **editableFiles**: Permissive validation (contains at least)

## Superseded Manifests and Test Execution

**Critical Behavior:** When a manifest is superseded, it is completely excluded from MAID operations:

- `uv run maid validate` ignores superseded manifests when merging manifest chains
- `uv run maid test` does NOT execute `validationCommand` from superseded manifests
- Superseded manifests serve as historical documentation only—they are archived, not active

**Why this matters:** If you supersede a manifest, its tests will no longer run. This is by design—superseded manifests represent obsolete contracts that have been replaced.

## Transitioning from Snapshots to Natural Evolution

**Key Insight:** Snapshot manifests are for "frozen" code. Once code needs to evolve, you must transition to the natural MAID flow.

### The Pattern

1. **Snapshot Phase** (Initial baseline):
   - Use `maid snapshot` to capture complete public API of existing code
   - `taskType: "snapshot"` declares ALL functions/classes at that point in time

2. **Transition Manifest** (First evolution):
   - When file needs changes, create an edit manifest that:
     - Declares ALL current functions (existing + new)
     - Supersedes the snapshot manifest
     - Uses `taskType: "edit"` (not "snapshot")
   - This is the bridge from frozen state to natural evolution

3. **Future Evolution** (Natural MAID flow):
   - Subsequent manifests only declare NEW changes
   - With `--use-manifest-chain`, validator merges all active manifests
   - No need to update previous manifests when adding new APIs

### Example Evolution

```
File history: src/service.py

task-015-snapshot-service.manifest.json (snapshot)
├─ Declares: func_1, func_2, func_3
└─ Status: SUPERSEDED by task-123

task-123-add-new-feature.manifest.json (edit, supersedes task-015)
├─ Declares: func_1, func_2, func_3, new_func  // ALL current functions
└─ Supersedes: ["task-015-snapshot-service.manifest.json"]

task-126-another-feature.manifest.json (edit)
└─ Declares: another_func  // Only the new addition

With --use-manifest-chain:
  Merged = task-123 + task-126
  = {func_1, func_2, func_3, new_func, another_func} ✅
```

### Why This Pattern Works

- **Snapshot** = baseline for static/legacy code
- **Transition manifest** = comprehensive edit that supersedes snapshot, declares complete current state
- **Natural flow** = incremental edits leveraging manifest chaining
- **Future manifests** can add APIs without touching previous manifests

### Key Rules

- Once you supersede a snapshot with a comprehensive edit manifest, continue using incremental edit manifests
- Don't create new snapshots unless establishing a new "checkpoint" baseline
- The transition manifest must be comprehensive (list ALL current functions), but future edits can be incremental

## File Deletion Pattern

When removing a file tracked by MAID: Create refactor manifest → Supersede creation manifest → Delete file and tests → Validate deletion.

**Manifest**: `taskType: "refactor"`, supersedes original, `status: "absent"` in expectedArtifacts

**Validation**: File deleted, tests deleted, no remaining imports

## File Rename Pattern

When renaming a file tracked by MAID: Create refactor manifest → Supersede creation manifest → Use `git mv` → Update manifest → Validate rename.

**Manifest**: `taskType: "refactor"`, supersedes original, new filename in `creatableFiles`, same API in `expectedArtifacts` under new location

**Validation**: Old file deleted, new file exists with working functionality, no old imports, git history preserved

**Key difference from deletion**: Rename maintains module's public API continuity under new location.

## Key Reminders

- This codebase **IS** the MAID implementation - exemplify the methodology
- Manifest chain = source of truth for file state
- Manifest = contract; tests support implementation and verification
- Every change needs a manifest with sequential numbering
- **Manifest immutability**: Current task's manifest can be modified during active development; all prior tasks' manifests are immutable
- **One file per manifest**: `expectedArtifacts` defines artifacts for ONE file only; multi-file changes require separate manifests

## Lessons Learned: Handling Prerequisite Discovery

### The Challenge (Task-007)
When implementing Task-007 (Type Definitions Module), we discovered that the validator couldn't detect module-level attributes like type aliases (`ManifestData = Dict[str, Any]`). The `_ArtifactCollector` only tracked class attributes and function definitions, not module-level assignments.

### The MAID-Compliant Solution

**What NOT to do:**
- ❌ Create workarounds in tests (artificial assertions)
- ❌ Document limitations and continue
- ❌ Modify the manifest to hide the problem

**The Correct Approach:**
1. **Stash Current Work**: `git stash` Task-007 implementation
2. **Create Prerequisite Task**: Task-006a to fix the validator
3. **Complete Prerequisite**: Full MAID workflow for Task-006a
4. **Restore and Complete**: Task-007 now works cleanly

### Task Numbering Strategy

When discovering prerequisites mid-task, use alphabetic suffixes:
- Task-006a, Task-006b, etc. for discovered prerequisites
- Preserves original task numbers (Task-007 remains Task-007)
- Maintains clean chronological ordering

### Key Principle: No Partial Solutions

**Every task must complete fully with all validations passing.** If validation fails, either:
1. Fix the test (if test is wrong)
2. Fix the implementation (if implementation is wrong)
3. Fix the prerequisite (if system limitation discovered)

Never leave a task partially complete or with failing validations.

### The Pattern for Prerequisite Discovery

```bash
# 1. Discovery Phase
> Implement Task-N
> Run validation
> ❌ Validation fails due to system limitation

# 2. Stash and Fix Phase
git stash push -m "Task-N implementation"
> Create Task-(N-1)a: Fix the limitation
> Complete Task-(N-1)a with full MAID workflow

# 3. Restore and Complete Phase
git stash pop
> Run validation again
> ✅ Validation passes
> Task-N complete
```

### Benefits of This Approach

1. **Clean History**: Each task in the chain is complete and valid
2. **No Technical Debt**: No workarounds accumulate
3. **Clear Dependencies**: Prerequisites are explicit in task ordering
4. **Maintainability**: Future developers understand the progression

### Example: Tasks 006a and 007

- **Task-007**: Create type definitions module
  - **Discovered**: Validator can't detect module-level attributes
- **Task-006a**: Fix validator to detect module-level attributes
  - **Implementation**: Enhanced `_ArtifactCollector.visit_Assign`
  - **Result**: Module attributes stored under `found_attributes[None]`
- **Task-007** (restored): Type definitions module
  - **Result**: Now validates completely with fixed validator

This pattern ensures every task contributes to a stronger, more capable system.

**Note:** Documents in the `./.claude/conversations` directory contain conversational history with Claude from experimentation and exploration. They should not be treated as a source of truth or referenced unnecessarily.

## ⚠️ CRITICAL: Commit Policy ⚠️

**NEVER AUTO-COMMIT WITHOUT EXPLICIT PERMISSION!**

Before ANY commit, you MUST:

1. **Run ALL validation and quality checks:**
   ```bash
   uv run maid validate    # Validate all MAID manifests
   uv run maid test        # Run all MAID validation commands
   make lint               # Check code style
   make type-check         # Check type hints
   make test               # Run full pytest suite
   make format             # Format code
   ```

2. **Fix ALL errors and issues** - Do NOT commit if there are ANY:
   - MAID validation errors
   - Test failures
   - Type errors
   - Linting errors
   - Build errors

3. **Wait for explicit user direction** - Even if the user mentioned committing earlier in the conversation, ALWAYS:
   - Show them the changes
   - Show them the quality check results
   - Wait for their explicit "commit now" or "go ahead" instruction
   - NEVER assume permission to commit

**This applies even if:**
- The user asked to commit earlier
- You think the changes are ready
- All tests pass
- The code looks perfect

**ALWAYS WAIT FOR EXPLICIT DIRECTION BEFORE COMMITTING!**
