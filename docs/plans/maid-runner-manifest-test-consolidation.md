# MAID-Runner Manifest & Test Consolidation (Mature-State Flattening)

**Status:** Design note — not scheduled. Do not start on files in the active
`perf/full-deep-verification-speedups` working set (see Coordination).
**Drafted:** 2026-08-13
**Context branch at drafting:** `perf/full-deep-verification-speedups`

## Problem

MAID-runner has accumulated ~1 year of manifests and behavioral tests. Much of
that history is sediment: the current code's contract can be described far more
compactly than the full development chronology. The question this note answers is
whether — for a mature module — the active validation set should be **flattened
to current-state** rather than continuing to re-validate the entire historical
chain on every run.

Conclusion: **yes, incrementally and per-file**, using mechanisms MAID already
sanctions, with a knockout-certified equivalence gate. This is not a new MAID
concept — it is the spec's **Consolidated Snapshots** pattern
(`docs/maid_specs.md:588`) applied to the flagship dogfood repo, paired with a
behavioral characterization module.

## Measured evidence (this repo, at drafting)

Reproduce with:

```
ls manifests/*.manifest.yaml | wc -l                       # active manifests
grep -h '^\s*-\s*name:' manifests/*.manifest.yaml | wc -l   # artifact declarations
grep -h '^\s*-\s*name:' manifests/*.manifest.yaml | sort -u | wc -l  # distinct
```

- **570 active manifests**, ~107k lines of manifest YAML.
- **2,947 artifact declarations for 478 distinct artifacts** → ~**6× declaration
  redundancy**. The same artifact is re-declared across many manifests
  (`knockout.py` spans 40; `artifact_coverage.py` spans 32).
- **378 test files**, ~126k lines of test vs ~63k lines of source.

The redundancy is the target: every redundant declaration is repeated
chain-merge + knockout + coverage work on every deep verify.

## The core idea: a per-file current-state freeze

Manifests and behavioral tests have **opposite retention logic** and must be
treated differently:

- **Manifests are contracts + audit records.** Historical/superseded manifests
  can be flattened because git already holds the chronology and MAID treats
  superseded manifests as "dead for validation, retained as audit log."
- **Tests are live behavioral guarantees.** Relevance, not age, decides
  retention. A year-old passing test protects behavior the current code still
  has. Only genuinely dead-behavior or truly-duplicate tests may be removed.

These converge into **one operation, not two**:

> one production file → one consolidated **snapshot manifest** (structure)
> → one cohesive **characterization test module** (behavior)

The snapshot manifest freezes *what artifacts exist*; the characterization module
freezes *what they do*. Together they are a complete current-state freeze.

Tooling that already exists: `maid snapshot <file>` generates a single manifest
describing a file's complete current state and supersedes its prior chain
(`maid_runner/cli/commands/snapshot.py`).

### Granularity rule

"Unified test per file" means **one cohesive test _module_ per file**, still
containing many small, scenario-named, one-behavior-per-test functions
(`docs/unit-testing-rules.md`). Do **not** collapse N focused tests into one
mega-test — that destroys the "which behavior broke" diagnostic signal.

## The equivalence gate (the load-bearing part)

Old tests may be retired only after the new characterization module is **proved
to replicate** their protection. "Both suites are green" proves nothing — on
correct code every test is green. Coverage proves the artifact was *executed*,
not that its behavior was *pinned*.

The gate has two measurable conditions, both already computed by this repo:

1. **Coverage parity (floor):** the new module executes ⊇ the artifacts/lines
   the old collection did. Measured by `artifact_coverage.py`.
2. **Knockout / fault-detection parity (proof):** for every artifact, the new
   module's detecting-nodeid set is a **superset** of what the old collection
   detected. `knockout.py` already computes per-artifact `detecting_nodeids`
   keyed by `KnockoutArtifactIdentity` (name + kind + parent class) —
   `maid_runner/core/knockout.py:110`.

Acceptance = **superset, not identical**: lose no coverage and no detected fault,
while shedding redundancy.

### Why coverage alone is insufficient (reproducible demo)

A coverage-only "characterization" test hits 100% coverage yet catches zero
regressions. Demonstrated 2026-08-13 with a throwaway `/tmp` example:

| suite | coverage of target | after knockout of the artifact |
| --- | --- | --- |
| coverage-only (no behavioral assert) | 100% | **passes** — fault undetected |
| characterization (behavioral assert) | 100% | **fails** — fault detected |

Identical coverage, opposite fault-detection. This is exactly why the gate is
knockout parity, not coverage parity — and why maid-runner already ships knockout
on top of artifact coverage.

## Relationship to verify performance (why flattening *helps* the optimization)

The `perf/` work makes the **algorithm** faster over a **bloated input**.
Flattening shrinks the **input** — permanently, for every future run. They
multiply, they do not compete:

- Deep verify merges the active manifest chain, then runs coverage + knockout.
  Cost scales with active-manifest count and artifact-declaration count.
- Collapsing a file's chain to one snapshot turns "walk N superseded+active
  manifests" into "read one current-state contract" and dedupes the ~6×
  redundant declarations that drive repeated knockout work.

**Sequencing (deliberate):**

1. Let the knockout speedups land first — the equivalence oracle that certifies
   each collapse *is* knockout, the expensive tool. Faster knockout makes each
   collapse cheap to certify.
2. Then flatten. Each collapse permanently lowers the input every subsequent
   verify pays for. Virtuous cycle: optimize knockout → use fast knockout to
   certify flattening → flattening shrinks knockout's future input.

## Coordination constraints

- **Do not flatten files in the active `perf/` working set** while that work is
  in flight. At drafting that set includes `knockout.py`,
  `_knockout_snapshot.py`, `artifact_coverage.py`, and their tests. Flattening
  those would collide head-on with the optimization branch.
- Prefer to begin this program **after the optimization branch merges**, so the
  faster knockout is in place before certifying collapses.

## Open prerequisites / risks

- **Provenance migration (must verify before scaling).** Plan locks, red
  evidence, and outcome records attach to manifests. A snapshot consolidation
  must *migrate* that provenance the way `maid manifest promote` migrates locks —
  not orphan it, or it trips the E702/E707 evidence gates. **Unverified:**
  confirm `maid snapshot` output lands with a clean lock/verify story (e.g.
  `maid snapshot <file> --dry-run` then trace the lock chain). If it does not,
  that tooling gap is the real first task.
- **Migration temporarily doubles execution** (old + new suites in parallel
  during the overlap window) — keep the window short and per-file, never global.
- **1:1 file↔test mapping does not always hold** — cross-file/integration
  behaviors and files tested only through a public entrypoint need exceptions,
  not forced artificial mappings.
- **Audit-trail philosophy.** maid-runner's product value *is* verifiable
  chronology. Flatten the *active validation set* to current state; retain the
  *audit trail* in git + `outcomes.json` + superseded manifests. Never delete
  history — demote it from "re-validated every run" to "recorded."

## Suggested first pilot

Pick one file with a long manifest chain **outside the `perf/` working set**.
For that file:

1. `maid snapshot <file>` → one current-state manifest (verify provenance
   migration first — see Open prerequisites).
2. Author one cohesive characterization module (many focused tests).
3. Run the equivalence gate: per-artifact detecting-nodeid superset + coverage
   superset vs. the union of the old tests.
4. **Measure** the deep-verify / knockout delta on that file before vs. after.
   Report a real number instead of an estimate; that decides whether this scales
   into a program.
