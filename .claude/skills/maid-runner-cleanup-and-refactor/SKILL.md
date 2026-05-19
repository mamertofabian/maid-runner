---
name: maid-runner-cleanup-and-refactor
description: Use in maid-runner when asked to audit the codebase for cleanup and refactor opportunities (dead code, duplication, long functions, weak abstractions, stale TODOs, orphaned manifests), capture confirmed findings, and create a draft-manifest queue of safe-refactor work for the Codex MAID loop to implement. Anchored on Feathers' Working Effectively With Legacy Code (characterization, seams, sprout method) and Fowler's Refactoring (named maneuvers and code-smell vocabulary). Covers characterization, behavior preservation, manifest evolution via maid-evolver, draft planning, plan self-review, schema validation, and optional branch/commit handoff.
---

# MAID Runner Cleanup And Refactor

Use this skill in `/home/atomrem/projects/codefrost-dev/maid-runner` when the
user wants a planning-grade pass over the codebase to find cleanup and
refactor opportunities: dead private code, duplicated validator logic, long
methods that drifted, weak abstractions, stale TODO/FIXME notes, orphaned or
unreferenced manifests, and structural debt that slows new MAID waves. The
output is a findings document plus a split-before-promote draft queue. This
skill plans only. It does not implement.

## Skill Coordination

This skill is the planning front end for cleanup work. The implementation
engines are the existing skills:

- `safe-refactor` performs the actual restructuring under characterization
  tests with behavior preservation.
- `maid-evolver` handles any intentional change to an existing manifest
  contract (renames, signature changes, splits, removals).
- `maid-runner-draft-implement` promotes and implements approved drafts.
- `maid-implementation-review` reviews implementation work before handoff.

Drafts produced by this skill must name which engine will own implementation
so the downstream loop selects the right workflow.

## Anchor Rules

This skill is anchored on two rule sets from `agent-rules-selector`:

- **Primary**: `working-effectively-with-legacy-code` (Feathers). Use his
  discipline for any audit that touches code without trustworthy tests:
  characterize before changing, find a seam before breaking a dependency,
  prefer sprout method or sprout class over editing the legacy block, and
  break one hard dependency at a time. Treat every confirmed cleanup target as
  legacy code until characterization tests prove otherwise.
- **Secondary**: `refactoring` (Fowler). Use his named maneuvers and code-smell
  vocabulary when describing each draft (Long Method, Duplicate Code, Primitive
  Obsession, Extract Method, Pull Up Method, Replace Magic Literal With
  Symbolic Constant, Introduce Parameter Object, etc.). Naming the maneuver
  makes the draft's scope unambiguous and easier for the reviewer agent to
  check.

If a draft falls outside both lenses (for example a deep-module redesign or
an architecture decision), invoke `agent-rules-selector` to pick a different
primary rule rather than stretching this skill's anchors.

## Scope

This skill is for planning and reference artifacts, not implementation.

Do:

- read the current code before assuming an old refactor target still exists;
- run small static probes (grep, ruff, mypy, manifest chain queries) to
  confirm each target is real;
- distinguish confirmed cleanups from speculative "nice to have" ideas;
- save findings in a concise Markdown reference under `docs/plans/`;
- create a split-before-promote draft queue under `manifests/drafts/`;
- review draft manifests for substance before handoff;
- validate all new drafts in schema mode and run root schema validation.

Do not:

- restructure code in place;
- weaken any anti-gaming validation rule to make a refactor easier;
- delete public artifacts without an explicit `maid-evolver` plan;
- mix performance and refactor scope in the same draft (use the
  `maid-runner-performance-optimization` skill for measurable speedups);
- promote draft manifests into `manifests/`;
- commit or push unless the user explicitly asks.

If the user asks to implement selected drafts, use `maid-runner-draft-implement`
instead.

## Refactor Contract

Cleanup and refactor work must keep MAID's manifest contract and the public
API stable. Treat these as invariants for every proposed change:

- the same inputs must produce the same `ValidationResult.success`, error
  codes, warnings, and JSON output as before the refactor;
- every public artifact declared in active manifests must still exist with the
  same signature, or be removed under an explicit `maid-evolver` plan;
- characterization tests must exist for every file in scope before any
  restructuring touches it (Feathers' rule);
- the manifest chain stays loadable: `uv run maid validate --mode schema` must
  pass at every step;
- no silent fallbacks, no fake/stale return values, no dead-code removal that
  changes observable behavior;
- private helpers (`_` prefix) can be renamed, split, or removed without an
  evolver plan provided behavior is preserved.

## Start

1. Check the branch and dirty worktree:

```bash
git status --short --branch --untracked-files=all
```

Work around unrelated user or automation changes. Do not revert them.

2. Read the current surfaces likely involved:

- `docs/maid-philosophy-and-vision.md`
- `docs/plans/maid-runner-cleanup-refactor-backlog.md` if it exists
- `maid_runner/core/validate.py`
- `maid_runner/core/chain.py`
- `maid_runner/core/manifest.py`
- `maid_runner/core/_validation_test_artifacts.py`
- `maid_runner/core/test_runner.py`
- `maid_runner/validators/python.py`
- `maid_runner/validators/typescript.py`
- `maid_runner/validators/svelte.py`
- `maid_runner/validators/base.py`
- `maid_runner/validators/registry.py`
- `maid_runner/graph/builder.py`
- `maid_runner/coherence/engine.py`
- `maid_runner/cli/commands/`

3. Read prior cleanup-relevant insights when present, especially clean-code,
duplication, dead-code, manifest-drift, and characterization notes under
`.claude/insights/`.

4. Inventory the cost surface:

```bash
find maid_runner -name '*.py' -not -path '*/tests/*' \
  | xargs wc -l | sort -n | tail -20
find manifests -maxdepth 2 -name '*.manifest.yaml' | wc -l
find tests -name 'test_*.py' | wc -l
```

Use the size and count to rank candidates: the longest files and the most-
frequently-imported helpers usually have the highest cleanup leverage.

## Audit Workflow

Prefer confirmed targets over intuition. Build small static probes that
prove each finding, and record exact file paths and line ranges. Frame every
finding in Fowler's vocabulary so the eventual maneuver is obvious: Long
Method for oversized functions, Duplicate Code for parallel branches,
Primitive Obsession for stringly-typed flags, Shotgun Surgery for changes
that ripple across many modules, Comments for stale notes that should be
deleted or replaced with explanatory tests.

Probe shapes that are usually enough:

```bash
# Dead private helpers: defined but never referenced outside their own module.
rg -n "^def _[a-z]" maid_runner | while read hit; do
  name=$(echo "$hit" | sed -E 's/.*def (_[a-z_0-9]+).*/\1/')
  rg -n "$name" maid_runner | wc -l
done

# Long functions: rough proxy via consecutive non-blank lines per def.
rg -n "^def |^    def " maid_runner --no-heading

# Duplicated validator logic.
diff -u maid_runner/validators/python.py maid_runner/validators/typescript.py \
  | rg "^[+-]" | head -40

# Orphaned manifests: declared files that no longer exist on disk.
uv run maid validate --quiet 2>&1 | rg -i "not found|missing"

# Stale TODO/FIXME with no owner or date.
rg -n "TODO|FIXME|XXX|HACK" maid_runner docs
```

Good cleanup categories:

- private helpers defined and only self-referenced;
- near-duplicate methods across the language validators that could move to
  `BaseValidator` without changing public behavior;
- functions or methods longer than ~80 lines or with more than two clear
  responsibilities;
- modules over ~600 lines that mix multiple concerns;
- nested conditionals and early returns that could become guard clauses;
- magic strings or numbers that already have a constant elsewhere;
- inconsistent error-code usage where a shared helper would be safer;
- stale TODO/FIXME comments that the manifest history shows are resolved;
- orphaned manifests whose files were renamed or removed without a refactor
  manifest;
- snapshot manifests that have been fully superseded by feature work and can
  be archived;
- tests that mock heavily where a fake would simplify maintenance, per the
  testability rules in `~/.claude/CLAUDE.md`.

For each confirmed target, capture:

- file path, line range, and call sites;
- which manifest declares the affected artifacts (if any);
- which engine should own the work (`safe-refactor` for behavior-preserving
  cleanup, `maid-evolver` for any public-contract change);
- the Fowler maneuver(s) the eventual draft will apply (Extract Method, Pull
  Up Method, Introduce Parameter Object, etc.);
- the Feathers seam the refactor will rely on (constructor parameter,
  extracted method, wrapper around a static call, adapter around a global),
  or note that the file is already test-friendly and no seam is needed;
- characterization plan: what tests must exist before the refactor begins;
- behavior-preservation plan: which observable outputs anchor the equivalence
  proof;
- closure shape, with the invariant from the Refactor Contract that must be
  preserved.

## Findings Document

Save confirmed findings as Markdown under `docs/plans/`, usually:

```text
docs/plans/maid-runner-cleanup-refactor-backlog.md
```

Use this structure:

- Purpose
- Refactor Contract (link to the section in the skill)
- Confirmed Cleanup Targets
- Speculative Ideas (kept separate until measured against the cost surface)
- Manifest-Evolution Targets (each one names the evolver plan)
- Gradual Closure Backlog
- Suggested Acceptance Criteria
- Verification Notes

Keep it technical and actionable. Do not write marketing text or generic
"improve quality" entries. Each confirmed entry must cite the file, the
function or method, and the call-site evidence that justifies the change.

Pure Markdown-only updates are normally documentation changes in this repo, so
a separate MAID manifest is not required unless the user asks or the change
touches code/test artifacts.

## Draft Manifest Queue

Create one epic plus implementation-sized child drafts under
`manifests/drafts/`. Use the next available numeric wave. For a cleanup queue,
use names like:

```text
035-00-maid-runner-cleanup-refactor-roadmap.epic.yaml
035-01-characterize-validate-engine.manifest.yaml
035-02-extract-shared-validator-base.manifest.yaml
```

Epic requirements:

- first lines:

```yaml
# draft-kind: epic
# promotion: split-before-promote
```

- `metadata.status: planning`;
- planned child order with characterization drafts before any restructuring;
- concise rationale tying the queue to maintainability without weakening
  validation or the MAID contract;
- temptations that prevent broad rewrites, dead-code deletion without
  characterization, and bundled performance work;
- at least one valid file section, because schema v2 requires a writable
  section.

Child draft requirements:

- first line:

```yaml
# draft-kind: implementation
```

- one confirmed cleanup target or tightly related cluster per draft;
- exact production files likely to change in `files.edit` or `files.create`;
- exact public artifacts that must remain stable, with signatures, return
  types, and attribute types;
- behavioral or characterization test-function artifacts that lock the
  observable behavior before any restructuring;
- explicit `engine:` metadata naming `safe-refactor` or `maid-evolver` so the
  draft-implement loop selects the right workflow;
- the Fowler maneuver(s) named in the description so the reviewer agent can
  confirm the diff matches the declared scope;
- `files.read` for supporting docs, existing tests, and adjacent helpers;
- 3-5 task-specific `temptations`, each with a concrete `instead`;
- a focused `validate:` command that runs the relevant tests once promoted.

Prefer an ordered queue. A sensible starting shape:

1. Characterize the largest mixed-concern modules before any restructuring
   (`validate.py`, `chain.py`, `test_runner.py`).
2. Extract shared validator behavior into `BaseValidator` without changing
   public Python, TypeScript, or Svelte validator surfaces.
3. Split overgrown methods (`ValidationEngine.validate_behavioral`,
   `_run_verify`) into named guard-clause helpers with the same outputs.
4. Replace magic strings with the constants that already exist (error codes,
   file-tracking statuses, severities).
5. Remove confirmed dead private helpers with characterization-anchored
   behavior tests.
6. Archive or supersede snapshot manifests fully replaced by feature work,
   using `maid-evolver`.
7. Resolve or remove stale TODO/FIXME comments backed by closed manifests.
8. Migrate heavily-mocked tests toward fakes per the testability rules in
   `~/.claude/CLAUDE.md`.

Adjust the order if the current repo state shows some drafts are already
implemented or promoted.

## Draft Self-Review

Before handoff, review every draft as if trying to game it.

Blockers to fix before reporting ready:

- vague goals that do not name the file, function, or duplication being
  removed;
- missing Fowler maneuver name in the description (Extract Method, Pull Up
  Method, etc.), so the reviewer cannot match the diff to a known scope;
- missing Feathers seam (or an explicit note that no seam is needed) when the
  target file lacks trustworthy tests;
- production artifacts without exact signatures;
- missing `args: []` for zero-argument functions or methods;
- new public classes without declared public attributes/methods;
- test functions that only assert "code still runs" without locking observable
  behavior, JSON output, or error codes;
- characterization drafts that skip negative cases (error paths, empty input,
  unicode/edge cases);
- `temptations` that name a risk without a procedural `instead`;
- drafts that delete public artifacts without a paired `maid-evolver` plan;
- drafts that bundle a performance change in with a cleanup;
- drafts that mix more than one Fowler maneuver per child (Shotgun Surgery in
  the refactor itself); split into separate drafts;
- validate commands that do not include the tests declared in the manifest.

For child drafts, make sure the test plan includes:

- at least one characterization test that locks current observable output
  (including error codes and JSON shape where relevant);
- at least one negative test proving the refactor does not change error
  behavior;
- for `maid-evolver` drafts: a test that proves the evolution path
  (renames map correctly, signatures match the new contract, removed
  artifacts no longer appear in `merged_artifacts_for`).

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
docs(maid): add cleanup and refactor draft queue
```

Never push without explicit user approval.
