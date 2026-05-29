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

Module size landscape (production code only), refreshed on 2026-05-29:

| Module | Lines |
|---|---|
| `maid_runner/validators/python.py` | 2051 |
| `maid_runner/validators/_typescript_implementation.py` | 1264 |
| `maid_runner/validators/_typescript_behavioral.py` | 1132 |
| `maid_runner/cli/commands/_format.py` | 769 |
| `maid_runner/core/chain.py` | 742 |
| `maid_runner/graph/query.py` | 726 |
| `maid_runner/core/_ts_export_scanner.py` | 674 |
| `maid_runner/core/_validation_test_artifacts.py` | 664 |
| `maid_runner/core/manifest.py` | 658 |
| `maid_runner/core/validate.py` | 592 |

Manifest count: 277 active or draft manifest files. Test file count: 110.

## Confirmed Cleanup Targets

### 1. Oversized methods in `validate.py`

Status: closed by the later `038` extraction wave and `039-01`.

The original audit found five oversized methods in `maid_runner/core/validate.py`.
Current code no longer matches that target. The public `ValidationEngine`
methods now mostly delegate to focused helper modules:

| Method | Line | Approx length |
|---|---|---|
| `ValidationEngine._validate` | 135 | 109 |
| `ValidationEngine.validate_acceptance` | 316 | 31 |
| `ValidationEngine.validate_all` | 245 | 30 |
| `ValidationEngine.validate` | 104 | 30 |
| `ValidationEngine.validate_implementation` | 399 | 18 |
| `ValidationEngine.validate_behavioral` | 301 | 14 |
| `ValidationEngine.validate_removed_artifacts` | 418 | 14 |

Do not create the previously suggested
`043-05-split-validation-engine-removed-artifacts.manifest.yaml` without a
fresh audit. The current `validate_removed_artifacts` wrapper is already thin
and delegates to `maid_runner/core/_removed_artifacts.py`.

The remaining `ValidationEngine._validate` method is the only still-large
method in this file. It may become a future refactor target, but it needs a
fresh characterization review because it handles public `validate(...)` result
assembly, path/schema load failures, chain diagnostics, acceptance validation,
warning splitting, and duration measurement.

**Engine**: `safe-refactor`.
**Closure shape**: closed for the old target. Any new target must be based on
current code evidence and scoped in a new draft.

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

1. Done: characterize `ValidationEngine` orchestration paths via `035-01`.
2. Done: extract shared parse-error wrapping via `035-02`.
3. Done: extract `validate_removed_artifacts` policy via `038-11`.
4. Done: extract `validate_all`, behavioral validation, implementation
   validation, and implementation coverage helpers through the 038 wave.
5. Next fresh cleanup work should start with a new audit of current large
   modules such as `validators/python.py`, TypeScript validator internals,
   `_format.py`, `chain.py`, or the remaining `ValidationEngine._validate`
   method.

The 035 draft queue covered items 1 and 2 as the seed batch; later 038/039
work continued the extraction.

## Suggested Acceptance Criteria

- `uv run maid validate --mode schema --quiet` passes.
- `uv run maid validate` (root) passes before and after each split.
- `uv run maid test` passes before and after each split.
- The characterization suite (added in step 1) passes before and after each
  split with identical assertions.
- `git diff --stat` for each child draft stays under ~300 lines of production
  code change.

## Verification Notes

Original audit performed against the worktree at
`.claude/worktrees/maid-runner-performance-optimization` based on HEAD
`c5ba688`.

2026-05-29 refresh: current `maid_runner/core/validate.py` is 592 lines, the
old `validate_removed_artifacts` and `validate_all` split targets are already
thin wrappers, and future cleanup drafts should be selected from current code
evidence rather than this historical method-size table.
