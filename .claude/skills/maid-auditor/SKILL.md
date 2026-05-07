---
name: maid-auditor
description: Audit the codebase against all existing MAID manifests to detect regressions, broken contracts, and architectural drift. Validates that past manifests still hold true against current code. Use before releases, after large changes, or periodically as a health check.
---

# MAID Auditor Skill

## Rules

- NEVER modify code, manifests, or tests during an audit. This skill is read-only.
- ALWAYS report findings objectively — what is broken, what is healthy, what is unknown.
- NEVER skip a manifest. Audit all active (non-superseded) manifests.
- ALWAYS distinguish between a broken contract (regression) and a missing implementation (backlog).

---

## What This Skill Does

MAID manifests are **durable contracts**. Unlike markdown plans that are disposable, a manifest declared last week should still validate against today's code. If it doesn't, something has drifted.

This skill checks the entire codebase against every active manifest and reports:

| Status | Meaning |
|--------|---------|
| ✅ **TRACKED** | Manifest validates, tests pass — contract is healthy |
| ❌ **REGRESSION** | Manifest was valid before, now fails — code broke a past contract |
| ⏳ **PENDING** | Manifest exists but implementation is incomplete — not yet done |
| ⚠️ **DRIFT** | Code changed in a tracked file but manifest wasn't updated — gap detected |
| 📦 **SUPERSEDED** | Manifest is archived — not active, not checked |

---

## Phase 1 — Full Validation Sweep

Run the complete validation suite:

```bash
# 1. Structural validation: do all manifests still match the code?
maid validate --json > /tmp/maid-audit-structural.json 2>&1

# 2. Behavioral validation: do all tests still pass?
maid test --json > /tmp/maid-audit-behavioral.json 2>&1

# 3. Coherence checks: any architectural violations?
maid validate --coherence --json > /tmp/maid-audit-coherence.json 2>&1

# 4. File tracking: any undeclared or partially compliant files?
maid validate --json > /tmp/maid-audit-tracking.json 2>&1
```

---

## Phase 2 — Analyze Results

### Structural Validation Analysis

For each manifest, determine status:

```bash
maid validate 2>&1
```

| Output | Interpretation |
|--------|---------------|
| `Passed: N` | N manifests have code that matches their contracts — **TRACKED** |
| `Failed: N` | N manifests have code that doesn't match — investigate each |
| `Skipped: N (superseded)` | N manifests are archived — **SUPERSEDED**, no action needed |

For each failed manifest, identify the specific failure:

```bash
maid validate manifests/<slug>.manifest.yaml --mode implementation
```

- **Artifact missing** → Code was refactored/deleted without updating manifest → **REGRESSION**
- **Extra artifact in strict mode** → Code added public symbols not in manifest → **DRIFT**
- **Signature mismatch** → Code changed a public signature → **REGRESSION**

### Behavioral Test Analysis

```bash
maid test
```

| Output | Interpretation |
|--------|---------------|
| All commands pass | Behavioral contracts intact — **TRACKED** |
| Specific test fails | Behavior changed without intent — **REGRESSION** |
| Test file missing | Test was deleted — **REGRESSION** |

### Coherence Analysis

```bash
maid coherence
```

| Check | What It Catches |
|-------|-----------------|
| `naming` | Artifacts that violate naming conventions |
| `duplicate` | Same artifact declared in multiple manifests |
| `boundary` | Cross-layer dependencies that violate architecture |
| `signature` | Signature inconsistencies across manifests |
| `dependency` | Circular or invalid manifest dependencies |

### File Tracking Analysis

The file tracking analysis identifies files that exist in the codebase but are not fully covered by manifests:

| Status | Meaning | Action |
|--------|---------|--------|
| **UNDECLARED** | File exists but not in any manifest | Add to a manifest |
| **REGISTERED** | File in manifest but incomplete (no artifacts, no tests) | Add artifacts and tests |
| **TRACKED** | File has full compliance (artifacts + tests) | No action needed |

---

## Phase 3 — Generate Audit Report

Present findings to the user in a clear summary:

```
## MAID Audit Report — <date>

### Overview
- Total manifests: <N>
- Active (non-superseded): <N>
- Superseded (archived): <N>

### Health Summary
✅ TRACKED:    <N> manifests — contracts healthy, tests passing
❌ REGRESSION: <N> manifests — code broke a past contract
⏳ PENDING:    <N> manifests — implementation not yet complete
⚠️ DRIFT:      <N> manifests — code changed without manifest update
📦 SUPERSEDED: <N> manifests — archived, not checked

### File Coverage
- TRACKED files:    <N> (full compliance)
- REGISTERED files: <N> (partial compliance)
- UNDECLARED files: <N> (no manifest coverage)

### Regressions (if any)
1. manifests/<slug>.manifest.yaml
   - Artifact 'X' missing from file Y
   - Likely cause: <refactor/change>
   - Action: Update manifest or restore artifact

### Drift (if any)
1. manifests/<slug>.manifest.yaml
   - Extra public artifact 'Z' in strict file Y
   - Action: Add to manifest or make private (_prefix)

### Coherence Issues (if any)
1. <check name>: <description>
   - Action: <recommendation>

### Recommendations
- <prioritized list of actions>
```

---

## Phase 4 — Recommend Actions

Based on findings, recommend prioritized actions:

### Critical (Fix Now)

- **Regressions** — broken contracts indicate unintended changes. Fix the code or update the manifest.
- **Missing behavioral tests** — manifests without passing tests provide no regression protection.

### Important (Fix Soon)

- **Drift** — code evolved without manifest update. Add the new artifacts to the manifest.
- **Coherence violations** — architectural inconsistencies that may cause future issues.

### Maintenance (Fix When Convenient)

- **UNDECLARED files** — add manifests for uncovered files to improve coverage.
- **REGISTERED files** — add artifacts and tests for partial coverage.
- **Consolidate snapshots** — merge long manifest chains into consolidated snapshots.

---

## Usage Patterns

### Before Release

```
User: "Are we clean for release?"
AI: [runs maid-auditor]
Report: ✅ 47 tracked, ❌ 0 regressions, ⏳ 2 pending
Result: Ship with confidence (pending items are known backlog)
```

### After Large Refactor

```
User: "I just refactored the auth module, check for regressions."
AI: [runs maid-auditor, filters for affected manifests]
Report: ❌ 1 regression — auth-service manifest broken
Result: Manifest updated to reflect new structure
```

### Periodic Health Check

```
User: "How's the MAID health of this project?"
AI: [runs maid-auditor]
Report: Full audit with coverage metrics
Result: Trend data — improving or declining coverage over time
```

### Brownfield Onboarding Progress

```
User: "How much of this brownfield project is MAID-covered?"
AI: [runs maid-auditor, focuses on file tracking]
Report: 30 TRACKED, 15 REGISTERED, 45 UNDECLARED
Result: Clear picture of onboarding progress
```

---

## Key Insight: Manifests as Regression Detectors

This is what makes MAID different from traditional testing:

| Traditional Approach | MAID Approach |
|---------------------|---------------|
| Tests verify behavior | Tests verify behavior **AND** manifests verify structure |
| Test decay over time (flaky tests) | Manifests are stable contracts (don't decay) |
| Regression caught by failing tests | Regression caught by **both** failing tests AND failing validation |
| Plan is disposable (markdown) | Plan is durable (manifest) — checked forever |
| No audit trail of intentional changes | Every change has a timestamped contract |

**The manifest is a regression detector that doesn't need to run.** It sits in the repository as a declarative statement: "this file MUST contain these artifacts." Every future `maid validate` checks that statement against reality.

---

## Quick Reference

### Audit Commands

```bash
# Full audit (all in one)
maid validate              # Structural: all manifests
maid test                  # Behavioral: all tests
maid validate --coherence  # Architectural: coherence checks

# JSON output (for automation)
maid validate --json
maid test --json

# Single manifest check
maid validate manifests/<slug>.manifest.yaml --mode implementation
```

### When to Use This Skill

- Before releases or deployments
- After large refactors or merges
- Periodic health checks (weekly/monthly)
- Brownfield onboarding progress tracking
- Onboarding new team members (understand contract coverage)
- Investigating suspected regressions

### When NOT to Use This Skill

- During active implementation (use `maid-implementer` instead)
- During planning (use `maid-planner` instead)
- For private-only refactors (no manifest impact)
