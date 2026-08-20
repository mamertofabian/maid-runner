# MAID-Runner Manifest & Test Consolidation (Mature-State Flattening)

**Status: Implemented.** The `maid chain merge` family shipped on the
`perf/full-deep-verification-speedups` branch in children 1–7.
**Originally drafted:** 2026-08-13
**Original context branch:** `perf/full-deep-verification-speedups`

## Problem

MAID-runner accumulated roughly a year of manifests and behavioral tests. Much
of that history was sediment: the current code's contract could be described
more compactly than the full development chronology. The question was whether,
for a mature module, the active validation set should be flattened to current
state instead of re-validating the entire historical chain on every run.

Conclusion: **yes, incrementally and per-file**, using mechanisms MAID already
sanctions and a knockout-certified equivalence gate. This is the specification's
**Consolidated Snapshots** pattern (`docs/maid_specs.md`) applied to the flagship
dogfood repository, paired with a behavioral characterization module.

## Measured evidence at drafting

The original measurements were reproducible with:

```sh
ls manifests/*.manifest.yaml | wc -l
grep -h '^\s*-\s*name:' manifests/*.manifest.yaml | wc -l
grep -h '^\s*-\s*name:' manifests/*.manifest.yaml | sort -u | wc -l
```

- **570 active manifests**, approximately 107,000 lines of manifest YAML.
- **2,947 artifact declarations for 478 distinct artifacts**, about
  **6× declaration redundancy**. The same artifact was re-declared across many
  manifests (`knockout.py` spanned 40 and `artifact_coverage.py` spanned 32).
- **378 test files**, approximately 126,000 lines of tests versus 63,000 lines
  of source.

The redundancy was the target: every redundant declaration added repeated
chain-merge, knockout, and coverage work to deep verification.

## The core idea: a per-file current-state freeze

Manifests and behavioral tests have **opposite retention logic** and must be
treated differently:

- **Manifests are contracts and audit records.** Historical or superseded
  manifests can leave the active validation set because Git retains chronology
  and MAID retains superseded manifests as an audit log.
- **Tests are live behavioral guarantees.** Relevance, not age, decides
  retention. Old tests that still protect current behavior may be removed only
  when equivalent protection is proven.

These converge on:

> one production file → one consolidated snapshot manifest (structure)
> → one cohesive characterization test module (behavior)

The snapshot manifest freezes what artifacts exist; the characterization module
freezes what they do. “One module per file” still means many small,
scenario-named, one-behavior-per-test functions. It does not mean one mega-test.
Cross-file and integration behavior remain legitimate exceptions.

## The equivalence gate

Old tests may be retired only after the new characterization module is proved to
replicate their protection. Two green suites prove nothing on unchanged code,
and coverage proves execution rather than an observable behavioral guarantee.

The gate therefore has two measurable conditions:

1. **Coverage parity:** the candidate executes a superset of the artifacts and
   lines covered by the old test union.
2. **Knockout parity:** for every artifact identity, the candidate detects a
   superset of the faults detected by the old test union.

Artifact identity, not test nodeid identity, is the comparison key. A legitimate
consolidation creates new nodeids while retaining or strengthening protection.

### Why coverage alone is insufficient

A coverage-only test can retain 100% target coverage after an artifact knockout
and still pass. The drafting demonstration compared that with a characterization
test whose observable assertion failed on the same knockout:

| suite | coverage of target | after knockout of the artifact |
| --- | --- | --- |
| coverage-only, no behavioral assertion | 100% | **passes** — fault undetected |
| characterization with behavioral assertion | 100% | **fails** — fault detected |

Identical coverage produced opposite fault detection. Coverage is therefore a
floor, while knockout detection supplies the behavioral proof.

## Implemented workflow

1. `maid chain merge <file> --json` reports structural fragmentation and records
   the acceptance bar from persisted coverage and knockout evidence.
2. `maid chain merge --all` produces a repository-wide DEFRAG, LEAN, or BLOCKED
   scoreboard.
3. `maid chain merge <file> --apply` materializes the complete single-file
   snapshot and refuses artifact loss or unsafe multi-file supersession. It does
   not change or retire tests.
4. A human or agent authors candidate characterization tests and runs the
   existing deep-evidence workflow.
5. `maid chain merge <file> --verify-equivalence BASELINE_REPORT` compares the
   complete saved baseline with current evidence. It accepts stronger coverage
   and detection, permits new nodeids, and fails closed with E715 for any loss
   or incomplete proof.

Reports and equivalence checks consume **recorded** evidence only. They never run
coverage or knockout inline. UNKNOWN remains visible when caches are cold,
stale, or partial.

## Relationship to verification performance

The performance work makes the algorithm faster over a large input; flattening
shrinks that input permanently. The improvements multiply rather than compete:

- deep verification merges the active manifest chain, then runs coverage and
  knockout, so cost scales with active contracts and artifact declarations;
- collapsing a file's chain to one snapshot replaces repeated chain traversal
  and redundant declarations with one current-state contract.

The original sequencing was deliberate: land knockout speedups first, use the
faster knockout oracle to certify flattening, and let each certified collapse
reduce future verification input. The implemented chain-merge workflow follows
that sequence.

## Resolution of the original risks

- **Provenance:** apply reuses the snapshot primitive and retains superseded
  manifests as audit history. Snapshot manifests are not plan-lock migrations;
  artifact-preservation refusal is the relevant safety boundary.
- **Evidence:** persisted coverage and knockout caches supply the acceptance bar
  cheaply, and evidence is never fabricated.
- **Test retirement:** apply is structural only. Retirement requires a separate,
  successful artifact-identity equivalence comparison.
- **Temporary overlap:** old and candidate tests may both execute during a
  migration, so the overlap should remain short and per-file.
- **Granularity:** cross-file behavior, integration behavior, and files exercised
  through public entry points remain explicit exceptions to a 1:1 mapping.
- **Audit trail:** consolidation shrinks the active contract set without deleting
  Git history, superseded manifests, or Outcome records.

## Remaining operational limits

- The tool does not auto-author characterization tests or auto-delete old tests.
- Evidence caches must be current for baseline capture and candidate comparison;
  UNKNOWN blocks certification.
- Apply refuses chains where a single-file snapshot would drop artifacts
  declared for another file.
- Repository-wide adoption remains incremental and per-file. Measure actual
  deep-verification changes before scaling a consolidation program.
- Full release handoff and its independent gates remain separate from chain
  merge; consolidation does not weaken or waive unrelated diagnostics.
