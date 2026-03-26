# MAID Runner v2 - Orchestration Guide

## Purpose

This is YOUR guide as the human orchestrator. It contains the exact prompts to give Claude Code at each phase of the implementation. Copy-paste the relevant prompt, let the agent work, review the output, and move to the next.

## Before You Start

### One-Time Setup

Create the implementation branch (if not already done):
```bash
git checkout -b v2-rewrite main
```

### Starting a New Session (Every Time)

Use this prompt at the start of EVERY new Claude Code session:

---

#### Session Start Prompt

```
Read the v2 rewrite specification at specs/v2-rewrite/. Start with:
1. specs/v2-rewrite/14-progress-tracker.md (to find current state)
2. The Session State section tells you what's in progress
3. Continue from where the last session left off

Rules:
- Follow TDD: write tests first from specs/v2-rewrite/15-golden-tests.md, then implement
- Follow docs/unit-testing-rules.md for test quality
- Update 14-progress-tracker.md checkboxes as you complete each task
- Update the Session State section before stopping
- Run the phase verification commands before marking a phase complete
- Do NOT modify any existing code outside of maid_runner/core/, maid_runner/validators/,
  maid_runner/compat/, maid_runner/graph/, maid_runner/coherence/, maid_runner/cli/commands/,
  maid_runner/schemas/, and tests/ (new test structure)
- The old code in maid_runner/cli/*.py and maid_runner/validators/manifest_validator.py
  must keep working until Phase 7

Continue the implementation now.
```

---

## Phase Prompts

Use these prompts to kick off each phase. If a phase spans multiple sessions, use the Session Start Prompt above for continuation sessions — the agent will pick up from the progress tracker.

### Phase 1: Foundation

```
We're starting Phase 1 of the MAID Runner v2 rewrite.

Read these specs:
- specs/v2-rewrite/03-data-types.md (all types to implement)
- specs/v2-rewrite/04-core-manifest.md (manifest loading)
- specs/v2-rewrite/13-backward-compatibility.md (v1 compat)
- specs/v2-rewrite/15-golden-tests.md sections 1 and 2 (golden test cases)
- specs/v2-rewrite/02-manifest-schema-v2.md (for the JSON Schema)

Tasks (from 14-progress-tracker.md):
1. Create package structure directories
2. Implement core/types.py with all enums and dataclasses (TDD)
3. Implement core/result.py with all result types (TDD)
4. Create schemas/manifest.v2.schema.json
5. Copy v1 schema
6. Implement core/manifest.py - loading and parsing (TDD)
7. Create test fixture manifests
8. Implement compat/v1_loader.py (TDD)
9. Implement core/config.py (TDD)

Write tests first using golden test cases from 15-golden-tests.md.
Update 14-progress-tracker.md as you complete each task.
Run phase verification when all tasks are done.
```

### Phase 2: Validation Engine

```
We're starting Phase 2 of the MAID Runner v2 rewrite.

Read these specs:
- specs/v2-rewrite/04-core-manifest.md (ManifestChain section)
- specs/v2-rewrite/05-core-validation.md (ValidationEngine)
- specs/v2-rewrite/05b-core-test-runner.md (test runner)
- specs/v2-rewrite/16-porting-reference.md sections 1-4 (algorithms to port)
- specs/v2-rewrite/15-golden-tests.md sections 3-7 (golden test cases)

Tasks:
1. Implement core/chain.py - ManifestChain (TDD)
2. Implement core/_type_compare.py - type normalization (TDD, port from 16-porting-reference.md)
3. Implement core/_file_discovery.py - source file discovery
4. Implement core/validate.py - ValidationEngine (TDD)
5. Implement core/test_runner.py - test execution and batch mode (TDD)

Critical: Read 16-porting-reference.md carefully for the type normalization pipeline,
self/cls filtering, strict/permissive rules, and behavioral validation logic.
These algorithms must be preserved exactly.

Update 14-progress-tracker.md as you complete each task.
```

### Phase 3: Validators (Can Run Parallel with Phase 2)

```
We're starting Phase 3 of the MAID Runner v2 rewrite.

Read these specs:
- specs/v2-rewrite/06-validators.md (full validator architecture)
- specs/v2-rewrite/16-porting-reference.md sections 2, 5, 6 (Python, TypeScript, Svelte algorithms)
- specs/v2-rewrite/15-golden-tests.md sections 4 and 8 (Python and TypeScript golden tests)

Tasks:
1. Implement validators/base.py - BaseValidator ABC, FoundArtifact, CollectionResult (TDD)
2. Implement validators/__init__.py - ValidatorRegistry with conditional imports (TDD)
3. Port validators/python.py - PythonValidator from current _ArtifactCollector (TDD)
4. Port validators/typescript.py - TypeScriptValidator from current typescript_validator.py (TDD)
5. Port validators/svelte.py - SvelteValidator (TDD)

For the Python validator, read the current maid_runner/validators/manifest_validator.py
_ArtifactCollector class (line 479+) as the source of truth for behavior.
The porting reference in 16-porting-reference.md has the distilled rules.

For TypeScript, read maid_runner/validators/typescript_validator.py for the full
tree-sitter implementation. Preserve all edge cases from tasks 053, 076-078, 153-159.

Update 14-progress-tracker.md as you complete each task.
```

### Phase 4: CLI Rewrite

```
We're starting Phase 4 of the MAID Runner v2 rewrite.

Read these specs:
- specs/v2-rewrite/09-cli.md (all CLI commands)
- specs/v2-rewrite/10-public-api.md (public API exports)
- specs/v2-rewrite/01-architecture.md (for the CLI layer rules)

Key rule: Each CLI command must be a thin wrapper (<50 lines) that calls the library
API from core/ and formats the output. No business logic in CLI.

Tasks:
1. Create cli/main.py - entry point and argument parser
2. Create cli/format.py - output formatters
3. Create cli/commands/validate.py through cli/commands/howto.py (one per command)
4. Write CLI tests
5. Update maid_runner/__init__.py with public API exports
6. Verify `maid` CLI command works end-to-end

The old CLI code (cli/validate.py, cli/test.py, etc.) must remain untouched —
it still handles the existing entry point until Phase 7.

Update 14-progress-tracker.md as you complete each task.
```

### Phase 5: Features

```
We're starting Phase 5 of the MAID Runner v2 rewrite.

Read these specs:
- specs/v2-rewrite/05a-core-snapshot.md (snapshot generation)
- specs/v2-rewrite/07-graph-module.md (knowledge graph)
- specs/v2-rewrite/08-coherence-module.md (coherence checks)

Tasks:
1. Implement core/snapshot.py (TDD)
2. Port graph/ module - update to use new Manifest/ManifestChain types (TDD)
3. Port coherence/ module - update to use new types (TDD)

For graph and coherence, the current implementations are already clean.
Read the current maid_runner/graph/ and maid_runner/coherence/ code,
then adapt to use the new core types (Manifest, ManifestChain, ArtifactSpec, etc.)
instead of raw dicts.

Update 14-progress-tracker.md as you complete each task.
```

### Phase 6: Integration & Ecosystem

```
We're starting Phase 6 of the MAID Runner v2 rewrite.

Read these specs:
- specs/v2-rewrite/10-public-api.md (verify API surface)
- specs/v2-rewrite/15-golden-tests.md (all golden tests should pass)

Tasks:
1. Write integration tests: tests/integration/test_full_workflow.py
2. Write integration tests: tests/integration/test_library_api.py
3. Write integration tests: tests/integration/test_backward_compat.py
4. Update README.md with v2 examples
5. Verify public API matches spec exactly

Integration tests should exercise the full pipeline:
- Load v2 YAML manifest -> validate -> check result
- Load v1 JSON manifest -> auto-convert -> validate -> check result
- Multi-file manifest -> chain resolution -> merged validation
- Snapshot generation -> save -> reload -> validate

Update 14-progress-tracker.md as you complete each task.
```

### Phase 7: Cleanup

```
We're starting Phase 7 (final phase) of the MAID Runner v2 rewrite.

Read specs/v2-rewrite/12-migration-plan.md Phase 7 section.

Tasks:
1. Remove old CLI modules (cli/validate.py, cli/test.py, cli/snapshot.py, cli/init.py, cli/_*.py)
2. Remove old validator integration (validators/manifest_validator.py, validators/semantic_validator.py, validators/_*.py)
3. Remove old cache module
4. Remove old test files (tests/test_task_*.py, tests/_test_task_*.py)
5. Run full test suite and coverage report
6. Run linting and type checking
7. Update pyproject.toml version to 2.0.0
8. Final verification

IMPORTANT: Before removing ANY file, verify that no new code imports from it.
Run `grep -r "from maid_runner.cli.validate import" maid_runner/` etc. before deleting.

After cleanup, run:
  uv run pytest tests/ -v --cov=maid_runner --cov-report=term-missing
  uv run mypy maid_runner/
  uv run black --check maid_runner/ tests/
  uv run ruff check maid_runner/ tests/

Update 14-progress-tracker.md and mark all tasks complete.
```

---

## Handling Common Situations

### Agent Runs Out of Context / Session Ends

Just start a new session with the **Session Start Prompt** above. The agent reads the progress tracker and continues.

### Agent Gets Stuck

```
Stop. Read the relevant spec file again:
- For type issues: specs/v2-rewrite/16-porting-reference.md section [N]
- For expected behavior: specs/v2-rewrite/15-golden-tests.md section [N]
- For architecture questions: specs/v2-rewrite/01-architecture.md

What specific test is failing? Show me the test, the implementation, and the error.
```

### Agent Wants to Deviate from Spec

```
Do not deviate from the spec. The specs at specs/v2-rewrite/ are the single source of truth.
If you think the spec is wrong, explain why and I'll decide whether to update it.
Do not implement something different from what the spec says.
```

### Verifying a Phase Is Complete

```
Run the phase verification commands from specs/v2-rewrite/14-progress-tracker.md
for Phase [N]. Show me the output. Do not mark the phase complete until all
verification commands pass.
```

### Something in the Spec Seems Wrong

If the agent identifies an actual spec issue, update the spec file first, then implement. Don't let specs and implementation drift.

### Reviewing Progress

```
Show me the current state of specs/v2-rewrite/14-progress-tracker.md.
How many tasks are complete? What's the next task? Are there any blockers?
```

---

## Quick Reference: Which Spec for Which Question

| Question | Read This |
|----------|-----------|
| "What's the overall structure?" | 01-architecture.md |
| "What does a v2 manifest look like?" | 02-manifest-schema-v2.md |
| "What type should this field be?" | 03-data-types.md |
| "How does manifest loading work?" | 04-core-manifest.md |
| "How does validation work?" | 05-core-validation.md |
| "How does snapshot work?" | 05a-core-snapshot.md |
| "How does test running work?" | 05b-core-test-runner.md |
| "How do validators work?" | 06-validators.md |
| "How does the graph work?" | 07-graph-module.md |
| "How do coherence checks work?" | 08-coherence-module.md |
| "What CLI commands exist?" | 09-cli.md |
| "What's the public API?" | 10-public-api.md |
| "How are tests organized?" | 11-testing-strategy.md |
| "What phase am I in?" | 14-progress-tracker.md |
| "What should this test case return?" | 15-golden-tests.md |
| "How does the current code work?" | 16-porting-reference.md |
| "How does v1 compat work?" | 13-backward-compatibility.md |
