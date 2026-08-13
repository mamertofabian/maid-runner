# `maid chain merge` — manifest-chain defragmentation

`maid chain merge` materializes the merge that MAID's Merging Validator already
performs in memory. A mature repo accumulates a long, fragmented per-file
manifest chain; this command family reports which files are fragmented and
collapses a file's chain into a single current-state snapshot — without losing
coverage or fault detection.

It sits beside `maid chain log` and `maid chain replay`: `replay` previews the
merged view, `merge` reports on and materializes it.

```
maid chain merge [--all] [--manifest-dir DIR] [--dry-run] [--apply] [--json] [file_path]
```

## Modes

### Report (default / `--dry-run`)

```
maid chain merge maid_runner/core/knockout.py --json
```

Prints a deterministic `ChainMergeReport` for one file: active/superseded
manifest counts, distinct vs total artifact declarations (the redundancy a merge
removes), the merged target contract, and a verdict:

- **DEFRAG** — more than one active manifest declares the file, or the same
  artifact is re-declared across active manifests.
- **LEAN** — at most one active manifest and no redundant declarations; nothing
  to merge.
- **BLOCKED** — no active writable manifest declares the file; cannot be
  snapshot-merged.

The report is pure aggregation over the manifest chain: it never runs knockout
or coverage. Only manifests that actually declare artifacts in the file count —
scope-only references do not inflate the verdict.

### Repo-wide sweep (`--all`)

```
maid chain merge --all
```

Runs the report across every tracked production file and prints an aggregate
DEFRAG/LEAN/BLOCKED summary with a deterministic worst-offenders ranking (by
redundant declarations). This is the finish-line scoreboard for a defrag
program: run it, then stop when every file is LEAN.

### Materialize (`--apply`)

```
maid chain merge maid_runner/core/knockout.py --apply
```

Writes a single current-state snapshot manifest (via the snapshot primitive)
that supersedes the file's active chain. `--apply` **only touches manifests** —
it never rewrites source or tests, so coverage is unchanged.

Apply is fail-closed around the anti-gaming artifact-preservation audit. It
**refuses, writing nothing**, when:

- the verdict is BLOCKED or LEAN;
- a manifest it would supersede also declares artifacts in **other files** (a
  single-file snapshot cannot preserve those); or
- the current code has dropped an artifact the chain declared for this file.

It never auto-seals the Grandfather lock; reconcile such conflicts manually. If
`--dry-run` and `--apply` are both given, `--dry-run` wins (read-only report).

## Determinism / evidence boundary

The report and verdicts are cheap, deterministic structural facts. Detecting
which tests would catch a regression (the behavioral half of a safe collapse) is
runtime evidence, not a manifest fact — so the report reads it only through an
injected evidence source and never runs knockout itself. Until a persisted
evidence source exists, detection is reported **UNKNOWN**, never fabricated.

## Not yet shipped (dependency-gated)

These parts of the epic depend on the persisted knockout/coverage evidence
caches and are not in the current command:

- evidence-backed detection acceptance (per-artifact detecting-nodeids) and a
  coverage/E710-derived BLOCKED reason;
- the knockout+coverage **equivalence gate** that proves a consolidated test
  module is a superset of the old tests' fault detection before old tests are
  retired.

Materializing the manifest chain (`--apply`) is safe on its own because it never
touches tests; retiring tests after a collapse still requires that equivalence
gate.
