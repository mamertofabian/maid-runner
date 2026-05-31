---
name: maid-runner-performance-optimization
description: Use in maid-runner when asked to analyze `maid validate`, `maid test`, and `maid verify` for performance and efficiency opportunities, profile hot paths, capture confirmed findings, and create a draft-manifest queue of speedups for the Codex MAID loop to implement. Covers benchmarking, caching boundaries, parser reuse, parallel execution, MAID draft planning, plan self-review, schema validation, and optional branch/commit handoff.
---

# MAID Runner Performance Optimization

Use this skill in `/home/atomrem/projects/codefrost-dev/maid-runner` when the
user wants a planning-grade pass over `maid validate`, `maid test`, and
`maid verify` to find speedups: redundant chain rebuilds, repeated YAML parses,
re-read source/test files, uncached AST or tree-sitter sessions, serial
subprocess loops that could batch or parallelize, and graph rebuilds across
stages. The output is a findings document plus a split-before-promote draft
queue. This skill plans only. It does not implement.

## Scope

This skill is for planning and reference artifacts, not implementation.

Do:

- read the current validator, chain, test runner, and CLI code before assuming
  a hot path still looks the way an older insight described;
- run small adversarial timing probes in throwaway projects under `/tmp`, or
  reuse this repo's `manifests/` with `time uv run maid ...`;
- distinguish confirmed measurable wins from speculative micro-optimizations;
- save findings in a concise Markdown reference under `docs/plans/`;
- create a split-before-promote draft queue under `manifests/drafts/`;
- review draft manifests for substance before handoff;
- validate all new drafts in schema mode and run root schema validation.

Do not:

- weaken any anti-gaming validation rule to make a path faster;
- skip behavioral coverage, file-tracking, worktree-scope, or coherence checks
  because they are slow;
- promote draft manifests into `manifests/`;
- replace fail-closed behavior with cached pass-through;
- commit or push unless the user explicitly asks.

If the user asks to implement selected drafts, use `maid-runner-draft-implement`
instead.

## Performance Contract

Speed gains must keep the validator's anti-gaming contract intact. Treat these
as invariants for every proposed optimization:

- the same inputs must produce the same `ValidationResult.success`, error codes,
  and warnings as the unoptimized path;
- caches must be keyed by content (path plus mtime or content hash plus inputs
  that change behavior), never by mutable global state;
- caches must live for the lifetime of a single CLI invocation by default;
  any process- or disk-level cache must be opt-in and disclosed;
- parallelism must not reorder structured error reporting in a way that hides
  earlier failures;
- a faster path must keep `maid validate --json` deterministic across runs.

## Start

1. Check the branch and dirty worktree:

```bash
git status --short --branch --untracked-files=all
```

Work around unrelated user or automation changes. Do not revert them.

2. Read the current surfaces likely involved:

- `docs/maid-philosophy-and-vision.md`
- `docs/plans/maid-runner-performance-backlog.md` if it exists
- `maid_runner/core/validate.py`
- `maid_runner/core/chain.py`
- `maid_runner/core/manifest.py`
- `maid_runner/core/_validation_test_artifacts.py`
- `maid_runner/core/test_runner.py`
- `maid_runner/core/result.py`
- `maid_runner/validators/python.py`
- `maid_runner/validators/typescript.py`
- `maid_runner/validators/svelte.py`
- `maid_runner/validators/registry.py`
- `maid_runner/graph/builder.py`
- `maid_runner/coherence/engine.py`
- `maid_runner/cli/commands/validate.py`
- `maid_runner/cli/commands/test.py`
- `maid_runner/cli/commands/verify.py`

3. Read prior performance-relevant insights when present, especially
parser-replacement, tree-sitter, chain-merge, file-tracking, and verify-stage
notes under `.claude/insights/`.

4. Inventory the cost surface:

```bash
find manifests -maxdepth 2 -name '*.manifest.yaml' | wc -l
find manifests/drafts -maxdepth 2 -name '*.manifest.yaml' | wc -l
find tests -name 'test_*.py' | wc -l
```

Use the counts to estimate amplification factors (n manifests x m files x k
phases) when ranking findings.

## Benchmark Workflow

Prefer measured wins over intuition. Build small, disposable timing probes
either in this repo or under `/tmp`, and record the command, manifest count,
and wall time.

Probe shapes that are usually enough:

```bash
# Full validate run, root manifest dir.
time uv run maid validate --quiet

# Validate one busy manifest with chain merging.
time uv run maid validate manifests/<slug>.manifest.yaml --mode implementation --quiet

# Verify all stages, where redundancy across stages tends to dominate.
time uv run maid verify --keep-going --json

# Test runner end-to-end.
time uv run maid test --json
```

For deeper inspection, drop a `cProfile` harness in `/tmp` that imports the
package directly:

```python
import cProfile, pstats
from maid_runner.core.validate import validate_all
cProfile.run("validate_all('manifests/')", "/tmp/maid.prof")
pstats.Stats("/tmp/maid.prof").sort_stats("cumulative").print_stats(40)
```

Capture wall time before and after a hypothetical fix is in place; if a fix
cannot show a measurable win on this repo's manifest set, downgrade it from
confirmed to speculative.

Good probe categories:

- chain rebuilt more than once per CLI command;
- the same manifest YAML parsed more than once per CLI command;
- the same test file read or AST-parsed more than once across manifests;
- the same source file AST-parsed for implementation and behavioral phases;
- tree-sitter parsers or grammars constructed per validator instance instead
  of once per process;
- `verify` stages each instantiating their own chain and graph;
- file-tracking that walks active manifests per source file instead of
  inverting to a file -> manifests index;
- `maid test` running `_can_batch`-compatible commands serially;
- redundant `subprocess` spawns where one batched pytest run would suffice;
- coherence and graph rebuilt for every validate even when nothing changed.

For each confirmed hot path, capture:

- scenario and amplification factor (manifests, files, phases);
- observed command, wall time, and cProfile cumulative-time anchor function;
- why this matters at the typical project scale (this repo and brownfield repos
  with hundreds of manifests);
- current code path and call sites;
- closure shape, with the invariant from the Performance Contract that must be
  preserved.

## Findings Document

Save confirmed findings as Markdown under `docs/plans/`, usually:

```text
docs/plans/maid-runner-performance-backlog.md
```

Use this structure:

- Purpose
- Performance Contract (link to the section in the skill)
- Confirmed Hot Paths
- Speculative Ideas (kept separate until measured)
- Gradual Closure Backlog
- Suggested Acceptance Criteria
- Verification Notes

Keep it technical and actionable. Do not write marketing text or generic
"make it faster" entries. Each confirmed entry must cite the file and the
function or method, and must include a measured before-number when possible.

Pure Markdown-only updates are normally documentation changes in this repo, so
a separate MAID manifest is not required unless the user asks or the change
touches code/test artifacts.

## Draft Manifest Queue

Create one epic plus implementation-sized child drafts under
`manifests/drafts/`. Use the next available numeric wave. For a performance
queue, use names like:

```text
034-00-maid-runner-performance-roadmap.epic.yaml
034-01-cache-manifest-chain-per-cli-invocation.manifest.yaml
034-02-share-source-ast-across-validation-phases.manifest.yaml
```

Epic requirements:

- first lines:

```yaml
# draft-kind: epic
# promotion: split-before-promote
```

- `metadata.status: planning`;
- planned child order;
- concise rationale tying the queue to measurable speedups without weakening
  validation;
- temptations that prevent broad rewrites, silent fallbacks, and
  contract-weakening shortcuts;
- at least one valid file section, because schema v2 requires a writable
  section.

Child draft requirements:

- first line:

```yaml
# draft-kind: implementation
```

- one confirmed hot path or tightly related cluster per draft;
- exact production files likely to change in `files.edit` or `files.create`;
- exact public artifacts with signatures, return types, and attribute types;
- behavioral test-function artifacts that prove correctness preservation
  (same inputs produce the same `ValidationResult`) and at least one timing
  or call-count assertion that proves the redundant work was eliminated;
- `files.read` for supporting docs, existing tests, and adjacent helpers;
- 3-5 task-specific `temptations`, each with a concrete `instead`;
- a focused `validate:` command that runs the relevant tests once promoted.

Prefer an ordered queue. A sensible starting order for this repo:

1. Cache the per-invocation `ManifestChain` so validate, coherence, file
   tracking, and verify reuse a single load.
2. Share parsed source ASTs between implementation and behavioral phases.
3. Cache test-file reads and parsed test artifact tables across manifests in
   the same CLI run.
4. Promote tree-sitter parsers to process-level singletons per language.
5. Invert file-tracking's per-file manifest lookup to a precomputed
   file -> manifests index.
6. Build the knowledge graph once per CLI invocation and pass it from
   validation into coherence.
7. Enable `_batch_pytest` for compatible validate commands in `maid test`.
8. Parallelize independent per-manifest validate work behind an opt-in flag
   that preserves ordered error reporting.
9. Add an opt-in `--cache-dir` for cross-invocation memoization keyed on
   content hashes, with cache-bypass on schema or chain mutation.

Adjust the order if the current repo state shows some drafts are already
implemented or promoted.

## Draft Self-Review

Before handoff, review every draft as if trying to game it.

Blockers to fix before reporting ready:

- vague goals that do not name the redundant work being removed;
- production artifacts without exact signatures;
- missing `args: []` for zero-argument functions or methods;
- new public classes without declared public attributes/methods;
- test functions that only check that "code runs faster" without asserting
  equivalent `ValidationResult` output;
- missing call-count or cache-hit assertions for caches and memoization;
- missing JSON-output equivalence checks for automation-facing CLI changes;
- `temptations` that name a risk without a procedural `instead`;
- validate commands that do not include the tests declared in the manifest;
- any draft that proposes silently swallowing errors or returning stale data
  in the name of speed.

For child drafts, make sure the test plan includes:

- at least one equivalence test (optimized result equals unoptimized result on
  the same inputs);
- at least one anti-redundancy test (call count, cache-hit count, or parser
  instantiation count) proving the work was deduplicated;
- at least one negative test proving the cache invalidates when its key inputs
  change.

## Validation

Run direct schema validation for each new draft:

```bash
uv run maid validate manifests/drafts/<draft>.manifest.yaml --mode schema --quiet
```

Then run root schema validation so inactive-draft markers are checked:

```bash
uv run maid validate --mode schema --quiet
```

Also run:

```bash
git diff --check
```

If any schema check fails, fix the draft rather than lowering scope.

## Branch And Commit Handoff

Only create branches or commits when the user explicitly asks.

When committing:

1. Create a branch from the current branch, preserving active checkout context.
2. Stage only the findings document and intended draft-manifest files.
3. Inspect:

```bash
git status --short --untracked-files=all
git diff --cached --name-only
git diff --cached --stat
git diff --cached --check
```

4. Re-run `uv run maid validate --mode schema --quiet`.
5. Commit with a scoped message such as:

```text
docs(maid): add performance optimization draft queue
```

Never push without explicit user approval.
