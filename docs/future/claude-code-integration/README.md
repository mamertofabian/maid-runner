# Claude Code Integration Examples

This directory contains **example** Claude Code configurations that demonstrate how to build MAID Agent-like automation using Claude Code as the AI backend with MAID Runner for validation.

## Important Context

**These are NOT part of MAID Runner's core.**

MAID Runner is a tool-agnostic validation framework. These examples show one way to build automation on top of MAID Runner using Claude Code's agent and command features.

## What's Here

### Automation Agents (`agents/`)

Five specialized Claude Code agents that automate the MAID workflow:

1. **maid-manifest-architect** - Creates and validates manifests
2. **maid-test-designer** - Generates behavioral tests from manifests
3. **maid-developer** - Implements code to pass tests
4. **maid-refactorer** - Improves code quality while maintaining compliance
5. **maid-auditor** - Enforces MAID methodology compliance

**How they work:**
```
User request → Claude Code agent → Uses MAID Runner CLIs → Validates → Iterates
```

### Automation Commands (`commands/`)

Claude Code slash commands for MAID workflow automation:

- `/generate-manifest` - Create manifest from description
- `/generate-tests` - Generate behavioral tests
- `/implement` - Implement code from manifest
- `/refactor` - Refactor while maintaining manifest compliance
- `/improve-tests` - Enhance test coverage

**How they work:**
```
/implement task-013.manifest.json
  ↓
Claude Code reads manifest
  ↓
Claude Code implements code
  ↓
Claude Code runs: validate_manifest.py task-013.manifest.json
  ↓
If validation fails, Claude Code fixes and retries
```

## Architecture

```
┌─────────────────────────────────────────────┐
│   User                                      │
│   /implement task-013.manifest.json        │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│   Claude Code (AI Backend)                  │
│   - Agents (automation logic)               │
│   - Commands (slash commands)               │
│   - Understands MAID methodology            │
└─────────────────────────────────────────────┘
                    ↓ calls
┌─────────────────────────────────────────────┐
│   MAID Runner (Validation Framework)        │
│   validate_manifest.py                      │
│   generate_snapshot.py                      │
└─────────────────────────────────────────────┘
```

## How to Use These Examples

### Option 1: Use As-Is with Claude Code

If you're using Claude Code for AI-assisted development:

1. Copy `agents/` to your project's `.claude/agents/`
2. Copy `commands/` to your project's `.claude/commands/`
3. Ensure MAID Runner is available in your environment
4. Use agents and commands as documented

### Option 2: Adapt for Your MAID Agent

If you're building your own MAID Agent with a different AI backend:

1. Study the agent logic in `agents/*.md`
2. Understand the workflow:
   - Load manifest → Generate code → Validate → Fix → Iterate
3. Implement similar logic in your agent using your AI backend
4. Call MAID Runner CLIs for validation (same as these examples do)

### Option 3: Build Different Automation

These are just examples. You can build different automation patterns:

- **Guardian Agent** - Monitors tests, auto-generates fix manifests
- **Scaffold Generator** - Creates empty implementations from manifests
- **Manifest Generator** - Reverse-engineers manifests from existing code
- **Custom workflows** - Your imagination!

All of them would use MAID Runner's validation CLIs the same way.

## Key Principles These Examples Follow

### 1. Validation Comes from MAID Runner

```bash
# Agent does NOT implement validation logic
# Agent CALLS MAID Runner validation

validate_manifest.py task-013.manifest.json --use-manifest-chain
```

### 2. Agents Iterate Based on Validation

```python
while not validated:
    # Generate/modify code
    code = ai_backend.generate()

    # Validate with MAID Runner
    result = subprocess.run(["validate_manifest.py", manifest])

    if result.returncode == 0:
        break  # Success!
    else:
        # Parse errors and retry
        errors = result.stderr
        ai_backend.fix(errors)
```

### 3. Tool-Agnostic Interface

These agents could be implemented with:
- Claude Code (this example)
- OpenAI API
- Anthropic API directly
- Aider
- Cursor
- Custom scripts

The MAID Runner interface stays the same.

## Comparison: MAID Runner vs MAID Agent

| Feature | MAID Runner | MAID Agent (this example) |
|---------|-------------|---------------------------|
| **Validation** | ✅ Core responsibility | ❌ Uses MAID Runner |
| **Manifest creation** | ❌ Not responsible | ✅ AI generates |
| **Code generation** | ❌ Not responsible | ✅ AI generates |
| **Test generation** | ❌ Not responsible | ✅ AI generates |
| **Iteration logic** | ❌ Not responsible | ✅ Agent orchestrates |
| **AI integration** | ❌ Tool-agnostic | ✅ Claude Code specific |

## Files in This Directory

### Agents (Automation)

```
agents/
├── README.md                    # Agent overview
├── maid-manifest-architect.md   # Phase 1: Manifest creation
├── maid-test-designer.md        # Phase 2: Test generation
├── maid-developer.md            # Phase 3: Implementation
├── maid-refactorer.md          # Phase 3.5: Refactoring
└── maid-auditor.md             # Cross-cutting: Compliance
```

Each agent file contains:
- Prompt that defines agent behavior
- Tools the agent can use
- How to invoke MAID Runner for validation
- Iteration logic

### Commands (Slash Commands)

```
commands/
├── generate-manifest.md    # /generate-manifest
├── generate-tests.md       # /generate-tests
├── implement.md            # /implement
├── improve-tests.md        # /improve-tests
└── refactor.md            # /refactor
```

Each command file contains:
- Command description
- Arguments
- Allowed tools
- Prompt for Claude Code

## Why These Are Examples, Not Core

**MAID Runner's philosophy:**
- Do ONE thing well: Validation
- Be tool-agnostic
- Let innovation happen in the automation layer

**Benefits of this separation:**
- Multiple automation tools can compete
- MAID Runner stays stable and focused
- Users choose automation that fits their workflow
- Innovation happens without destabilizing validation

## Building Your Own MAID Agent

If you want to build a MAID Agent (like this Claude Code example):

### 1. Choose Your AI Backend

- Claude API (Anthropic)
- OpenAI API
- Local models (Ollama, LM Studio)
- Existing tools (Aider, Cursor)

### 2. Implement Core Workflows

**Manifest Creation Workflow:**
```python
def create_manifest(goal: str) -> str:
    # AI generates manifest
    manifest = ai.generate(f"Create MAID manifest for: {goal}")

    # Validate with MAID Runner
    result = run(["validate_manifest.py", manifest])

    if result.returncode != 0:
        # Fix and retry
        manifest = ai.fix(manifest, result.stderr)

    return manifest
```

**Implementation Workflow:**
```python
def implement_task(manifest_path: str):
    # Load manifest
    manifest = json.load(open(manifest_path))

    # AI implements
    code = ai.generate_implementation(manifest)

    # Validate with MAID Runner
    result = run(["validate_manifest.py", manifest_path])

    while result.returncode != 0:
        # Fix and retry
        code = ai.fix(code, result.stderr)
        result = run(["validate_manifest.py", manifest_path])
```

### 3. Call MAID Runner for Validation

**Always use subprocess to call MAID Runner CLIs:**

```python
import subprocess

# Schema + implementation + type validation
result = subprocess.run([
    "python", "validate_manifest.py",
    "manifests/task-013.manifest.json",
    "--use-manifest-chain",
    "--quiet"
], capture_output=True, text=True)

if result.returncode == 0:
    print("✓ Validation passed")
else:
    print(f"✗ Errors:\n{result.stderr}")
```

### 4. Iterate Until Validation Passes

The key pattern in all MAID Agents:

```
Loop:
  1. Generate/modify artifact
  2. Validate with MAID Runner
  3. If failed: analyze errors, fix, goto 1
  4. If passed: done!
```

## Future: Standalone MAID Agent Project

Eventually, these examples may evolve into a full **MAID Agent** project:

```
maid-agent/  (future separate repository)
├── maid_agent/
│   ├── backends/
│   │   ├── claude.py      # Claude API backend
│   │   ├── openai.py      # OpenAI API backend
│   │   └── local.py       # Local model backend
│   ├── guardian.py        # Guardian Agent
│   ├── generator.py       # Manifest generation
│   └── scaffolder.py      # Scaffold and Fill
├── cli.py
└── requirements.txt
    maid-runner>=1.2.0      # Depends on MAID Runner!
```

But for now, these Claude Code examples demonstrate the pattern!

## Questions?

- **Want to use these with Claude Code?** Copy to your `.claude/` directory
- **Building your own agent?** Study the patterns, use MAID Runner CLIs
- **Different AI backend?** Implement similar logic, call same CLIs
- **Need help?** These examples show the way!

---

**Remember:** MAID Runner validates. Agents automate. This is an example of the latter using the former.
