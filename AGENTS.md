# Repository Guidelines

## Project Structure & Module Organization

`maid_runner/` contains the Python package and CLI. Core validation logic lives in `maid_runner/core/`, language collectors in `maid_runner/validators/`, graph features in `maid_runner/graph/`, coherence checks in `maid_runner/coherence/`, CLI commands in `maid_runner/cli/commands/`, and JSON schemas in `maid_runner/schemas/`. Tests are under `tests/`, grouped by domain such as `tests/core/`, `tests/validators/`, `tests/cli/`, `tests/integration/`, and `tests/e2e/`. Active MAID contracts live in `manifests/*.manifest.yaml`; mutable planning inventory belongs in `manifests/drafts/`. Long-form design notes are in `docs/` and `specs/`.

## Build, Test, and Development Commands

- `uv sync --group dev`: install runtime and development dependencies.
- `uv run maid validate`: validate active manifests against the current tree.
- `uv run maid test`: run validation commands declared by active manifests.
- `uv run python -m pytest tests/ -v`: run the full pytest suite.
- `uv run ruff check .`: lint Python files.
- `uv run black .`: format Python files.
- `make build`: sync packaged Claude assets and build the distribution.
- `make dead-code`: run the vulture dead-code scan for review.

## Coding Style & Naming Conventions

Use Python 3.10+ with type hints for public APIs. Follow Black formatting and Ruff linting; keep imports tidy and avoid broad, unrelated refactors. Name tests `test_*.py` and use scenario-focused function names such as `test_validate_rejects_missing_artifact()`. Keep manifests semantic and kebab-cased, for example `manifests/fix-path-validation.manifest.yaml`.

## Testing Guidelines

This repository dogfoods MAID. For code changes, create or evolve the relevant manifest before implementation, add focused behavioral tests, then run behavioral and implementation validation for the touched manifest. Finish with `uv run maid validate`, `uv run maid test`, and the relevant pytest scope. Tests should assert observable behavior, include failure cases, and follow `docs/unit-testing-rules.md`.

## MAID Review-Fix-Ready Loop

Every MAID-backed coding session must end with an implementation review gate before handoff. After implementation and validation, run `maid-implementation-review` or an equivalent read-only reviewer against a self-contained packet: active manifest path, changed files, diff summary, validation output, environment limits, and any `plan-revision.md` signal.

Standing authorization: for MAID implementation review in this repository, the user explicitly authorizes Codex to spawn the required read-only reviewer subagent without asking for a separate per-turn approval. Use the same independence pattern as `tools/codex_maid_loop.py`: `fork_context=false`, prefer `agent_type=explorer`, use `gpt-5.5` with `reasoning_effort=medium` when the environment permits, and pass only the explicit review packet instead of the implementation transcript. If `explorer` is unavailable, use the default role with the same read-only packet. Close each reviewer subagent with `close_agent` after consuming its verdict.

Fix valid review findings, rerun the focused validation commands, and re-review until the final verdict is ready. Do not report ready, merge-ready, or commit-ready while the latest review verdict is `needs changes`, `needs discussion`, blocked, or missing. Fall back to local-only review only when the subagent tool is technically unavailable or the user explicitly disables subagents for that turn.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commits, including `fix:`, `feat:`, `docs:`, and `release:`. Keep commits scoped to one logical change and do not mix generated artifacts with unrelated edits. Pull requests should explain the behavior change, link issues when applicable, list the exact validation commands run, and call out any intentionally skipped checks.

## Agent-Specific Instructions

Pure markdown-only documentation edits may skip the full MAID workflow, but verify accuracy against current files. Do not commit or push without explicit approval.
