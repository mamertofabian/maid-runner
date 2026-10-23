# CLAUDE.md

@AGENTS.md

## Claude Code

Claude Code reads `CLAUDE.md`, not `AGENTS.md`; this file imports the shared
repo guidance from `AGENTS.md` so Claude and Codex follow the same current
instructions without duplicating them.

Keep this file focused on Claude-specific behavior. Long MAID reference
material belongs in docs and skills so Claude's startup instructions stay
specific, concise, and consistent.

## MAID Skills Workflow

When available, use the installed Claude MAID skills as the primary workflow:

- `maid-planner`: create or revise the manifest and behavioral tests.
- `maid-plan-review`: review the manifest and tests before implementation.
- `maid-implement-draft`: resume a `manifests/drafts` child through lock,
  promote, implement, review, and Outcome capture.
- `maid-implementer`: implement only within approved manifest scope.
- `maid-implementation-review`: review changed files, artifacts, tests, and
  validation before handoff.
- `maid-evolver`: intentionally change an existing manifest contract.
- `maid-auditor`: check active manifests for regressions and drift.
- `maid-incident-logger`: capture useful MAID workflow drift or gaming examples.

The repo-level Claude payload also includes the
`maid-implementation-reviewer` agent for independent implementation review.

Repo-specific maid-runner skills (under `.claude/skills/`):

- `maid-runner-draft-implement`: implement `manifests/drafts` children as a
  batch through promotion, validation, and review.
- `maid-runner-self-improvement`: synthesize lessons into a prioritized
  self-improvement backlog and draft queues.
- `maid-validate-hardening`: audit `maid validate` / `maid verify` for
  anti-gaming loopholes.
- `maid-runner-cleanup-and-refactor`: audit for cleanup and safe-refactor work.
- `maid-runner-performance-optimization`: profile and queue speedups.

## Claude Role (this repo)

Claude Code is the primary agent in this repository. By default, Claude runs
the full single-agent MAID lifecycle described in `AGENTS.md`: draft or evolve
the manifest, write behavioral tests, confirm the red phase, plan-review,
`maid plan lock`, `maid manifest promote`, implement within scope, validate,
run the implementation review gate below, and capture Outcome.

- When continuing from `manifests/drafts/*.manifest.yaml`, use
  `maid-implement-draft` (or `maid-runner-draft-implement` for batches).
- Use the `maid-planner` skill's **Planning Handoff Mode** (stop after the
  draft and adversarial self-review, emit a handoff packet) only when the user
  explicitly asks for a handoff to another agent.
- The optional multi-agent split in `AGENTS.md` remains available; any agent
  can play any role.

## Claude Implementation Review Gate

`AGENTS.md` ("MAID Review-Fix-Ready Loop") requires an independent read-only
review before handoff. Standing authorization: for MAID implementation review
in this repository, the user explicitly authorizes Claude to spawn the required
read-only reviewer subagent without a separate per-turn approval.

Claude equivalents of the Codex mechanics in `AGENTS.md`:

- `fork_context=false` → spawn a fresh agent with the Agent tool, never
  `subagent_type: "fork"`, so the reviewer does not inherit the implementation
  transcript.
- `agent_type=explorer` → `subagent_type: "maid-implementation-reviewer"`
  (read-only tools). If it is unavailable, use a general-purpose agent with the
  same read-only packet.
- Leave `model` and `effort` unset so the reviewer inherits from the main agent.
- `close_agent` → not needed; the reviewer ends when it returns its verdict.
  Do not reuse a prior reviewer via SendMessage for a re-review; spawn a fresh
  one with an updated packet.

Pass only the verdict-neutral review packet defined in `AGENTS.md`, and exclude
prior review lineage and coordinator-owned follow-up state.

## MAID Workflow Anchors

For new features, bug fixes, and refactors, follow the shared MAID workflow in
`AGENTS.md` — see its "MAID Plan-Lock Lifecycle" and "MAID Review-Fix-Ready
Loop" sections for the plan-lock, draft-promotion, handoff-gate, and Outcome
capture requirements. This file does not restate them, to keep a single
source of truth.

Keep these release-tested anchors discoverable here:

- The planning loop ends with `maid plan lock <manifest>`, and the
  implementation handoff must not proceed until
  `maid verify --summary --require-plan-lock --require-red-evidence` passes.
  Prefer `--summary` for agent and human handoff because it keeps blocking
  failures visible while deduplicating warning storms; rerun with raw text,
  `--json`, `--packet`, or SARIF only when exhaustive machine-readable detail
  is needed. Treat older handoff examples such as
  `maid verify --require-plan-lock --require-red-evidence` as superseded unless
  raw text is intentionally required.
- `maid manifest promote` migrates the promoted manifest's plan lock; use
  `maid plan revise` for intentional contract changes instead of recreating
  evidence.
- MAID manifests carry a self-describing comment header. Agents may include it
  when writing manifests directly, but `maid plan lock`, `maid plan revise`,
  and `maid manifest promote` backfill it automatically as an advisory step.
- `E707` / `RED_EVIDENCE_COMMAND_MISMATCH` means red-phase evidence no longer
  matches the manifest validation commands and must be fixed before handoff.
- `E708` / `PLAN_LOCK_SCOPE_WIDENED` is non-blocking. It reports deliberate
  fail-closed widening after changed-scope baseline resolution; reconcile the
  named manifests or pass an explicit baseline if the wider scope was not
  intended.

## References

- `docs/maid_specs.md`: complete MAID methodology and manifest details.
- `docs/agent-skills.md`: current MAID skill distribution and sync notes.
- `docs/draft-manifest-workflow.md`: draft promotion workflow.
- `docs/manifest-outcome-records.md`: Outcome record requirements.
- `docs/unit-testing-rules.md`: testing standards for this repo.

Documents in `./.claude/conversations` are experimental conversation history,
not source-of-truth project guidance.
