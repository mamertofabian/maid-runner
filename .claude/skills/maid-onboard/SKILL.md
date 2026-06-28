---
name: maid-onboard
description: Bring the current repository up to full MAID adoption, or refresh a repo that was onboarded before plan-lock/verify existed. Detects how the repo invokes maid-runner (a scripts/maid wrapper, uvx, or a project dependency), runs `maid init` for the agents in use (Claude and/or Codex) so skills/agents/config are installed as repo-local files, reconciles stale hand-written MAID guidance in CLAUDE.md/AGENTS.md, verifies the payload is clean, and stops for explicit commit approval. Use when asked to "set up MAID here", "onboard this repo to MAID", "bring this repo up to full MAID", "refresh MAID tooling", "fix stale MAID setup", or "the repo isn't running maid verify / plan lock".
---

# MAID Onboard

Make a repository use MAID Runner to the full, self-contained and not dependent
on user-level skills. This skill installs/refreshes the repo-local MAID payload
and aligns the repo's guidance docs with the current plan-lock/verify workflow.

## Why this exists

`maid init` installs MAID skills, agents, config, and a marked guidance section
as **repo-local files**. A repo that never ran init (or ran an old version)
silently falls back to stale **user-level** skills (`~/.claude/skills`,
`~/.codex/skills`) and to a hand-written CLAUDE.md/AGENTS.md that predates
`maid plan lock` and `maid verify`. The result: the repo skips plan-lock, the
verify handoff gate, and other current workflow steps. This skill closes that
gap. Per-repo install is the isolation model — never rely on user-level skills.

## Rules

- NEVER auto-commit. Run quality checks, show the diff, and stop for explicit
  approval (the user's commit policy is strict).
- `maid init` is non-destructive to user content: skills/agents are written as
  files, `settings.json` hooks are merged, and CLAUDE.md/AGENTS.md change only
  inside the `<!-- BEGIN MAID RUNNER -->` / `<!-- END MAID RUNNER -->` markers.
- Use `--force` to refresh a repo that is already initialized.
- Do not stage gitignored payload (`.claude/insights/`, `.claude/settings.local.json`,
  `.maid/outcomes.json`).
- If anything is ambiguous (which agents to install, whether to reconcile
  authored docs), ask rather than guess.

## Phase 1 — Detect the maid invocation (install style)

Repos run maid-runner in different ways. Determine `<maid>` — the command this
repo uses — in this order:

1. **Repo wrapper:** if `scripts/maid` (or `scripts/maid.cmd` / `scripts/maid.ps1`)
   or an npm script wrapping `scripts/maid-runner.js` exists, use it. These
   typically run `uvx --from "maid-runner[all]@latest" maid` and need no install.
2. **uvx, no project dependency:** if there is no wrapper and maid-runner is not
   a project dependency, use `uvx --from "maid-runner[all]@latest" maid`
   (pinnable via `MAID_RUNNER_SPEC`). Requires `uv`.
3. **Project dependency:** if maid-runner is in `pyproject.toml` / lockfile, use
   `uv run maid`.

Confirm it works: `<maid> --version` and `<maid> plan --help` (the latter
confirms plan-lock support, i.e. a current enough maid-runner). Use `<maid>` for
every command below.

## Phase 2 — Survey current state

```bash
ls .maidrc.yaml manifests 2>/dev/null
ls .claude/skills .codex/skills 2>/dev/null     # existing repo-local payload?
ls CLAUDE.md AGENTS.md 2>/dev/null               # guidance files present?
```

Classify the repo:
- **Fresh adopt** — no `manifests/` / `.maidrc.yaml`.
- **Stale refresh** — has MAID but no `.claude/skills`/`.codex/skills` (relying
  on user-level fallback), or guidance docs predate plan-lock/verify.
- **Current** — already has repo-local skills referencing plan-lock/verify.

Decide which agents to install. Default to **both Claude and Codex** (the user
uses them interchangeably). Narrow only if the user says so, or install just the
one whose guidance file (CLAUDE.md / AGENTS.md) exists when only one is present.

## Phase 3 — Make the maid-runner version current

The repo can only install the current payload if its maid-runner is current.

- **Wrapper / uvx (`...@latest`):** already current on next run; nothing to do
  unless a version is pinned via `MAID_RUNNER_SPEC` or the wrapper — bump it if a
  needed fix is newer.
- **Project dependency (path/editable):** `uv sync --reinstall-package maid-runner`
  (or `uv sync`) so the venv reflects current source.
- **Project dependency (pinned PyPI):** the repo only gets fixes that are
  published. If a needed fix is unreleased, tell the user it requires publishing
  maid-runner (or temporarily using the wrapper/uvx); do not fake it.

For a **fresh adopt**, recommend the wrapper pattern (a `scripts/maid` that runs
`uvx --from "maid-runner[all]@latest" maid`) as the most portable default —
cross-platform, no project-dependency footprint, auto-updates from PyPI.

## Phase 4 — Preview the payload (dry run)

For each chosen agent:

```bash
<maid> init --tool claude --force --dry-run
<maid> init --tool codex  --force --dry-run
```

Sanity-check before installing:
- Codex must list **only generic** skills (`maid-planner`, `maid-plan-review`,
  `maid-implementer`, `maid-implementation-review`, `maid-auditor`,
  `maid-outcome-enrich`) — **no**
  `maid-runner-*` or `maid-validate-hardening`. If repo-internal skills appear, the maid-runner in
  use is stale (return to Phase 3) — do not pollute the repo.
- Claude lists its generic skills + the implementation-reviewer agent.

## Phase 5 — Install

```bash
<maid> init --tool claude --force    # if using Claude Code
<maid> init --tool codex  --force    # if using Codex
```
(Omit `--force` only on a truly fresh adopt where nothing exists yet.)

## Phase 6 — Reconcile stale guidance docs

`maid init` adds/updates only the marked section. A repo onboarded before
plan-lock/verify usually also has a **hand-written** MAID section describing the
old flow (e.g. ending at `make check`, with no `maid plan lock` or
`maid verify`). Find it and reconcile:

- Read CLAUDE.md / AGENTS.md. If a hand-written MAID workflow omits plan-lock and
  the verify gate, update it: add the `maid plan lock` step (after approval,
  before implementation) and the `maid verify --require-plan-lock
  --require-red-evidence` handoff step, and state that the installed skills are
  the authoritative workflow.
- Keep edits minimal and faithful; preserve project-specific content. Do not
  touch the marker-delimited section (init owns it).

## Phase 7 — Verify

```bash
<maid> validate                            # should pass for existing manifests
ls .codex/skills 2>/dev/null               # only the 6 generic skills, including maid-auditor and maid-outcome-enrich
grep -c "maid-runner-" AGENTS.md 2>/dev/null   # expect 0
```

Confirm: skills/agents installed as real files, no repo-internal skills leaked
into a distributed repo, validation still green, guidance docs consistent.
Also verify the `maid init` installed guidance includes the Outcome learning-digestion workflow: related Outcome evidence should be digested by
naming applicable lessons, rejecting stale or irrelevant lessons with a reason,
and stating what changed because of the evidence, while preserving the advisory
boundary that recall, insights, and digested Outcomes do not replace MAID
gates.

## Phase 8 — Hand off for commit (do not auto-commit)

Run the repo's quality gate if present (`make check`, or lint/type/test), show
`git status` and the doc diffs, and summarize what changed. Stage the payload
(`.claude/`, `.codex/`, `.maidrc.yaml`, updated CLAUDE.md/AGENTS.md) but **stop
and ask for explicit approval** before committing. For a project-dependency repo
built from a local path, remind the user that durability across fresh clones
depends on publishing maid-runner (or pinning to the released version).

## Optional — refresh the user-level fallback

The user-level `~/.codex/skills` / `~/.claude/skills` are the global fallback for
any repo not yet onboarded and may be stale. Mention this once; offer to
re-sync them from the current maid-runner payload, but treat per-repo init as
the supported path.

## Full usage reminder

After onboarding, "using MAID to the full" per change is: `maid-planner` →
approve → run
`maid recall --for-manifest manifests/drafts/<slug>.manifest.yaml --plan-packet`
before promoting the selected draft when completed Outcomes exist →
`maid plan lock` (red evidence) →
`maid manifest promote manifests/drafts/<slug>.manifest.yaml` → implement →
`maid validate --mode implementation` →
`maid verify --require-plan-lock --require-red-evidence` → review →
capture `outcome:` + `maid learn`. Optionally wire `maid verify` / SARIF into CI.
Recall is advisory planning context only; it does not expand scope or replace
red evidence, behavioral validation, plan lock, implementation validation, or
review.
