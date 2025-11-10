# MAID Agent - Future Project

This directory contains planning documents for **MAID Agent**, a separate project that will build upon MAID Runner.

## Project Separation

### MAID Runner (Current Project)
**Purpose:** Tool-agnostic validation framework

**Responsibilities:**
- ✅ Validate manifest schema
- ✅ Validate behavioral tests
- ✅ Validate implementation
- ✅ Validate type hints
- ✅ Validate manifest chain
- ✅ Generate snapshots from existing code

**Does NOT:**
- ❌ Create manifests automatically
- ❌ Generate code
- ❌ Implement AI agents
- ❌ Orchestrate development workflow

### MAID Agent (Future Project)
**Purpose:** AI-driven development automation tool

**Responsibilities:**
- ✅ Use MAID Runner for validation
- ✅ Implement Guardian Agent framework
- ✅ Automated manifest generation
- ✅ Scaffold and Fill tooling
- ✅ Fix dispatch system
- ✅ Development workflow orchestration

**Uses MAID Runner:**
```python
# MAID Agent will call MAID Runner like this:
import subprocess

result = subprocess.run([
    "python", "validate_manifest.py",
    "manifests/task-013.manifest.json",
    "--use-manifest-chain"
])

if result.returncode == 0:
    # MAID Agent proceeds with automation
    pass
```

## Documents in This Directory

These documents were originally written for MAID Runner but describe automation features that belong in a separate MAID Agent project:

- **ROADMAP.md** - MAID v1.3 roadmap with automation features
- **ISSUES.md** - Detailed issues for automation implementation
- **COMPLETION_ROADMAP.md** - Earlier roadmap with agent workflows

## Why This Separation?

**Architectural Benefits:**
1. **MAID Runner** stays focused on validation (single responsibility)
2. **Tool-agnostic design** - any AI tool can use MAID Runner
3. **MAID Agent** becomes one of many possible automation tools
4. **Clean dependencies** - MAID Agent depends on MAID Runner, not vice versa

**Integration Options:**
```
MAID Runner (validation core)
    ↓
    ├─→ MAID Agent (our AI automation)
    ├─→ Claude Code (with MAID integration)
    ├─→ Aider (with MAID plugin)
    ├─→ Cursor (with MAID support)
    └─→ Custom tools (using validation CLI)
```

## When to Build MAID Agent

**Prerequisites:**
- ✅ MAID Runner v1.2+ is stable
- ✅ Validation CLI is complete
- ✅ Snapshot generation works
- ✅ External tools can integrate successfully

**Timeline:**
- After MAID Runner reaches production maturity
- When automation use cases are well-understood
- When AI agent patterns are validated

## Notes

The roadmaps in this directory are still valuable - they represent the vision for AI-assisted MAID development. They just belong in a separate project that **uses** MAID Runner rather than being part of it.

Think of it like:
- **pytest** = test framework (like MAID Runner = validation framework)
- **pytest-xdist** = automation plugin (like MAID Agent = automation tool)
