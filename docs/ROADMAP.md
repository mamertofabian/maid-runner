# MAID Runner Roadmap

**Project:** MAID Runner - validation framework for Manifest-driven AI Development
**Status:** Active v2 development
**Current Version:** 2.16.0
**Last Updated:** 2026-06-01

## Purpose

This roadmap describes the current MAID Runner direction. It replaces the old
v0.1.3 feature-set roadmap, which mixed completed v2 work with speculative
2025 milestones.

MAID Runner remains a validation-first tool. It validates manifests, code,
tests, chain history, file scope, and handoff gates. It does not own general AI
agent orchestration, code generation, or product workflows outside validation.

## Current State

MAID Runner is now a v2 YAML-manifest package published as `maid-runner`.
The local CLI reports `maid 2.16.0`.

Supported languages:

- Python via the built-in AST.
- TypeScript and JavaScript via tree-sitter plus bounded compiler-backed
  resolution where parser evidence is insufficient.
- Svelte via tree-sitter-backed component parsing.

Core validation surfaces:

- Schema validation for manifest structure and lifecycle metadata.
- Behavioral validation that checks test coverage for declared artifacts.
- Implementation validation that checks declared code artifacts and removed
  artifacts.
- Acceptance validation for declared acceptance test files.
- Manifest-chain merging, supersession diagnostics, lifecycle checks, and
  chain replay/logging.
- Coherence, file-tracking, worktree-scope, changed-scope, and combined
  `maid verify` gates for handoff.
- Supersession auditing for historical artifact preservation.

Current CLI commands:

- `maid validate`
- `maid test`
- `maid verify`
- `maid snapshot`
- `maid snapshot-system`
- `maid bootstrap`
- `maid learn`
- `maid recall`
- `maid insights`
- `maid manifest create`
- `maid manifests`
- `maid files`
- `maid init`
- `maid graph`
- `maid coherence`
- `maid schema`
- `maid howto`
- `maid chain log`
- `maid chain replay`
- `maid audit supersessions`
- `maid serve`

Current command options include explicit parallel test-stage controls:
`maid test --jobs N` for independent implementation command groups and
`maid verify --test-jobs N` for the verify test stage. `maid init --tool`
currently accepts `claude`, `codex`, `cursor`, `windsurf`, `generic`, and
`auto`.

## Active Workstreams

### Validation Trust

Goal: keep green validation meaningful and fail closed when evidence is weak.

Current references:

- `docs/plans/maid-validate-hardening-backlog.md`
- `manifests/030-*`
- `manifests/032-*`
- `manifests/043-01-retire-grandfathered-chain-noise.manifest.yaml`
- `manifests/043-02-enforce-active-manifest-lifecycle-status.manifest.yaml`
- `manifests/043-03-archive-consumed-draft-epics.manifest.yaml`

Near-term direction:

- Keep hardening focused on reproduced false-green paths.
- Preserve structured error codes and JSON-visible diagnostics.
- Avoid broad custom static analyzers when runtime-backed evidence or existing
  parser/compiler services can close the loophole more reliably.

### Performance

Goal: reduce common `maid validate`, `maid test`, and `maid verify` latency
without weakening validation evidence.

Current references:

- `docs/plans/maid-runner-performance-backlog.md`
- `manifests/041-*`
- `manifests/043-04-cache-typescript-compiler-project-for-import-resolution.manifest.yaml`
- `manifests/046-01-parallelize-independent-maid-test-command-groups.manifest.yaml`

Near-term direction:

- Use `maid test --jobs N` for active manifest-set runs and
  `maid verify --test-jobs N` only as explicit opt-in parallel test-stage
  acceleration; single-manifest `maid test --manifest ...` and default
  execution remain serial.
- Re-benchmark representative projects after `046-01` before planning another
  optimization slice.
- Keep cross-invocation disk caches speculative until profiling proves they are
  the right next boundary.

### Maintainability

Goal: keep validation internals small enough to review safely while preserving
observable behavior.

Current references:

- `docs/plans/maid-runner-cleanup-refactor-backlog.md`
- `manifests/035-*`
- `manifests/038-*`
- `manifests/039-01-speed-up-pnpm-vitest-and-typescript-validation.manifest.yaml`

Current state:

- The original large `ValidationEngine` methods listed in the cleanup backlog
  have been characterized and mostly extracted into focused helper modules.
- `ValidationEngine.validate_removed_artifacts`, `validate_all`,
  `validate_behavioral`, `_check_test_coverage`, and
  `validate_implementation` are now thin public API wrappers.
- Future cleanup should be selected from current code evidence, not from the
  stale pre-038 method-size table.

Near-term direction:

- Refresh cleanup findings before creating new refactor drafts.
- Keep refactor slices behavior-preserving and characterization-backed.
- Do not mix cleanup with performance changes unless a manifest explicitly
  scopes both.

### MAID Workflow And Process

Goal: make the repository's own MAID practice auditable and hard to misread.

Current references:

- `docs/plans/maid-runner-self-improvement-backlog.md`
- `manifests/drafts/README.md`
- `AGENTS.md`

Near-term direction:

- Keep `manifests/drafts/` reserved for live draft inventory plus explicit
  archive pointers.
- Keep active manifest lifecycle metadata truthful.
- End MAID-backed implementation sessions with an implementation-review gate.
- Treat markdown-only documentation updates as lightweight, but verify claims
  against current files.

## Deferred Or External Work

These areas remain possible future work, but they are not the active v2 core
roadmap unless a dedicated spec promotes them:

- Editor/LSP integrations.
- Additional language validators such as Go, Rust, Java, or C#.
- Cross-repository validation.
- General AI agent orchestration and natural-language product workflows.
- Long-lived daemon adoption beyond the current `maid serve` validator socket.

## What MAID Runner Should Not Absorb

MAID Runner should stay focused on validation. The following belong in external
tools or separate specs:

- General code generation.
- End-user product orchestration.
- Model selection and LLM integration.
- Autonomous feature planning outside a MAID contract.
- UI/editor experiences that require a separate product surface.

External tools can call MAID Runner through the CLI or Python API and use its
exit codes, JSON output, and structured diagnostics as validation evidence.

## Maintenance Notes

Before adding a new roadmap milestone, check whether it already belongs in one
of the specialist backlogs:

- Validation trust: `docs/plans/maid-validate-hardening-backlog.md`
- Performance: `docs/plans/maid-runner-performance-backlog.md`
- Cleanup/refactor: `docs/plans/maid-runner-cleanup-refactor-backlog.md`
- Whole-system prioritization:
  `docs/plans/maid-runner-self-improvement-backlog.md`

Roadmap entries should name the owning lane, current evidence, and the next
manifest or spec needed to make the work implementable.
