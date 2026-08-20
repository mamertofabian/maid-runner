# MAID Claude Agents

This repository keeps one repo-level Claude agent:

## maid-implementation-reviewer

**Purpose:** Review implementation work against the approved MAID manifest before handoff.

Use it after implementation to check changed files, declared artifacts, behavioral tests, and validation evidence.

Implementation work is not ready while a reviewer reports blocking or current-scope actionable findings. After addressing such findings and rerunning focused validation, use a fresh independent reviewer with a self-contained verdict-neutral packet containing the task baseline, complete baseline-to-current diff, complete changed-file list, complete manifest-declared artifact definitions and file inventory, factual validation outcomes, environment limits, and plan-revision signal. Exclude prior review lineage and coordinator-owned follow-up state instead of passing the implementation transcript. The repo grants standing authorization to run the read-only implementation-reviewer agent for this gate; do not ask for separate per-turn approval unless the user explicitly disables reviewer agents.

The primary MAID workflow lives in `.claude/skills/`.
