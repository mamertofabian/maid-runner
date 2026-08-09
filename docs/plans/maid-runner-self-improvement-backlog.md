# MAID Runner Self-Improvement Backlog

Initial audit: 2026-07-02 on v2.19.1. Baseline refresh: 2026-08-08 on
`release/v2.next` at v2.25.0 (`3056009`). Cross-repository feedback trial:
2026-08-09 on the same branch at v2.25.0 (`b00843d`), with a clean worktree
before this documentation update. The July evidence is retained below for
history; the refresh section and routed backlog are authoritative for next
work.

## Purpose

This document is the post-June-10 audit of MAID Runner as a whole system. On
2026-06-10 the improvement roadmap epics 061-071 were drafted
(`88810ea`, `bc8564d`); this audit reviews everything that landed since then
(v2.17.0 → v2.19.1), verifies which planned work is consumed versus still open,
triages the fifteen `~/.maid/bug-report/` entries filed since June 14, and
routes the confirmed findings into prioritized, implementation-sized themes.

It is written as a takeover packet: another AI agent should be able to pick up
MAID planning and implementation from this file alone, following the repo
workflow in `AGENTS.md` (plan-lock lifecycle, draft promotion, review-fix-ready
loop). This backlog plans only; every code change below still requires its own
draft manifest, behavioral tests, red phase, plan lock, and implementation
review.

## 2026-08-08 Refresh

Current health is strong: `maid validate --quiet` passed, all 228 deduplicated
`maid test --json` commands passed, and `maid verify --profile handoff` passed
all eight applicable stages in 166 seconds (clean-tree `changed_scope` skipped)
with only two known non-blocking E307 warnings. The remaining opportunities are
therefore bounded trust, lifecycle, and planning-hygiene gaps rather than a
general regression.

### R1. Reconcile strict-delta with the real strict-default dogfood gate

- **Priority / lane:** P0, validation trust.
- **Evidence:** Current `uv run maid validate --strict-delta --json` passes with
  `strict_delta: []` across 498 manifests. The parked
  `feat/062-04-strict-default-flip` branch records the opposite result after
  making the same strict gates default: broad E710 artifact-execution failures
  and E900 validate-command failures. Its `plan-revision.md` explicitly blocks
  Outcome and release. The current branch still contains the clean delta, and
  the parked branch still contains the failed flipped-default evidence.
- **Why it matters:** Migration tooling currently provides false confidence:
  an empty delta does not prove that the future default run will pass.
- **Owner:** `maid-validate-hardening`, then `maid-evolver` for the existing
  062 contracts.
- **Closure shape:** Add a 062 follow-up child that first pins the mismatch as a
  behavioral reproduction, determines whether strict-delta omits a gate,
  changes gate composition, or invokes commands under different defaults, and
  makes an empty delta equivalent to a passing flipped-default dogfood run.
  Do not resume or merge 062-04 until both checks agree and pass.
- **Acceptance:** the reproduction fails before the fix; strict-delta contains
  every newly failing E710/E900 identity; an empty delta implies default-flip
  validate and verify pass; legacy/default semantics remain unchanged before
  the flip.

### R2. Make stale theme-map errors staleness-first

- **Priority / lane:** P1, developer experience with validation-trust impact.
- **Evidence:** After `maid learn` refreshed 211 Outcomes, the stale
  `.maid/outcomes-digest.json` was correctly reported stale, but
  `maid insights --theme-map .maid/outcomes-digest.json` exited 2 with
  `unknown lesson_type 'plan-lock-maintenance'`. In
  `maid_runner/cli/commands/insights.py`, full theme-map validation runs before
  `digest_is_stale`, so stale source vocabulary can mask the actionable
  refresh instruction. Plain `maid insights` succeeds.
- **Why it matters:** Planner and self-improvement skills deliberately fall
  back on stale digests; a misleading integrity error makes normal staleness
  look like corrupted current Outcome data.
- **Owner:** `maid-evolver` for the active theme-map contract.
- **Closure shape:** Check digest fingerprint staleness before validating
  current-index lesson identities unless the user explicitly allows a stale
  digest; retain full fail-closed validation for fresh or explicitly allowed
  digests.
- **Acceptance:** a stale digest with obsolete lesson types reports only the
  staleness remedy; a fresh fabricated digest still fails identity validation;
  `--allow-stale-digest` still validates before applying the map.

### R3. Archive consumed or rejected planning epics

- **Priority / lane:** P1, MAID workflow.
- **Evidence:** Before this pass, four draft epics said `status: planning`:
  062, 064, 085, and the newly opened 096 performance roadmap. All seven 085
  children are promoted and carry completed Outcomes, so 085 is consumed. The
  daemon's 064-01 default-routing experiment
  failed its benchmark gate and 064-05 was abandoned; the delivered cache,
  protocol, transports, and client children have completed Outcomes. Only 062
  remains legitimately open because R1 and 062-04 are unresolved. The 096
  roadmap remains live pending fresh post-096-01 artifact-coverage measurements.
- **Why it matters:** Stale planning records repeatedly cause takeover agents
  to reopen completed work and make the draft inventory untrustworthy.
- **Owner:** `maid-evolver`.
- **Closure shape:** Archive 085 as consumed. Close 064 as
  infrastructure-delivered/default-routing-rejected unless a fresh benchmark
  shows a material win; do not revive archived 064 children without that data.
- **Acceptance:** only 062 and 096 remain planning; archive pointers list their
  completed or rejected children and schema validation passes.

### R4. Refresh specialist backlogs against v2.25

- **Priority / lane:** P2, documentation and portfolio hygiene.
- **Evidence:** The cleanup backlog still describes a May 31 tree, and the
  hardening backlog still describes a May 29 threat model. Both predate plan
  locks, knockout evidence, scope hooks, strict preview/delta, coverage-risk
  recommendations, verify profiles, and the July/August bug-fix wave.
- **Owner:** `maid-runner-cleanup-and-refactor` and
  `maid-validate-hardening` respectively.
- **Acceptance:** every previously open item is re-probed on v2.25, closed
  items cite their manifest, and only current reproductions remain prioritized.

### R5. Surface shared-test plan-lock dependents and recovery commands

- **Priority / lane:** P2, developer experience and MAID workflow.
- **Evidence:** A privacy-bounded `maid feedback export` from an isolated copy
  of the completed `maid-validator-csharp` Outcome for
  `distinguish-csharp-overloads` produced feedback ID
  `b19b5f29aa8cf3c17196a5d8f75d01449f57144c1a7a435cb4a14776c9ffdb7f`.
  `maid feedback aggregate` retained one advisory workflow record while
  omitting repository identity and paths. The source repository was not
  changed because no downstream Outcome had yet opted into export.
- **Current reproduction:** In a scratch v2.25 project, two active locked
  manifests both referenced `tests/test_shared.py`. Adding one assertion made
  both `maid plan status` commands exit 1 as `TAMPERED`; repository verify
  emitted one E701 per manifest. `maid manifests tests/test_shared.py`
  reported no references because that query indexes writable paths, not
  read-only behavioral dependencies.
- **Why it matters:** Per-manifest evidence must remain independent, but a
  shared full-suite test can invalidate many otherwise unchanged locks. Agents
  currently discover and repair the fan-out manually, which encourages missed
  historical locks or ad hoc hash edits.
- **Owner:** `maid-evolver` for the active plan-lock and summary-output
  contracts.
- **Closure shape:** Add a read-only shared-test dependency view and group E701
  summary guidance by changed test path. Report every affected active manifest
  and an exact per-lock `maid plan revise` recovery command; do not mutate
  locks automatically, infer that evidence is preservable, or include
  superseded manifests.
- **Acceptance:** a two-lock shared-test fixture reports both dependents and
  both recovery commands; a superseded lock is excluded; JSON/SARIF retain
  per-manifest diagnostics; no command revises evidence without an explicit
  operator invocation and the existing preservation checks.

The former batching probe is closed: compatible pytest and Vitest batching is
covered by `batch-compatible-maid-test-command-groups`,
`038-19-extract-test-command-batching`, and focused pnpm/Vitest batching tests;
parallel independent command groups landed in 046-01. No new batching draft is
warranted without a fresh downstream reproduction.

## What Landed Since 2026-06-10 (context for takeover)

All of the following are implemented, promoted under `manifests/`, and covered
by Outcome records (the initial audit saw 102 records in `.maid/outcomes.json`
via `maid learn`; 082-01..06 added six more manifest Outcomes):

- **061 manifest authoring & brownfield onboarding** (consumed/archived):
  `maid manifest from-diff`, validate-command suggestion, bootstrap adoption
  ranking, brownfield onboarding docs.
- **062 strict-by-default validation gates**: preview, delta, pytest-config
  hardening, and migration inventory landed; the default flip remains blocked
  by R1 — see Theme 6 and the 2026-08-08 refresh.
- **063 validator plugin distribution** (consumed/archived): entry-point
  discovery, `maid validators` listing, conformance kit, authoring docs.
- **064 daemon-first agent validation** (partially open): daemon-resident
  validation cache, verify protocol, TCP transport, client API and diagnostic
  command. Children 064-01 (route CLI validate through daemon) and 064-05
  (benchmark & default daemon auto) were **archived after the benchmark gate
  failed or their dependency was abandoned**; the 064-00 epic remains planning
  and needs an honest benchmark-gated closure decision — see Theme 7.
- **065 CI-native SARIF reporting** (consumed/archived): diagnostics registry
  export, SARIF output for validate/verify, GitHub Actions wiring, CI docs.
- **066 outcome recall planning integration** (consumed/archived):
  `maid recall` manifest-derived queries, planning recall packet, skill and
  init-payload sync.
- **067 plan locks & red-phase evidence** (consumed/archived by Theme 8):
  tamper-evident `maid plan lock|revise|status`,
  red-evidence capture, `--require-plan-lock` / `--require-red-evidence` in
  verify, task-window scoping, E707 command cross-check, handoff baseline fix,
  `--preserve-red-evidence`.
- **068 behavioral constraint evidence** (consumed/archived): artifact
  execution coverage gate, knockout harness, verify wiring.
- **069 edit-time scope hooks** (consumed/archived): `maid task` active
  manifest commands, hook scope-check command, init payload wiring.
- **070 structured retry packets** (consumed/archived): error-code registry
  with repair recipes, failure packets, bounded retry loop.
- **071 gaming incident flywheel** (consumed/archived): incident storage and
  capture, DPO export, temptation suggestions.
- **073-076 workflow fixes**: plan-lock migration on draft promotion,
  Outcome-before-ready gate, outcome index refresh after capture, init payload
  alignment, stash-backed `plan revise --stash-implementation` (076-01..03).
- **077 outcome learning loop in skills** (consumed/archived by Theme 8):
  auditor insights cadence, learning-loop guidance, related-match recall
  scoring, init payload sync.
- **078-080**: quiet-validate test-command caching, versioned init instruction
  payloads, CLI help text fill.
- **081 outcome LLM enrichment** (consumed/archived by Theme 8): deterministic
  enrichment core + `maid enrich`, theme maps in `maid insights`,
  `maid-outcome-enrich` skill, quality hardening, planner theme-map preference.
- **082 self-improvement trust fixes** (completed by Themes 1-5 and 8):
  honest warning-summary labels, clean-tree `changed_scope` skip, dirty
  `files.read` stash-revise support, manifest-visible E310 default-hook
  acknowledgments, proportionate E307 no-validator diagnostics, and archived
  consumed 067/077/081/084 epics.
- **verify summary** (`6cb3107`): `maid verify --summary` deduplicated output;
  now the preferred handoff command per `AGENTS.md`.
- **Brownfield validator fixes** from the June 24-27 bug-report burst: Claude
  scope-check hook envelopes (`874ec86`), nested TS assertion scanning
  (`740bde8`), Svelte 5 props collection (`3ec80cc`), scope-only files as
  tracked inventory (`6e0875c`, `59ac5d3`), `maid test` fast-only (`b38e963`),
  Python skill-script E200 identity (`5456463`), TS object-return stub
  detection (`3b90dde`).

## Current Evidence Reviewed

- `uv run maid validate --quiet`: exit 0, silent. Healthy.
- `uv run maid test`: all commands PASS.
- Initial audit evidence recorded `uv run maid verify --summary` as **FAIL**
  because `changed_scope` E115 blocked on a clean release tree with no baseline;
  Theme 2 closed that defect in `082-02`.
- Initial audit evidence recorded `uv run maid verify --summary --keep-going`
  with **392 raw / 147 unique warnings** dominated by E307/E310 noise; Themes 4
  and 5 closed the identified dogfood false positives/noise policy issues.
- `uv run maid learn` + `uv run maid insights`: 102 Outcome records indexed;
  top tags `outcome-records` (22), `anti-gaming` (17).
- Cross-repository feedback trial on 2026-08-09: one explicitly selected
  `maid-validator-csharp` workflow lesson exported and aggregated locally, then
  reproduced against v2.25 as two E701 failures from one shared test edit (R5).
- Fifteen bug reports under `~/.maid/bug-report/` dated 2026-06-14 through
  2026-07-01, cross-checked against fix commits (dates verified with
  `git log`). The two still-open items from the initial audit were closed by
  `082-02` and `082-03`.
- Pending insights in `.claude/insights/review/2026/07/01/` on E210 handling
  and the misleading warning-summary label were closed by Theme 1
  (`082-01`).
- Epic drafts under `manifests/drafts/` header-checked: 061/063/065/066/067/
  068/069/070/071/077/081/084 archived; 062/064 still `status: planning`.
  Theme 8 closed the stale consumed epic planning records under
  `manifests/082-06-archive-consumed-post-067-epics.manifest.yaml`.
- Specialist backlog freshness: hardening backlog last touched 2026-05-29,
  cleanup backlog 2026-05-31 (both predate the 061-081 waves); performance
  backlog 2026-06-27 (current).
- Memory-tracked issues re-verified: Codex distributable-skills pollution is
  fixed (`f15e0a4`, `scripts/sync_claude_files.py` `CODEX_DISTRIBUTABLE_SKILLS`,
  `tests/test_agent_payload_distribution.py`); `maid-plan-review` ships in
  `maid_runner/codex/skills/`.

## Prioritized Improvement Themes

### 1. Fix the misleading "non-blocking" warning-summary label

- **Status:** Completed by
  `manifests/082-01-honest-blocking-warning-summary-label.manifest.yaml`.
- **Outcome:** `maid verify --summary` now distinguishes warning-driven
  blocking stages from advisory warnings, removes the misleading
  `non-blocking` label when warnings drove a failed stage, and exposes the
  same attribution in summary JSON.
- **Primary lane:** Correctness (CLI reporting).
- **Initial evidence (tier 1, closed):**
  `~/.maid/bug-report/20260701-125513-life-dashboard-verify-warnings.md`;
  insights `2026-07-01_16-11_fix-misleading-warning-summary-label` and
  `..._maid-runner-e210-warning-handling`. Before `082-01`,
  `maid_runner/cli/commands/_format.py:380` printed
  `WARNINGS (non-blocking, deduplicated N -> M):` unconditionally.
- **Symptom:** Under strict verify policy, E210/E310-class warnings can drive
  `FAIL behavioral`, yet the summary labels the same warnings "non-blocking".
  In life-dashboard this made a policy-correct failure look like a validator
  bug and generated a bug report.
- **Why it matters:** The verify summary is now the canonical handoff surface;
  a dishonest label undermines exactly the trust it was built to provide.
- **Owner:** `maid-evolver` (evolve `manifests/add-verify-summary-output.manifest.yaml`).
- **Closure shape:** When any failed stage is warning-driven, change the label
  (e.g. `WARNINGS (deduplicated N -> M; some warnings are blocking under
  verify policy):`) or split blocking-contributing warning groups from advisory
  ones. Do **not** change the strict policy itself — it is intentional and
  test-covered. Document `--advisory` as the brownfield escape hatch.
- **Acceptance criteria:** a behavioral test where a warning-driven stage
  failure produces a label that does not say "non-blocking"; existing
  summary-format tests updated; `maid verify --summary` output on a
  warning-clean failure unchanged.
- **Size/risk:** small / low.

### 2. Make `changed_scope` skip visibly instead of failing bare `maid verify`

- **Status:** Completed by
  `manifests/082-02-changed-scope-visible-skip-on-clean-tree.manifest.yaml`.
- **Outcome:** Bare `maid verify` now reports the default `changed_scope` stage
  as visibly skipped on clean trees when no baseline is resolvable, while dirty
  trees, explicit `--changed-scope`, and explicit baselines still fail closed.
- **Primary lane:** Developer experience (verify defaults).
- **Initial evidence (tier 1, closed):** On the clean release tree before
  `082-02`, `uv run maid verify --summary` exited FAIL:
  `E115 --changed-scope requires --since, --base-ref, or metadata.maid_task_base`.
  The July 1 life-dashboard report shows real users cycling through
  `--since HEAD` / `--no-changed-scope` to get around the same failure.
- **Symptom:** The documented handoff command cannot pass on a clean tree or
  release branch without extra flags, so "verify fails" is ambiguous between
  real problems and missing-baseline configuration.
- **Why it matters:** A health probe that always fails trains agents to add
  bypass flags reflexively — the opposite of what an anti-gaming gate wants.
- **Owner:** `maid-validate-hardening` (this changes an enforcement stage's
  default posture; needs adversarial review). Note: the explicit-baseline
  requirement is deliberate contract from
  `manifests/037-01-add-task-baseline-changed-scope-gate.manifest.yaml`
  ("MAID will not guess main, dev, or a remote branch") — change it via
  `maid-evolver` on that contract, not as an incidental fix.
- **Closure shape:** When no baseline is resolvable **and** the worktree is
  clean, report `changed_scope` as a visible SKIPPED stage (with the reason)
  instead of a blocking FAIL; keep the fail-closed E115 whenever the tree is
  dirty or any `--changed-scope`-strengthening flag was passed explicitly.
  Alternative if review rejects auto-skip: keep FAIL but add a first-class
  documented baseline for release trees. Decide in plan review, not ad hoc.
- **Acceptance criteria:** clean-tree verify passes with a visible
  `SKIPPED changed_scope (no baseline; clean tree)` line; dirty-tree behavior
  unchanged (still E115); JSON/SARIF outputs represent the skip explicitly;
  adversarial test proving a dirty tree cannot ride the skip path.
- **Size/risk:** small-medium / medium (touches verify gate semantics).

### 3. Let `plan revise --stash-implementation` handle dirty `files.read` wiring paths

- **Status:** Completed by
  `manifests/082-03-stash-revise-files-read-wiring-paths.manifest.yaml`.
- **Outcome:** Stash-backed plan revision now includes manifest-declared
  non-test `files.read` wiring edits when a manifest also has a contracted
  writable implementation file, while unrelated dirt and scope-only context
  files are still refused.
- **Primary lane:** MAID workflow (red-evidence recapture).
- **Initial evidence (tier 1, closed):**
  `~/.maid/bug-report/20260630-182412-life-dashboard-maid-plan-revise-files-read.md`.
  Before `082-03`, `_cmd_plan_revise_with_stashed_implementation`
  (`maid_runner/cli/commands/plan.py:271`) builds targets from
  `manifest.all_writable_paths`, which (`maid_runner/core/types.py`) covers
  create/edit/delete/snapshot/scope but **not** `files.read`. The June 29
  sibling report was only fixed for scope-only files (`8bd90cc`).
- **Symptom:** Manifests that follow the documented touched-but-uncontracted
  wiring pattern (e.g. SvelteKit `+page.svelte` under `files.read`) cannot
  recapture red evidence after a review-driven contract change; the verify gate
  then reports E707 `RED_EVIDENCE_COMMAND_MISMATCH` with no sanctioned path
  forward.
- **Why it matters:** This blocks the exact workflow (review → revise → fresh
  red evidence) that 067/076 built, and it recurred twice in two days in a real
  downstream repo.
- **Owner:** `maid-validate-hardening` for the contract decision (red-evidence
  integrity is at stake), then evolve `manifests/076-01-add-stash-backed-plan-revise.manifest.yaml`.
- **Closure shape:** treat manifest-declared `files.read` dirty paths as stash
  **targets** (they are implementation edits that must be hidden during red
  capture), not merely allowed dirt. Keep refusing genuinely undeclared dirty
  paths. Consider whether unbounded `files.read` stashing weakens the
  anti-gaming posture (files.read is cheap to declare) — if so, bound it to
  paths that appear in the manifest with an explicit wiring rationale, and say
  so in the error message.
- **Acceptance criteria:** reproduction from the bug report passes; undeclared
  dirty paths still refused; E707 no longer forced in the wiring scenario;
  adversarial test that a contracted-artifact file cannot masquerade as
  read-only wiring to dodge red capture.
- **Size/risk:** small-medium / medium.

### 4. Stop E310 flagging intentional base-class default hooks as stubs

- **Status:** Completed by
  `manifests/082-04-exempt-documented-default-hooks-from-e310.manifest.yaml`.
- **Outcome:** Intentional default hooks are acknowledged with manifest-visible
  `default_hook: true` artifacts and E310 suppression is keyed to exact active
  manifest declarations instead of a hardcoded whitelist.
- **Primary lane:** Validation trust (heuristic precision).
- **Initial evidence (tier 1, closed):** before `082-04`, every verify run on
  this repo emitted E310 x7 for `BaseValidator.module_path`, `.resolve_reexport`,
  `.get_test_function_bodies`, `.generate_test_stub`
  (`maid_runner/validators/base.py:128-184`). Reading the code confirms these
  are documented template-method default hooks (`return None` / `{}` / `""`)
  that subclasses override — not stubs. Same false-positive class as the fixed
  TS object-return case (`3b90dde`, report 20260627-150713).
- **Symptom:** 28 recurring false warnings on the runner's own verify output;
  under strict verify policy E310 warnings can block downstream repos with the
  same pattern.
- **Why it matters:** Dogfooded false positives teach agents to ignore E310,
  which is exactly the stub-detection signal the anti-gaming design needs to
  stay credible.
- **Owner:** `maid-validate-hardening` (bounded syntactic rule per the
  Validator Hardening Constraints in `AGENTS.md` — no control-flow modeling).
- **Closure shape:** a narrow, documented exemption: method in a class, with a
  docstring, whose trivial return is a documented default **and** at least one
  subclass in the project overrides it — or, if override detection is too
  broad, an explicit per-artifact acknowledgment in the manifest (e.g.
  `default_hook: true`) so the exemption is contract-visible rather than
  heuristic. Prefer the contract-visible form; silent heuristics grow.
- **Acceptance criteria:** clean verify on this repo emits zero E310 for
  `validators/base.py`; a real stub (bare `pass` / `NotImplementedError`
  without the exemption) still flags; the exemption is documented in the error
  registry repair recipe.
- **Size/risk:** small-medium / medium (anti-gaming surface).

### 5. Tame the E307 "no validator available" warning storm

- **Status:** Completed by
  `manifests/082-05-proportionate-e307-no-validator-policy.manifest.yaml`.
- **Outcome:** Recognized non-code files now emit E307 as info, retain
  per-file JSON/SARIF diagnostics, and collapse into one summary INFO group;
  unsupported source-like files remain warnings.
- **Primary lane:** Developer experience (signal-to-noise).
- **Initial evidence (tier 1, closed):** before `082-05`, verify on this clean
  tree reported 392 raw / 147 unique warnings; the overwhelming majority were
  E307 for declared `.md`,
  `.toml`, `.json`, `.gitignore`, `.cjs` files (skill payloads, docs,
  pyproject). The summary dedup (`6cb3107`) mitigated but did not resolve it.
- **Symptom:** Real warnings (like Theme 4's E310) sit inside 140+ lines of
  noise; downstream repos see the same storm.
- **Why it matters:** Warning fatigue is the failure mode summary output was
  built to prevent; 147 unique warnings still exceeds what an agent will read.
- **Owner:** `maid-validate-hardening` (it is a policy boundary: which files
  deserve a "cannot validate" warning at all).
- **Closure shape (decide in plan review):** (a) downgrade E307 to info for
  recognized non-code extensions while keeping it a warning for source-like
  files with no validator; or (b) a presence-only validator for doc/config
  files so declaring them is checkable without noise; or (c) collapse all E307
  into one summary group with a count. Keep the fail-loud principle: the
  information must remain visible, just proportionate.
- **Acceptance criteria:** clean-tree verify summary warning list fits in one
  screen; E307 still appears (in whatever downgraded/grouped form) so nothing
  is silently hidden; SARIF/JSON consumers still receive per-file records.
- **Size/risk:** small-medium / low-medium.

### 6. Execute epic 062: strict-by-default validation gates

- **Primary lane:** Validation trust (roadmap execution).
- **2026-08-08 status:** Partially completed. Children 062-01, 062-02,
  062-03, and 062-05 are promoted with completed Outcomes. The remaining
  062-04 flip is blocked by R1: strict-delta is empty while the parked flipped
  default branch fails its dogfood gate.
- **Evidence (tier 2):** `manifests/drafts/062-00` and children 062-01..04 are
  fully drafted and untouched since June 10 — the only June 10 epic with zero
  children landed. The July 1 verify-warnings confusion is live evidence of
  the migration pain 062-02 (`--strict-preview`) and 062-03 (strict migration
  delta report) were designed to absorb.
- **Symptom:** Strictness arrived piecemeal (verify treats warnings as
  blocking) without the preview/delta tooling, so downstream brownfield repos
  experience policy as surprise.
- **Why it matters:** 062 is the bridge between "gates exist" (067/068 landed)
  and "gates are on by default without revolt".
- **Owner:** `maid-runner-draft-implement` for 062-01..04. The previous
  062-04 hold condition is now satisfied because Themes 1, 2, 4, and 5 have
  landed; still promote the children in order after re-validating each draft
  against the current tree.
- **Next action:** re-validate the four child drafts against the current tree
  (they predate waves 063-081; artifact and path assumptions may have
  drifted), revise via `maid plan revise` where stale, then promote 062-01
  first.
- **Size/risk:** medium / medium.

### 7. Close the daemon epic 064 with a benchmark-gated decision

- **Primary lane:** Performance.
- **2026-08-08 status:** Still open as planning hygiene. No later evidence
  reverses the failed 064-01 benchmark; absent a fresh measured win, archive
  the epic as infrastructure-delivered/default-routing-rejected.
- **Evidence (tier 2):** 064-02/03/04/06 landed; 064-01 was archived after
  failing its benchmark gate (`0f8651c`); 064-05 was archived as an
  abandoned-draft-manifest because it depended on 064-01. The 064-00 epic still
  has `status: planning` and requires any future child to restate the benchmark
  gate. Initial audit evidence put verify with tests on this repo at ~97s.
- **Symptom:** The daemon exists (cache, protocol, transports, client API) but
  nothing defaults to it, so the investment currently yields no routine
  speedup.
- **Why it matters:** Either the daemon becomes the default fast path with
  measured wins, or the epic should be closed honestly as
  infrastructure-delivered/auto-default-rejected — leaving it half-open invites
  unbenchmarked "just route it" work, which 064-01 already proved wrong.
- **Owner:** `maid-runner-performance-optimization`.
- **Next action:** run the benchmark-gated epic closure decision: measure
  daemon-backed verify/validate on this repo plus one reference project, then
  either plan a new default-routing child only if there is a measured win or
  archive 064-00 honestly with the benchmark evidence in its Outcome.
- **Size/risk:** medium / medium.

### 8. Archive consumed epics and make draft inventory truthful again

- **Primary lane:** MAID workflow (planning hygiene).
- **Status:** Completed by
  `manifests/082-06-archive-consumed-post-067-epics.manifest.yaml`.
- **Evidence (tier 1):** epic files 067-00, 077-00, 081-00 previously carried
  `# draft-kind: epic` / `status: planning` although every planned child was
  promoted and implemented. They now follow the 043-03 archive pattern
  (`# archive-kind: consumed-draft-epic`, `status: archived`) and point to
  their promoted child manifests. Also: two active manifests share the ID
  prefix `072-01-*` (`disable-cli-option-abbreviation` and
  `quiet-legacy-created-chain-warnings`) — keep avoiding that collision in
  future draft numbering.
- **Why it matters:** This backlog's own predecessor documented (Theme 3,
  2026-05) that stale planning inventory creates false priorities; the same
  drift re-accumulated within three weeks. Takeover agents will re-open
  consumed epics.
- **Owner:** `maid-evolver` (completed; active `files.read` references were
  checked before rewriting, per the 043-03 lesson).
- **Acceptance criteria:** every fully-consumed epic under `manifests/drafts/`
  is an archive pointer; only 062, 064, and 096 remain `planning`; schema-mode
  validation passes; next new draft wave starts at **082** to avoid collisions.
- **Size/risk:** small / low.

### 9. Refresh the stale specialist backlogs

- **Primary lane:** Documentation.
- **2026-08-08 status:** Still open and now more stale; see R4.
- **Evidence (tier 1):** `docs/plans/maid-validate-hardening-backlog.md`
  last touched 2026-05-29 and `docs/plans/maid-runner-cleanup-refactor-backlog.md`
  2026-05-31 — both predate plan locks, knockout gates, scope hooks, retry
  packets, and the incident flywheel, so their threat models and cleanup maps
  describe a system that no longer exists. The performance backlog
  (2026-06-27) is current.
- **Owner:** `maid-validate-hardening` and `maid-runner-cleanup-and-refactor`
  respectively, as the opening step of their next audits (markdown-only,
  no manifest needed per repo policy).
- **Acceptance criteria:** each backlog states what the 061-081 waves already
  closed, and its open items are re-verified against the current tree.
- **Size/risk:** small / low.

### 10. Verify multi-command test batching for same-runner commands

- **Primary lane:** Performance.
- **2026-08-08 status:** Closed by the existing compatible pytest/Vitest
  batching contracts and tests plus 046-01 parallel command-group execution.
- **Evidence (tier 3, stale-but-plausible):**
  `~/.maid/bug-report/20260625-200358-erindelle-maid-test-playwright-batching.md`
  had two halves: slow E2E in the fast gate (fixed by `b38e963`,
  fast-only `maid test`) and two separate Playwright invocations where one
  batched run was expected (no fix commit found). Batching still matters for
  `maid test --all` and the verify tests stage (~87s of the 97s keep-going run).
- **Owner:** `maid-runner-performance-optimization`.
- **Next action:** a probe, not a draft — reproduce whether identical-runner
  commands across manifests are batched in `maid test --all`/verify; only
  draft if the reproduction shows redundant runner startup with measurable
  cost.
- **Size/risk:** probe: small.

## Routed Backlog

Priority order for the next agent (rationale: false-green/false-fail trust
issues first, then correctness of daily workflow, then roadmap execution,
then hygiene):

1. R1 — reconcile strict-delta with the flipped-default dogfood gate before
   resuming 062-04 (`maid-validate-hardening`, then `maid-evolver`).
2. R2 — make theme-map rejection staleness-first while preserving fresh-map
   integrity checks (`maid-evolver`).
3. R3 — archive consumed 085 and close 064 honestly against its failed
   benchmark (`maid-evolver`; performance re-probe only if default routing is
   reconsidered).
4. R4 — refresh hardening and cleanup specialist backlogs against v2.25.
5. R5 — add a read-only shared-test lock-dependency view and grouped E701
   recovery guidance without automatic lock mutation (`maid-evolver`).

Completed:

- Theme 1 — completed by `082-01`.
- Theme 2 — completed by `082-02`.
- Theme 3 — completed by `082-03`.
- Theme 4 — completed by `082-04`.
- Theme 5 — completed by `082-05`.
- Theme 8 — completed by `082-06`; consumed epics 067/077/081/084 are archived.
- Theme 10 — compatible batching and parallel command groups are implemented
  and covered; no current reproduction remains.

Sequencing note: do not resume the parked 062-04 implementation merely because
its migration prerequisites shipped. R1 is a current release blocker: reconcile
the empty strict-delta with the failing flipped-default dogfood evidence first.

## Specialist Follow-Ups

- `maid-validate-hardening` owns R1 and should refresh its stale specialist
  backlog while investigating the strict-delta/default-flip mismatch.
- `maid-runner-performance-optimization` should only reopen daemon default
  routing if a fresh benchmark can overturn 064-01's negative result. The old
  batching probe is closed.
- `maid-runner-cleanup-and-refactor` has no confirmed current findings from
  this audit; its next audit should start from a fresh code scan plus its
  refreshed backlog, not from this document.
- The June 24-27 brownfield burst (7 reports, all fixed in days) shows the
  bug-report → narrow-fix → regression-test loop working; keep routing
  language-validator edge cases through it rather than building broader static
  analysis (see Validator Hardening Constraints in `AGENTS.md`).
- `maid-evolver` owns R5 because it extends active plan-lock and verify-summary
  behavior. Keep the first slice read-only; batch lock revision needs a
  separate trust review if it is ever proposed.

## Draft Manifest Candidates

Created and completed:

- `082-01-honest-blocking-warning-summary-label` (Theme 1; completed).
- `082-02-changed-scope-visible-skip-on-clean-tree` (Theme 2; completed).
- `082-03-stash-revise-files-read-wiring-paths` (Theme 3; completed).
- `082-04-exempt-documented-default-hooks-from-e310` (Theme 4; completed).
- `082-05-proportionate-e307-no-validator-policy` (Theme 5; completed).
- `082-06-archive-consumed-post-067-epics` (Theme 8; completed).

Remaining manifest work:

- Add a bounded 062 follow-up child for R1 after the hardening owner identifies
  the exact mismatch; do not broaden 062-04 itself before that reproduction is
  pinned.
- Add a narrow R2 fix draft evolving the active theme-map contract.
- Archive the consumed 085 epic and close 064 against its recorded benchmark
  decision. Do not revive 064-05 as a live child.
- Add a narrow R5 developer-experience draft after choosing whether the public
  entry point is a new plan subcommand or an extension of an existing query.
  Pin dependency discovery and grouped guidance only; automatic multi-lock
  revision is explicitly out of scope.

Every candidate must follow the full lifecycle: draft → behavioral tests →
red phase → `maid validate --mode behavioral` → plan review → `maid plan lock`
→ `maid manifest promote` → implement → implementation review → Outcome →
`maid learn`.

## Speculative Ideas (no drafts until a probe confirms)

- **Payload staleness surfacing:** 079-01 versioned init payloads; a
  `maid verify` advisory or doctor-style check could warn downstream repos
  when installed skill payloads lag the package version (memory:
  life-dashboard ran stale guidance for weeks). Needs a design decision on
  where the check lives.
- **Brownfield characterization corpus:** distill the June bug-report
  reproductions (Svelte 5 props, nested TS assertions, skill-script identity)
  into a versioned fixture corpus run in CI, so validator changes are checked
  against real downstream shapes. Medium effort; propose only if validator
  churn continues.
- **Enrichment adoption loop:** 081 landed `maid enrich` + theme maps; no
  evidence yet on whether theme-mapped insights change planner behavior
  downstream. Revisit after a few weeks of Outcome data.
- Carried over: productized Layer 3/4 orchestrator
  (`docs/maid-philosophy-and-vision.md`) — still needs `feature-spec-architect`
  first; editor/LSP integration — still lower priority than trust items.

## Verification Notes

Commands run on 2026-08-09 for the cross-repository feedback trial:

- `maid learn` over an isolated copy of one completed
  `maid-validator-csharp` Outcome — indexed 1 record.
- `maid feedback export` — exported 1 explicitly marked workflow lesson and
  emitted the required inspection notice.
- `maid feedback aggregate` — accepted 1 unique bundle and produced 1 advisory
  record with `reported_source_count: 1`.
- Scratch shared-test reproduction: both `maid plan status` invocations exited
  1 with the same test mismatch; `maid verify --summary --require-plan-lock
  --no-changed-scope --keep-going` exited 1 with two E701 diagnostics.
- `maid manifests tests/test_shared.py` returned no references, confirming the
  current writable-only query cannot discover read-only shared behavioral
  dependencies.

Commands run on 2026-08-08 against `release/v2.next` @ `3056009` (v2.25.0),
clean tree:

- `uv run maid validate --quiet` — exit 0, silent.
- `uv run maid test --json` — 228/228 commands passed; the main batched pytest
  command completed in about 110 seconds.
- `uv run maid verify --profile handoff` — PASS; 8 stages passed, clean-tree
  `changed_scope` skipped, 2 unique non-blocking E307 warnings, 166 seconds.
- `uv run maid validate --strict-delta --json` — PASS across 498 manifests;
  `strict_delta: []`.
- `uv run maid learn` — indexed 211 Outcomes. The enrichment digest was stale;
  plain `uv run maid insights` succeeded with 190 completed records.
- `uv run maid insights --theme-map .maid/outcomes-digest.json` — exit 2 with
  `unknown lesson_type 'plan-lock-maintenance'` after the digest had already
  been identified as stale, confirming R2's error-precedence gap.
- Schema validation passed for the planning epics 062, 064, and 085 and for the
  existing 062-04 draft.

Commands run on 2026-07-02 against `main` @ `e5e24ca` (v2.19.1), clean tree:

- `uv run maid validate --quiet` — exit 0, no output.
- `uv run maid test` — all listed commands PASS.
- `uv run maid verify --summary` — FAIL: 1 blocking (`changed_scope` E115),
  6 stages passed, 147/392 warnings, 10s.
- `uv run maid verify --summary --keep-going` — FAIL: same blocking stage,
  7 stages passed (adds `tests`), 97s.
- `uv run maid learn` then `uv run maid insights` — 102 records;
  `outcome-records` (22) and `anti-gaming` (17) dominate.
- `uv run maid --version` — 2.19.1.
- Code reads verified: `_format.py:376-387` (Theme 1),
  `plan.py:271-342` + `core/types.py` `all_writable_paths` (Theme 3),
  `validators/base.py:128-184` (Theme 4).
- Takeover update: 082-01..06 were created, implemented, reviewed, and
  completed after the initial audit. Drafts 062-01..04 must be re-validated by
  their owning skill before promotion; 064-05 is archived and must not be
  promoted.
