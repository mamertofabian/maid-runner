---
name: maid-validate-hardening
description: Use in maid-runner when asked to audit `maid validate` / `maid verify` for anti-gaming loopholes, evaluate validator-hardening design, save confirmed findings, or create draft-manifest queues. Emphasizes evidence-backed closure through schema, VCS/worktree scope, test-runner output, compiler/parser services, bounded syntax checks, reference documentation, MAID draft planning, plan self-review, schema validation, and optional branch/commit handoff.
---

# MAID Validate Hardening

Use this skill in `/home/atomrem/projects/codefrost-dev/maid-runner` when the
user wants to audit or improve `maid validate` / `maid verify` hardening:
review MAID's purpose, probe loopholes an AI agent could game, choose the
smallest reliable evidence source for each closure, document confirmed
findings, and create draft manifests only when the closure shape is bounded.

## Scope

This skill is for planning and reference artifacts, not implementation.

Do:

- inspect the current code path before assuming an old loophole still exists;
- run small adversarial scenarios in throwaway projects under `/tmp`;
- distinguish confirmed loopholes from speculative hardening ideas;
- classify each loophole by the most reliable evidence source before drafting;
- prefer compiler-, parser-, test-runner-, VCS-, schema-, or runtime-backed
  evidence over custom static interpretation;
- save findings in a concise Markdown reference under `docs/plans/`;
- create a split-before-promote draft queue under `manifests/drafts/` when the
  closure shape is bounded enough for implementation;
- review draft manifests for substance before handoff;
- validate all new drafts in schema mode and run root schema validation.

Do not:

- edit production validator code while using this skill;
- promote draft manifests into `manifests/`;
- plan broad Python control-flow or reachability analyzers as the default fix;
- inflate `maid_runner/core/validate.py` with language-specific analysis that
  belongs behind a parser/compiler/test-runner seam;
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

2. If the task involves design direction, parser/compiler behavior, or a
   suspected bloated hardening branch, use the `agent-rules-selector` skill.
   Prefer:

- `language-implementation-patterns` for parser, compiler, AST, symbol, and
  identity work;
- `building-evolutionary-architectures` when choosing incremental fitness
  functions and avoiding broad rewrites.

3. Read the current validator surfaces likely involved:

- `docs/maid-philosophy-and-vision.md`
- `docs/plans/maid-validate-hardening-backlog.md` if it exists
- `maid_runner/core/validate.py`
- `maid_runner/core/chain.py`
- `maid_runner/core/manifest.py`
- `maid_runner/core/result.py`
- `maid_runner/core/test_runner.py`
- `maid_runner/core/ts_compiler_resolver.py`
- `maid_runner/core/ts_compiler_resolver.cjs`
- `maid_runner/core/ts_module_paths.py`
- `maid_runner/cli/commands/validate.py`
- `maid_runner/cli/commands/verify.py`
- `maid_runner/cli/commands/files.py`
- `docs/spikes/spike-parser-library-replacement-options.md`
- relevant tests under `tests/core/` and `tests/cli/`

4. Check prior hardening insights when present, especially path-escape,
recursive discovery, supersession, duplicate-YAML, strict-mode, worktree-scope,
review-loop, command-integrity, and stalled branch notes under
`.claude/insights/`.

5. If a previous branch is named in the prompt, inspect its shape before
copying it:

```bash
git diff --stat main...<branch>
git diff --name-status main...<branch>
```

Treat large growth in `maid_runner/core/validate.py`,
`tests/core/test_validate.py`, or language-specific heuristics as a design
signal. Summarize what behavior it tried to close, then reframe the closure
around smaller evidence-backed seams where possible.

## Hardening Strategy

Use this evidence ladder before writing drafts. Prefer the first applicable
level that can fail closed with clear output:

1. **Schema or manifest contract:** invalid combinations such as snapshot task
   types with implementation write sections should be rejected at schema or
   manifest-validation boundaries.
2. **VCS/worktree evidence:** changed files must be writable in the active
   manifest chain. Use worktree-scope for dirty changes and branch-diff scope
   for already-committed feature work.
3. **Test-runner evidence:** if the question is whether tests actually ran or
   were skipped/xfailed, prefer structured runner output, collected-test
   metadata, or execution reports over trying to predict pytest behavior from
   source syntax.
4. **Compiler or parser services:** use existing language services for import,
   re-export, symbol, package, or tsconfig semantics. Keep them behind stable
   MAID interfaces such as `resolve_ts_import`, `resolve_ts_reexport`, and
   validator collectors.
5. **Narrow syntactic rule:** only use a custom AST rule when the bad pattern is
   deliberately narrow, locally decidable, and documented as limited.
6. **Human review gate:** if the desired guarantee needs broad semantic
   judgement, make it an implementation-review checklist item rather than a
   pretend-static validator.

Do not default to case-by-case AST interpretation for Python control flow,
pytest fixture execution, import aliasing, or language semantics. The abandoned
`033` reachability/skipped-test approach showed the cost: large growth in
`validate.py` and `tests/core/test_validate.py`, many special cases, and still
incomplete coverage of pytest and Python execution semantics.

Good closure shapes:

- snapshot/write-section misuse: schema and manifest model checks;
- `files.read` hiding changed production files: worktree and branch-diff scope
  gates;
- no-op `validate:` or `acceptance.tests` commands: command-target integrity
  plus recognized test-runner checks;
- skipped, xfailed, or uncollected tests: test-runner execution metadata or a
  small runner adapter;
- TypeScript import, re-export, package, and `tsconfig` identity: the existing
  opportunistic compiler bridge with parser/path fallback;
- Python artifact existence and local references: stdlib `ast` collectors for
  file-local syntax, with identity-backed matching; use runtime coverage or
  review gates before attempting broad reachability.

Stop and propose a design direction before implementation when:

- the closure requires modeling pytest fixture resolution, decorators, marks,
  parametrization, or unittest behavior in custom AST code;
- the closure requires general Python reachability, symbolic execution, or
  control-flow analysis;
- the test plan grows into dozens of near-duplicate syntax cases;
- the intended patch would add hundreds of lines to `validate.py` instead of a
  focused module, adapter, or existing validator seam;
- the guarantee is better answered by `coverage.py`, pytest reports, Git diff
  scope, a compiler API, or implementation review.

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
- changed production files hidden under `files.read` after prior commits;
- no-op or wrong-target `validate:` / `acceptance.tests` commands;
- skipped, xfailed, deselected, or zero-collected behavioral tests;
- obvious dead test code, but only as a probe for runtime-backed or narrow
  closure design;
- coherence failures printed after a green validate result;
- worktree changes outside manifest writable scope.

For each confirmed loophole, capture:

- scenario;
- observed command and exit code;
- why it matters for AI anti-gaming;
- current code path or file area;
- evidence source selected from the hardening strategy ladder;
- closure shape.

## Findings Document

Save confirmed findings as Markdown under `docs/plans/`, usually:

```text
docs/plans/maid-validate-hardening-backlog.md
```

Use this structure:

- Purpose
- Confirmed Loopholes
- Evidence Classification
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
0NN-00-maid-validate-hardening-roadmap.epic.yaml
0NN-01-reject-snapshot-write-sections.manifest.yaml
0NN-02-add-changed-scope-gate.manifest.yaml
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
- the evidence source for each child draft;
- temptations that prevent broad rewrites, broad static analyzers, and
  documentation-only fixes;
- at least one valid file section, because schema v2 requires a writable
  section.

Child draft requirements:

- first line:

```yaml
# draft-kind: implementation
```

- one confirmed loophole or tightly related loophole cluster per draft;
- exact production files likely to change in `files.edit` or `files.create`;
- avoid `maid_runner/core/validate.py` as the default home for new logic; prefer
  a focused helper/module when the check has its own policy or integration;
- exact public artifacts with signatures, return types, and attribute types;
- behavioral test-function artifacts with scenario, action, and expected
  behavior metadata;
- `files.read` for supporting docs, existing tests, and adjacent helpers;
- 3-5 task-specific `temptations`, each with a concrete `instead`, including
  one that prevents broad AST/control-flow modeling when relevant;
- a focused `validate:` command that runs the relevant tests once promoted.

Order the queue by reliability and blast radius, not by the age of the idea.
Prefer:

1. schema/model invariants with small impact;
2. VCS/worktree scope gates;
3. command integrity and test-runner execution evidence;
4. compiler/parser-backed identity improvements behind existing interfaces;
5. narrow syntactic guards with documented limits;
6. review guidance for anything that cannot be automated cheaply.

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
- no evidence classification or a closure shape that ignores a better runner,
  compiler, schema, or VCS signal;
- broad reachability/control-flow plans that do not explain why runtime-backed
  evidence is unavailable;
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
