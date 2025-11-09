# CLAUDE.md

**⚠️ CRITICAL: This project dogfoods MAID v1.2. Every code change MUST follow the MAID workflow.**

**Note on Documentation Changes:** Pure documentation changes (modifying only `.md` files with no code artifacts) may be exempt from the full MAID workflow, but should still be reviewed for accuracy and consistency. When in doubt, create a manifest.

## MAID Workflow (Required for ALL changes)

### Phase 1: Goal Definition
Confirm the high-level goal with user before proceeding.

### Phase 2: Planning Loop
**Before ANY implementation - iterative refinement:**
1. Draft manifest (`manifests/task-XXX.manifest.json`) - **PRIMARY CONTRACT**
2. Draft behavioral tests (`tests/test_task_XXX_*.py`) to support and verify the manifest
3. Run structural validation (checks manifest↔tests AND implementation↔history):
   `uv run python validate_manifest.py manifests/task-XXX.manifest.json --use-manifest-chain`
4. Refine BOTH tests & manifest together until validation passes

### Phase 3: Implementation
1. Load ONLY files from manifest (`editableFiles` + `readonlyFiles`)
2. Implement code to pass tests
3. Run behavioral validation (from `validationCommand`)
4. Iterate until all tests pass

### Phase 3.5: Refactoring
1. After tests pass, improve code quality
2. Maintain public API and manifest compliance
3. Apply clean code principles and patterns
4. Validate tests still pass after each change

### Phase 4: Integration
Verify complete chain: `uv run python -m pytest tests/ -v`

## MAID Subagents

**Specialized Claude Code subagents are available for each MAID phase.** See `.claude/agents/README.md` for detailed information.

### Available Agents:
1. **maid-manifest-architect** - Phase 1: Creates and validates manifests
2. **maid-test-designer** - Phase 2: Creates behavioral tests from manifests
3. **maid-developer** - Phase 3: Implements code to pass tests
4. **maid-refactorer** - Phase 3.5: Improves code quality (completes TDD cycle)
5. **maid-auditor** - Cross-cutting: Enforces strict MAID compliance across all phases

### Invoking Agents:
```bash
# These agents will be invoked PROACTIVELY by Claude Code when appropriate
# You can also explicitly request them:
> Use the maid-manifest-architect to create a manifest for feature X
> Have the maid-test-designer create tests for task-005
> Get the maid-developer to implement task-005
> Use the maid-refactorer to improve code quality for task-005
> Run the maid-auditor to check for MAID compliance violations
```

**Note:** The MAID workflow embodies TDD at two levels:
- **Planning Loop**: Iterative test-manifest refinement (micro TDD)
- **Overall Workflow**: Red (failing tests) → Green (passing implementation) → Refactor (quality improvement)

## Project Overview

MAID Runner implements and enforces the Manifest-driven AI Development (MAID) methodology from `docs/maid_specs.md`. It validates that code artifacts match their declarative manifests, ensuring AI-generated code aligns with architectural specifications through strict chronological tracking.

## Architecture

### Core Components

1. **Manifest Validator** (`validate_manifest.py`)
   - Validates manifest JSON against schema
   - Behavioral test validation: Verifies tests USE declared artifacts
   - Implementation validation: Verifies code DEFINES artifacts
   - Enforces manifest chain chronology

2. **Manifest Schema** (`validators/schemas/manifest.schema.json`)
   - Defines the required structure for task manifests
   - Artifact types: class, function, attribute, parameter

3. **Manifest Files** (`manifests/`)
   - Chronologically ordered, immutable task records
   - Sequential naming: task-001, task-002, task-003, etc.
   - Each represents a single atomic change

4. **Bootstrap Development Tools**
   - `dev_bootstrap.py`: TDD runner for manifest-driven development
   - `Makefile`: Convenience commands for development workflow
   - Enables building MAID tools using MAID methodology

### Key MAID Principles in This Codebase

- **Explicitness**: Every task context is explicitly defined in manifests
- **Extreme Isolation**: Tasks touch minimal files, specified in manifest
- **Test-Driven Validation**: Tests define success, not subjective assessment
- **Verifiable Chronology**: Current state = sequential manifest application

## Key Rules

**NEVER:** Modify code without manifest | Skip validation | Access unlisted files
**ALWAYS:** Manifest first → Tests → Implementation → Validate

## Validation Flow

The `validate_manifest.py` script performs validation in this order:

1. **Schema Validation**: Ensures manifest follows the JSON schema
2. **Behavioral Test Validation**: Verifies test files USE the declared artifacts (AST-based)
3. **Implementation Validation**: Verifies implementation DEFINES the artifacts

Note: Behavioral validation only checks artifacts from the current manifest, not the merged chain.

## Validation Modes (MAID v1.2)

- **Strict Mode** (`creatableFiles`): Implementation must EXACTLY match `expectedArtifacts`
- **Permissive Mode** (`editableFiles`): Implementation must CONTAIN `expectedArtifacts` (allows existing code)

## Manifest Template

```json
{
  "goal": "Clear task description",
  "taskType": "edit|create|refactor",
  "supersedes": [],  // Optional: paths to obsolete manifests
  "creatableFiles": [],  // New files (Strict Mode)
  "editableFiles": [],   // Existing files (Permissive Mode)
  "readonlyFiles": [],   // Dependencies and tests
  "expectedArtifacts": {
    "file": "path/to/file.py",
    "contains": [
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

## Quick Commands

```bash
# Bootstrap Development (TDD workflow)
make dev TASK=005        # Run tests once for task-005
make watch TASK=005      # Watch mode with auto-test for task-005
make validate            # Validate all manifests with chain

# Find next manifest number
ls manifests/task-*.manifest.json | tail -1

# Validation Flow
# 1. Structural validation (pre-implementation)
uv run python validate_manifest.py manifests/task-XXX.manifest.json --use-manifest-chain

# 2. The validator now runs THREE checks:
#    a) Schema validation (manifest structure)
#    b) Behavioral validation (tests USE artifacts)
#    c) Implementation validation (code DEFINES artifacts)

# 3. Behavioral test execution (run actual tests)
uv run python -m pytest tests/test_task_XXX_*.py -v

# Full test suite
make test  # or: uv run python -m pytest tests/ -v

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

## Key Reminders

- This codebase **IS** the MAID implementation - exemplify the methodology
- Manifest chain = source of truth for file state
- Manifest = contract; tests support implementation and verification
- Every change needs a manifest with sequential numbering

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

1. **Run ALL code quality checks:**
   ```bash
   make lint          # Check code style
   make type-check    # Check TypeScript types
   make test          # Run tests
   make format        # Format code
   ```

2. **Fix ALL errors and type issues** - Do NOT commit if there are ANY:
   - Type errors
   - Linting errors
   - Test failures
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
