# MAID Runner Cleanup And Refactor Backlog

## Purpose

This document records confirmed cleanup and refactor targets in the
`maid-runner` codebase. The goal is to keep the validator and CLI surfaces
maintainable as MAID waves accumulate, without weakening the anti-gaming
contract or changing observable behavior.

Findings are scoped to behavior-preserving refactors. Measurable speedups go
through the `maid-runner-performance-optimization` skill instead. Intentional
public-contract changes go through `maid-evolver`.

## Refactor Contract

Cleanup and refactor work must satisfy these invariants:

- the same inputs must produce the same `ValidationResult.success`, error
  codes, warnings, and JSON output as before the refactor;
- every public artifact declared in active manifests must still exist with the
  same signature, or be removed under an explicit `maid-evolver` plan;
- characterization tests must exist for every file in scope before any
  restructuring touches it;
- `uv run maid validate --mode schema` must pass at every step;
- private helpers (`_` prefix) can be renamed, split, or removed without an
  evolver plan provided behavior is preserved.

See `.claude/skills/maid-runner-cleanup-and-refactor/SKILL.md` for the full
workflow.

## Cost Surface

Module size landscape (production code only):

| Module | Lines |
|---|---|
| `maid_runner/validators/python.py` | 2051 |
| `maid_runner/core/validate.py` | 1212 |
| `maid_runner/validators/_typescript_implementation.py` | 1186 |
| `maid_runner/validators/_typescript_behavioral.py` | 1096 |
| `maid_runner/core/test_runner.py` | 984 |
| `maid_runner/core/_validation_test_artifacts.py` | 813 |
| `maid_runner/cli/commands/_format.py` | 769 |
| `maid_runner/graph/query.py` | 726 |

Manifest counts: 184 active, 3 drafts (before 034 batch). Test count: 73.

## Confirmed Cleanup Targets

### 1. Oversized methods in `validate.py`

`maid_runner/core/validate.py` carries five methods each between 107 and 160
lines that mix orchestration, error construction, and flow-control branches.
These are the highest-leverage split candidates in the codebase.

| Method | Line | Approx length |
|---|---|---|
| `ValidationEngine.validate_removed_artifacts` | 701 | 160 |
| `ValidationEngine.validate_all` | 226 | 136 |
| `ValidationEngine.validate` | 115 | 111 |
| `ValidationEngine._check_test_coverage` | 542 | 110 |
| `ValidationEngine.validate_behavioral` | 362 | 107 |

Each method has multiple early-return branches and inline error construction
that obscures the orchestration intent. Splitting into named guard-clause
helpers improves readability and lowers the cost of future hardening waves,
provided characterization tests lock the existing error codes, severities,
JSON output, and warning shapes first.

**Engine**: `safe-refactor`.
**Closure shape**: characterize first, then extract guard-clause helpers
within the same module. No new public artifacts.

### 2. Duplicated parse-error wrapping across validators

`PythonValidator` and `TypeScriptValidator` repeat the same parse-then-wrap
pattern in both implementation and behavioral collection paths:

- `maid_runner/validators/python.py:51-95` (both methods)
- `maid_runner/validators/typescript.py:51-112` (both methods)

The Python variant wraps `ast.parse` `SyntaxError`; the TypeScript variant
wraps `parse_typescript_source` errors. The control flow is identical: parse,
short-circuit with `CollectionResult` carrying `errors=`, otherwise return
`CollectionResult` with artifacts.

`maid_runner/validators/base.py` already exposes `BaseValidator` as an
abstract class. A small shared helper (e.g.
`BaseValidator._collect_with_parse_guard(parse_fn, language, file_path)`)
would consolidate the wrapping. Svelte delegates to TypeScript so no
additional duplication exists there.

**Engine**: `safe-refactor`.
**Closure shape**: add the protected helper on `BaseValidator`, route both
Python collection methods and both TypeScript collection methods through it,
keep the public method signatures identical, and prove via tests that
malformed sources still produce the same `CollectionResult` shape, language
field, and error strings.

## Categories Examined And Cleared

The skill's standard probe categories were also exercised. The following
returned no confirmed targets at this time and are noted so a future audit
can re-check them rather than rediscover them from scratch:

- **Dead private helpers**: spot-checked single-use helpers in `core/snapshot.py`,
  `core/identity.py`, and `core/supersession_audit.py`. All are legitimate
  internal helpers, not unused code.
- **Magic strings for error codes**: no literal `"E###"` strings found outside
  `core/result.py`. `ErrorCode` enum usage is consistent.
- **Stale TODO/FIXME**: production code carries no actionable maintenance
  TODOs. The only `TODO` token sits inside a literal example string in
  `_typescript_implementation.py`.
- **Orphaned manifests**: every `path:` reference in active manifests resolves
  to an existing file on disk.
- **Snapshot manifests fully superseded**: no active manifest declares an
  active snapshot under `supersedes:`. No archival candidates.

## Speculative Ideas (Not Confirmed)

These were considered and downgraded to speculative because they need either
explicit user direction or additional measurement before becoming drafts.

- **Test mocking density**: `tests/core/test_validate.py` (~15 mocks),
  `tests/cli/test_coherence_cmd.py` (~10), `tests/cli/test_init_cmd.py` (~8).
  These are CLI/integration tests where mocks at process boundaries are
  defensible. Migration to fakes is a maintenance question, not a confirmed
  cleanup target.
- **`validators/python.py` size (2051 lines)**: large but already partitioned
  into named collector classes. No specific split target identified without a
  deeper read.
- **CLI format helpers (`cli/commands/_format.py`, 769 lines)**: large but
  cohesive. No specific split target identified.

## Manifest-Evolution Targets

None at this time. Both confirmed cleanup targets stay inside private
implementation and do not touch any artifact declared by an active manifest.

## Gradual Closure Backlog

Recommended order so each refactor lands with characterization first:

1. Characterize `ValidationEngine` orchestration paths so the existing error
   codes, severities, JSON output, and warning shape are locked down before
   any extraction.
2. Extract the shared parse-error wrapping helper on `BaseValidator` and
   route Python and TypeScript validators through it.
3. Split `validate_removed_artifacts` into named guard-clause helpers.
4. Split `validate_all` into named guard-clause helpers.
5. Split `validate`, `_check_test_coverage`, and `validate_behavioral`
   similarly, one at a time, with the characterization suite re-run after
   each split.

The 035 draft queue covers items 1 and 2 as the seed batch.

## Suggested Acceptance Criteria

- `uv run maid validate --mode schema --quiet` passes.
- `uv run maid validate` (root) passes before and after each split.
- `uv run maid test` passes before and after each split.
- The characterization suite (added in step 1) passes before and after each
  split with identical assertions.
- `git diff --stat` for each child draft stays under ~300 lines of production
  code change.

## Verification Notes

Audit performed against the worktree at
`.claude/worktrees/maid-runner-performance-optimization` based on HEAD
`c5ba688`. Re-run the probes if the manifest set or the listed modules have
materially changed.
