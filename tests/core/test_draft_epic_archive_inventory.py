from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKLOG_PATH = REPO_ROOT / "docs" / "plans" / "maid-runner-self-improvement-backlog.md"

CONSUMED_EPICS = {
    "092-00-coverage-priority-recommender.epic.yaml": (
        "092-01-add-risk-v1-coverage-recommendations.manifest.yaml",
        "092-02-add-validator-risk-analysis-hooks.manifest.yaml",
        "092-03-add-coverage-risk-policy-cache-and-deep-evidence.manifest.yaml",
        "092-04-align-risk-v1-guidance.manifest.yaml",
    ),
    "095-00-onboarding-entry-point-wiring.epic.yaml": (
        "095-01-wire-guidance-to-cli-entry-points.manifest.yaml",
        "095-02-add-verify-profile-presets.manifest.yaml",
        "095-03-migrate-generated-hook-to-verify-profile.manifest.yaml",
        "095-04-migrate-generated-profile-payloads.manifest.yaml",
        "095-05-complete-profile-guidance-and-archive-adoption-epics.manifest.yaml",
    ),
    "097-00-cross-repository-maid-feedback.epic.yaml": (
        "097-01-export-local-maid-feedback-bundle.manifest.yaml",
        "097-02-validate-and-aggregate-maid-feedback-bundles.manifest.yaml",
        "097-03-route-confirmed-feedback-into-self-improvement.manifest.yaml",
    ),
    "067-00-plan-lock-and-red-phase-evidence.epic.yaml": (
        "067-01-add-plan-lock-storage-and-cli.manifest.yaml",
        "067-02-capture-red-phase-evidence-on-lock.manifest.yaml",
        "067-03-enforce-plan-lock-in-verify.manifest.yaml",
        "067-04-document-plan-lock-workflow.manifest.yaml",
        "067-05-scope-plan-lock-enforcement-to-changed-manifests.manifest.yaml",
        "067-06-cross-check-red-evidence-commands.manifest.yaml",
        "067-07-fix-handoff-gate-baseline-resolution.manifest.yaml",
        "067-08-preserve-red-evidence-on-plan-revise.manifest.yaml",
    ),
    "077-00-skills-exploit-outcome-learning-loop.epic.yaml": (
        "077-01-add-insights-cadence-to-maid-auditor.manifest.yaml",
        "077-02-activate-learning-loop-guidance-in-workflow-skills.manifest.yaml",
        "077-03-add-related-match-recall-scoring.manifest.yaml",
        "077-04-sync-init-payloads-with-learning-digestion.manifest.yaml",
    ),
    "081-00-outcome-llm-enrichment.epic.yaml": (
        "081-01-add-outcome-enrichment-core.manifest.yaml",
        "081-02-add-maid-enrich-command.manifest.yaml",
        "081-03-wire-theme-map-into-insights.manifest.yaml",
        "081-04-add-outcome-enrich-skill.manifest.yaml",
        "081-05-harden-enrichment-prompt-and-quality.manifest.yaml",
        "081-06-planner-prefers-theme-map-insights.manifest.yaml",
    ),
    "083-00-close-outcome-enrichment-consumption-loop.epic.yaml": (
        "083-01-report-stale-digest-on-learn.manifest.yaml",
        "083-02-point-planner-at-digest-narrative.manifest.yaml",
        "083-03-add-theme-aware-recall.manifest.yaml",
        "083-04-converge-lesson-type-vocabulary-at-capture.manifest.yaml",
        "083-05-feed-digest-into-self-improvement-audit.manifest.yaml",
        "083-06-harden-enrich-staleness-flags-and-prompt-scaling.manifest.yaml",
        "083-07-add-improvement-hypotheses-channel.manifest.yaml",
        "083-08-align-recall-stale-digest-flag.manifest.yaml",
    ),
    "084-00-after-action-run-evaluation.epic.yaml": (
        "084-01-add-agent-provenance-to-outcome-records.manifest.yaml",
        "084-02-capture-agent-provenance-in-plan-locks.manifest.yaml",
        "084-03-record-contract-deltas-in-lock-revisions.manifest.yaml",
        "084-04-add-maid-evaluate-run-command.manifest.yaml",
        "084-05-add-maid-evaluate-compare-aggregation.manifest.yaml",
        "084-06-add-run-review-enrichment-pipeline.manifest.yaml",
        "084-07-add-maid-run-review-skill-and-docs.manifest.yaml",
    ),
    "085-00-plan-lock-ceremony-reduction.epic.yaml": (
        "085-01-recognize-django-tests-py-test-modules.manifest.yaml",
        "085-02-preserve-red-evidence-on-contract-preserving-revisions.manifest.yaml",
        "085-03-contract-scoped-plan-lock-manifest-hash.manifest.yaml",
        "085-04-test-only-green-red-evidence-mode.manifest.yaml",
        "085-05-stash-implementation-session-robustness.manifest.yaml",
        "085-06-review-convergence-and-iteration-guidance.manifest.yaml",
        "085-07-ast-scoped-behavioral-test-hash.manifest.yaml",
    ),
}

LIVE_PLANNING_EPICS = {
    "062-00-strict-by-default-validation-gates.epic.yaml",
    "064-00-daemon-first-agent-validation.epic.yaml",
    "096-00-bound-directory-artifact-coverage.epic.yaml",
}

ARCHIVE_BOUNDARY_PHRASES = {
    "097-00-cross-repository-maid-feedback.epic.yaml": (
        "privacy-bounded",
        "local-only",
        "no network transport",
        "advisory evidence",
    ),
}


def _draft_path(name: str) -> Path:
    return REPO_ROOT / "manifests" / "drafts" / name


def _load_manifest(name: str) -> tuple[str, dict]:
    text = _draft_path(name).read_text(encoding="utf-8")
    return text, yaml.safe_load(text)


def test_consumed_epic_drafts_are_archived_pointers_to_promoted_children():
    for name, child_manifest_names in CONSUMED_EPICS.items():
        text, manifest = _load_manifest(name)

        assert text.startswith("# archive-kind: consumed-draft-epic\n")
        assert not text.startswith("# draft-kind: epic\n")
        assert manifest["metadata"]["status"] == "archived"
        assert (
            "Do not promote or implement this archived epic." in manifest["description"]
        )

        read_paths = set(manifest["files"]["read"])
        expected_child_paths = {
            f"manifests/{child_manifest_name}"
            for child_manifest_name in child_manifest_names
        }
        assert read_paths == expected_child_paths

        for phrase in ARCHIVE_BOUNDARY_PHRASES.get(name, ()):
            assert phrase in text.lower()

        for child_path in expected_child_paths:
            assert (REPO_ROOT / child_path).exists()


def test_only_unconsumed_epics_remain_live_planning_inventory():
    live_planning_names = set()

    for path in (REPO_ROOT / "manifests" / "drafts").glob("*.epic.yaml"):
        text = path.read_text(encoding="utf-8")
        if text.startswith("# draft-kind: epic\n"):
            manifest = yaml.safe_load(text)
            if manifest["metadata"]["status"] == "planning":
                live_planning_names.add(path.name)

    assert live_planning_names == LIVE_PLANNING_EPICS


def test_self_improvement_backlog_no_longer_describes_consumed_epics_as_stale():
    backlog = BACKLOG_PATH.read_text(encoding="utf-8")

    stale_phrases = (
        "067 plan locks & red-phase evidence** (fully consumed, epic file still",
        "077 outcome learning loop in skills** (fully consumed, epic stale)",
        "081 outcome LLM enrichment** (fully consumed, epic stale)",
        "067/077/081 still `status: planning`",
    )

    for phrase in stale_phrases:
        assert phrase not in backlog

    assert (
        "067 plan locks & red-phase evidence** (consumed/archived by Theme 8)"
        in backlog
    )
    assert (
        "077 outcome learning loop in skills** (consumed/archived by Theme 8)"
        in backlog
    )
    assert "081 outcome LLM enrichment** (consumed/archived by Theme 8)" in backlog
