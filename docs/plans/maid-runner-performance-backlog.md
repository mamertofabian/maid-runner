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

Next draft:

1. `manifests/drafts/043-04-cache-typescript-compiler-project-for-import-resolution.manifest.yaml`

## Suggested Acceptance Criteria

- Tower Recall strict behavioral validation reduces bridge request cumulative
  time without changing `ValidationResult` success flags, error codes,
  warnings, or import identities.
- CJS bridge tests prove import resolution does not construct a TypeScript
  program per import request when a compiler host is enough.
- Cache invalidation tests cover tsconfig and importer root changes.
- `maid verify --json` remains deterministic except for duration fields.
- No optimization weakens schema, file-tracking, worktree-scope, coherence, or
  validate-command integrity checks.

## Verification Notes

This is a planning pass. No production code was changed. Draft manifests must
schema-validate before promotion, then be implemented one at a time through the
MAID implementation workflow.

Commands run during the 2026-05-29 refresh:

- `uv run maid validate --mode schema --quiet`
- `uv run maid validate --mode behavioral --quiet`
- `uv run maid validate --mode implementation --quiet`
- `uv run maid test --json`
- `uv run maid verify --keep-going --no-changed-scope --advisory --json`
- stage-level `ValidationEngine.validate_all(...)` probes for `maid-runner`,
  `tower-recall`, and `life-dashboard`
- cProfile probe for Tower Recall behavioral validation with assertion checks
