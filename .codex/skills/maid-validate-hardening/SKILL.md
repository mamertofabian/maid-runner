---
name: maid-validate-hardening
description: Use in maid-runner when asked to audit `maid validate` for anti-gaming loopholes, save confirmed findings, or create a substantial draft-manifest queue for closing validator gaps. Covers adversarial scenario design, reference documentation, MAID draft planning, plan self-review, schema validation, and optional branch/commit handoff.
---

# MAID Validate Hardening

Use this skill in `/home/atomrem/projects/codefrost-dev/maid-runner` when the
user wants to repeat the validator-hardening process: review MAID's purpose,
probe `maid validate` for loopholes an AI agent could game, document confirmed
findings, and create draft manifests that the Codex MAID loop can implement.

## Scope

This skill is for planning and reference artifacts, not implementation.

Do:

- inspect the current code path before assuming an old loophole still exists;
- run small adversarial scenarios in throwaway projects under `/tmp`;
- distinguish confirmed loopholes from speculative hardening ideas;
- save findings in a concise Markdown reference under `docs/plans/`;
- create a split-before-promote draft queue under `manifests/drafts/`;
- review draft manifests for substance before handoff;
- validate all new drafts in schema mode and run root schema validation.

Do not:

- edit production validator code while using this skill;
- promote draft manifests into `manifests/`;
- weaken or remove active manifests to get validation green;
- commit or push unless the user explicitly asks.

If the user asks to implement selected drafts, use `maid-runner-draft-implement`
instead.

## Start

1. Check the branch and dirty worktree:

```bash
git status --short --branch --untracked-files=all
```

Work around unrelated user or automation changes. Do not revert them.

2. Read the current validator surfaces likely involved:

- `docs/maid-philosophy-and-vision.md`
- `docs/plans/maid-validate-hardening-backlog.md` if it exists
- `maid_runner/core/validate.py`
- `maid_runner/core/chain.py`
- `maid_runner/core/manifest.py`
- `maid_runner/core/result.py`
- `maid_runner/core/test_runner.py`
- `maid_runner/cli/commands/validate.py`
- `maid_runner/cli/commands/files.py`
- relevant tests under `tests/core/` and `tests/cli/`

3. Check prior hardening insights when present, especially path-escape,
recursive discovery, supersession, duplicate-YAML, strict-mode, worktree-scope,
and review-loop notes under `.claude/insights/`.

## Adversarial Probe Workflow

Build small, disposable projects under `/tmp` to prove each suspected loophole.
Prefer invoking the local package entry point through `uv run` or direct Python
imports. Keep probes simple enough that their output can be summarized in the
reference doc.

Good probe categories:

- missing or empty manifest directories;
- structural validation green while `validate:` commands fail;
- behavioral tests that reference artifacts but assert nothing;
- warnings that still exit zero;
- manifest paths that escape `project_root`;
- duplicate YAML keys that change the parsed contract;
- undeclared production files outside the active manifest chain;
- coherence failures printed after a green validate result;
- worktree changes outside manifest writable scope.

For each confirmed loophole, capture:

- scenario;
- observed command and exit code;
- why it matters for AI anti-gaming;
- current code path or file area;
- closure shape.

## Findings Document

Save confirmed findings as Markdown under `docs/plans/`, usually:

```text
docs/plans/maid-validate-hardening-backlog.md
```

Use this structure:

- Purpose
- Confirmed Loopholes
- Gradual Closure Backlog
- Suggested Acceptance Criteria
- Verification Notes

Keep it technical and actionable. Do not write marketing text. Mention which
checks were actually run and which findings are only proposals.

Pure Markdown-only updates are normally documentation changes in this repo, so
a separate MAID manifest is not required unless the user asks or the change
touches code/test artifacts.

## Draft Manifest Queue

Create one epic plus implementation-sized child drafts under
`manifests/drafts/`. Use the next available numeric wave. For a validator
hardening queue, use names like:

```text
030-00-maid-validate-hardening-roadmap.epic.yaml
030-01-fail-empty-manifest-discovery.manifest.yaml
030-02-make-coherence-flag-fail-closed.manifest.yaml
```

Epic requirements:

- first lines:

```yaml
# draft-kind: epic
# promotion: split-before-promote
```

- `metadata.status: planning`;
- planned child order;
- concise rationale tying the queue to fail-closed validation;
- temptations that prevent broad rewrites and documentation-only fixes;
- at least one valid file section, because schema v2 requires a writable
  section.

Child draft requirements:

- first line:

```yaml
# draft-kind: implementation
```

- one confirmed loophole or tightly related loophole cluster per draft;
- exact production files likely to change in `files.edit` or `files.create`;
- exact public artifacts with signatures, return types, and attribute types;
- behavioral test-function artifacts with scenario, action, and expected
  behavior metadata;
- `files.read` for supporting docs, existing tests, and adjacent helpers;
- 3-5 task-specific `temptations`, each with a concrete `instead`;
- a focused `validate:` command that runs the relevant tests once promoted.

Prefer an ordered queue:

1. Fail closed on missing or empty manifest discovery.
2. Make `--coherence` affect exit status.
3. Reject manifest path escapes.
4. Reject duplicate YAML mapping keys.
5. Promote missing behavioral coverage from warning to error.
6. Expose strict CLI flags for assertions, stubs, and warnings.
7. Add file-tracking fail gates.
8. Add `maid validate --run-tests`.
9. Add worktree scope gate.
10. Add a combined `maid verify` done gate.

Adjust the order if the current repo state shows some drafts are already
implemented or promoted.

## Draft Self-Review

Before handoff, review every draft as if trying to game it.

Blockers to fix before reporting ready:

- vague goals that do not name the failing behavior;
- production artifacts without exact signatures;
- missing `args: []` for zero-argument functions or methods;
- new public classes without declared public attributes/methods;
- test functions that only check parser acceptance and not exit code or
  structured errors;
- missing JSON-output expectations for automation-facing CLI changes;
- `temptations` that name a risk without a procedural `instead`;
- validate commands that do not include the tests declared in the manifest.

For child drafts, make sure the test plan includes at least one adversarial
case proving the old bypass fails with a non-zero exit status or structured
error.

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
docs(maid): add validate hardening draft queue
```

Never push without explicit user approval.
