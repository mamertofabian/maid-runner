# MAID Runner Performance Backlog

## Purpose

This backlog records measured performance diagnostics for `maid validate`,
`maid test`, and `maid verify` across MAID Runner and five reference projects:

- `maid-runner`: 267 manifests, 182 active, Python package with Python, TS, and Svelte validators.
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

## Timing Summary

| Project | Schema validate | Behavioral validate | Implementation validate | `maid test --json` | Verify gate |
| --- | ---: | ---: | ---: | ---: | ---: |
| maid-runner | 1.573s | 3.426s | 3.507s | 34.168s | 47.833s |
| adverio-tools-api | 0.544s | 0.959s failed | 1.047s failed | 0.535s failed | 4.875s failed |
| adverio-tools-app | 0.298s | 0.938s | 1.052s | 0.267s failed | 4.212s failed |
| tower-recall | 0.337s | 40.694s | 36.538s | 20.116s | 92.591s failed |
| atomic-carpool | 0.745s failed | 3.801s failed | 3.842s failed | 0.651s failed | 8.865s failed |
| life-dashboard | 0.643s | 11.718s | 6.633s | 10.752s | 106.265s failed |

Nonzero exits were caused by current project state, not timing harness errors:

- `adverio-tools-api`: duplicate manifest sequence numbers E107.
- `adverio-tools-app`: E230 validate-command integrity failures around `yarn test --testPathPattern`.
- `atomic-carpool`: duplicate YAML key in `manifests/018-05-event-trip-detail-api.manifest.yaml`.
- `tower-recall`: verify file-tracking gate failed with undeclared and registered files.
- `life-dashboard`: one batched pytest command failed in current dirty worktree.

## Stage Timing

Stage-level API timing isolates the current bottlenecks:

| Project | Schema | Behavioral with assertions | Implementation with stubs | Coherence | File tracking | Tests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tower-recall | 0.191s | 46.356s | 42.509s | 0.009s | 0.789s | 20.489s |
| life-dashboard | 0.554s | 93.856s | 6.331s | 0.132s | 1.889s | 10.591s |
| maid-runner | 1.569s | 9.394s | 2.488s | 0.141s | 0.445s | 38.897s |

Coherence and file tracking are not the main cost in these runs. Strict
behavioral validation and TypeScript identity resolution dominate.

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

Closure shape:

- Cache assertion-check results by resolved test path, validator/language family,
  file mtime, and file size for the lifetime of one validation run.
- Cache command/directory test-file discovery by normalized command and directory
  signature to avoid repeated `rglob()` expansion.
- Preserve per-request error locations and warning order, and clear caches at
  the existing validation-run boundary.

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

Closure shape:

- Keep the existing per-invocation result caches, but replace one-Node-process
  per request with a per-validation compiler resolver session or batched request
  API.
- Batch import and re-export resolution requests discovered during TS/Svelte
  behavioral collection and identity matching where possible.
- Cache project config signatures and module entry signatures inside the same
  resolver context so cache-key construction does not repeatedly stat the same
  module entries.
- Preserve fail-closed behavior: if the compiler bridge is missing, times out,
  or returns malformed JSON, validation must expose the same result as the
  current path.

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

Closure shape:

- Add an explicit command-wide validation cache scope for `maid verify`.
- Keep caches process-local and invocation-local; clear them before verify starts
  and after it finishes.
- Add JSON equivalence tests for verify output apart from duration fields, plus
  call-count tests proving TypeScript resolver/cache reuse across behavioral and
  implementation stages.

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

1. `041-01-cache-assertion-checks-and-test-discovery.manifest.yaml`
2. `041-02-batch-typescript-compiler-resolution.manifest.yaml`
3. `041-03-share-verify-validation-cache-scope.manifest.yaml`

## Suggested Acceptance Criteria

- Life Dashboard strict behavioral validation avoids reparsing unchanged Python
  tests per manifest, with an anti-redundancy test proving each unchanged test
  file is assertion-checked once per validation run.
- Tower Recall behavioral validation avoids one Node compiler subprocess per
  unresolved TypeScript request, with a call-count test proving batched or
  session-backed compiler resolution.
- `maid verify --json` remains deterministic except for duration fields.
- Cache invalidation tests cover file content changes, mtime/size changes, and
  project config changes.
- No optimization weakens schema, file-tracking, worktree-scope, coherence, or
  validate-command integrity checks.

## Verification Notes

This is a planning pass. No production code was changed. New draft manifests
must schema-validate before promotion, then be implemented one at a time through
the MAID implementation workflow.
