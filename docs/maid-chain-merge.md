# `maid chain merge` — manifest-chain defragmentation

`maid chain merge` turns MAID's in-memory merged contract into an explicit,
reviewable workflow for mature repositories. It reports fragmentation, consumes
recorded runtime evidence, can materialize a safe single-file snapshot, and can
prove that replacement tests preserve the old test union's protection.

```text
maid chain merge [--all] [--manifest-dir DIR] [--dry-run] [--apply] [--verify-equivalence BASELINE_REPORT] [--json] [file_path]
```

## Modes

### Report (default / `--dry-run`)

```bash
maid chain merge maid_runner/core/knockout.py --json
```

The single-file report includes active and superseded manifest counts, distinct
and repeated artifact declarations, a DEFRAG/LEAN/BLOCKED verdict, blocking
reasons, and an acceptance section. DEFRAG means consolidation would remove
structural redundancy; LEAN means no useful merge remains; BLOCKED means either
the chain is structurally unsafe to snapshot or the recorded evidence is not
strong enough to certify test retirement.

The report reads current recorded evidence from the persisted coverage and
knockout caches. It never runs coverage or knockout. Missing, stale, or partial
evidence remains UNKNOWN, and recorded E710 coverage debt makes the report
BLOCKED rather than inventing a green acceptance bar. That evidence verdict
blocks behavioral certification and test retirement; by itself it does not
prevent the separate structural `--apply` operation.

`--dry-run` is explicit documentation of the default read-only behavior. When
combined with `--apply`, it wins and no manifest is written.

### Repository sweep (`--all`)

```bash
maid chain merge --all --json
```

The sweep visits every tracked production file and returns aggregate
DEFRAG/LEAN/BLOCKED counts plus a deterministic worst-offenders list ordered by
redundant declarations. It is a structural program view; it does not apply
snapshots or generate evidence.

### Materialize (`--apply`)

```bash
maid chain merge maid_runner/core/knockout.py --apply
```

Apply reuses the snapshot primitive to write one complete current-state manifest
that supersedes the file's active chain. It evaluates the structural report
without loading coverage or knockout evidence, and refuses a structurally
BLOCKED or LEAN chain, multi-file supersession that a single-file snapshot
cannot preserve, and any result that would drop a declared artifact. It never
auto-seals the Grandfather lock and never retires tests. Source and test files
are not rewritten.

Snapshot materialization is therefore independently useful for structural
defragmentation, but it is not permission to delete redundant-looking tests.

### Verify test equivalence (`--verify-equivalence BASELINE_REPORT`)

Before editing tests, save the complete baseline report while the old test union
and its current recorded evidence are still present:

```bash
maid chain merge src/service.py --json > before-consolidation.json
```

After authoring and running the candidate characterization tests through the
existing deep evidence workflow, compare current evidence with that complete
baseline report:

```bash
maid chain merge src/service.py \
  --verify-equivalence before-consolidation.json \
  --json
```

Equivalence is an artifact identity comparison, not literal old/new test-nodeid
identity. Every previously covered artifact must satisfy the coverage superset,
and every previously detected artifact knockout must satisfy the
knockout-detection superset. Consolidated tests may have new nodeids; at least
one current nodeid must still detect each baseline artifact's knockout. Stronger
candidate coverage or detection is allowed.

The gate exits 0 only for a complete superset. It exits 1 with blocking E715
diagnostics for a blocked or incomplete baseline, unavailable or malformed
evidence, a missing artifact, lost coverage, or lost knockout detection. An
unreadable, mismatched, or structurally invalid baseline file is a usage error
and exits 2. `--verify-equivalence` cannot be combined with `--all` or `--apply`;
`--dry-run` is harmless because equivalence is read-only.

Only retire old tests after this gate passes. The command certifies evidence; it
does not author characterization tests or remove files automatically.

## Common options

- `--manifest-dir DIR` selects the manifest directory (default `manifests/`).
- `--json` emits one machine-readable document for reports, sweeps, apply, and
  equivalence results.
- `file_path` is required for report, apply, and equivalence modes; omit it only
  with `--all`.

## Evidence lifecycle

Evidence freshness is owned by the existing deep verification caches. Run the
appropriate deep evidence workflow before capturing the baseline and again after
the candidate tests change. A cold or stale cache is deliberately UNKNOWN. The
chain-merge command never performs an expensive probe as a hidden side effect.
