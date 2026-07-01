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

## MAID Plan-Lock Lifecycle

For implementation-ready MAID work, the planning loop must end with an approved
plan lock before implementation begins:

1. Draft or evolve the manifest and focused behavioral tests.
2. Confirm the red phase fails for the intended reason.
3. Run behavioral validation for the manifest.
4. After approval, run `uv run maid plan lock <manifest>`.
5. Promote implementation drafts with `uv run maid manifest promote manifests/drafts/<slug>.manifest.yaml` so plan locks, self-referencing validate paths, and red evidence migrate through the sanctioned workflow. Do not manually move or copy draft manifests.
6. Implement only within the promoted manifest scope.
7. Run implementation validation, manifest tests, `uv run maid validate`, and `uv run maid test`.
8. Before handoff, run `uv run maid verify --summary --require-plan-lock --require-red-evidence` and treat plan-lock or red-evidence failures as workflow blockers rather than recreating evidence after implementation. Prefer `--summary` for agent and human handoff because it keeps blocking failures visible while deduplicating warning storms; rerun with raw text, `--json`, `--packet`, or SARIF only when exhaustive machine-readable detail is needed. Treat older handoff examples such as `uv run maid verify --require-plan-lock --require-red-evidence` as superseded unless raw text is intentionally required.

## Optional Multi-Agent Division of Labor

MAID is tool-agnostic: a single agent may run the entire lifecycle (plan,
contract, implement, review). This repository also supports an optional split
across agents, and the MAID skills support either mode without imposing one.

When the split is used here, the roles are:

1. **Strategy / draft (planning agent):** decompose the work, set scope
   boundaries, and design the epic or draft manifest under `manifests/drafts/`.
   In handoff mode the planning agent stops after the draft and adversarial
   self-review and emits a handoff packet (draft path, scope boundaries,
   declared-artifact intent, planned tests and `validate` commands, expected
   red-phase failure, open questions and rationale) instead of locking.
2. **Contract hardening (implementing agent):** resume from the handoff packet —
   write behavioral tests, confirm the intended red phase, run
   `uv run maid validate <manifest> --mode behavioral`, plan-review, and after
   approval `uv run maid plan lock <manifest>` then
   `uv run maid manifest promote manifests/drafts/<slug>.manifest.yaml`.
3. **Implementation:** implement strictly within the promoted, locked scope; do
   not relax tests or rewrite the manifest. Send genuinely new work back into a
   planning loop instead.
4. **Implementation review:** review the diff against the locked contract in a
   separate session or subagent per the MAID Review-Fix-Ready Loop, so the
   review does not inherit blind spots from contract authoring.

The split is optional and tool-neutral; any agent can play any role. Repository
guidance (CLAUDE.md for Claude, this file for shared/Codex behavior) records
whether a given agent prefers a specific role by default.

## Validator Hardening Constraints

Do not build or extend custom static analyzers as the default answer to validator hardening, especially for Python control-flow or behavioral reachability. The abandoned 033 reachability hardening attempt showed that case-by-case AST interpretation causes large validator and test growth while still missing language edge cases. Prefer runtime-backed evidence, instrumentation, existing parser/compiler services, or a deliberately narrow syntactic rule with documented limits. If a hardening task starts requiring broad control-flow modeling, stop and propose a design direction before implementation.

## MAID Review-Fix-Ready Loop

Every MAID-backed coding session must end with an implementation review gate before handoff. After implementation and validation, run `maid-implementation-review` or an equivalent read-only reviewer against a self-contained packet: active manifest path, changed files, diff summary, validation output, environment limits, and any `plan-revision.md` signal.

Standing authorization: for MAID implementation review in this repository, the user explicitly authorizes Codex to spawn the required read-only reviewer subagent without asking for a separate per-turn approval. Use the same independence pattern as `tools/codex_maid_loop.py`: `fork_context=false`, prefer `agent_type=explorer`, leave the reviewer model and reasoning effort unset so they inherit from the main agent, and pass only the explicit review packet instead of the implementation transcript. If `explorer` is unavailable, use the default role with the same read-only packet. Close each reviewer subagent with `close_agent` after consuming its verdict.

Fix valid review findings, rerun the focused validation commands, and re-review until the final verdict is ready. Capture Outcome after implementation review and before final handoff: update the promoted manifest with an evidence-backed `outcome:` section that cites validation commands, review findings, and relevant lessons. After Outcome capture, run `uv run maid learn` to refresh the local `.maid/outcomes.json` advisory index for subsequent recall. `.maid/outcomes.json` is generated and ignored; do not commit it. If `maid learn` fails, report the refresh failure as advisory unless recall or insights are required for the current task. Do not report ready, merge-ready, commit-ready, or handoff-ready while the latest review verdict is `needs changes`, `needs discussion`, blocked, missing, or while Outcome is missing unless the final report states a concrete not-applicable or blocked reason. Fall back to local-only review only when the subagent tool is technically unavailable or the user explicitly disables subagents for that turn.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commits, including `fix:`, `feat:`, `docs:`, and `release:`. Keep commits scoped to one logical change and do not mix generated artifacts with unrelated edits. Pull requests should explain the behavior change, link issues when applicable, list the exact validation commands run, and call out any intentionally skipped checks.

## Git Branch Workflow

Keep `main` release-only and stable. It should point at tagged or release-ready states such as `release: 2.11.0`; do not leave routine fix, feature, or refactor commits on `main` unless the user explicitly asks for release preparation.

Use `release/v2.next` as the standing integration branch for the next v2 batch. When work is a general fix batch or next-release stabilization item, put it on `release/v2.next` rather than creating broad catch-all branches such as `fix/general-fix-batch`.

Use short-lived scoped branches only when a change needs isolated review or handoff before joining the batch. Prefer slash-based names that match the existing history, for example `fix/package-runner-dir-exec-detection`, `feat/<short-slug>`, `refactor/<short-slug>`, or `docs/<short-slug>`. Merge or cherry-pick validated scoped work into `release/v2.next` before release promotion.

If a non-release commit lands on `main` by mistake before it is pushed, preserve the commit on the intended branch first, then move local `main` back to the release base. Do not rewrite published history, push branches, or delete remote branches without explicit user approval.

## Agent-Specific Instructions

Pure markdown-only documentation edits may skip the full MAID workflow, but verify accuracy against current files. Do not commit or push without explicit approval.
