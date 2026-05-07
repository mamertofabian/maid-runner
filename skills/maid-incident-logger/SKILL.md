---
name: maid-incident-logger
description: Record curated MAID gaming or implementation-drift incidents as chosen/rejected examples for future review, hooks, or DPO datasets. Use when the user asks to log a MAID incident, capture a model gaming pattern, save a chosen/rejected pair, or prepare DPO training material.
---

# MAID Incident Logger

Create a human-curated incident record. Do not auto-infer that every mistake is DPO-worthy.

## Storage

Write incidents under:

```text
~/.maid/incidents/
```

Use a filename like:

```text
YYYYMMDD-HHMMSS-<repo-or-topic>.md
```

## Required Metadata

Each incident must include:

- `schema: maid-incident.v1`
- `timestamp`
- `repo`
- `manifest`
- `llm_alias`
- `model_details` when known
- `incident_type`
- `dpo_candidate`

Use the active model name or user-provided model alias for `llm_alias`. If unknown, write `unknown` rather than guessing.

## Incident Body

Record these sections:

- Rejected behavior: what the model did or proposed.
- Chosen behavior: the preferred correction.
- Why rejected: the architectural, testing, or MAID-contract reason.
- Why chosen: why the clean path is preferable.
- Visible context: what context was available to the model.
- Notes: reviewer judgment, uncertainty, or follow-up hook ideas.

## DPO Curation Rules

Mark `dpo_candidate: true` only when:

- the rejected and chosen paths solve the same immediate task
- the chosen path was visible from the model's context
- the rejected behavior is a recurring or likely recurring pattern
- the preference is about architecture/process quality, not just a typo

Mark `dpo_candidate: false` when the model lacked necessary context, the task was ambiguous, or the issue was a one-off bug.

## Template

```markdown
---
schema: maid-incident.v1
timestamp: ""
repo: ""
manifest: ""
llm_alias: ""
model_details: ""
incident_type: "private-access|schema-loosening|test-gaming|scope-drift|plan-drift|other"
dpo_candidate: false
---

# MAID Incident

## Rejected Behavior


## Chosen Behavior


## Why Rejected


## Why Chosen


## Visible Context


## Notes

```
