# Agent Skills for MAID Workflow

## Overview

Four AI agent skills that operationalize the MAID methodology across the complete development lifecycle. Each skill is a self-contained prompt definition that guides an AI agent through a specific phase of contract-driven development.

### The Four Skills

| Skill | Phase | Question It Answers |
|-------|-------|---------------------|
| `maid-planner` | Create | "What are we building?" |
| `maid-implementer` | Execute | "Make it work." |
| `maid-evolver` | Evolve | "We need to change the plan." |
| `maid-auditor` | Verify | "Did anything break?" |

### Lifecycle

```
maid-planner    →  maid-implementer    →  maid-auditor
    │                    │                    │
    │                    │                    └── regression detected
    │                    │                        │
    │                    └───────────┐            ▼
    │                                ▼      maid-evolver
    └────────────────────────────  evolve ──────┐
                    ▲                           │
                    └───────────────────────────┘
                              repeat
```

---

## Tool Packaging

The canonical, versioned copies of these skills live in this repo under `skills/`.

The core skill payload is tool-agnostic:

- `SKILL.md` — the trigger metadata plus the operating procedure
- Optional `scripts/`, `references/`, or `assets/` only when the workflow genuinely needs them

Tool-specific packaging can then be layered on top of that core:

- **Codex:** may add `agents/openai.yaml` for UI-facing metadata such as `display_name`, `short_description`, and `default_prompt`
- **Claude Code:** can use the `SKILL.md` directly and does not require `agents/openai.yaml`

This keeps the methodology and workflow documentation reusable across tools while still allowing Codex-specific metadata where it improves discoverability.

### Recommended Distribution Pattern

1. Edit the source-of-truth skill under `skills/<name>/`
2. Keep `SKILL.md` focused on the reusable procedure, not tool-specific UI metadata
3. Add tool-specific metadata files only for the tools that need them
4. Copy or adapt the skill folder into the target tool's install location as needed

---

## Skills

### maid-planner

**Location:** `skills/maid-planner/SKILL.md`

**Purpose:** Replace free-form markdown planning with machine-checkable manifest contracts.

**Workflow:**
1. Analyze the project (structure, existing manifests, tests, conventions)
2. Ask up to 5 clarifying questions
3. Draft a manifest in `manifests/<slug>.manifest.yaml`
4. Draft behavioral tests that USE every declared artifact
5. Run `maid validate --mode behavioral` — iterate until it passes
6. Present for user approval

**Key insight:** The plan IS the contract. No translation step. The manifest is structured (YAML with JSON Schema), machine-validatable, and durable (checked on every future validation run).

**Works for:** Greenfield projects (new files, `files.create`) and brownfield projects (existing files, `files.edit` + `files.read`). The planner analyzes what exists and declares the delta.

---

### maid-implementer

**Location:** `skills/maid-implementer/SKILL.md`

**Purpose:** Implement code against an approved manifest, following the behavioral tests as the primary guide.

**Workflow:**
1. Load the approved manifest (read-only — never modify during implementation)
2. Load all `files.read` dependencies — this is the complete context
3. Implement against the behavioral tests (not the manifest directly)
4. Run `maid validate --mode implementation` (structural check)
5. Run `maid test --manifest <slug>` (behavioral check)
6. Iterate until both pass
7. Optional refactoring (private code only, no manifest change needed)
8. Run full integration validation: `maid validate` + `maid test`

**Key rules:**
- Only load files declared in the manifest. Never touch unlisted files.
- If the manifest is wrong, stop — do not work around it.
- Private implementation is free. Public API is frozen to the manifest.

**Error recovery paths:**
- **Manifest is wrong:** Stop, flag it, suggest `maid-planner` revision
- **Tests are wrong:** Stop, flag them, suggest `maid-planner` revision
- **Missing prerequisite:** `git stash` → fix prerequisite (separate manifest) → `git stash pop` → continue

---

### maid-evolver

**Location:** `skills/maid-evolver/SKILL.md`

**Purpose:** Intentionally change an existing manifest contract — rename, modify, remove, or split artifacts.

**Core decision: chain merge vs. supersede.**

| Change Type | Path | Old Manifest | New Manifest Declares |
|-------------|------|-------------|-----------------------|
| Add new artifact | Chain merge | Stays active | Only the new artifact |
| Add optional arg (backward compatible) | Chain merge | Stays active | Updated signature |
| Rename artifact | Supersede | Archived | ALL current artifacts |
| Change signature (breaking) | Supersede | Archived | ALL current artifacts |
| Remove artifact | Supersede | Archived | ALL remaining artifacts |
| Move between files | Supersede | Archived | ALL artifacts at new location |

**Decision rule:** If the old artifact must stop existing, you MUST supersede. Chain merging is additive only — it combines artifacts from all active manifests. It cannot remove or rename.

**Supersede consequences (must be understood before proceeding):**
1. The old manifest is completely excluded from validation
2. The old manifest's `validate` commands stop running
3. The new manifest must declare the COMPLETE current state (transition pattern)
4. The new manifest's `validate` commands must cover all behavioral tests
5. Dependent manifests may need updating

**Workflow:**
1. Identify the affected manifest: `maid manifests <file-path>`
2. Classify the change (addition vs. alteration)
3. Create new manifest (chain merge or supersede)
4. Update behavioral tests
5. Check dependent manifests: `maid coherence`
6. Validate: structural, behavioral, integration, coherence

---

### maid-auditor

**Location:** `skills/maid-auditor/SKILL.md`

**Purpose:** Audit the entire codebase against all active manifests to detect regressions, broken contracts, and architectural drift.

**Read-only skill.** Never modifies code, manifests, or tests.

**Workflow:**
1. Run full validation sweep: `maid validate`, `maid test`, `maid coherence`
2. Analyze results for each manifest:
   - **TRACKED** — validates, tests pass, contract healthy
   - **REGRESSION** — was valid before, now fails, code broke a past contract
   - **PENDING** — manifest exists, implementation incomplete
   - **DRIFT** — code changed without manifest update
   - **SUPERSEDED** — archived, not checked
3. Check file tracking: UNDECLARED, REGISTERED, TRACKED
4. Generate audit report with prioritized recommendations

**Usage patterns:**
- **Before release:** "Are we clean?" — full audit, ship if green
- **After large refactor:** "Did I break anything?" — focused regression check
- **Periodic health check:** "How's MAID coverage?" — trend data over time
- **Brownfield onboarding:** "How much is covered?" — UNDECLARED → TRACKED progress

**Key insight:** Manifests are durable regression detectors. Unlike markdown plans that decay, a manifest declared last week still validates against today's code. Every `maid validate` checks that statement against reality.

---

## Lessons Learned

### The Adoption Bottleneck

**Problem:** The original MAID workflow asked users to commit to an entire methodology before seeing value. "Learn MAID, write manifests, follow the workflow" is a high barrier.

**Solution:** Start with planning. AI agents already produce plans before coding. The skill replaces unstructured markdown plans with structured manifest plans. The user gets better planning immediately — the methodology reveals itself through use, not through documentation.

**Principle:** People adopt tools that improve their current workflow, not methodologies they must learn first.

---

### Manifests Are Durable, Markdown Is Disposable

**Problem:** Traditional markdown plans are written once and never checked again. They decay the moment the code changes.

**Solution:** Manifests are validated on every `maid validate` run. A manifest declared last week serves as a regression detector today. If someone renames a method, the manifest catches it — it checks the AST, not a human's memory.

**Principle:** A contract that isn't enforced is not a contract. Machine-checkable > human-readable for durability.

---

### Behavioral Tests Define the Boundary

**Problem:** Without behavioral tests, the manifest only declares structure (what exists) but not behavior (what it does). The AI agent has freedom but no guidance.

**Solution:** The planner skill produces both the manifest AND behavioral tests. The behavioral validation (`--mode behavioral`) verifies that tests actually USE every declared artifact via AST analysis. If the manifest declares `AuthService.login()` but no test calls it, validation fails.

**Principle:** Structure without behavior is a skeleton. Behavior without structure is ungrounded. Both are required.

---

### Chain Merge Is Additive, Supersede Is Replace

**Problem:** Not all changes are equal. Adding a method is cheap; renaming one is expensive. The methodology needed to distinguish between them.

**Solution:** The evolver skill classifies every change:
- **Additions** (new artifacts, backward-compatible changes) use chain merge — cheap, old contract stays alive
- **Alterations** (renames, removals, breaking changes) use supersede — expensive, old contract dies, complete state must be declared

**Principle:** The right tool depends on the change. One size does not fit all.

---

### Supersede Has a Cost

**Problem:** Superseding a manifest kills its regression detection. The old tests stop running. The old structural checks stop executing.

**Solution:** The evolver skill makes this cost explicit before proceeding. The user must understand that superseding replaces the entire contract for that file, and the new manifest must be comprehensive.

**Principle:** Every architectural decision has a cost. Make it visible.

---

### Brownfield Onboarding Is Incremental

**Problem:** The original approach assumed full project coverage from the start. Brownfield projects resist big-bang migration.

**Solution:** Each manifest covers one slice. That slice is protected forever. Over time, coverage grows. The auditor reports progress (UNDECLARED → REGISTERED → TRACKED). No big-bang needed.

**Principle:** Incremental adoption beats all-or-nothing. Each manifest adds value immediately, not at the end.

---

### Error Recovery Must Be Explicit

**Problem:** AI agents tend to work around problems rather than stopping. A wrong manifest leads to wrong code, which leads to wrong tests, which creates an illusion of correctness.

**Solution:** The implementer skill has explicit stop conditions: wrong manifest → stop, wrong tests → stop, missing prerequisite → stash and fix separately. Never work around a broken contract.

**Principle:** A broken contract upstream corrupts everything downstream. Stop early.

---

## Remaining Gaps

### 1. Multi-Manifest Coordination

**Gap:** When a single change affects multiple manifests (e.g., renaming a type used across 5 modules), the evolver skill handles one manifest at a time. Coordinating multiple supersede operations in the right order requires manual orchestration.

**Potential solution:** A batch evolution mode that identifies all affected manifests and proposes a supersede order based on dependency analysis. The coherence engine's dependency check could generate this order automatically.

**Priority:** Medium — affects large refactors but not daily work.

---

### 2. Behavioral Test Generation Quality

**Gap:** The planner skill asks the AI to write behavioral tests, but the quality depends on the AI's judgment. Tests that are too narrow constrain implementation unnecessarily. Tests that are too broad miss edge cases.

**Potential solution:** A test quality heuristic — e.g., minimum test count per artifact, edge case coverage checklist, mutation testing integration. The `docs/unit-testing-rules.md` provides guidelines but not enforcement.

**Priority:** Medium — affects the reliability of the behavioral contract.

---

### 3. Manifest Diff Visualization

**Gap:** When the evolver supersedes a manifest, there is no visual diff showing what changed between the old contract and the new one. The user must read both manifests and compare mentally.

**Potential solution:** A `maid diff <old-manifest> <new-manifest>` command that shows artifact-level changes (added, removed, modified). This would make the cost of supersede visible at a glance.

**Priority:** Low — useful but not blocking.

---

### 4. Cross-Language Evolution

**Gap:** The skills assume a single-language project. A project with both Python backend and TypeScript frontend may need coordinated manifests across languages. A renamed API endpoint affects both the Python route handler and the TypeScript client.

**Potential solution:** Cross-language dependency tracking in the coherence engine. When a Python manifest is superseded, flag TypeScript manifests that import from it.

**Priority:** Low — multi-language projects are a smaller segment.

---

### 5. Skill Integration with Specific AI Tools

**Gap:** The skills are written as generic prompt definitions. They work with any AI agent that reads markdown, but integration with specific tools (Claude Code skills, Cursor rules, Copilot custom instructions) may require format adaptation.

**Potential solution:** Tool-specific wrappers or adapters that translate the skill format. For example, a `.clinerules` file for Cline, a `.cursor/rules` file for Cursor, or a pi skill registration.

**Priority:** High — adoption depends on frictionless integration with the user's tool of choice.

---

### 6. Automated Regression Attribution

**Gap:** When the auditor detects a regression, it reports WHICH manifest is broken but not WHAT change caused it. The user must investigate git history manually.

**Potential solution:** Integrate with git blame to attribute the breaking change to a specific commit. `maid audit --blame` could show: "Manifest X broke at commit Y by author Z, changing file W."

**Priority:** Low — useful for debugging but not for the core workflow.

---

### 7. Partial Supersede

**Gap:** Currently, supersede is all-or-nothing. If a manifest declares 10 artifacts and you want to change 1, you must list all 10 in the new manifest. This is the transition pattern requirement, but it creates friction.

**Potential solution:** A `partial-supersede` mode that replaces only specific artifacts while keeping the rest of the old manifest active. The chain merger would understand that artifact A from the old manifest is replaced by artifact A' from the new one.

**Risk:** This complicates the chain merging logic and the validation model. The current all-or-nothing model is simple and correct.

**Priority:** Low — the transition pattern works, it's just verbose.

---

## Skill Locations

```
skills/
├── maid-planner/
│   ├── SKILL.md
│   └── agents/openai.yaml      # Codex-specific metadata when needed
├── maid-implementer/
│   ├── SKILL.md
│   └── agents/openai.yaml      # Codex-specific metadata when needed
├── maid-evolver/
│   ├── SKILL.md
│   └── agents/openai.yaml      # Codex-specific metadata when needed
└── maid-auditor/
    ├── SKILL.md
    └── agents/openai.yaml      # Codex-specific metadata when needed
```

## Related Documentation

- `docs/ai-compiler-workflow.md` — ArchSpec + MAID Runner pipeline
- `docs/maid_specs.md` — MAID methodology specification
- `docs/unit-testing-rules.md` — Behavioral test quality guidelines
- `CLAUDE.md` — MAID workflow and key rules for this codebase
