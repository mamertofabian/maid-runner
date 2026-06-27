# Manifest Outcome Records

Outcome records are explicit completion metadata for MAID manifests. They are
authored after implementation review and before final handoff, when the
implementation, behavioral tests, validation commands, and review result are
known.

Outcome records are stored in the optional top-level `outcome` manifest field.
They preserve what happened when a contract closed: the final status, summary,
rationale, structured lessons, review notes, validation evidence, and optional
completion timestamp. A human or an agent may author the record, but MAID only
validates and later learns from the explicit structured data in the manifest.
MAID does not infer missing lessons from unstructured history, commit messages,
or AI-only conversation state.

## Lifecycle

The normal MAID implementation lifecycle remains authoritative:

1. Plan or promote a manifest with declared files, artifacts, behavioral tests,
   validation commands, and temptations.
2. Implement strictly inside the manifest's declared scope.
3. Run the declared tests and validation commands.
4. Complete implementation review and fix valid findings.
5. Capture Outcome after implementation review and before final handoff.

Outcome is not a planning shortcut and is not an implementation escape hatch.
It records completion evidence after the contract has been exercised. Outcome
does not replace behavioral tests, declared artifacts, validation commands,
supersession, manifest evolution, or implementation review.

## Status Semantics

`outcome.status` uses the exact schema values:

- `completed`: the contract closed successfully after tests, validation, and
  review. Completed outcomes are the default learning source for future MAID
  commands.
- `failed`: the work did not produce an accepted implementation.
- `partial`: some useful work landed or was learned, but the manifest did not
  close as a complete success.
- `superseded`: a later manifest replaced this contract.
- `archived`: the manifest remains historical context but is not active
  learning input by default.
- `abandoned`: the work was intentionally stopped without a successful
  completion.

Completed outcomes are the default learning source because they represent
reviewed, validated work. Failed, partial, superseded, archived, and abandoned
outcomes may still contain useful evidence, but future indexing, recall, or
insights commands must include them only through explicit filters. Commands
must not quietly mix non-completed statuses into the completed-learning set.

## Authoring Boundaries

An Outcome record may be human-authored, agent-authored, or edited by both, but
the durable source is the manifest data itself. The record should cite concrete
validation evidence and review findings that can be checked by a reader. Avoid
private memory, hidden summaries, or inferred claims that cannot be traced to
files, commands, review notes, or the implementation result.

Outcome lessons should describe reusable evidence without weakening the next
manifest. Recalled lessons are planning context only. Every new MAID-backed
change still needs its own behavioral tests, declared artifacts, validation
commands, and implementation review.

## Why Outcome Records Matter

Outcome records close the loop between completed MAID work and future MAID
planning. A manifest already acts as both a living planning document and a
verifiable contract. Outcome adds the durable completion memory: what the work
proved, what reviewers found, which tests mattered, and what future work should
remember.

That memory is useful because it is attached to the manifest that declared the
contract. A loose retrospective note can drift away from the files, tests, and
validation commands that made the result trustworthy. Outcome data keeps the
lesson tied to source paths, declared artifacts, review evidence, and command
evidence.

MAID still does not generate wisdom. MAID stores and retrieves explicit
evidence. Humans and agents use that evidence to make better planning,
implementation, and review decisions.

## Learning Commands

Outcome-aware commands use deterministic data from completed manifests:

- `maid learn` builds or refreshes a local Outcome index from explicit
  manifest data. Completed outcomes are indexed by default. Other statuses
  require explicit filters.
- `maid recall` retrieves related Outcome records by deterministic signals such
  as manifest slug, tag, path, artifact, validation command, review text, and
  plain text.
- `maid insights` aggregates the learned records so repeated patterns are
  visible across manifests, modules, tags, validation evidence, and review
  findings.

The command boundary is important. These commands may rank, group, filter, and
report explicit records, but they must not invent missing lessons, summarize
private conversation state, call AI services, or hide stale index data.

After Outcome capture, run `uv run maid learn` to
refresh the local `.maid/outcomes.json` advisory index for subsequent recall.
`.maid/outcomes.json` is generated and ignored; do not commit it. If
`maid learn` fails, report the refresh failure as advisory unless recall or insights are required for the current task.

## Learning Evidence Digestion

Learning commands close the loop from completed Outcome records to current agent decisions only when the agent reasons over the retrieved evidence. A
planner, implementer, reviewer, or auditor should not paste a raw recall or
insights transcript into the current task and stop there. The agent should name
applicable lessons, reject stale or irrelevant lessons with a reason, and state
what changed because of the evidence.

The decision impact should be concrete and phase-specific: manifest scope,
behavioral tests, temptations, open questions, implementation approach, risk
controls, review findings, Outcome capture, or candidate follow-up work. If no
completed Outcome records are relevant, say that and continue with the current
manifest's own tests, scope, validation commands, and review.

To intentionally include instructive failed or abandoned Outcome lessons,
refresh the index with
`uv run maid learn --include-status completed --include-status abandoned` and
then recall from that index. This is an opt-in failure-lesson workflow; the
completed-only default is unchanged. Recalled, aggregated, and digested
Outcomes are advisory evidence. They do not replace behavioral tests, declared
artifacts, validation commands, supersession, manifest evolution,
implementation review, or any approval, promotion, done, or review gate.

## Practical Uses

### Planning Recall Packet

Before drafting or promoting a manifest, recall related outcomes by the paths,
artifacts, tags, and problem area expected for the new work. The result becomes
a small planning packet: prior lessons, review notes, and validation evidence
that should influence the draft.

For example, work touching `maid_runner/core/manifest.py` can recall lessons
about strict schema boundaries, non-object YAML loader safety, and Outcome
metadata staying separate from manifest scope, artifacts, validation commands,
metadata, and supersession behavior.

### Implementation Pattern Hints

During implementation, recalled outcomes can suggest focused tests and risk
areas without expanding the approved manifest scope.

Examples:

- schema work should test unknown fields, exact enum values, timestamp parsing,
  and round-trip serialization;
- indexing work should test stale indexes, missing manifest directories,
  inactive archives, custom status filters, and malformed index data;
- workflow documentation should assert lifecycle placement and contract
  boundary language.

These hints are not permission to skip red phase, broaden scope, or avoid the
declared validation commands. They are historical evidence for choosing better
tests and cleaner implementation paths.

### Review Checklist Generation

`outcome.review_notes` records what implementation review found. Future reviews
can recall those notes to build a targeted checklist for similar work.

For example, Outcome indexing work recorded review findings around inactive
archive recursion, missing manifest directories, undeclared downstream edits,
supersession metadata loss, malformed index acceptance, and stale custom-filter
handling. A reviewer working near Outcome indexing or manifest-chain code should
actively check those risks again.

### Fragile Area Heatmap

Aggregating `lessons[].paths`, `lessons[].tags`, and review severities can show
which areas repeatedly need care. If the same module, tag, or warning pattern
appears across multiple completed outcomes, it may deserve additional tests,
cleanup, validation hardening, documentation, or a follow-up draft manifest.

### Test Pattern Library

Outcome lessons form a lightweight library of test patterns that survived
implementation and review. Lesson types such as `schema-hardening`,
`loader-safety`, `chain-semantics`, `command-integrity`, and `documentation`
can be recalled when similar behavior is planned again.

The useful unit is not just the lesson summary. It is the combination of lesson
type, tags, paths, review notes, and validation evidence that explains why the
pattern mattered.

### Self-Improvement Backlog Feed

Recurring Outcome evidence should feed the MAID self-improvement loop:

- repeated validation lessons can route to validator hardening work;
- repeated performance lessons can route to performance optimization drafts;
- repeated review warnings in one module can route to cleanup or refactor
  drafts;
- repeated workflow confusion can route to documentation or agent-skill
  updates.

The signal should stay evidence-backed. One useful lesson may guide planning,
but repeated lessons or repeated review findings are stronger candidates for
new draft manifests.

### Agent Skill Loop Closure

Agent skills should consume Outcome records without becoming the source of
truth for Outcome semantics:

- planners recall related outcomes before drafting when an index is available;
- implementers consult related outcomes for test and code pattern evidence
  while staying inside the approved manifest scope;
- plan reviewers check whether relevant recalled outcomes are reflected in the
  draft when available;
- implementation reviewers check whether completed work needs a new or updated
  `outcome` section after the review verdict is ready;
- self-improvement workflows route recurring Outcome lessons into appropriate
  future draft queues.

This closes the cycle: completed manifests teach future manifests, but every
new manifest still carries its own behavioral contract.

### Release And Process Intelligence

Outcome summaries and validation evidence can improve release notes, monthly
work summaries, and project-health reports because they describe the completed
behavior and the proof that closed the contract. Over time, Outcome data can
also support process metrics such as:

- how often review finds warnings before final approval;
- which lesson types recur;
- which modules repeatedly need hardening;
- which validation commands are most relied on;
- whether completed manifests consistently capture Outcome data.
