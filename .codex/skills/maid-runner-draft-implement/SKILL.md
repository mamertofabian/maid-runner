---
name: maid-runner-draft-implement
description: Use when implementing maid-runner MAID draft manifests from manifests/drafts, promoting them into manifests, and validating implementation batches with review before handoff.
---

# maid-runner Draft Implement

Use this skill when continuing implementation of approved maid-runner draft
manifests. The goal is to refine a draft if needed, promote it into active
`manifests/`, implement within the manifest scope, validate the promoted path,
and run a read-only implementation review before handoff.

## Skill Coordination

Use this skill as the maid-runner batch wrapper, not as a replacement for the
general MAID skills:

- Use `maid-plan-review` before implementation when a draft's behavioral tests
  are weak, non-behavioral, or inconsistent.
- Use `maid-implementer` for the actual manifest-scoped implementation flow.
- Use `maid-evolver` before changing or adding public artifacts in a file that
  an already-promoted manifest owns.
- Use `maid-implementation-review` before final handoff.
- Spawn the read-only review subagent without a full-history fork:
  `fork_context=false`, `agent_type=explorer`, model `gpt-5.5`, and
  `reasoning_effort=medium`. Pass an explicit review packet instead of
  inheriting the implementation transcript. If the local Codex agent registry
  does not expose an `explorer` role, omit `agent_type` and use the default
  role with the same read-only packet.
- Close each review subagent after consuming its verdict by calling
  `close_agent`, whether the verdict is ready, needs changes, or needs
  discussion.

## Start

1. If the automation prompt lists selected draft manifest(s), treat that list
   as authoritative. Otherwise pick the next implementable child draft from
   `manifests/drafts/*.manifest.yaml`; ignore `*.epic.yaml`.
2. Read the draft manifest, its declared files, and its behavioral tests.
3. Run the draft's focused validation command before editing and confirm the
   red phase is meaningful.
4. Restate the manifest `temptations` before editing.

## Automation-Selected Scope

When invoked by `tools/codex_maid_loop.py`, implement only the
automation-selected draft manifest(s) listed in the prompt for that pass.
Do not promote unselected draft manifests, delete unselected draft files, or
implement future drafts early. If the selected draft cannot be completed
without first implementing a different draft, stop with BLOCKED or
NEEDS_CHANGES instead of broadening scope.

## Promotion Procedure

For each approved and implemented draft:

1. Move `manifests/drafts/<slug>.manifest.yaml` to
   `manifests/<slug>.manifest.yaml`.
2. Rewrite downstream promoted manifest `read:` references from
   `manifests/drafts/<dependency>.manifest.yaml` to
   `manifests/<dependency>.manifest.yaml`.
3. Validate the promoted path, not only the draft path:

```bash
maid validate manifests/<slug>.manifest.yaml --mode behavioral
maid validate manifests/<slug>.manifest.yaml --mode implementation
uv run python -m pytest -q <declared focused tests>
maid validate
maid test
```

4. Confirm no stale references to the deleted draft path remain:

```bash
rg "manifests/drafts/<slug>.manifest.yaml" manifests manifests/drafts
```

## Implementation Rules

- Keep edits inside the promoted manifest's `files.create`, `files.edit`, and
  narrow allowed `files.read` call-site/test coverage.
- Do not edit behavioral tests to weaken the contract.
- Do not make compiler-backed validation the default path unless the promoted
  manifest explicitly requires it. Preserve fast parser/path-backed validation
  where it is sufficient.
- Do not hide broken behavior with fake, stale, placeholder, or silently
  fallback data.
- If a manifest-contract problem appears, stop for a plan revision instead of
  editing around it.

## Review Loop

Before reporting done, run a read-only implementation review subagent scoped to
the promoted manifest, current diff, changed files, and validation output. The
review must check:

- changed files stayed within manifest scope;
- declared artifacts exist without undeclared public drift;
- behavioral tests are meaningful and still match the manifest;
- validation commands passed on the promoted path;
- no draft references remain stale after promotion;
- compiler-backed code remains bounded and does not slow default validation
  without a manifest-backed reason.

Fix valid findings, rerun focused validation, and re-review until ready. If
subagents are unavailable, perform the same read-only review locally and say so
explicitly.

## Automation Reporting

When this skill is invoked by `tools/codex_maid_loop.py`, end with exactly one
status line:

```text
AUTOMATION_STATUS: READY
AUTOMATION_STATUS: NEEDS_CHANGES
AUTOMATION_STATUS: BLOCKED
AUTOMATION_STATUS: NO_DRAFTS
```

Use `READY` only when the implementation is ready for the outer script to ask
for commit approval. Include this commit packet when ready:

```text
AUTOMATION_COMMIT_MESSAGE: <conventional commit message>
AUTOMATION_COMMIT_FILES:
- <path>
- <path>
AUTOMATION_STATUS: READY
```

Include every changed tracked, deleted, and untracked file that belongs in the
commit. The outer loop prompts for fresh typed approval by default, unless the
user started it with `--auto-commit`.
