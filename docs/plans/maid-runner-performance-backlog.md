# MAID Runner Performance Backlog

## Purpose

This backlog records measured performance diagnostics for `maid validate`,
`maid test`, and `maid verify` across MAID Runner and five reference projects.
It was refreshed after the 041 performance work landed:

- `maid-runner`: 276 active manifests, Python package with Python, TS, and Svelte validators.
- `adverio-tools-api`: 51 manifests, 43 active, Django/docker-heavy backend.
- `adverio-tools-app`: 22 manifests, 22 active, Angular/Nx/Jest frontend.
- `tower-recall`: 39 manifests, 28 active, Svelte/Vitest frontend.
- `atomic-carpool`: 120 manifests, 104 active, Next/Vitest/Playwright app.
- `life-dashboard`: 161 manifests, 161 active, Python API plus Svelte frontend.

The goal is to prioritize speedups that preserve MAID's anti-gaming contract:
the same inputs must produce the same success flags, error codes, warnings,
locations, and JSON-visible results.

## Benchmark Notes

Commands used the local MAID Runner checkout via:

```bash
uv run --project /home/atomrem/projects/codefrost-dev/maid-runner maid <command>
```

`verify` was timed as:

```bash
maid verify --keep-going --no-changed-scope --advisory --json
```

`--no-changed-scope` removes git baseline noise from cross-project timing while
keeping schema, behavioral, implementation, coherence, file tracking, worktree
scope when applicable, and test stages.

## Post-043 Timing Summary

Measured on 2026-05-29 after `043-04` landed.

| Project | Command | Wall time | Result | Notes |
| --- | --- | ---: | --- | --- |
| maid-runner | `uv run maid validate --mode schema --quiet` | 1.56s | pass | 281 active manifests. |
| maid-runner | `uv run maid validate --mode behavioral --quiet` | 3.32s | pass | Strict assertion cache work is holding. |
| maid-runner | `uv run maid validate --mode implementation --quiet` | 3.53s | pass | Source artifact caches are holding. |
| maid-runner | `uv run maid verify --keep-going --json` | 43.05s | pass | Tests stage was 37.20s of 42.89s JSON-reported duration. |
| maid-runner | `uv run maid test --json` | 36.85s | pass | 28 command executions after batching and pruning; one batched pytest run took 23.72s. |
| tower-recall | `maid validate --mode behavioral --quiet` via local runner | 3.76s | pass | Down from the post-041 19.57s TypeScript hotspot. |
| tower-recall | `maid validate --mode implementation --quiet` via local runner | 3.80s | pass | Comparable to implementation timing after prior cache work. |
| tower-recall | `maid verify --keep-going --no-changed-scope --advisory --json` via local runner | 25.25s | failed | Current project file-tracking failure; tests stage still passed and took 17.70s. |
| tower-recall | `maid test --json` via local runner | 16.75s | pass | Five serial command groups. |
| tower-recall | Same five `maid test` commands launched concurrently | 7.26s | pass | Confirms opt-in parallel command execution can reduce test-stage wall time. |

The refreshed measurements show the previous TypeScript compiler-resolution
hotspot is closed enough to stop planning more TypeScript-cache work for now.
The remaining measurable MAID-runner-side opportunity is the `maid test` stage:
after safe batching and pruning, independent command groups still run serially.

## Post-077 `maid test` Timing Probe

Measured on 2026-06-27 on `release/v2.next` with 381 manifest files, 6 draft
manifests, and 200 pytest files.

| Command / probe | Wall time | Result | Notes |
| --- | ---: | --- | --- |
| `uv run maid test --json` | 4:06.26 | pass | 147 command executions after batching and pruning. |
| `uv run maid test --jobs 8 --json` | 1:33.64 | pass | 149 command executions after adding the 078 drafts; overlaps subprocess fallback work but still spends 253.07s summed command time. |
| `uv run maid validate --mode schema --quiet` | 2.95s | pass | Mode-wide schema validation. |
| `uv run maid validate --mode behavioral --quiet` | 6.50s | pass | Mode-wide behavioral validation. |
| `uv run maid validate --mode implementation --quiet` | 7.07s | pass | Mode-wide implementation validation. |
| `uv run maid validate --quiet` | 6.99s | pass | Default implementation validation. |
| In-process probe over 140 validate-shaped commands with `--quiet` stripped and outer chain cache | 15.80s | pass | Counterfactual for making quiet commands cache-eligible inside `run_tests()`. |
| In-process probe over the same commands with outer chain and validation cache scopes | 13.88s | pass | Validation cache scope adds a small extra win; chain caching is the dominant win. |

`maid test --json` split by command kind:

| Kind | Count | Sum | Max | Notes |
| --- | ---: | ---: | ---: | --- |
| `maid validate` commands | 140 | 166.18s | 6.54s | 130 included `--quiet` and were not cache-eligible. |
| pytest commands | 5 | 70.04s | 60.72s | The largest command is one batched pytest run over the repo test suite. |
| docs / formatting commands | 2 | 3.69s | 3.11s | Sphinx API docs build and Black check. |

The current slowdown is not primarily the pytest batch. The largest avoidable
amplification is 130 `maid validate ... --quiet` commands falling through the
in-process cache parser and running as external `uv run maid validate`
subprocesses. Those commands account for 161.86s of the 246.26s wall run.
Only 10 non-quiet validate commands were cache-compatible, and they accounted
for 4.32s total.

Because `run_tests()` already opens an outer manifest-chain cache scope, adding
`--quiet` support to `_parse_maid_validate_command` should allow the existing
cached path to reuse the chain across these commands. The counterfactual probe
shows the validate-shaped portion can fall from roughly 166s to roughly 16s
without weakening validation or changing the declared command set.

Immediate workaround: `uv run maid test --jobs 8 --json` reduces wall time to
1:33.64 in the current checkout, but it does this by running multiple external
`uv run maid validate` subprocesses concurrently. It uses similar total CPU
time to the default run, so it is useful for local waiting time but does not
close the underlying cache miss.

## Post-041 Timing Summary

Measured on 2026-05-29 after `041-01` through `041-04` landed. Commands used
the same local MAID Runner checkout and the same verify flags listed above.

| Project | Schema validate | Behavioral validate | Implementation validate | `maid test --json` | Verify gate |
| --- | ---: | ---: | ---: | ---: | ---: |
| maid-runner | 1.54s | 3.35s | 3.50s | 41.07s | 47.49s |
| adverio-tools-api | 0.55s | 0.91s failed | 0.99s failed | 0.49s failed | 4.34s failed |
| adverio-tools-app | 0.27s | 1.14s | 1.31s | 0.28s failed | 4.31s failed |
| tower-recall | 0.33s | 19.57s | 17.45s | 17.85s | 39.91s failed |
| atomic-carpool | 0.72s failed | 21.08s failed | 16.50s failed | 0.62s failed | 37.36s failed |
| life-dashboard | 0.67s | 6.04s | 4.06s | 13.91s | 22.77s failed |

The same project-state failures still explain most nonzero exits, except
Atomic Carpool now spends materially more time before failing and needs a
separate project-local triage before using it as a benchmark anchor.

Nonzero exits in the refreshed matrix were caused by current project state, not
timing harness errors:

- `adverio-tools-api`: duplicate manifest sequence numbers E107.
- `adverio-tools-app`: E230 validate-command integrity failures around `yarn test --testPathPattern`.
- `atomic-carpool`: duplicate YAML key and downstream validation failures in
  current project state.
- `tower-recall`: verify file-tracking gate failed with undeclared and registered files.
- `life-dashboard`: one batched pytest command failed in current dirty worktree.

## Stage Timing

Stage-level API timing isolates strict validation bottlenecks. The current
numbers were gathered inside one `ValidationEngine.validation_cache_scope()` to
match the post-041 verify cache-sharing behavior.

| Project | Schema | Behavioral with assertions | Implementation with stubs | File tracking | Tests |
| --- | ---: | ---: | ---: | ---: | ---: |
| tower-recall | 0.189s | 19.134s | 3.509s | 4.083s failed | 17.85s |
| life-dashboard | 0.495s | 7.307s | 1.107s | 2.562s failed | 13.91s |
| maid-runner | 1.440s | 3.505s | 2.880s | 2.992s | 41.07s |

The 041 work moved the previous worst cases substantially:

- Life Dashboard behavioral-with-assertions fell from 93.856s to 7.307s.
- Tower Recall implementation-with-stubs fell from 42.509s to 3.509s.
- Tower Recall behavioral-with-assertions is still 19.134s and remains the
  best current optimization target.

Coherence was not remeasured in this pass because the prior run showed it below
0.15s and the current slow stages are elsewhere.

## Confirmed Hot Paths

### 1. Assertion checks reparse the same test tree per manifest

Files and functions:

- `maid_runner/core/_behavioral_validation.py::_run_behavioral_validation`
- `maid_runner/core/_test_assertions.py::validate_test_assertions`
- `maid_runner/core/_test_assertions.py::check_test_assertions`
- `maid_runner/core/_validation_test_artifacts.py::find_test_files`

Evidence:

- Life Dashboard has 161 active manifests and 156 active validate commands that
  are effectively `pytest tests/ -v`.
- Plain behavioral validate was 11.718s, but behavioral validate with assertion
  checks was 93.856s.
- cProfile for Life Dashboard strict behavioral validation recorded
  184.429s cumulative in `validate_test_assertions`, 28,266 Python AST parses,
  and 61,072,601 `ast.walk` calls under profiling.
- `find_test_files` expands directory targets with `Path.rglob()` per manifest,
  so a broad command such as `pytest tests/ -v` turns into the whole test tree
  repeatedly.

Status: closed by `041-01-cache-assertion-checks-and-test-discovery`.

Current evidence: Life Dashboard strict behavioral validation is now 7.307s,
down from 93.856s. Keep the invalidation and fail-closed tests from 041 visible
when changing assertion-cache boundaries.

### 2. TypeScript compiler resolution spawns Node per unresolved request

Files and functions:

- `maid_runner/core/ts_module_paths.py::resolve_ts_import`
- `maid_runner/core/ts_module_paths.py::resolve_ts_reexport`
- `maid_runner/core/ts_compiler_resolver.py::_run_compiler_request`
- `maid_runner/core/_behavioral_validation.py::_validate_artifacts_used_in_tests`

Evidence:

- Tower Recall behavioral validate with assertions was 46.356s.
- cProfile for Tower Recall behavioral validation recorded 40.538s cumulative
  in `ts_compiler_resolver._run_compiler_request`, through 101 `subprocess.run`
  calls to the Node bridge.
- The same profile recorded 12.036s cumulative in `_validate_artifacts_used_in_tests`,
  with 5,176 `resolve_ts_reexport` calls and 69 compiler-backed re-export
  requests.

Status: partially closed by `041-02-batch-typescript-compiler-resolution` and
`041-04-cache-ts-reexport-compiler-fallback`.

Current evidence: Tower Recall strict behavioral validation is now 19.134s,
down from 46.356s. A fresh cProfile run still recorded 15.220s cumulative in
`ts_compiler_resolver.py::_request`, driven by 105 session requests and 33
compiler import resolutions. The remaining cost is no longer Node process
startup per request; it is mostly bridge request latency while the CJS bridge
rebuilds TypeScript project state for import resolution.

### 3. Verify clears validation caches between validation stages

Files and functions:

- `maid_runner/cli/commands/verify.py::_run_verify_cached`
- `maid_runner/core/validate.py::ValidationEngine.validate_all`
- `maid_runner/core/validate.py::ValidationEngine._enter_validation_cache_scope`
- `maid_runner/core/validate.py::ValidationEngine._exit_validation_cache_scope`

Evidence:

- `verify` reuses a `ValidationEngine`, but each `_validation_stage` calls
  `engine.validate_all()` independently.
- `validate_all()` enters and exits the validation cache scope on every call.
  The outermost exit clears artifact collection caches and TypeScript resolution
  caches.
- Tower Recall verify spent 46.356s in strict behavioral validation and 42.509s
  in strict implementation validation, while the same command-wide run could
  safely share source fingerprints, TypeScript resolution results, and parsed
  source state across those two stages.

Status: closed by `041-03-share-verify-validation-cache-scope`.

Current evidence: Tower Recall verify fell from 92.591s to 39.91s, and Life
Dashboard verify fell from 106.265s to 22.77s, despite both still failing on
current project-local gates.

### 4. TypeScript bridge rebuilds project state for import resolution

Files and functions:

- `maid_runner/core/ts_compiler_resolver.cjs::resolveImport`
- `maid_runner/core/ts_compiler_resolver.cjs::loadProject`
- `maid_runner/core/ts_compiler_resolver.py::TypeScriptCompilerResolverSession._request`
- `maid_runner/validators/_typescript_behavioral.py::_scan_imports`

Evidence:

- Tower Recall strict behavioral validation still takes 19.134s.
- Fresh cProfile for Tower Recall recorded 15.220s cumulative in
  `TypeScriptCompilerResolverSession._request`, with 105 request/response waits
  and 33 `resolveImport` compiler calls.
- `resolveImport` currently calls `loadProject`, and `loadProject` creates a
  full TypeScript program even though import resolution only needs parsed
  compiler options and a compiler host.

Closure shape:

- Split the CJS bridge's import-resolution path away from full program
  construction.
- Cache parsed config/options and compiler hosts inside one session process,
  keyed by project root, tsconfig signature, and extra importer root when
  needed.
- Keep re-export resolution on a program-backed path, because symbol chasing
  needs the TypeScript checker.
- Preserve existing fail-closed semantics when TypeScript is missing, config
  parsing fails, the bridge times out, or a request returns malformed JSON.

Status: closed by `043-04-cache-typescript-compiler-project-for-import-resolution`.

Current evidence: Tower Recall strict behavioral validation is now 3.76s, down
from the post-041 19.134s and the pre-041 46.356s. Do not create more
TypeScript-resolution performance work without a fresh profile showing a new
dominant TypeScript bridge cost.

### 5. `maid test` serializes independent command groups after batching

Files and functions:

- `maid_runner/core/test_runner.py::run_tests`
- `maid_runner/core/test_runner.py::_run_implementation_commands`
- `maid_runner/core/_test_command_execution.py::_run_test_command`
- `maid_runner/cli/commands/_main.py::_register_test_parser`
- `maid_runner/cli/commands/test.py::cmd_test`
- `maid_runner/cli/commands/verify.py::_tests_stage`

Evidence:

- MAID Runner `maid verify --keep-going --json` passed in 43.05s, with the
  tests stage accounting for 37.20s.
- MAID Runner `maid test --json` passed in 36.85s after existing batching
  reduced the run to 28 command executions. The largest batched pytest command
  took 23.72s, but remaining independent commands still ran serially.
- Tower Recall `maid test --json` passed in 16.75s with five command groups:
  batched Vitest 2.27s, `pnpm check` 5.59s, `pnpm lint` 4.73s,
  `pnpm format:check` 3.68s, and one Python pytest command 0.14s.
- Launching those same five Tower Recall commands concurrently passed in
  7.26s. That is a 57% wall-time reduction for the test stage without changing
  the command set or exit status.

Closure shape:

- Add an opt-in `maid test --jobs N` and matching `maid verify --test-jobs N`
  path for independent implementation command groups after existing
  de-duplication, pruning, and pytest batching.
- Preserve default serial execution and fail-fast semantics; either disable
  parallelism when fail-fast is active or document and test a deterministic
  policy that does not hide the first failing command.
- Preserve output determinism by returning `BatchTestResult.results` in the
  same command order the serial runner would have produced, regardless of
  completion order.
- Keep cached in-process `maid validate` command reuse serial unless the
  implementation isolates per-worker validation caches safely.

Status: closed by
`046-01-parallelize-independent-maid-test-command-groups.manifest.yaml`.

Current behavior: `maid test --jobs N` opts active manifest-set runs into
parallel execution for independent implementation command groups, and
`maid verify --test-jobs N` applies the same policy to the verify tests stage.
Single-manifest `maid test --manifest ...` execution remains serial. Default
jobs remain serial, fail-fast stays on the serial path, cached in-process
`maid validate` commands are kept out of the worker pool, and results are
reported in serial-equivalent order.

### 6. `maid test` misses cached execution for quiet `maid validate` commands

Files and functions:

- `maid_runner/core/_maid_validate_command_cache.py::_parse_maid_validate_command`
- `maid_runner/core/_maid_validate_command_cache.py::_run_cached_maid_validate_command_in_scope`
- `maid_runner/core/test_runner.py::_run_implementation_commands`
- `maid_runner/cli/commands/_format.py::format_validation_result`
- `maid_runner/cli/commands/_format.py::format_batch_result`

Evidence:

- MAID Runner `uv run maid test --json` passed in 4:06.26 on 2026-06-27.
- The run executed 147 commands after batching and pruning. 140 were
  `maid validate` shaped commands with a combined 166.18s duration.
- 130 of the 140 validate-shaped commands included `--quiet`.
  `_parse_maid_validate_command` accepts `--mode`, `--manifest-dir`, `--json`,
  and `--no-chain`, but rejects unrecognized flags, so every quiet validate
  command falls back to a full subprocess.
- The 130 quiet validate commands accounted for 161.86s. The 10 non-quiet
  validate commands accounted for 4.32s.
- A throwaway in-process probe over the same 140 commands, with `--quiet`
  stripped and an outer manifest-chain cache scope matching `run_tests()`, took
  15.80s with all commands passing.

Closure shape:

- Extend `_parse_maid_validate_command` to accept `--quiet` and record a
  `quiet` boolean separately from `json_mode`.
- Keep unsupported flags fail-closed; do not broaden the parser to arbitrary
  validate options without tests for output equivalence and cache safety.
- Make `_run_cached_maid_validate_command_in_scope` pass the parsed quiet flag
  into `format_validation_result` and `format_batch_result`, preserving quiet
  success output shape and visible diagnostics on failure.
- Add runner coverage proving `maid test` does not call the subprocess
  fallback for quiet `maid validate` commands and still returns the same
  success flags, exit codes, command ordering, and quiet stdout/stderr shape.
- Re-benchmark `uv run maid test --json` after implementation. Expected wall
  time should fall near the remaining pytest/docs cost plus roughly 16s of
  cached validation.

Status: implemented as
`manifests/078-01-cache-quiet-maid-validate-test-commands.manifest.yaml`.

## Speculative Ideas

- Opt-in parallel validation can help only after the caching work above. Running
  serial per-manifest validation is visible in `_validate_active_manifests`, but
  parallelism before cache cleanup risks multiplying TypeScript compiler
  subprocesses and making output ordering harder to reason about.
- A long-lived daemon may help many tiny single-manifest calls, but it is not
  the main fix for Tower Recall or Life Dashboard. Their bottlenecks are repeated
  parsing and resolver subprocesses inside one command.
- Cross-invocation disk caches should remain out of the first wave. They need
  content hashes, schema/version keys, and explicit opt-in invalidation policy.

## Gradual Closure Backlog

Completed:

1. `041-01-cache-assertion-checks-and-test-discovery.manifest.yaml`
2. `041-02-batch-typescript-compiler-resolution.manifest.yaml`
3. `041-03-share-verify-validation-cache-scope.manifest.yaml`
4. `041-04-cache-ts-reexport-compiler-fallback.manifest.yaml`
5. `043-04-cache-typescript-compiler-project-for-import-resolution.manifest.yaml`
6. `046-01-parallelize-independent-maid-test-command-groups.manifest.yaml`
7. `078-01-cache-quiet-maid-validate-test-commands.manifest.yaml`

Next draft:

- None pending from the current performance backlog. Re-benchmark before
  planning another optimization slice.

Future draft candidates:

- Re-benchmark the 60.72s batched pytest command after 078-01 lands before
  planning pytest parallelization, xdist, or batching-policy changes. The
  current evidence says the first MAID-owned win is quiet validate caching.
- None for TypeScript validation until a fresh profile shows a new dominant
  TypeScript bridge cost.

## Suggested Acceptance Criteria

- Tower Recall strict behavioral validation reduces bridge request cumulative
  time without changing `ValidationResult` success flags, error codes,
  warnings, or import identities.
- CJS bridge tests prove import resolution does not construct a TypeScript
  program per import request when a compiler host is enough.
- Cache invalidation tests cover tsconfig and importer root changes.
- `maid test --jobs N` proves the same commands and exit statuses are reported
  in deterministic result order, with deterministic overlap instrumentation
  proving eligible independent command groups can run concurrently.
- Quiet `maid validate` commands executed by `maid test` use the in-process
  cached path and preserve quiet output semantics.
- `maid verify --json` remains deterministic except for duration fields.
- No optimization weakens schema, file-tracking, worktree-scope, coherence, or
  validate-command integrity checks.

## Verification Notes

The post-041 planning pass promoted and implemented `043-04`. The 046 pass
promoted and implemented opt-in parallel test command execution. Future draft
manifests must schema-validate before promotion, then be implemented one at a
time through the MAID implementation workflow.

Commands run during the 2026-06-27 refresh:

- `uv run maid test --json`
- `uv run maid test --jobs 8 --json`
- `uv run maid validate --mode schema --quiet`
- `uv run maid validate --mode behavioral --quiet`
- `uv run maid validate --mode implementation --quiet`
- `uv run maid validate --quiet`
- `uv run maid validate manifests/drafts/078-01-cache-quiet-maid-validate-test-commands.manifest.yaml --mode schema --quiet`
- throwaway in-process probes over the 140 validate-shaped command tuples from
  `/tmp/maid-test-default.json`

Commands run during the 2026-05-29 refresh:

- `uv run maid validate --mode schema --quiet`
- `uv run maid validate --mode behavioral --quiet`
- `uv run maid validate --mode implementation --quiet`
- `uv run maid test --json`
- `uv run maid verify --keep-going --no-changed-scope --advisory --json`
- stage-level `ValidationEngine.validate_all(...)` probes for `maid-runner`,
  `tower-recall`, and `life-dashboard`
- cProfile probe for Tower Recall behavioral validation with assertion checks
