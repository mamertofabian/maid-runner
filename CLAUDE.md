# CLAUDE.md

**CRITICAL: This project dogfoods MAID v2 (YAML manifests). Every code change MUST follow the MAID workflow.**
**USE SUBAGENTS: When MAID subagents are available (maid-manifest-architect, maid-test-designer, maid-developer, etc.), INVOKE them via the Task tool for each phase.**

**Note on Documentation Changes:** Pure documentation changes (modifying only `.md` files with no code artifacts) may be exempt from the full MAID workflow, but should still be reviewed for accuracy and consistency. When in doubt, create a manifest.

## MAID Workflow (Required for ALL changes)

### Phase 1: Goal Definition
Confirm the high-level goal with user before proceeding.

### Phase 2: Planning Loop
**Before ANY implementation - iterative refinement:**
1. Draft manifest (`manifests/<slug>.manifest.yaml`) - **PRIMARY CONTRACT**
2. Draft behavioral tests in the appropriate `tests/` subdirectory (e.g., `tests/core/`, `tests/validators/`)
3. Run behavioral validation (checks that tests USE declared artifacts):
   `uv run maid validate manifests/<slug>.manifest.yaml --mode behavioral`
4. Refine BOTH tests & manifest together until validation passes

### Phase 3: Implementation
1. Load ONLY files from manifest (`files.edit` + `files.read`)
2. Implement code to pass tests
3. Run implementation validation (checks that code DEFINES declared artifacts):
   `uv run maid validate manifests/<slug>.manifest.yaml --mode implementation`
4. Run behavioral tests (from `validate` commands)
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

## MAID Skills Workflow

When MAID skills are available, use them as the primary workflow:

| Skill | Phase | When to Use |
|-------|-------|-------------|
| `maid-planner` | Plan | Create or revise a manifest and behavioral tests |
| `maid-plan-review` | Plan Gate | Review the manifest and tests before implementation |
| `maid-implementer` | Implement | Implement only within approved manifest scope |
| `maid-implementation-review` | Implementation Gate | Review changed files, artifacts, tests, and validation before handoff |
| `maid-evolver` | Evolve | Change an existing manifest contract intentionally |
| `maid-auditor` | Audit | Check active manifests for regressions, drift, and broken contracts |
| `maid-incident-logger` | Incident Logging | Capture useful MAID workflow drift or gaming examples |

These skills are installed into team repositories by `maid init --tool claude`.

## MAID Subagents (Use When Available)

**When these subagents are available, INVOKE them via the Task tool for each phase:**

| Subagent | Phase | When to INVOKE |
|----------|-------|----------------|
| `maid-manifest-architect` | Phase 1 | Creating any manifest |
| `maid-test-designer` | Phase 2 | Creating behavioral tests |
| `maid-developer` | Phase 3 | Implementing code to pass tests |
| `maid-refactorer` | Phase 3.5 | Improving code quality |
| `maid-fixer` | Phase 3 Support | Fixing validation errors |
| `maid-auditor` | Cross-cutting | Checking MAID compliance |

**Note:** MAID Runner is a validation-only tool. The subagents above are provided by the MAID Runner plugin or configured in `.claude/agents/`. They use MAID Runner CLI commands internally.

**Note:** The MAID workflow embodies TDD at two levels:
- **Planning Loop**: Iterative test-manifest refinement (micro TDD)
- **Overall Workflow**: Red (failing tests) -> Green (passing implementation) -> Refactor (quality improvement)

## Project Overview

MAID Runner implements and enforces the Manifest-driven AI Development (MAID) methodology. It validates that code artifacts match their declarative YAML manifests, ensuring AI-generated code aligns with architectural specifications. It provides both a CLI (`maid`) and a Python library API (`from maid_runner import validate, ManifestChain`).

> See `docs/ai-compiler-workflow.md` for the full ArchSpec + MAID Runner pipeline.

## Architecture

### Package Structure

```
maid_runner/
├── core/                # Manifest loading, validation engine, chain, types, results
├── validators/          # Language-specific artifact collectors (Python, TypeScript, Svelte)
├── graph/               # Knowledge graph (manifest relationship analysis)
├── coherence/           # Architectural coherence checks
├── compat/              # V1 JSON backward compatibility layer
├── cli/commands/        # CLI command modules
└── schemas/             # JSON Schema (manifest.v1.schema.json, manifest.v2.schema.json)
```

### Core Components

1. **Validation Engine** (CLI: `maid validate`, Library: `validate()`)
   - Validates manifest YAML against JSON Schema (`schemas/manifest.v2.schema.json`)
   - Behavioral test validation: Verifies tests USE declared artifacts
   - Implementation validation: Verifies code DEFINES artifacts
   - Manifest chain merging (enabled by default)
   - Coherence checks (optional, `--coherence`)

2. **Manifest Schema** (`schemas/manifest.v2.schema.json`)
   - Defines the required structure for v2 YAML manifests
   - Artifact kinds: class, function, method, attribute, interface, type, enum, namespace

3. **Manifest Files** (`manifests/`)
   - YAML v2 format with semantic slug names (e.g., `add-auth.manifest.yaml`)
   - Chronological ordering via `created` timestamp
   - Multi-file support: one manifest can declare artifacts across multiple files
   - Current task's manifest can be modified during active development; all prior tasks' manifests are immutable

4. **Development Tools**
   - `Makefile`: Convenience commands for development workflow
   - `maid test`: TDD runner with watch mode support

### Key MAID Principles in This Codebase

- **Explicitness**: Every task context is explicitly defined in manifests
- **Extreme Isolation**: Tasks touch minimal files, specified in manifest
- **Test-Driven Validation**: Tests define success, not subjective assessment
- **Verifiable Chronology**: Current state = sequential manifest application

## Key Rules

**NEVER:** Modify code without manifest | Skip validation | Access unlisted files
**ALWAYS:** Manifest first -> Tests -> Implementation -> Validate

## Refactoring Private Implementation

MAID provides flexibility for refactoring private implementation details without requiring manifests:

- **Private code** (functions, classes, variables with `_` prefix) can be refactored freely
- **Internal logic changes** that don't affect the public API are allowed
- **Code quality improvements** (splitting functions, extracting helpers, renaming privates) are permitted

**Requirements:**
- All tests must continue to pass (`make test`, `uv run maid test`)
- All validations must pass (`uv run maid validate`)
- Public API must remain unchanged (no changes to public functions, classes, or signatures)
- No MAID rules are violated

**When No Manifest Is Needed:**

If a change only modifies private implementation (no public methods/classes changed) and doesn't change the public API:

1. **Do NOT create a manifest**
2. **Update the tests** of the existing latest manifest for the file being edited
3. Add test cases to cover the new behavior or fix
4. Ensure all existing tests continue to pass

This approach maintains the audit trail through test updates while avoiding unnecessary manifest proliferation for internal improvements.

**For complete methodology details**, see `docs/maid_specs.md`.

## Testing Standards

All tests must follow the unit testing rules defined in `docs/unit-testing-rules.md`. Key principles:
- Test behavior, not implementation details
- Minimize mocking to essential dependencies
- Make tests deterministic and independent
- Test for failure conditions, not just happy paths
- Keep tests simple, readable, and maintainable

Tests are domain-organized:
- `tests/core/` - Core module tests (manifest, chain, validate, types, result)
- `tests/validators/` - Language-specific validator tests
- `tests/coherence/` - Coherence check tests
- `tests/graph/` - Knowledge graph tests
- `tests/compat/` - V1 compatibility tests
- `tests/cli/` - CLI command tests
- `tests/integration/` - Integration tests
- `tests/e2e/` - End-to-end tests

See `docs/unit-testing-rules.md` for complete guidelines on writing effective unit tests.

## Documentation Standards

**Focus on current state, not temporal comparisons:**

**NEVER use in documentation or code:**
- Temporal markers: "NEW", "UPDATED", "ADDED", "LATEST"
- Temporal comparisons: "Before/After", "What's Missing", "What We Currently Have"
- Marketing language: "Exciting new feature", "Now available", "Just released"
- Date-based qualifiers: "As of today", "Recently added", "Coming soon"

**ALWAYS:**
- State facts clearly: "System supports X", "Feature Y validates Z"
- Use present tense: "This validates", not "This will validate"
- Document current capabilities: "The system provides", not "We've added"
- Let git history track changes

**Rationale:** Git history handles temporal tracking. Documentation should describe the current state objectively. We're building technical documentation, not marketing pages.

**If temporal context is needed:** User will explicitly request it. Otherwise, omit it.

## Validation Flow

The `maid validate` command supports two validation modes:

### Behavioral Mode (`--mode behavioral`)
**Use during Phase 2 (Planning Loop) when writing tests**

1. **Schema Validation**: Ensures manifest follows the JSON Schema
2. **Behavioral Test Validation**: Verifies test files USE the declared artifacts (AST-based)

Note: Behavioral validation only checks artifacts from the current manifest, not the merged chain.

### Implementation Mode (`--mode implementation`, default)
**Use during Phase 3 (Implementation) when writing code**

1. **Schema Validation**: Ensures manifest follows the JSON Schema
2. **Implementation Validation**: Verifies code DEFINES the declared artifacts
3. **File Tracking Analysis** (with chain, enabled by default): Detects undeclared and partially compliant files

### Coherence Mode (`--coherence`)
**Use during Phase 4 (Integration) for architectural checks**

1. Builds knowledge graph from all manifests
2. Checks for naming violations, duplicate artifacts, boundary issues
3. Can run standalone: `maid coherence`

### File Tracking Analysis

When validating with manifest chains (default), MAID Runner performs automatic file tracking analysis with a two-level warning system:

- **UNDECLARED** (High Priority): Files exist in codebase but not in any manifest
  - No audit trail of when/why created
  - **Action**: Add to `files.create` or `files.edit` in a manifest

- **REGISTERED** (Medium Priority): Files in manifests but incomplete compliance
  - Issues: Missing `artifacts`, no tests, or only in `files.read`
  - **Action**: Add `artifacts` and `validate` commands for full compliance

- **TRACKED** (Clean): Files with full MAID compliance
  - Properly documented with artifacts and behavioral tests

This progressive compliance system helps identify accountability gaps and supports gradual migration to MAID.

## Validation Modes

- **Strict Mode** (`files.create`): Implementation must EXACTLY match declared `artifacts`
- **Permissive Mode** (`files.edit`): Implementation must CONTAIN declared `artifacts` (allows existing code)

## Manifest Template

V2 manifests use YAML with multi-file support:

```yaml
schema: "2"
goal: "Clear task description"
type: feature|fix|refactor|snapshot
sequence_number: 42            # Optional — deterministic event-log ordering
version_tag: "v1.0"            # Optional — release label
supersedes:                    # Optional: slugs of obsolete manifests
  - old-manifest-slug

files:
  create:                      # New files (Strict Mode)
    - path: path/to/new_file.py
      artifacts:
        - kind: function|class|method|attribute
          name: artifact_name
          of: ParentClass       # For methods/attributes
          args:                 # For functions/methods
            - name: arg1
              type: str
          returns: ReturnType   # Optional
  edit:                        # Existing files (Permissive Mode)
    - path: path/to/existing.py
      artifacts:
        - kind: method
          name: new_method
          of: ExistingClass
  read:                        # Dependencies and tests (paths only)
    - tests/test_file.py
  delete:                      # Files to remove
    - path: path/to/remove.py
      reason: "Explanation"

validate:
  - pytest tests/test_file.py -v
```

## MAID CLI Commands

**IMPORTANT: Always use the `maid` CLI for validation and snapshots, NOT direct Python scripts.**

### Whole-Codebase Validation (Recommended)

```bash
# Validate ALL active manifests with chain merging (default)
uv run maid validate

# Run ALL validation commands from all active manifests
uv run maid test
```

**These commands are the primary way to verify complete MAID compliance across the entire codebase.**

### Individual Commands

```bash
# Validate a specific manifest
uv run maid validate <manifest-path> [--mode behavioral|implementation] [--quiet]

# Validate without chain merging
uv run maid validate <manifest-path> --no-chain

# Validate with coherence checks
uv run maid validate --coherence

# JSON output (for CI/CD and tool integration)
uv run maid validate --json

# Generate a snapshot manifest from existing code
uv run maid snapshot <file-path> [--output-dir <dir>]

# Create a new manifest for a file
uv run maid manifest create <file-path> --goal "Description" [--artifacts JSON] [--dry-run] [--json]

# Generate system-wide manifest aggregating all active manifests
uv run maid snapshot-system [--output <file>] [--manifest-dir <dir>] [--quiet]

# List manifests that reference a file
uv run maid manifests <file-path> [--manifest-dir <dir>] [--quiet]

# Run validation commands from specific manifests
uv run maid test [--manifest-dir <dir>] [--fail-fast] [--verbose] [--json]

# Watch mode: Single-manifest watch (re-run tests on file changes)
uv run maid test --manifest <manifest-path> --watch

# Watch mode: Multi-manifest watch (run affected tests on changes)
uv run maid test --watch-all

# Knowledge graph operations
uv run maid graph query|export|analyze

# Run coherence checks
uv run maid coherence [--checks <checks>] [--exclude <exclude>] [--json]

# Display JSON Schema
uv run maid schema

# Event-log inspection
uv run maid chain log [--until-seq N] [--version-tag TAG] [--active] [--json]

# Replay preview (effective artifacts at a point in time)
uv run maid chain replay [--until-seq N] [--version-tag TAG] [--json]

# Get help
uv run maid --help
uv run maid validate --help
```

## Quick Commands

```bash
# Whole-Codebase Validation (Primary Commands)
uv run maid validate     # Validate ALL active manifests with chain merging
uv run maid test         # Run ALL validation commands from active manifests
make test                # Run full pytest suite

# Watch Mode (Live TDD workflow)
uv run maid test --manifest manifests/<slug>.manifest.yaml --watch  # Single-manifest watch
uv run maid test --watch-all                                        # Multi-manifest watch

# Development Shortcuts (Makefile)
make validate            # Validate all manifests with chain

# Individual Manifest Validation Flow
# 1. During Planning: Behavioral validation (checks tests USE artifacts)
uv run maid validate manifests/<slug>.manifest.yaml --mode behavioral

# 2. During Implementation: Implementation validation (checks code DEFINES artifacts)
uv run maid validate manifests/<slug>.manifest.yaml --mode implementation

# 3. Behavioral test execution (run actual tests)
uv run python -m pytest tests/core/test_<module>.py -v

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
- **`files.create`**: Strict validation (exact match)
- **`files.edit`**: Permissive validation (contains at least)
- **`kind`**: `class`, `function`, `method`, `attribute`, `interface`, `type`, `enum`, `namespace`
- **`of`**: Parent class name (required for methods and class attributes)

## Superseded Manifests and Test Execution

**Critical Behavior:** When a manifest is superseded, it is completely excluded from MAID operations:

- `uv run maid validate` ignores superseded manifests when merging manifest chains
- `uv run maid test` does NOT execute `validate` commands from superseded manifests
- Superseded manifests serve as historical documentation only -- they are archived, not active

**Why this matters:** If you supersede a manifest, its tests will no longer run. This is by design -- superseded manifests represent obsolete contracts that have been replaced.

## Transitioning from Snapshots to Natural Evolution

**Key Insight:** Snapshot manifests are for "frozen" code. Once code needs to evolve, you must transition to the natural MAID flow.

### The Pattern

1. **Snapshot Phase** (Initial baseline):
   - Use `maid snapshot` to capture complete public API of existing code
   - `type: snapshot` declares ALL functions/classes at that point in time

2. **Transition Manifest** (First evolution):
   - When file needs changes, create an edit manifest that:
     - Declares ALL current functions (existing + new)
     - Supersedes the snapshot manifest
     - Uses `type: feature` or `type: fix` (not "snapshot")
   - This is the bridge from frozen state to natural evolution

3. **Future Evolution** (Natural MAID flow):
   - Subsequent manifests only declare NEW changes
   - With chain merging (default), validator merges all active manifests
   - No need to update previous manifests when adding APIs

### Example Evolution

```
File history: src/service.py

snapshot-service.manifest.yaml (snapshot)
|-- Declares: func_1, func_2, func_3
`-- Status: SUPERSEDED by add-new-feature

add-new-feature.manifest.yaml (feature, supersedes snapshot-service)
|-- Declares: func_1, func_2, func_3, new_func  // ALL current functions
`-- Supersedes: [snapshot-service]

add-another-feature.manifest.yaml (feature)
`-- Declares: another_func  // Only the new addition

With chain merging (default):
  Merged = add-new-feature + add-another-feature
  = {func_1, func_2, func_3, new_func, another_func}
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

When removing a file tracked by MAID: Create refactor manifest -> Supersede creation manifest -> Delete file and tests -> Validate deletion.

**Manifest**: `type: refactor`, supersedes original, file listed under `files.delete` with reason

**Validation**: File deleted, tests deleted, no remaining imports

## File Rename Pattern

When renaming a file tracked by MAID: Create refactor manifest -> Supersede creation manifest -> Use `git mv` -> Update manifest -> Validate rename.

**Manifest**: `type: refactor`, supersedes original, new filename in `files.create`, old file in `files.delete`, same API in `artifacts` under new location

**Validation**: Old file deleted, new file exists with working functionality, no old imports, git history preserved

**Key difference from deletion**: Rename maintains module's public API continuity under new location.

## Key Reminders

- This codebase **IS** the MAID implementation - exemplify the methodology
- Manifest chain = source of truth for file state
- Manifest = contract; tests support implementation and verification
- Every change needs a manifest with a descriptive slug name
- **Manifest immutability**: Current task's manifest can be modified during active development; all prior tasks' manifests are immutable
- **Multi-file support**: V2 manifests support artifacts across multiple files in a single manifest

## Lessons Learned: Handling Prerequisite Discovery

### The Challenge
When implementing a task, you may discover that the validator or framework lacks a capability needed for the current work.

### The MAID-Compliant Solution

**What NOT to do:**
- Create workarounds in tests (artificial assertions)
- Document limitations and continue
- Modify the manifest to hide the problem

**The Correct Approach:**
1. **Stash Current Work**: `git stash` current implementation
2. **Create Prerequisite Manifest**: A separate manifest to fix the underlying issue
3. **Complete Prerequisite**: Full MAID workflow for the prerequisite
4. **Restore and Complete**: Original task works cleanly

### Key Principle: No Partial Solutions

**Every task must complete fully with all validations passing.** If validation fails, either:
1. Fix the test (if test is wrong)
2. Fix the implementation (if implementation is wrong)
3. Fix the prerequisite (if system limitation discovered)

Never leave a task partially complete or with failing validations.

**Note:** Documents in the `./.claude/conversations` directory contain conversational history with Claude from experimentation and exploration. They should not be treated as a source of truth or referenced unnecessarily.

## CRITICAL: Commit Policy

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
