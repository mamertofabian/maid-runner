# Full and Deep Verification Performance Redesign

## Purpose

The task-scoped handoff optimization in 121-01 reduced the common verification
path from about four minutes to 23-26 seconds, but it deliberately left full
`maid test` and the `deep` profile repository-wide. Those paths now dominate
the remaining workflow cost. This plan reopens the 121 performance roadmap and
targets the underlying runtime amplification without skipping commands,
weakening artifact attribution, or caching an inadequately keyed pass.

## Performance Contract

Every performance-only implementation child must preserve these invariants.
The differential-knockout child is deliberately separated because it evolves
the 068 contract; it must use `maid-evolver`, prove that unrelated failures no
longer count as detection, and may strengthen but never relax the gate:

- the same repository inputs select the same manifest commands and pytest
  nodes;
- command/test failures remain visible and produce the same gate success,
  stable error codes, warnings, and deterministic manifest-order reporting;
- artifact coverage is attributed only to tests selected by the declaring
  manifest, never to unrelated ambient execution;
- missing workers, incomplete runtime evidence, unresolvable selectors, and
  invalid cache metadata widen to the existing serial/full path or fail
  visibly; they never become an empty success;
- test-duration history may choose a scheduler but may not reuse a pass;
- buffered ordinary-test results carry typed resolved-runner/environment and
  all command-observable project-state identities, and are not reused across
  the current in-place knockout stage;
- persistent pass/evidence caching remains out of scope until MAID has a
  hermetic input declaration that includes repository bytes, dependencies,
  interpreter/tool versions, environment, and external services.

## Confirmed Current Baseline

Measurements were taken on 2026-08-10 on the integrated
`release/v2.next` tree at `0e4e2c5` (16 logical CPUs). The last fully green
full-command evidence on the immediately preceding performance commit was
241/241 commands in 233.22-235.27 seconds. The integrated tree's latest
profile completed in 225.79 seconds with 244/245 commands passing; its one
failure is the stale 121 live-epic expectation that reopening this roadmap
resolves.

| Scenario | Measured wall time | Dominant evidence |
| --- | ---: | --- |
| `uv run maid validate --quiet` | 5.90s | Static validation is not the current bottleneck. |
| `uv run maid test --json` | 225.79s latest; 233.22s last green | One broad pytest batch used 184.23s; the remaining command results used 35.32s summed. |
| Broad pytest suite | 176.96-184.23s | 3,927 cases in the clean pre-roadmap probe; 3,921 passed, with only a missing docs dependency failing in that temporary worktree. The reopened planning inventory currently collects 3,936. |
| Exact handoff, task tests | 23.10-25.92s | Already closed by 121-01. |
| Exact handoff, repository tests | 237.62-263.82s | Control path retaining all manifest commands. |
| Assessed deep verify | 1,827.5s | Reached repository artifact coverage and stopped on historical E710 debt before knockout or the normal tests stage. |

The slow-test distribution is concentrated enough to justify test-design
work before scheduling work:

- the 45 recorded tests at or above one second consumed 85.21 seconds;
- the slowest 150 tests consumed 136.19 seconds;
- `tests/cli/test_nested_strict_preview.py` consumed 18.66 seconds across five
  tests;
- `tests/core/test_artifact_coverage_batch.py` consumed 18.16 seconds across
  seven tests;
- the recorded slow cases in `tests/core/test_artifact_coverage.py`,
  `tests/cli/test_plan_legacy_baseline_cmd.py`, and
  `tests/cli/test_plan_cmd_stash_implementation.py` consumed another 36.33
  seconds.

These tests repeatedly launch coverage, pytest, validation, or Git processes.
They are behavioral, but most scenarios are policy matrices that can use an
owned fake at an injected process boundary while a small integration layer
continues to execute the real adapter.

## Confirmed Deep-Gate Amplification

The integrated active chain has 413 manifests. Static inventory of the current
implementation found:

- 1,680 Python artifact-coverage targets across 329 manifests;
- 353 coverage-command declarations and 297 exact pytest argument tuples;
- 352 of 353 declarations share one existing batch-compatibility key;
- `run_artifact_coverage_batch` executes the 297 exact tuples serially through
  `_run_shared_coverage_command`, even though a per-test-attributed compatible
  run could cover the selected nodes once;
- 1,093 knockout declarations, representing 554 unique artifacts;
- up to 1,867 validate-command executions in the current serial in-place
  knockout loop.

Artifact coverage currently runs before the normal tests stage. Deep verify
therefore pays for runtime tests under coverage, discards that process-level
evidence, and would later run the tests again. If coverage became green, the
current deep profile would then mutate source files one artifact at a time and
run each declaring manifest's commands serially. The 30-minute observed run is
therefore a lower bound on the old design, not the complete deep-gate cost.

## Strategy

### 1. Establish test isolation as a gate prerequisite

The rejected 121-02 experiment showed different outcomes, but its isolated
worktree was missing the declared `node_modules/typescript` dependency. After
`npm install`, the suspected TypeScript tests and full serial `maid test`
passed. That evidence was environment-confounded and does not justify cache
cleanup. Add a non-recursive external probe that compares the full collected
node set, setup/call/teardown outcomes, and exit result between fresh serial
pytest and one pinned xdist scheduler in the same resolved environment. Both
runs must exit zero; matching failures are not equivalence. Do not rely on a
marker that xdist does not enforce. Parallel execution cannot become the
default until the full serial and worker outcome sets agree.

### 2. Reduce serial work at the test-design boundary

Separate policy from subprocess/Git mechanism in the slowest test clusters.
Artifact-coverage and nested strict-preview policy tests should consume a fake
runtime-evidence executor; plan-lock/stash tests should clone a prebuilt tiny
Git template instead of initializing and committing an entire repository for
every case. Keep real-adapter integration tests for success, command failure,
timeout, mutation/restoration, and Git index/worktree behavior. Prove reduced
spawn/init counts rather than asserting fragile wall-clock thresholds in unit
tests.

### 3. Separate timing policy from pytest parallelism

First add content-bound advisory timing history and a pure worker decision; it
may choose a scheduler but can never skip a node or reuse a pass. In a separate
child, use pytest's runner-native scheduler instead of MAID file sharding. The
integration detects xdist in the resolved consumer command environment,
respects an existing command/config `-n`, merges controller/worker timings,
and emits structured text/JSON scheduling notices. Automatic worker injection
is pinned to `--dist loadscope` and eight workers, the exact scheduler/count
accepted by the repository-wide probe; any other injected scheduler or count
falls back visibly or fails until it has its own equivalence evidence. One
process budget covers both pytest workers and independent command groups so
nested concurrency cannot oversubscribe the host.
Small task-scoped commands stay on the low-overhead serial path, and explicit
single-worker/job requests win.

### 4. Collect attributed runtime evidence once

For deep verification, execute each compatible pytest behavior group once
under a MAID pytest plugin that records:

- each collected node ID and setup/call/teardown outcome;
- line and function/method call execution keyed by node context;
- collection/import contexts that cannot be assigned to a node;
- fixture contexts plus their scope and complete consuming-node set;
- the exact command identity, normalized behavior group, selector-to-node map,
  worker set, completeness state, and diagnostics.

Coverage.py contexts and pytest hooks provide runtime evidence without a
custom control-flow analyzer. Consumer-node closure proves attribution, not
fixture-lifecycle equivalence: grouping formerly separate selectors can change
class/module/package/session or autouse fixture multiplicity, state, order, and
yield-fixture teardown. Only function-scoped fixture lifecycles proven
identical under the grouped command are reusable. Every wider, autouse,
dynamic, yield-teardown, or otherwise unproven lifecycle runs the affected
exact legacy command. Ambiguous collection, worker, or selector evidence does
the same. Maid-runner itself has two session-autouse fixtures in root
`tests/conftest.py`, so correctness can conservatively force all 297 tuples to
fallback; the roadmap does not pretend otherwise. The optimistic grouped path
still exists, but 121-15 separately bounds the exact fallback path after
snapshot isolation. Per-manifest reports union only proven contexts selected
by that manifest's original command, so unrelated execution cannot satisfy
E710.

### 5. Prove report equivalence, then let deep reuse the run

First compare evidence-derived honest/missing artifacts, command errors, and
JSON with the exact legacy coverage runner, including fixture/collection
fallbacks. Only then may deep build the ordinary test plan and execute a whole
matching pytest group at the existing artifact-coverage boundary. Partial
groups are not reusable; command, targets, behavior options, environment, and
  content and typed resolved-environment identity must match the later ordinary
  plan. Residual and
non-overlapping commands remain unexecuted until the ordinary
tests stage, preserving its side-effect boundary. A missing context, selector
mismatch, worker loss, or content-digest mismatch runs the affected legacy
command or emits a blocking diagnostic. Recompute relevant generated/untracked
state immediately before reuse. Because in-place knockout currently intervenes
between artifact coverage and tests, a deep run with knockout discards the
ordinary buffered result and runs tests fresh; only a later independently
reviewed post-isolation change may remove that guard. Text and JSON retain
separate `tests` and `artifact_coverage` stages even when execution is shared.

### 6. Replace knockout amplification without heuristic skips

Index the 1,093 declarations as 554 immutable unique-mutation specifications
while retaining every per-manifest declaration and exact command. This first
step changes planning only; it does not share a mutable mutation lifetime or
claim runtime savings. Baseline non-execution is not proof that a test is
irrelevant: source/AST readers, collection hooks, fixtures, ordering, and child
processes may still observe the changed file. Runtime contexts may therefore
propose a focused detector only as speculative positive evidence.
Accept it only when the same controlled execution shape proves
unmutated-green, mutant-red, then restored-green. Any incomplete or
inconclusive case runs the original command. This deliberately strengthens the
current gate by refusing to count an unrelated pre-existing command failure as
mutation detection; implementation must evolve the 068 contract explicitly.

This is a confirmed hardening finding, not a hypothetical one:
`maid_runner/core/knockout.py::_run_validate_commands` currently sets
`detected = True` for any nonzero validate-command result without first proving
the same command is green against the unmutated source. The selected evidence
source is test-runner output in a controlled green/red/restored-green sequence,
with the exact original command as fallback. No custom reachability or fixture
AST model is proposed.

After exact plan parity and differential semantics are proven, apply mutations
in materialized current-byte project snapshots. An import-only
overlay is insufficient because source readers, path loaders, editable
installs, subprocesses, and non-pytest commands must see the same mutated
bytes. Every retained declaration receives a fresh/reset child snapshot, even
when several declarations share one unique specification; a prior command's
generated state cannot become the next declaration's baseline. Each active
worker has an independent cwd and generated/cache state; inability to produce
an equivalent snapshot fails closed. Run independent snapshots under one
bounded process budget, buffer results, and report them in chain/declaration
order without ever modifying the shared checkout.

Snapshot isolation includes repository metadata. Ordinary `.git` directories
and linked-worktree pointer/common-dir layouts must become independently
writable metadata with no shared index, refs, stash/logs, config, worktree
records, or mutable objects. Adversarial snapshot commands commit, stash,
update refs/config/index, reset, and run maintenance; original HEAD, refs,
stash, config, index, object identity, worktree registrations, source bytes,
and status must remain unchanged or the harness returns E712.

### 7. Bound the conservative coverage fallback itself

Grouped evidence is an optional fast path, not the only route to the budget.
After the snapshot and process-budget boundaries are proven, execute each
unproven artifact-coverage fallback as its original exact selector in its own
pytest process and independently materialized snapshot. This preserves
session/module/autouse and yield-teardown lifetime while allowing bounded
overlap. Normalize coverage paths and buffer reports in original manifest and
command order.

Each worker records pre/post observable project and Git identities. Any
unclassified material write, external execution uncertainty, worker loss,
snapshot mismatch, or path-remapping gap discards the entire parallel batch and
runs the exact legacy sequence in original order (so later state readers remain
equivalent) or emits E900/E712. Consumer defaults remain one; maid-runner opts
in only after a full active-inventory
serial-versus-isolated report comparison and a separately measured parallel
phase below 180 seconds. Thus the root session-autouse fixtures reduce the
grouped hit rate without invalidating the final performance path.

## Executable Fitness Functions

The queue is evolutionary rather than a verification rewrite. Each boundary
has a repeatable enablement signal and a retained fallback:

| Architectural characteristic | Fitness function | Enablement / rollback rule |
| --- | --- | --- |
| Pytest outcome equivalence | 121-03 compares full serial and pinned-xdist collection, phase outcomes, and exit status in fresh processes. | Do not enable workers while any node differs; retain serial execution. |
| Scheduler transparency and resource safety | 121-06/07 prove unchanged node selection, resolved-runner capability checks, structured notices, and one process budget. | Explicit one stays serial; missing capability falls back visibly or fails an explicit request. |
| Manifest-specific runtime attribution | 121-08 records command, node, fixture setup/teardown, collection, worker, lifecycle, and completeness identities; 121-09 compares E710/E900/JSON reports. | Any attribution ambiguity or unproven fixture-lifecycle equivalence executes the affected exact legacy command. |
| Deep stage behavior | 121-10 records execution sequence and compares text/JSON/fail-fast results. | Reuse only an entire content/environment-bound ordinary group; run partial/residual commands at the original tests-stage boundary. |
| Mutation-plan integrity | 121-11 compares deduplicated identities, limits, declaration records, source digests, and command order with legacy planning while characterizing existing per-declaration restore. | Do not share execution state in this child; proceed only when the plan is exact and declarations remain independently restored. |
| Mutation-caused detection | 121-12 proves green-mutant-red-restored-green and adversarial exact fallback. | Never use focused evidence for non-detection; inconclusive cases run the original command. |
| Worktree isolation | 121-13 verifies source readers/children see snapshot bytes while original content and Git status never change. | Snapshot uncertainty is E712; retain serial behavior until equivalence is proven. |
| Git-metadata isolation | 121-13 exercises ordinary and linked-worktree metadata writes against HEAD, refs/stash, config, index, objects, registrations, and status. | Any shared pointer/inode or source-repository identity change is E712. |
| Bounded deterministic concurrency | 121-14 proves overlap, per-declaration child-snapshot reset, effective config/command/auto xdist token bounds, crash handling, and serial/parallel payload parity. | Jobs=1 is always available; a lost worker or shared mutable declaration state is E712, never success. |
| Exact coverage fallback latency | 121-15 compares full normalized serial/isolated reports and measures the parallel phase after equivalence. | Any material write/uncertainty reruns serial; the 180-second budget is enabled only after acceptance. |

## Ordered 121 Continuation

1. `121-03-prove-pytest-process-isolation-before-parallelism`
2. `121-04-separate-runtime-policy-from-subprocess-tests`
3. `121-05-reuse-fast-real-git-test-projects`
4. `121-06-record-duration-informed-pytest-policy`
5. `121-07-integrate-duration-informed-pytest-workers`
6. `121-08-collect-fixture-aware-runtime-evidence`
7. `121-09-prove-runtime-evidence-artifact-coverage-equivalence`
8. `121-10-reuse-runtime-evidence-in-deep-verify`
9. `121-11-deduplicate-knockout-mutation-specs`
10. `121-12-require-differential-knockout-detection`
11. `121-13-isolate-knockouts-in-project-snapshots`
12. `121-14-run-isolated-knockouts-with-bounded-workers`
13. `121-15-parallelize-isolated-artifact-coverage-fallbacks`

Each child is independently reviewable and must remeasure before the next
child is promoted. Do not enable workers in 121-07 until 121-03 proves
full-suite outcome equivalence; do not wire deep reuse in 121-10 until 121-09
proves report equivalence; do not enable knockout workers in 121-14 until
121-12 and 121-13 prove differential attribution and snapshot equivalence; do
not enforce coverage/deep budgets until 121-15 proves exact fallback report
equivalence and remeasures the parallel phase.

## Performance Budgets

These are acceptance targets to verify, not claims that profiling has already
proved them:

- retain task-scoped handoff below 30 seconds;
- reduce this repository's green `maid test` to at most 60 seconds on the
  16-thread reference machine, with a cleaned-up serial fallback below 90
  seconds;
- reduce the cold artifact-coverage stage below 180 seconds after the 121-15
  full report-equivalence acceptance proves the isolated fallback path;
- reduce a known-green full deep profile, including knockout, below five
  minutes; apply the same repository-wide target only after the independent
  1,680 E710 debt items are closed;
- keep a small/focused pytest command serial when predicted parallel overhead
  exceeds its work.

If a child cannot demonstrate a measurable reduction and identical observable
results on this repository, stop or redesign it rather than landing complexity
for a speculative win.

## Explicitly Rejected Shortcuts

- raw target-file sharding or round-robin subprocesses;
- file-count-only worker thresholds;
- skipping repository commands or E710/E711 findings;
- treating incomplete coverage contexts as empty success;
- using baseline non-execution to skip a knockout command;
- import-only mutation overlays or concurrent mutation of the shared checkout;
- persistent green-result caching keyed only by Git commit, mtimes, or test
  files;
- weakening deterministic JSON/error ordering to gain concurrency.
- treating the two root session-autouse fixtures as grouped-equivalent without
  proof, or leaving their exact fallback serial and still claiming the budget;

## Verification Notes

Evidence commands used for this redesign:

- `uv run maid validate --quiet`
- `uv run maid test --json`
- `uv run pytest tests/ --collect-only -q`
- `uv run pytest tests/ -q --durations=150`
- static active-chain inventory using `get_cached_manifest_chain`,
  `_coverage_targets`, `_pytest_args`, `_batch_group_key`, and
  `_knockout_targets`
- the 121-01 handoff and repository-scope benchmarks already recorded in the
  performance backlog
- the assessed deep command recorded by 121-01, which ran 1,827.5 seconds and
  stopped at repository-wide E710 debt; future end-to-end timing must use
  `--keep-going` or a known-green fixture until that debt is independently
  closed

## Continuation reopened 2026-08-13 (121-19, 121-20, 121-26)

A review of this branch confirmed the deep gate still spent 24-46 minutes in
the legacy serial coverage batch because the grouped-evidence fast path is
preflight-disabled for any conftest-bearing repository and never ran here. The
hardened isolated boundary from 121-13/121-14/121-15 existed but was reachable
only through that disabled path. Three childs reconnect and correct it:

- **121-19** routes the legacy `run_artifact_coverage_batch` itself through the
  isolated lanes (config-resolved `fallback_jobs`/`max_processes`), with a
  disclosed `ArtifactCoverageExecutionSummary` per report; `jobs=1` stays
  byte-for-byte serial. Consumer default remains one lane.
- **121-20** replaces the single whole-batch `unsafe` flag. Material writes and
  worker/harness errors stay whole-batch fail-closed; a command that merely
  exited non-zero without material writes escalates only its own identity, in
  deterministic chain order. This removes the double-work regression that made
  the isolated path slower than serial when a few genuinely failing commands
  (for example the coverage-under-coverage meta-tests) were present.
- **121-26** binds the `sys.monitoring` DISABLE sentinel once at registration
  in both generated coverage-runner scripts. A test that legitimately swaps
  `sys.monitoring` (maid-runner's own `test_runtime_evidence.py`) no longer
  makes the callback raise, which previously produced an unraisable E900,
  empty execution data, and fabricated E710 coverage gaps.

Measured on this repository (bounded sampled equivalence, never a full serial
reference): serial-versus-isolated reports are byte-identical (`to_dict` minus
the disclosure key); per-identity escalation replays only genuinely red
commands; the pre-121-20 double-work regression (265s isolated vs 147s serial
on a red-heavy 3-command sample) is gone (179s vs 172s). The isolated path
carries a per-lane snapshot cost, so it wins only on large batches where a few
lane snapshots amortize across many slow commands (the full ~297-command deep
stage); it is break-even to slower on small or fast batches. A command-count
threshold to keep small dir-level batches serial is a follow-up, relevant once
121-24 task-scopes the coverage and knockout stages. The full known-green deep
budget stays gated behind the independent 1,680 E710 debt and the sysmon
coverage-under-coverage meta-test conflicts, both pre-existing.
