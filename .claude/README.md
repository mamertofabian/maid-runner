# Claude Code Configuration

This directory contains the repo-level Claude payload distributed by `maid init --tool claude`.

## Layout

```
.claude/
├── agents/
│   └── maid-implementation-reviewer.md
├── skills/
│   ├── maid-auditor/
│   ├── maid-evolver/
│   ├── maid-implementation-review/
│   ├── maid-implementer/
│   ├── maid-incident-logger/
│   ├── maid-plan-review/
│   └── maid-planner/
└── manifest.json
```

The generated package payload under `maid_runner/claude/` is synced from this directory.
