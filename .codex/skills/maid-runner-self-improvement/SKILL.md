---
name: maid-runner-self-improvement
description: Use in maid-runner when asked to improve MAID runner as a whole system, synthesize lessons from bug reports, review findings, insights, failed MAID loops, release friction, user feedback, or recurring workflow pain, and route confirmed opportunities into cleanup/refactor, performance, validation hardening, documentation, developer-experience, release, or MAID workflow draft queues. Produces a prioritized self-improvement backlog and scoped draft-manifest candidates; delegates deep specialist audits to the existing maid-runner cleanup/refactor, performance optimization, validation hardening, draft implementation, and implementation review skills instead of replacing them.
---

# MAID Runner Self Improvement

Use this skill in `/home/atomrem/projects/codefrost-dev/maid-runner` when the
user wants a planning-grade improvement pass over MAID runner as an operating
system: what keeps breaking, what slows agents down, what review findings keep
recurring, what bug reports reveal about validator limits, and which improvement
work should happen next. The output is a prioritized backlog plus routed draft
manifest candidates. This skill plans only. It does not implement.

## Skill Coordination

This skill is the portfolio layer above the existing specialist skills. Use it
to synthesize scattered evidence, rank opportunities, and decide which lane owns
the next work.

Delegate deep investigation or implementation as follows:

- `maid-runner-cleanup-and-refactor`: structural debt, duplicate code, dead
  code, long functions, weak abstractions, stale TODOs, and orphaned manifests.
- `maid-runner-performance-optimization`: measured speedups for `maid validate`,
  `maid test`, `maid verify`, parser reuse, caching, batching, and redundant
  work.
- `maid-validate-hardening`: anti-gaming loopholes, validator trust, command
  integrity, file-scope enforcement, schema boundaries, and evidence-backed
  closure design.
- `maid-runner-draft-implement`: promotion and implementation of approved draft
  manifests.
- `maid-implementation-review`: read-only review of completed MAID-backed
  implementation work before handoff.
- `maid-evolver`: intentional changes to artifacts already covered by active
  MAID manifests.
- `feature-spec-architect`: broad product or architecture changes that need a
  technical spec before MAID drafts are safe.

If a user asks specifically for cleanup, performance, or validation hardening,
use the specialist skill directly. Use this skill when the request is broader:
"make MAID runner better", "find the next improvements", "learn from recent
failures", "prioritize the backlog", "turn these incidents into improvement
work", or "audit our self-improvement loop".

## Scope

Do:

- gather evidence from current repo state, recent insights, bug reports,
  review findings, draft manifests, validation logs, and release notes;
- deduplicate repeated symptoms into confirmed improvement themes;
- classify each theme by owner lane and required evidence level;
- rank opportunities by impact, confidence, risk, implementation size, and
  whether the work unlocks future MAID adoption;
- create or update a concise backlog under `docs/plans/`;
- create split-before-promote draft-manifest candidates under
  `manifests/drafts/` when an item is bounded enough;
- run schema validation for any new or edited manifests;
- clearly label speculative ideas separately from confirmed findings.

Do not:

- implement production code or tests while using this skill;
- perform a deep cleanup, performance, or hardening audit when a specialist
  skill should own it;
- turn every weak signal into a manifest;
- use vague improvement goals such as "make validation better" without a
  bounded behavior, owner lane, and evidence source;
- promote draft manifests into `manifests/`;
- commit or push unless the user explicitly asks.

Pure Markdown-only updates are normally documentation changes in this repo, so
a separate MAID manifest is not required unless the user asks or the change
touches code, tests, schemas, or active manifests.

## Start

1. Check branch and dirty worktree:

```bash
git status --short --branch --untracked-files=all
```

Work around unrelated user or automation changes. Do not revert them.

2. Read current planning and philosophy documents when present:

- `docs/maid-philosophy-and-vision.md`
- `docs/plans/maid-runner-self-improvement-backlog.md`
- `docs/plans/maid-runner-cleanup-refactor-backlog.md`
- `docs/plans/maid-runner-performance-backlog.md`
- `docs/plans/maid-validate-hardening-backlog.md`
- `docs/plans/`
- `specs/`

3. Read operational evidence selectively:

- `.claude/insights/` and `.claude/insights/review/`
- `~/.maid/bug-report/`
- `manifests/drafts/`
- recent release notes or recovery notes in `docs/`
- current validation output from `uv run maid validate`, `uv run maid test`, or
  `uv run maid verify` when the prompt asks for current health

Use `rg`, `find`, `git log`, and focused file reads. Do not bulk-load every
insight or every manifest; sample enough to confirm themes, then inspect the
best evidence for each candidate.

## Evidence Triage

Treat evidence quality as the first filter. Prefer current, reproducible
signals over old notes.

Evidence tiers:

1. **Confirmed current failure:** a command, test, review, or bug report still
   reproduces on the current tree.
2. **Repeated review finding:** multiple implementation reviews, insights, or
   bug reports point at the same weakness.
3. **Stale but plausible signal:** an older insight names a problem that still
   appears in current files.
4. **Speculative idea:** no current evidence yet; keep it out of draft manifests
   until a probe confirms it.

Useful probes:

```bash
# Current health.
uv run maid validate --quiet
uv run maid test --quiet
uv run maid verify --keep-going --quiet

# Planning inventory.
find manifests/drafts -maxdepth 2 -name '*.yaml' | sort
find docs/plans -maxdepth 1 -type f | sort
find ~/.maid/bug-report -maxdepth 1 -type f 2>/dev/null | sort

# Recent evidence.
git log --oneline --decorate -20
rg -n "needs changes|blocked|loophole|regression|drift|slow|flake|TODO|FIXME" \
  .claude/insights docs manifests tests maid_runner
```

When a probe is expensive or noisy, summarize what was sampled and why that was
enough for ranking. Do not claim a finding is confirmed unless the supporting
artifact was read or the command was run.

## Classification

Assign exactly one primary lane to each confirmed theme, with optional secondary
lanes only when they affect sequencing.

Primary lanes:

- **Correctness:** user-visible wrong behavior, broken CLI behavior, bad result
  aggregation, bad error reporting, or command failure.
- **Validation trust:** anti-gaming loopholes, file-scope gaps, command
  integrity, schema misuse, skipped-test visibility, or evidence source quality.
- **Performance:** repeated work, slow commands, parser/session churn, serial
  subprocess loops, cache boundaries, or graph rebuild cost.
- **Maintainability:** duplication, long functions, weak abstractions,
  confusing module boundaries, dead code, or hard-to-test dependencies.
- **Developer experience:** unclear CLI output, poor diagnostics, confusing
  defaults, missing guidance, rough local workflow, or agent handoff friction.
- **Documentation:** stale or missing docs, unclear examples, release notes, or
  philosophy/spec drift.
- **MAID workflow:** weak manifests, stale drafts, missing brownfield coverage,
  review-loop gaps, plan quality, or implementation drift.
- **Release/process:** branch hygiene, release recovery, versioning, packaging,
  or CI handoff issues.

Specialist routing:

- Validation trust themes normally route to `maid-validate-hardening`.
- Performance themes normally route to `maid-runner-performance-optimization`.
- Maintainability themes normally route to `maid-runner-cleanup-and-refactor`.
- Existing-manifest artifact changes route through `maid-evolver`.
- Multi-lane architecture changes need a spec or epic before child drafts.

## Ranking

Rank each confirmed opportunity with a small rubric:

- **Impact:** high when it prevents invalid green runs, protects releases,
  reduces repeated review failures, or unlocks multiple future tasks.
- **Confidence:** high when there is a current reproduction, active review
  finding, or repeated independent evidence.
- **Urgency:** high when it blocks current work, affects release readiness, or
  creates false confidence in validation.
- **Size:** prefer implementation-sized child drafts over large rewrites.
- **Risk:** higher risk when the change touches schema contracts, CLI behavior,
  test runner semantics, cross-language validators, or active manifests.

Use this priority order unless the user gives a different objective:

1. false green validation or review-loop failures;
2. correctness bugs that affect normal MAID workflows;
3. release blockers and packaging failures;
4. recurring implementation-review findings;
5. measurable performance pain on common commands;
6. cleanup that lowers risk for already-prioritized work;
7. docs and DX improvements that remove repeated confusion.

## Backlog Document

Save or update:

```text
docs/plans/maid-runner-self-improvement-backlog.md
```

Use this structure:

- Purpose
- Current Evidence Reviewed
- Prioritized Improvement Themes
- Routed Backlog
- Specialist Follow-Ups
- Draft Manifest Candidates
- Speculative Ideas
- Verification Notes

For each confirmed theme, include:

- title;
- primary lane;
- evidence source and file/command reference;
- current symptom;
- why it matters;
- recommended owner skill;
- closure shape;
- suggested acceptance criteria;
- next draft or follow-up action.

Keep entries short and concrete. If an item cannot be tied to a file, command,
review finding, bug report, or user-observed workflow, put it in Speculative
Ideas.

## Draft Manifest Queue

Create draft manifests only for bounded, evidence-backed work. If the backlog
contains several lanes, create one self-improvement epic plus child drafts that
delegate to specialist lanes. Use the next available numeric wave under
`manifests/drafts/`, for example:

```text
035-00-maid-runner-self-improvement-roadmap.epic.yaml
035-01-close-review-loop-drift.manifest.yaml
035-02-simplify-validation-diagnostics.manifest.yaml
035-03-route-stale-drafts-to-specialist-queues.manifest.yaml
```

Epic requirements:

- first lines:

```yaml
# draft-kind: epic
# promotion: split-before-promote
```

- `metadata.status: planning`;
- evidence summary and priority order;
- planned child order;
- explicit delegation per child draft;
- temptations that prevent broad rewrites, vague quality goals, and
  implementation without evidence;
- at least one valid file section, because schema v2 requires a writable
  section.

Child draft requirements:

- one primary lane and one owner skill;
- a behavioral or characterization acceptance shape;
- files scoped narrowly enough for implementation review;
- concrete validation commands;
- no mixed implementation of unrelated cleanup, performance, and hardening work;
- explicit handoff note when a specialist skill must take over before
  implementation.

Validate new or edited drafts:

```bash
uv run maid validate manifests/drafts/<draft>.manifest.yaml --mode schema
uv run maid validate --mode schema
```

If schema validation fails because the draft structure is wrong, fix the draft.
If validation appears unable to represent a legitimate workflow, first rule out
bad manifests and environment problems. Only then consider a MAID bug report
under `~/.maid/bug-report/`.

## Handoff

End with:

- backlog path and any draft manifest paths created or updated;
- the top three recommended next actions;
- commands run and their outcomes;
- any specialist skill that should own the next phase;
- any skipped checks and why.

Do not describe the work as ready for implementation unless each proposed draft
has a clear owner lane, acceptance criteria, and schema validation status.
