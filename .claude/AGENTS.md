# MAID Claude Agents

This repository keeps one repo-level Claude agent:

## maid-implementation-reviewer

**Purpose:** Review implementation work against the approved MAID manifest before handoff.

Use it after implementation to check changed files, declared artifacts, behavioral tests, and validation evidence.

Implementation work is not ready until valid reviewer findings are fixed, focused validation is rerun, and the implementation is re-reviewed to a `Ready to merge` verdict. Pass the reviewer a self-contained packet instead of the implementation transcript. The repo grants standing authorization to run the read-only implementation-reviewer agent for this gate; do not ask for separate per-turn approval unless the user explicitly disables reviewer agents.

The primary MAID workflow lives in `.claude/skills/`.
