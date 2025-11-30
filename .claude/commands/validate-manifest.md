---
description: Validate and review manifest (Phase 1/2 quality gate)
argument-hint: [manifest-path]
---

Validate manifest: $1

Can use the maid-plan-reviewer subagent if tests exist.

Tasks:
1. Validate manifest structure: `maid validate $1 --use-manifest-chain`
2. If tests exist, validate behavioral: `maid validate $1 --validation-mode behavioral --use-manifest-chain`
3. Review for quality (clarity, completeness, atomicity)
4. Provide feedback or approval

See CLAUDE.md for validation modes.
