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
- `maid-implementer`: implement only within approved manifest scope.
- `maid-implementation-review`: review changed files, artifacts, tests, and
  validation before handoff.
- `maid-evolver`: intentionally change an existing manifest contract.
- `maid-auditor`: check active manifests for regressions and drift.
- `maid-incident-logger`: capture useful MAID workflow drift or gaming examples.

The repo-level Claude payload also includes the
`maid-implementation-reviewer` agent for independent implementation review.

## MAID Workflow Anchors

For new features, bug fixes, and refactors, follow the shared MAID workflow in
`AGENTS.md` — see its "MAID Plan-Lock Lifecycle" and "MAID Review-Fix-Ready
Loop" sections for the plan-lock, draft-promotion, handoff-gate, and Outcome
capture requirements. This file does not restate them, to keep a single
source of truth.

## References

- `docs/maid_specs.md`: complete MAID methodology and manifest details.
- `docs/agent-skills.md`: current MAID skill distribution and sync notes.
- `docs/draft-manifest-workflow.md`: draft promotion workflow.
- `docs/manifest-outcome-records.md`: Outcome record requirements.
- `docs/unit-testing-rules.md`: testing standards for this repo.

Documents in `./.claude/conversations` are experimental conversation history,
not source-of-truth project guidance.
