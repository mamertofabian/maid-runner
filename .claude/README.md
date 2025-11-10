# Claude Code Configuration for MAID Runner Development

This directory contains Claude Code-specific configuration for developing MAID Runner itself.

## Important Distinction

**These are NOT part of MAID Runner** - they are development tools for building MAID Runner using Claude Code as the development assistant.

```
┌──────────────────────────────────────┐
│   Claude Code                        │
│   (AI assistant for development)     │
│   Uses: .claude/ config              │
└──────────────────────────────────────┘
              ↓ develops
┌──────────────────────────────────────┐
│   MAID Runner                        │
│   (Tool-agnostic validator)          │
│   Product: validate_manifest.py     │
└──────────────────────────────────────┘
```

## What's in This Directory

### Commands (`commands/`)

Validation-focused slash commands for development:

- **`/run-validation`** - Run validation tests for a manifest
- **`/validate-manifest`** - Validate a manifest file
- **`/maid-help`** - Show MAID workflow commands
- **`/maid-status`** - Show MAID project status

These help during MAID Runner development but are NOT part of the MAID Runner product.

### Hooks (`hooks/`)

Quality gates that run during development:

- **`ast-validator.py`** - Validates manifest-implementation alignment
- **`test-runner.py`** - Runs test suite
- **`check-todos.py`** - Validates TODO management

These ensure MAID Runner development follows MAID methodology (dogfooding).

### Conversations (`conversations/`)

Development notes and analysis from working sessions.

## What Was Removed

**Automation features moved to `docs/future/claude-code-integration/`:**

- ❌ 5 automation agents (maid-manifest-architect, maid-test-designer, etc.)
- ❌ 5 automation commands (/generate-manifest, /implement, etc.)

**Why removed:**
- They represent AUTOMATION, not validation
- They are examples of how to build a MAID Agent with Claude Code
- They don't belong in the core MAID Runner (validation-only tool)
- Users building their own automation can reference them as examples

## For MAID Runner Users

**If you're USING MAID Runner:**
- You don't need this directory
- Use `validate_manifest.py` and `generate_snapshot.py` directly
- Integrate with your own tools (Aider, Cursor, custom scripts, etc.)

**If you're DEVELOPING MAID Runner with Claude Code:**
- This directory provides helpful commands and hooks
- Fork the repo and customize as needed

**If you're BUILDING a MAID Agent:**
- See `docs/future/claude-code-integration/` for examples
- Those show how to build automation using MAID Runner for validation
- You can adapt them to your AI backend (OpenAI, Claude API, etc.)

## Directory Structure

```
.claude/
├── README.md (this file)
├── commands/          # Validation commands for development
│   ├── maid-help.md
│   ├── maid-status.md
│   ├── run-validation.md
│   └── validate-manifest.md
├── hooks/             # Quality gates for development
│   ├── README.md
│   ├── ast-validator.py
│   ├── test-runner.py
│   └── check-todos.py
└── conversations/     # Development notes
```

## Relationship to MAID Runner

```
MAID Runner (the product)
  ├── validate_manifest.py    ✓ Core tool
  ├── generate_snapshot.py    ✓ Core tool
  └── validators/             ✓ Core library

Development Tools (not shipped)
  ├── .claude/                ✗ Development only
  ├── tests/                  ✗ Development only
  └── docs/                   ✓ Documentation only
```

## For Other Editors/Tools

If you're not using Claude Code for development:
- Ignore this directory entirely
- Use your own development tools
- MAID Runner works the same way regardless

---

**Summary:** This directory helps develop MAID Runner using Claude Code. It's not part of the MAID Runner product itself.
