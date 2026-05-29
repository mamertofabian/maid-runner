# MAID Runner Self-Improvement Backlog

## Purpose

This document prioritizes improvement work for MAID Runner as a whole system:
validation trust, workflow reliability, performance, maintainability,
documentation freshness, and release/process hygiene. It routes confirmed
themes to specialist queues instead of turning broad quality goals into
unbounded implementation work.

## Current Evidence Reviewed

- `uv run maid validate --quiet` on the current tree now passes without E111
  grandfathered-drop chain notices after `043-01`.
- The original `uv run maid test` health probe passed 18 commands and reported
  no E111 chain noise after `043-01`; the 2026-05-29 performance refresh later
  measured `uv run maid test --json` at 26 commands and 41.07s.
- `uv run maid test --quiet` was rejected because `maid test` does not support
  `--quiet`; the supported command was rerun.
- Existing specialist plans were reviewed:
  - `docs/plans/maid-validate-hardening-backlog.md`
  - `docs/plans/maid-runner-performance-backlog.md`
  - `docs/plans/maid-runner-cleanup-refactor-backlog.md`
- Current draft epics and reference usage were reviewed:
  - `manifests/drafts/028-00-clean-code-maintainability-roadmap.epic.yaml`
  - `manifests/drafts/029-00-clean-code-maintainability-next-wave.epic.yaml`
  - `manifests/drafts/030-00-maid-validate-hardening-roadmap.epic.yaml`
  - `manifests/drafts/032-00-maid-validate-post-030-hardening-roadmap.epic.yaml`
  - `manifests/drafts/034-00-maid-runner-performance-roadmap.epic.yaml`
  - `manifests/drafts/035-00-maid-runner-cleanup-refactor-roadmap.epic.yaml`
  - `manifests/drafts/041-00-maid-runner-performance-diagnostics.epic.yaml`
- Active-manifest references to draft epics were checked with `rg`; `034-00`
  and `035-00` are still declared in active manifest `files.read` sections.
- Recent insights around TypeScript brownfield contracts, cache invalidation,
  parse-error refactoring, release recovery, and branch workflow were sampled.
- `docs/maid-philosophy-and-vision.md`, `docs/ROADMAP.md`, and `specs/` were
  sampled for strategy and documentation drift.
- A fresh MAID bug report was reviewed:
  `~/.maid/bug-report/20260529-103724-arch-spec-uv-run-project-command-integrity.md`.
  It showed a valid `uv run --project backend pytest ...` validate command
  rejected by command-integrity parsing with E230.

## Prioritized Improvement Themes

### 1. Retire the Remaining E111 Grandfathered Drops

Primary lane: MAID workflow.

Status: Completed by `manifests/043-01-retire-grandfathered-chain-noise.manifest.yaml`.

Evidence: `uv run maid validate --quiet` and `uv run maid test` both pass but
report 11 E111 chain notices for dropped artifacts in file discovery, validation,
graph constants, and retired tests.

Current symptom: The health checks are green but noisy. A maintainer or agent
must know that the E111 notices are expected, which weakens the meaning of a
clean done gate.

Why it matters: Persistent tolerated chain issues normalize noisy validation.
That makes future real chain regressions easier to miss.

Recommended owner skill: `maid-evolver`, with `maid-validate-hardening` review
if the closure changes chain semantics.

Closure shape: Supersede or normalize the affected historical manifests so the
current active chain no longer emits these grandfathered-drop notices, while
preserving intentional artifact removals.

Suggested acceptance criteria:

- `uv run maid validate --quiet` exits 0 and emits no E111 notices.
- `uv run maid test` exits 0 and reports `Chain issues: 0`.
- Focused tests prove intentional historical artifact drops remain auditable.

Next action: none. Keep explicit supersession audit coverage visible for
grandfathered drops.

### 2. Make Manifest Lifecycle Metadata Truthful

Primary lane: MAID workflow.

Status: Implemented by
`manifests/043-02-enforce-active-manifest-lifecycle-status.manifest.yaml`.

Evidence: Active manifests such as `032-*`, `035-01`, and `041-*` still include
`metadata.status: draft` or `metadata.status: planning` even though git history
shows related implementation commits have landed and validation passes.

Current symptom: Manifest lifecycle metadata does not consistently represent
whether a manifest is planning inventory, promoted implementation contract, or
completed historical record.

Why it matters: Agents use manifest status as workflow context. Stale status
increases the chance of re-planning already implemented work or misclassifying
active contracts as drafts.

Recommended owner skill: `maid-evolver`.

Closure shape: Define lifecycle metadata semantics for active manifests and add
a lightweight validation or audit check that flags impossible status values in
active `manifests/*.yaml` files.

Suggested acceptance criteria:

- Active manifests no longer use `planning` unless they are explicitly allowed
  as planning-only artifacts.
- Draft-only status remains valid under `manifests/drafts/`.
- A focused test or audit command catches stale active-manifest lifecycle
  metadata.

Next action: monitor future active manifests for
`ACTIVE_MANIFEST_INACTIVE_STATUS`; current stale active-manifest status metadata
was removed as a one-time cleanup in `043-02`.

### 3. Archive Consumed Draft Epics And Mark Live Plans

Primary lane: MAID workflow.

Status: Completed by `manifests/043-03-archive-consumed-draft-epics.manifest.yaml`.

Evidence: The `028`, `029`, `030`, `032`, and `041` draft epics each have their
planned child manifests promoted under `manifests/`. `034-00` and `035-00` are
also largely consumed, but active manifests still list those draft epic paths in
`files.read`, so deleting them directly would create manifest drift.

Current symptom: `manifests/drafts/` mixes live planning inventory, completed
roadmaps, and historical context. Future self-improvement passes can mistake
completed epics for current work.

Why it matters: Stale planning inventory is a source of false priorities. It
can make agents re-open completed waves or quote old performance and cleanup
guidance as if it were current.

Recommended owner skill: `maid-evolver`.

Closure shape: Create an explicit archive/retirement policy for consumed draft
epics. For unreferenced consumed epics, delete or move them to a historical
archive. For referenced epics such as `034-00` and `035-00`, first evolve the
active manifests that read them, or replace the draft files with short
"completed/archived" pointers that no longer look like active planning work.

Suggested acceptance criteria:

- `manifests/drafts/` contains only active draft inventory plus documented
  parked alignment maps such as `000-parser-replacement-roadmap.md`.
- Active manifests do not reference deleted draft paths.
- Completed epics are either removed, archived outside active draft inventory,
  or reduced to concise status pointers.
- `uv run maid validate --mode schema --quiet` and `uv run maid validate`
  both pass after the cleanup.

Next action: none for the consumed epics archived in `043-03`. Future draft
cleanup should only delete archived paths after active `files.read` references
are evolved.

### 4. Refresh Performance Measurements After the 041 Work

Primary lane: Performance.

Status: Completed as a planning refresh on 2026-05-29, then implemented by
`manifests/043-04-cache-typescript-compiler-project-for-import-resolution.manifest.yaml`.
The refreshed measurements are recorded in
`docs/plans/maid-runner-performance-backlog.md`.

Evidence: The performance backlog had identified assertion parsing, TypeScript
compiler resolution, and verify cache scope as hot paths. Git history shows the
041 cache/session/share-scope work has since landed. The refreshed local
`maid-runner` measurements now show `maid test --json` at 41.07s for 26
commands, while strict validation bottlenecks have moved mostly to Tower Recall
TypeScript behavioral validation.

Current symptom: The backlog contains pre-optimization benchmark numbers. The
next bottleneck should be chosen from fresh measurements, not from stale timing
data.

Why it matters: The obvious next ideas, such as parallel validation or
cross-invocation disk caches, have correctness and ordering risks. They should
only be pursued after measuring what remains slow.

Recommended owner skill: `maid-runner-performance-optimization`.

Closure shape: Re-run the benchmark matrix from the performance backlog against
MAID Runner and the reference projects, then update the backlog with post-041
timings and one or two new implementation-sized drafts.

Suggested acceptance criteria:

- The backlog contains before/after numbers for the 041 work.
- Remaining hot paths are backed by profile output or command timing.
- Any new draft preserves JSON-visible output and fail-closed validation
  behavior.

Next action: re-benchmark Tower Recall-style TypeScript behavioral validation
before creating another performance draft.

### 5. Continue Characterized ValidationEngine Refactoring

Primary lane: Maintainability.

Status: Closed as already implemented by the later `038` extraction wave and
the `039-01` cache/refactor work. The self-improvement backlog entry was stale,
not an unimplemented draft.

Evidence: `maid_runner/core/validate.py` now delegates the old large
orchestration paths to focused modules:

- `ValidationEngine.validate_removed_artifacts` delegates to
  `maid_runner/core/_removed_artifacts.py`.
- `ValidationEngine.validate_all` delegates to
  `maid_runner/core/_validate_all.py`.
- `ValidationEngine.validate_behavioral` delegates to
  `maid_runner/core/_behavioral_validation.py`.
- `ValidationEngine._check_test_coverage` delegates to
  `maid_runner/core/_implementation_coverage.py`.
- `ValidationEngine.validate_implementation` delegates to
  `maid_runner/core/_implementation_runner.py`.

Current symptom: The cleanup backlog still contains the pre-extraction method
size table and recommended next steps for `validate_removed_artifacts` and
`validate_all`, even though those wrappers are now thin.

Why it matters: A stale cleanup target can make a future agent create a
redundant `043-05` draft instead of selecting cleanup work from current code
evidence.

Recommended owner skill: `maid-runner-cleanup-and-refactor` for the next fresh
cleanup audit, not for the stale `validate_removed_artifacts` split.

Suggested acceptance criteria:

- The self-improvement backlog no longer points at
  `validate_removed_artifacts` as pending implementation work.
- The roadmap explains that future cleanup work must start from current code
  evidence rather than the stale pre-038 method-size table.
- Documentation verification confirms the current CLI version and schema-mode
  validation still pass.

Next action: refresh cleanup findings before creating any new refactor draft.

### 6. Update Stale Strategy And Roadmap Documentation

Primary lane: Documentation.

Status: Completed as a markdown-only refresh on 2026-05-29.

Evidence: `docs/ROADMAP.md` described version `0.1.3`, old test counts, a
2025 roadmap, and command names that no longer matched the current v2-era
CLI. The current package and CLI report `2.13.0`, and
`maid_runner/cli/commands/_main.py` exposes the current command set.

Current symptom: Closed for the roadmap. `docs/maid-philosophy-and-vision.md`
remains a long-form philosophy document and should be treated as strategic
context rather than a live implementation plan.

Why it matters: MAID Runner is workflow-heavy; stale docs cause expensive
misreads and repeated clarification.

Recommended owner skill: plain documentation editing. No MAID manifest is
required because this was a markdown-only accuracy update.

Closure shape: `docs/ROADMAP.md` now describes v2 current state, active
workstreams, the current CLI command surface, deferred/external work, and links
to the specialist backlogs instead of duplicating obsolete implementation
status.

Suggested acceptance criteria:

- Current version, command set, validation surfaces, and active workflow gates
  are accurate.
- Old roadmap claims are removed instead of left as live priorities.
- The roadmap points maintainers to the hardening, performance, cleanup, and
  self-improvement backlogs.

Next action: none for the roadmap. A future pass may separately tighten
`docs/maid-philosophy-and-vision.md` if it is being used as operational
guidance instead of background philosophy.

### 7. Recognize `uv run --project` Validate Commands

Primary lane: Validation trust.

Status: Implemented by
`manifests/043-05-recognize-uv-run-options-for-test-command-integrity.manifest.yaml`.

Evidence: A 2026-05-29 bug report from `arch-spec` showed
`uv run --project backend pytest backend/tests/services/test_prompt_engineering.py -q`
successfully running the intended test file manually, while MAID reported E230
because command-integrity parsing only recognized `uv run <runner>`.

Current symptom: Valid uv wrapper options before the test runner can make
`maid test` report zero executable commands even though the validate command is
a real pytest invocation targeting the declared behavioral test file.

Why it matters: E230 is a fail-closed anti-gaming gate. False positives force
authors to rewrite valid commands or use workarounds, which weakens trust in the
done gate and hides the real command shape projects need.

Recommended owner skill: `maid-validate-hardening` for evidence and contract,
then `maid-runner-draft-implement` style implementation review.

Closure shape: Strip bounded, non-cwd-changing `uv run` options before runner
detection and target scanning, then delegate to the existing test-runner
integrity checks so selector, collect-only, help, cwd-changing wrappers, and
unknown-wrapper behavior remains fail-closed.

Suggested acceptance criteria:

- `validate_manifest_test_commands` accepts `uv run --project backend pytest
  <declared-test-file> -q`.
- `test_paths_from_executing_validate_command` reports the declared test file
  after uv wrapper options.
- The manifest validates in behavioral, schema, and implementation modes.
- The focused command-integrity and validate CLI tests pass.

Next action: watch for other valid `uv run` wrapper options reported by real
projects; do not broaden wrapper parsing without a reproduced command shape.

## Routed Backlog

1. Done: retire E111 grandfathered-drop chain noise via `043-01`.
2. Done: define and enforce active-manifest lifecycle metadata via `043-02`.
3. Done: archive consumed draft epics as stable archive pointers via `043-03`.
4. Done: re-benchmark after 041 and plan the next measured optimization wave.
5. Done: close the stale characterized `ValidationEngine` method-split item
   against the already-landed 038/039 extraction work.
6. Done: refresh stale strategy and roadmap documentation for the current v2
   CLI and workflow state.
7. Done: recognize bounded `uv run` wrapper options before pytest in
   validate-command integrity via `043-05`.

## Specialist Follow-Ups

- Validation hardening should stay focused on false-green behavior. No new
  hardening draft should be created from speculative static-analysis ideas
  without a reproduced bypass.
- Performance work should not add parallelism or disk caches until fresh
  profiling proves redundant in-process work is no longer the main cost.
- Cleanup work should keep performance and behavior changes out of refactor
  drafts.
- Consumed draft epics should not be deleted until active manifest `files.read`
  references have been checked and evolved where needed.

## Draft Manifest Progress

Completed:

- `043-01-retire-grandfathered-chain-noise.manifest.yaml`
- `043-02-enforce-active-manifest-lifecycle-status.manifest.yaml`
- `043-03-archive-consumed-draft-epics.manifest.yaml`
- `043-04-cache-typescript-compiler-project-for-import-resolution.manifest.yaml`
- `043-05-recognize-uv-run-options-for-test-command-integrity.manifest.yaml`

Remaining candidates:

- None from this backlog as of the 2026-05-29 documentation refresh.

Future candidates should be created one at a time by the owning specialist
skill after confirming current evidence. Do not create the stale
`043-05-split-validation-engine-removed-artifacts.manifest.yaml` candidate
unless a new code audit finds a current behavior-preserving refactor target.

## Speculative Ideas

- Build the Layer 3/Layer 4 orchestrator described in
  `docs/maid-philosophy-and-vision.md` as a productized state machine. This is
  promising but needs a feature spec before MAID drafts.
- Revisit the parser replacement roadmap for TypeScript. Recent TypeScript
  brownfield fixes show the validator is still complex, but there is no current
  reproduced failure requiring a broad parser architecture change.
- Add editor/LSP integrations. This remains useful for developer experience,
  but it is not more urgent than false-green cleanup, lifecycle hygiene, and
  post-041 measurement.

## Verification Notes

- `uv run maid validate --quiet`: now passes without E111 notices after
  `043-01`.
- `uv run maid test --quiet`: failed because the argument is unsupported.
- `uv run maid test`: passed 18 commands; 0 failed; no E111 chain issues
  reported after `043-01`.
- `043-02` added an active-manifest lifecycle metadata diagnostic with focused
  tests in `tests/core/test_manifest_chain_discovery.py` and schema-mode
  coverage in `tests/core/test_validate_schema_mode.py`.
- `043-02` implementation review returned ready after the one-time active
  manifest metadata cleanup was declared in the manifest contract.
- `043-03` rewrote consumed epic drafts as `archive-kind` pointers with
  `metadata.status: archived`, preserving paths still read by active manifests.
- `043-04` performance refresh measured MAID Runner plus five reference
  projects after 041, confirmed Tower Recall TypeScript compiler bridge import
  resolution as the next current hot path, then promoted and implemented the
  cache-backed import-resolution bridge manifest.
- The 2026-05-29 documentation refresh confirmed `maid --version` reports
  `2.13.0`, refreshed `docs/ROADMAP.md`, and closed the stale
  `ValidationEngine.validate_removed_artifacts` cleanup candidate because the
  current method is already a delegate to `_removed_artifacts`.
- The `043-05` bug-fix pass reproduced the E230 false positive for
  `uv run --project ... pytest ...`, added focused command-target and
  command-integrity regression tests, and confirmed the fixed tests pass.
