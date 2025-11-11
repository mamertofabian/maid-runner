# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**⚠️ CRITICAL: This project dogfoods MAID v1.2. Every code change MUST follow the MAID workflow.**

## Project Overview

MAID Agents is a Claude Code automation layer for the MAID (Manifest-driven AI Development) methodology. It provides CLI tools and agents that automate the four phases of MAID workflow by invoking Claude Code in headless mode.

This package was built using MAID itself - it's a self-referential implementation that demonstrates the methodology it automates.

## Key Commands

### Development

```bash
# Install package in editable mode
uv pip install -e .

# Run tests
pytest tests/ -v

# Run specific task tests
pytest tests/test_task_018_agent_visibility.py -v

# Code quality
black maid_agents/        # Format code
ruff check maid_agents/   # Lint code
```

### Using ccmaid CLI

```bash
# Full workflow (all phases)
ccmaid run "Add user authentication to the API"

# Phase 1-2: Planning (manifest + tests)
ccmaid plan "Add user authentication" --max-iterations 10

# Phase 3: Implementation
ccmaid implement manifests/task-042.manifest.json --max-iterations 20

# Phase 3.5: Refactoring
ccmaid refactor manifests/task-042.manifest.json

# Phase 2 Quality Gate: Refinement
ccmaid refine manifests/task-042.manifest.json --goal "Improve test coverage"

# Mock mode (for testing without API calls)
ccmaid --mock plan "Test feature"
```

## Architecture

### Core Components

**MAIDOrchestrator** (`maid_agents/core/orchestrator.py`)
- Coordinates the complete MAID workflow
- Manages state machine: INIT → PLANNING → IMPLEMENTING → REFACTORING → COMPLETE
- Three main loops:
  - `run_planning_loop()`: Phase 1-2 (manifest + tests with validation)
  - `run_implementation_loop()`: Phase 3 (code generation until tests pass)
  - `run_refinement_loop()`: Phase 2 quality gate (manifest/test improvement)
- Uses `dry_run` mode for testing without file writes
- Path validation to prevent directory traversal attacks

**Agent System** (`maid_agents/agents/`)
- All agents inherit from `BaseAgent` abstract class
- **ManifestArchitect**: Creates MAID manifests from high-level goals
- **TestDesigner**: Generates behavioral tests from manifests
- **Developer**: Implements code to pass tests
- **Refactorer**: Improves code quality (Phase 3.5)
- **Refiner**: Iteratively improves manifest and test quality
- Each agent wraps Claude Code CLI via `ClaudeWrapper`

**ClaudeWrapper** (`maid_agents/claude/cli_wrapper.py`)
- Invokes Claude Code headless CLI: `claude --print <prompt> --output-format json`
- Supports `mock_mode` for testing without real API calls
- Returns `ClaudeResponse` dataclass with success/error status

**ValidationRunner** (`maid_agents/core/validation_runner.py`)
- Wraps `maid` CLI commands for validation
- `validate_manifest()`: Structural validation via `maid validate`
- `run_behavioral_tests()`: Executes pytest from manifest's `validationCommand`
- Parses validation errors for feedback loops

### Workflow Loops

**Planning Loop** (orchestrator.py:164-262)
1. ManifestArchitect creates manifest
2. TestDesigner generates tests
3. Behavioral validation (tests must USE artifacts)
4. Iterate until validation passes (max 10 iterations)

**Implementation Loop** (orchestrator.py:335-444)
1. Run tests (should fail - red phase)
2. Developer generates code
3. Write code to files
4. Run tests again
5. If pass, validate manifest compliance
6. Iterate until success (max 20 iterations)

**Refinement Loop** (orchestrator.py:446-533)
1. Refiner analyzes manifest and tests
2. Apply improvements
3. Structural validation
4. Behavioral validation
5. Iterate until both pass (max 5 iterations)

### MAID Workflow Integration

This codebase follows MAID methodology:
- All tasks have manifests in `manifests/task-*.manifest.json`
- All behavioral tests in `tests/test_task_*_*.py`
- Sequential task numbering (task-001, task-002, etc.)
- Validation enforced via `maid validate --use-manifest-chain`

## Configuration

**Settings** (`maid_agents/config/settings.py`)
- `ClaudeConfig`: Model, timeout, temperature
- `MAIDConfig`: Directory paths, iteration limits
- Defaults: claude-sonnet-4-5-20250929, 300s timeout, 0.0 temperature

## Key Design Patterns

**Mock Mode for Testing**
- All agents accept `ClaudeWrapper(mock_mode=True)` for testing
- Orchestrator uses `dry_run=True` to skip file writes
- Enables unit testing without API calls or file I/O

**Iterative Refinement with Feedback**
- Each loop collects validation errors
- Errors passed to next iteration as context
- Maximum iteration limits prevent infinite loops

**Path Safety**
- `_validate_safe_path()` prevents directory traversal
- All file operations resolve paths relative to project root
- MAX_FILE_SIZE (1MB) limit on generated code

**Agent Visibility** (Task-018)
- Agents must operate within manifest boundaries
- Only access files listed in manifest (creatable/editable/readonly)
- Prevents context leakage and ensures isolation

## MAID Compliance Notes

When making changes to this codebase:

1. **Always create manifests first** - Use sequential numbering
2. **Create tests before implementation** - Tests define success criteria
3. **Validate early and often** - Run `maid validate` before implementation
4. **Honor the chain** - Use `--use-manifest-chain` for validation
5. **Preserve public APIs** - All public methods/classes must be in manifests

## Testing Strategy

- **Unit tests**: Test individual agents with `mock_mode=True`
- **Integration tests**: Test orchestrator loops with `dry_run=True`
- **Behavioral tests**: Full workflow validation via pytest
- All tests follow naming: `test_task_NNN_description.py`

## Dependencies

- **maid-runner**: Core validation engine (sibling package)
- **click**: CLI framework
- **rich**: Terminal formatting
- **pytest**: Test framework
- **black**, **ruff**: Code quality tools

## CLI Entry Point

`ccmaid` command → `maid_agents/cli/main.py:main()` → MAIDOrchestrator

All commands route through argparse subcommands (run, plan, implement, refactor, refine).
