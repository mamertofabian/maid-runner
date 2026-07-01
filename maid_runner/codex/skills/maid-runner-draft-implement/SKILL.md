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
- This skill has standing explicit user authorization from repo `AGENTS.md` to
  spawn read-only reviewer subagents for the MAID review gate. Do not require a
  separate per-turn subagent approval.
- Spawn the read-only review subagent without a full-history fork:
  `fork_context=false`, `agent_type=explorer`, and leave reviewer model and
  reasoning effort unset so they inherit from the main agent. Pass an explicit
  review packet instead of inheriting the implementation transcript. If the
  local Codex agent registry does not expose an `explorer` role, omit
  `agent_type` and use the default role with the same read-only packet.
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

## Packet-Driven Retry Gates

For implementer retries, run validation gates with `--packet`; for example,
`maid validate --packet` and `maid verify --packet`. When a packet-aware gate fails, read `.maid/last-failure-packet.json` instead of re-exploring the repository. The packet is the retry context: failed command argv, exit code, project root, failed manifest excerpts, diagnostics, `next_action` repair recipes, failed-command output tails, and environment versions.

Respect `next_action` exactly. Valid kinds include `edit-implementation`,
`edit-tests`, `edit-manifest`, `run-command`, `revise-plan`, and
`escalate-human`; kinds that change tests or manifests route through explicit
plan revision when the contract must change. Recipes never authorize weakening tests or manifests to silence errors, and they never authorize weakening tests or manifests as the first remedy for an implementation failure.

Stop at the default 5 attempt bound. If the gate still fails, or the packet
requests `escalate-human`, stop and escalate to a human with the final packet
instead of looping, hiding the failure, or broadening scope.

## Outcome-Aware MAID Guidance

Outcome records are deterministic manifest data, not agent-only memory. When
available, use `maid learn`, `maid recall`, and `maid insights` as explicit
historical evidence for the current draft pass.

- Before promoting a draft, use deterministic Outcome recall when a learned index is available.
- Consult recalled Outcome records when choosing focused tests and code patterns.
- Use `maid insights` only to identify recurring lesson patterns that may need
  future manifests, not to expand this manifest's implementation scope.
- Recalled outcomes are planning evidence only and do not replace behavioral tests, declared scope, validation, or review.

## Automation-Selected Scope

When invoked by `tools/codex_maid_loop.py`, implement only the
automation-selected draft manifest(s) listed in the prompt for that pass.
Do not promote unselected draft manifests, delete unselected draft files, or
implement future drafts early. If the selected draft cannot be completed
without first implementing a different draft, stop with BLOCKED or
NEEDS_CHANGES instead of broadening scope.

## Promotion Procedure

For each approved draft selected for implementation:

1. Confirm the planning loop already created an approved plan lock before
   promotion:

```bash
uv run maid plan lock manifests/drafts/<slug>.manifest.yaml
```

If the lock is missing after implementation has begun or tests are already
green, stop and report a workflow gap. Do not create after-the-fact red
evidence.

2. Promote the draft with the sanctioned command so the lock, self-referencing
   validate-command paths, and red evidence migrate together:

```bash
uv run maid manifest promote manifests/drafts/<slug>.manifest.yaml
```

Do not manually move or copy draft manifests.

After promotion and before implementation edits, start the active task so hook
integrations can check writes against the promoted contract:

```bash
uv run maid task start manifests/<slug>.manifest.yaml
```

Interactive editor sessions use the default fail-open policy: no active task
and internal hook errors allow the edit. Locked-down autonomous loops should
pass `--strict` to deny those outcomes. The hook is advisory edit-time
infrastructure only. maid verify changed-scope checks remain the authoritative handoff evidence.
Hook decisions do not replace validation or add `ErrorCode` entries.

3. If promotion warns that other active manifests still reference the draft
   path, report the warning and handle those references through their own
   approved manifest or plan-revision path. Do not broaden the selected draft
   scope.
4. Validate the promoted path, not only the draft path:

```bash
maid validate manifests/<slug>.manifest.yaml --mode behavioral
maid validate manifests/<slug>.manifest.yaml --mode implementation
uv run python -m pytest -q <declared focused tests>
maid validate
maid test
```

5. Confirm no stale references to the deleted draft path remain:

```bash
rg "manifests/drafts/<slug>.manifest.yaml" manifests manifests/drafts
```

6. Run the plan-lock handoff gate and treat E700/E704/E705 on the promoted
   manifest as workflow blockers, not as evidence to fabricate after green
   implementation:

```bash
uv run maid verify --summary --require-plan-lock --require-red-evidence
```

Prefer `--summary` for agent and human handoff because it keeps blocking
failures visible while deduplicating warning storms. Rerun without `--summary`,
or with `--json`, `--packet`, or SARIF, only when exhaustive machine-readable
detail is needed. Treat older handoff examples such as
`uv run maid verify --require-plan-lock --require-red-evidence` as superseded
unless raw text is intentionally required.

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

Before reporting done, spawn a read-only implementation review subagent scoped
to the promoted manifest, current diff, changed files, and validation output.
Do not substitute a local-only review because the current turn did not mention
subagents; repo `AGENTS.md` provides standing authorization. The review must
check:

- changed files stayed within manifest scope;
- declared artifacts exist without undeclared public drift;
- behavioral tests are meaningful and still match the manifest;
- validation commands passed on the promoted path;
- no draft references remain stale after promotion;
- compiler-backed code remains bounded and does not slow default validation
  without a manifest-backed reason.

Fix valid findings, rerun focused validation, and re-review until ready. Fall
back to local-only review only when the subagent tool is technically unavailable
or the user explicitly disables subagents for that turn.

## Outcome Capture

Capture Outcome after implementation review and before final handoff. Once the
latest review verdict is ready, update the promoted manifest with an
evidence-backed `outcome:` section that records status, summary, rationale,
review notes, validation evidence, and any lessons.

Do not report READY when Outcome is missing. Use `AUTOMATION_STATUS: READY`
only after the promoted manifest has the `outcome:` section, unless the final
response explicitly reports why Outcome is not applicable or is blocked.
After Outcome capture, run `uv run maid learn` to refresh the local `.maid/outcomes.json` advisory index for subsequent recall.
`.maid/outcomes.json` is generated and ignored; do not commit it. If `maid learn` fails, report the refresh failure as advisory unless recall or insights are required for the current task.
After Outcome capture, run `uv run maid task stop` to clear the active task
pointer before handoff.

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
