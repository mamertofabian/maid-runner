# Strict Coverage Migration Backlog

## Evidence Source

**Generated from:** `uv run maid validate --strict-delta --json`
**Run date:** 2026-07-06T07:50:02+08:00
**Observed runtime:** 13.69s
**Source snapshot:** release/v2.next @ c8bee583fed85566f4c35d97429df56326476ed5

The counts below are generated from the cited strict-delta run, not hand estimates.
Regenerate this document by rerunning the command above and replacing the
evidence sections with the resulting structured `strict_delta` entries.

## Per-Code Counts

| Code | Meaning | Count |
| --- | --- | ---: |
| E710 | ARTIFACT_NOT_EXECUTED_BY_TESTS | 0 |
| E900 | INTERNAL_ERROR | 0 |

## Per-Manifest / Cohort Breakdown

No manifest cohorts were present in the cited strict-delta run.

## Zero-E900 Completion Evidence

E900 count: 0, demonstrated by the cited strict-delta run. No coverage-wrapped
validate command failed under the artifact-coverage harness, so there are no
E900 manifest command repairs in scope for 062-05.

## E710 Burn-Down Batch Plan

No E710 burn-down batches are required for the cited run. No `062-06`
artifact-coverage migration batch is currently required while the strict-delta
inventory remains empty.

If a future regeneration finds E710 entries, create follow-up draft manifests
for bounded cohorts. Those drafts must strengthen validation commands and tests
so declared Python artifacts execute under coverage, or intentionally retire
stale contracts through the supersession workflow.

## Deferral Rationale

No contracts are deferred, retired, archived, or superseded by this inventory.
No artifact-coverage gate weakening is authorized or performed by 062-05.
