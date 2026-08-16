# MAID-Runner Manifest & Test Consolidation (Mature-State Flattening)

**Status: Implemented** — the `maid chain merge` family shipped on the
perf-based chain-merge branch in children 1–7.
**Originally drafted:** 2026-08-13
**Original context branch:** `perf/full-deep-verification-speedups`

## Problem and measured rationale

MAID-runner had accumulated roughly a year of manifest and behavioral-test
history. At drafting, 570 active manifests contained about 2,947 artifact
declarations for 478 distinct artifacts: approximately 6× declaration redundancy.
The same public contract was repeatedly merged and evaluated by
deep verification.

Manifests and behavioral tests have **opposite retention logic**:

- manifests are contracts and audit records, so superseded history can leave the
  active validation set while remaining in Git and Outcome records;
- tests are live behavioral guarantees, so relevance rather than age determines
  whether they can be retired.

The adopted unit is therefore one production file, one consolidated snapshot
manifest, and—where useful—one cohesive characterization module containing many
small scenario-focused tests rather than one mega-test.

## Why coverage alone is insufficient

A test can execute every line without asserting behavior. In the original
throwaway demonstration, a coverage-only test retained 100% target coverage
after an artifact knockout but still passed; a characterization test with an
observable assertion failed on the same knockout. **Coverage alone is
insufficient** to establish behavioral protection.

The safety bar therefore combines:

1. a coverage superset for the artifacts proven by the old test union; and
2. a knockout-detection superset keyed by artifact identity.

Test nodeid identity is not part of equivalence. A legitimate consolidation
creates new nodeids; the candidate must still detect the same artifact knockout.

## Implemented workflow

1. `maid chain merge <file> --json` reports structural fragmentation and records
   the current acceptance bar from persisted coverage and knockout evidence.
2. `maid chain merge --all` provides the repository-wide DEFRAG/LEAN/BLOCKED
   scoreboard.
3. `maid chain merge <file> --apply` materializes the complete single-file
   snapshot and refuses artifact loss or unsafe multi-file supersession. It never
   changes or retires tests.
4. A human or agent authors the candidate characterization tests and runs the
   existing deep evidence workflow.
5. `maid chain merge <file> --verify-equivalence BASELINE_REPORT` compares the
   complete saved baseline with current evidence. It accepts stronger coverage
   and detection, allows new nodeids, and fails closed with E715 for any loss or
   incomplete proof.

Reports and equivalence checks consume **recorded** evidence only. They never run
coverage or knockout inline, and UNKNOWN remains visible when caches are cold,
stale, or partial.

## Resolution of original open risks

- **Provenance:** apply reuses the snapshot primitive and retains superseded
  manifests as audit history. Snapshot manifests are not plan-lock migrations;
  artifact-preservation refusal is the relevant safety boundary.
- **Evidence:** persisted coverage and knockout caches from the performance branch
  supply the acceptance bar cheaply; evidence is never fabricated.
- **Test retirement:** apply is structural only. Retirement requires a separate
  successful artifact-identity equivalence comparison.
- **Granularity:** cross-file and integration behavior remain legitimate
  exceptions to one-file/one-characterization-module organization.
- **Audit trail:** consolidation shrinks the active contract set without deleting
  Git history, superseded manifests, or Outcome records.

## Remaining operational limits

- The tool does not auto-author characterization tests or auto-delete old tests.
- Evidence caches must be current for both baseline capture and candidate
  comparison; UNKNOWN blocks certification.
- Apply deliberately refuses chains where a single-file snapshot would drop
  artifacts declared for another file.
- Repository-wide adoption remains incremental and per-file. Measure real deep
  verification changes before scaling a consolidation program.
- This branch's full deep handoff remains separately affected by the documented
  pre-existing E307/E310 baseline warnings; they are not weakened by chain merge.
