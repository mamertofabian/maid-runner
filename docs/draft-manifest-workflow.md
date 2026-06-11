# Draft Manifest Workflow

Draft manifests are MAID planning inventory. Promoted manifests are active
contracts.

This workflow is useful when a larger goal can be split into known,
implementation-sized pieces before the first code change starts. Instead of
tracking those pieces in free-form markdown, put each known child task in
`manifests/drafts/` as a draft manifest. The draft queue gives automation a
concrete list to work through while keeping unapproved plans out of the active
manifest chain.

## Directories

- `manifests/drafts/*.manifest.yaml`: mutable child drafts that are not active
  MAID contracts yet.
- `manifests/drafts/*.epic.yaml`: larger planning records that must be split
  before promotion.
- `manifests/*.manifest.yaml`: promoted, active MAID contracts.

Normal validation and test execution should target promoted manifests in
`manifests/`. Draft validation is focused on plan quality before promotion.
Early inventory drafts may reference planned test files that do not exist yet;
that makes them not promotion-ready, but it is not by itself a planning defect.

## Lifecycle

1. Define the larger goal in an issue, spec, roadmap, or epic draft.
2. Split the known work into child draft manifests under `manifests/drafts/`.
3. Review and refine each draft until its scope, declared artifacts, planned or
   actual behavioral tests, validation command, dependencies, and temptations
   are coherent.
4. Promote one implementation-sized draft by moving it from
   `manifests/drafts/<slug>.manifest.yaml` to
   `manifests/<slug>.manifest.yaml`.
5. Implement strictly inside the promoted manifest's declared file scope.
6. Validate the promoted path, run the declared tests, run the changed-scope
   handoff gate, and review the implementation against the manifest.
7. Capture Outcome after implementation review and before final handoff when
   the schema is available. Outcome records are completion metadata documented
   in `docs/manifest-outcome-records.md`; they do not replace behavioral tests,
   declared artifacts, validation commands, or review.
8. Commit only after the manifest, implementation, validation evidence, review,
   and Outcome capture are ready.
9. Re-scan `manifests/drafts/` for the next child draft.

Drafts may be edited freely before promotion. After promotion, do not silently
rewrite the contract. Use the normal MAID evolution path instead.

## When To Pre-Create Drafts

Pre-create drafts when the work can be enumerated with reasonable confidence:

- parser replacement phases;
- CLI automation follow-ups;
- multi-file features with obvious child boundaries;
- remediation batches discovered during audit or review.

Do not force a complete draft set when discovery is still the main task. It is
valid to start with a small queue and add more draft manifests as gaps become
visible.

## Promotion Criteria

A child draft is ready to promote when:

- it is implementation-sized and not an epic;
- its file scope is narrow and explicit;
- every declared public artifact has the intended kind, owner, signature, and
  type information;
- behavioral tests exist for the declared production artifacts, unless the
  draft is explicitly characterization-only;
- the red phase fails for the intended reason before implementation;
- `maid validate manifests/drafts/<slug>.manifest.yaml --mode behavioral`
  passes;
- dependencies on earlier drafts are clear and ordered.

If a draft fails these checks, refine the draft before promotion.

Do not apply the promotion checklist to every draft in the queue. For an
inventory draft, schema validation and coherent scope may be enough to keep it
as a future work item. For the draft selected for implementation, the first
work is to create or refine the behavioral tests, confirm the red phase, pass
behavioral validation against the draft path, then promote it to `manifests/`.

## Plan Locks at Promotion

`maid manifest promote` migrates the promoted manifest's plan lock so
promotion never strands tamper evidence. When `.maid/plan-locks/<slug>.lock.json`
exists and records the draft being promoted, promote:

- rewrites self-referencing validate-command paths in the manifest from the
  drafts/ path to the promoted path (this happens for unlocked drafts too);
- re-locks the promoted manifest through the sanctioned revision path: the
  prior hashes are preserved in the lock's revision history and the revision
  reason records the promotion;
- recaptures red-phase evidence by running the promoted manifest's validate
  commands, matching `maid plan lock`; pass `--no-run` to skip capture and
  record null evidence. Evidence capture is lock-gated: promoting an unlocked
  draft never runs validate commands;
- resolves the lock directory from `--project-root` (default `.`), mirroring
  the `maid plan` subcommands.

Promotion fails closed: a lock that exists but is unreadable, or that records
a different manifest path, aborts the promotion with exit code 2 and leaves
the draft and the lock untouched. If lock migration fails mid-promotion, the
promoted file is removed and the draft is kept.

Promote does not edit other manifests. When another active manifest still
references the promoted draft path (for example in `files.read`), promote
prints a warning naming it; update that reference and run `maid plan revise`
for its lock, since silently rewriting a locked manifest would defeat tamper
evidence.

## From-Diff Authoring Loop

`maid manifest from-diff` creates a draft manifest from an implemented change so
the author can review and correct a generated contract. Code the change, then
run the command with exactly one baseline option:

```bash
maid manifest from-diff --since <commit>
maid manifest from-diff --base-ref <ref>
maid manifest from-diff --worktree
```

Supplying zero baseline options or more than one baseline option exits with code
2 and a baseline-required message that follows the `E115` fail-closed rule. MAID
does not guess `main`, `dev`, or a remote branch.

The command writes deterministic, schema-valid drafts under
`manifests/drafts/<slug>.manifest.yaml`. The default slug is
`from-diff-<UTC-date>-<short-commit-hash>`, and callers can use `--slug`,
`--output`, `--force`, `--dry-run`, and `--json`. `--force` is required to
overwrite an existing draft. A generated draft starts with the goal placeholder
`"TODO: describe this change"` plus these markers:

```yaml
metadata:
  generated_by: maid-manifest-from-diff
  needs_review: true
```

Generated drafts are not active contracts and do not self-promote. They remain
in `manifests/drafts/` until the author reviews them, replaces the goal
placeholder, fills any placeholder artifacts, clears `needs_review: true`, and
satisfies the promotion criteria above. The `metadata.needs_review: true`
marker means the draft is not promotable yet. Artifacts whose exact types are
not known omit the unknown fields instead of guessing.

Generated drafts suggest pytest commands only for test files that exist and
currently reference at least one changed artifact. Without that evidence, the
draft's `validate:` list contains only:

```bash
maid validate <draft-path> --mode schema --quiet
```

## Outcome Capture

Outcome records close a promoted implementation session after implementation
review and before final handoff. Add or update the manifest's optional
`outcome` section only after the implementation result, validation evidence,
and review notes are known.

The canonical Outcome guide is
[`docs/manifest-outcome-records.md`](manifest-outcome-records.md). Outcome is
completion metadata; it does not loosen manifest scope, replace declared
artifacts, substitute for behavioral tests, skip validation commands, or bypass
implementation review.

## Automation

The local loop scripts treat `manifests/drafts/*.manifest.yaml` as the work
queue and ignore epic drafts:

```bash
npm run maid:codex-loop -- --once
npm run maid:claude-loop -- --once
```

The outer loop owns pass granularity. By default, one selected draft is handed
to a fresh agent session. Use the loop script's explicit batch option only when
several selected drafts are intentionally safe to implement in one pass.

Each ready pass should include the promoted manifest, implementation changes,
test changes, validation evidence, and an implementation review verdict. The
loop must not treat one previous approval as permission to commit future
passes.

### Handoff Scope Gate

`maid verify` runs changed-scope by default, but the task baseline must still
be explicit. Every ready implementation pass should run it before review or
commit so already-committed task changes cannot be hidden by moving a production
file from `files.edit` to `files.read`.

Use one of these forms:

```bash
maid verify --base-ref <parent-branch>
maid verify --since <task-start-commit>
```

`--base-ref` compares from `git merge-base <parent-branch> HEAD` to the current
working tree, which is the usual choice for stacked branches. `--since` compares
from the exact commit-ish supplied by the caller. A manifest may also declare
`metadata.maid_task_base`, but all active manifests that declare it must agree.

If no baseline can be resolved, MAID fails with `E115`; it does not guess
`main`, `master`, `dev`, `development`, or a remote branch. Git does not retain
a reliable branch-origin fact after rebases and merges, and a default commit
count can miss task changes. Use `--include-tests` when changed tests should be
scope-checked too. Use `--no-changed-scope` only for intentionally non-handoff
verification runs.

## Evolution During Implementation

Implementation will expose gaps sometimes. Handle them based on whether the
affected contract is still a draft or already promoted:

- Before promotion: edit the draft and rerun behavioral validation.
- After promotion, additive change: create a new manifest that adds the new
  artifact or file and let chain merging combine the active contracts.
- After promotion, breaking change: create a superseding manifest that declares
  the complete replacement contract.
- If a selected draft depends on unimplemented work, stop the pass as blocked
  or add/refine the prerequisite draft rather than implementing outside scope.

The goal is not to predict every implementation detail upfront. The goal is to
make the known plan enumerable, reviewable, and machine-checkable before each
piece becomes an active MAID contract.
