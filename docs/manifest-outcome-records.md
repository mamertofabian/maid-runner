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
