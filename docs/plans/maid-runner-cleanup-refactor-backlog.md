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

See `.codex/skills/maid-runner-cleanup-and-refactor/SKILL.md` for the Codex
workflow and `.claude/skills/maid-runner-cleanup-and-refactor/SKILL.md` for
the Claude copy.

## Cost Surface

Module size landscape (production code only), refreshed on 2026-05-29:

| Module | Lines |
|---|---|
| `maid_runner/validators/python.py` | 2054 |
| `maid_runner/validators/_typescript_implementation.py` | 1264 |
| `maid_runner/validators/_typescript_behavioral.py` | 1132 |
| `maid_runner/cli/commands/_format.py` | 769 |
| `maid_runner/core/chain.py` | 742 |
| `maid_runner/graph/query.py` | 726 |
| `maid_runner/core/_ts_export_scanner.py` | 674 |
| `maid_runner/core/_validation_test_artifacts.py` | 791 |
| `maid_runner/core/manifest.py` | 658 |
| `maid_runner/core/validate.py` | 592 |

Manifest count: 281 active or draft `*.manifest.yaml` files, or 290
manifest/epic YAML files including draft epics. Test file count: 110.

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

Status: closed by `035-02-extract-shared-parse-error-handling`.

The original audit found that `PythonValidator` and `TypeScriptValidator`
repeated the same parse-then-wrap pattern in both implementation and behavioral
collection paths. Current code has the shared helper in place:

- `maid_runner/validators/base.py:91-125`
  `BaseValidator._collect_with_parse_guard(...)`.
- `maid_runner/validators/python.py:124-157` routes Python implementation and
  behavioral collection through the helper.
- `maid_runner/validators/typescript.py:51-104` routes TypeScript
  implementation and behavioral collection through the helper.

Do not recreate the old `035-02` draft. Future work in this area should start
from a fresh validator-specific target.

**Engine**: `safe-refactor`.
**Closure shape**: closed for the old target; no new draft needed.

### 3. Long CLI parser construction method in `_main.py`

Status: closed by `045-01-extract-cli-parser-registration`.

`maid_runner/cli/commands/_main.py:9-336` keeps every top-level and nested CLI
subparser in one 328-line `build_parser()` method. This is a classic **Long
Method** and **Shotgun Surgery** risk: every new CLI surface edits the same
function, and current manifests repeatedly redeclare `build_parser` for
unrelated command additions, for example:

- `manifests/030-09-add-worktree-scope-gate.manifest.yaml:64-67`.
- `manifests/032-03-make-verify-strict-by-default.manifest.yaml:38-41`.
- `manifests/036-01-maid-serve-validator-daemon.manifest.yaml:305-308`.
- `manifests/040-37-retire-worktree-scope-legacy-cases.manifest.yaml:95-98`.

The public API is narrow and well covered: callers use
`build_parser() -> argparse.ArgumentParser` and `main(argv: list[str] | None)
-> int`. Existing tests already cover many parser surfaces in
`tests/cli/test_main.py`, `tests/cli/test_audit_cmd.py`,
`tests/cli/test_chain_cmd.py`, and `tests/daemon/test_cli_serve.py`.

**Engine**: `safe-refactor`.
**Fowler maneuver**: Extract Method.
**Feathers seam**: `build_parser()` already returns an in-memory parser, so
tests can characterize parser output without subprocesses.
**Characterization plan**: lock the full top-level command inventory, nested
`manifest`, `graph`, `chain`, and `audit` command parsing, and strict/scope
flag defaults before extracting registration helpers.
**Closure shape**: keep `build_parser()` and `main(...)` signatures unchanged;
move command-family registration into private helpers that accept the
subparser action and preserve the same parsed attributes, defaults, help
strings, and suppressed aliases.

### 4. Mixed-concern `maid test` orchestration in `test_runner.py`

Status: closed by `045-02-extract-test-runner-stream-orchestration`.

`maid_runner/core/test_runner.py:188-356` keeps chain loading, chain error
handling, command integrity checks, stream command collection, batching
planning, acceptance execution, implementation execution, cached
`maid validate` execution, fail-fast accounting, and final
`BatchTestResult` assembly in one 169-line `_run_tests_cached()` function.

Earlier extraction waves already moved command normalization and batching
policy into helpers (`038-17`, `038-18`, `038-19`, `038-20`, and `038-21`),
but the orchestration wrapper still mixes those mechanisms. The current tests
cover the observable behavior:

- `tests/core/test_test_runner.py:255-314` chain and integrity failure cases.
- `tests/core/test_test_runner.py:326-597` pytest batching and sequential
  fallback behavior.
- `tests/core/test_test_runner.py:436-473` acceptance-first plus batched
  implementation behavior.
- `tests/core/test_test_runner.py:1548-1626` multi-manifest and empty-directory
  behavior.

**Engine**: `safe-refactor`.
**Fowler maneuver**: Extract Method.
**Feathers seam**: `run_command`, `_run_cached_maid_validate_command`, and
batching helpers are already imported seams; tests can monkeypatch execution
or use temporary manifests.
**Characterization plan**: add focused tests for acceptance-before-
implementation ordering, fail-fast result accounting, and cached
`maid validate` fallback before extracting helpers.
**Closure shape**: keep `run_tests(...)`, `run_manifest_tests(...)`, and
`_run_tests_cached(...)` signatures and `BatchTestResult` fields unchanged;
extract private helpers for stream command collection, batched implementation
planning/execution, and result accounting without changing which commands run.

## Categories Examined And Cleared

The skill's standard probe categories were also exercised. The following
returned no confirmed targets at this time and are noted so a future audit
can re-check them rather than rediscover them from scratch:

- **Dead private helpers**: single-use helper names were inspected as
  refactor candidates, but no unused private helper was confirmed. Large
  private functions such as `_validate_removed_artifacts` and
  `_resolve_reexport_source_or_fallback` are active implementation points, not
  dead code.
- **Magic strings for error codes**: no literal `"E###"` strings found outside
  `core/result.py`. `ErrorCode` enum usage is consistent.
- **Stale TODO/FIXME**: production code carries no actionable maintenance
  TODOs. The only `TODO` token sits inside a literal example string in
  `_typescript_implementation.py`.
- **Orphaned manifests**: `uv run maid validate --quiet` produced no missing
  path or not-found diagnostics in this refresh.
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
- **`validators/python.py` size (2054 lines)**: large but already partitioned
  into named collector classes. No specific split target identified without a
  deeper read.
- **CLI format helpers (`cli/commands/_format.py`, 769 lines)**: large but
  cohesive. No specific split target identified.

## Manifest-Evolution Targets

None at this time. The confirmed targets include public artifacts already
declared by active manifests (`build_parser` and `run_tests`), but the planned
cleanup keeps their signatures and observable behavior unchanged. No
intentional public-contract change is proposed, so no `maid-evolver` target is
needed for this queue.

## Gradual Closure Backlog

Recommended order so each refactor lands with characterization first:

1. Done: characterize `ValidationEngine` orchestration paths via `035-01`.
2. Done: extract shared parse-error wrapping via `035-02`.
3. Done: extract `validate_removed_artifacts` policy via `038-11`.
4. Done: extract `validate_all`, behavioral validation, implementation
   validation, and implementation coverage helpers through the 038 wave.
5. Done: characterize and extract CLI command-family registration helpers from
   `_main.build_parser` via `045-01`.
6. Done: characterize and extract stream planning/execution helpers from
   `_run_tests_cached` via `045-02`.
7. Future cleanup work can continue with current large modules such as
   `validators/python.py`, TypeScript validator internals, `_format.py`,
   `chain.py`, or the remaining `ValidationEngine._validate` method, but those
   need fresh target-specific evidence before drafting.

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

2026-05-29 second refresh: parse-guard duplication is confirmed closed.
Current confirmed cleanup targets are `build_parser()` in
`maid_runner/cli/commands/_main.py` and `_run_tests_cached()` in
`maid_runner/core/test_runner.py`. Draft queue `045` captures those targets.

2026-05-29 closure update: the `045` queue is consumed. `045-01` promoted the
CLI parser registration helper extraction, and `045-02` promoted the test
runner stream orchestration helper extraction. The draft epic remains only as
an archived historical pointer.
