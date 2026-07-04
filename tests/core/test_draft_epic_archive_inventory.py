from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKLOG_PATH = REPO_ROOT / "docs" / "plans" / "maid-runner-self-improvement-backlog.md"

CONSUMED_EPICS = {
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
}

LIVE_PLANNING_EPICS = {
    "062-00-strict-by-default-validation-gates.epic.yaml",
    "064-00-daemon-first-agent-validation.epic.yaml",
    "083-00-close-outcome-enrichment-consumption-loop.epic.yaml",
    "084-00-after-action-run-evaluation.epic.yaml",
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
        for child_manifest_name in child_manifest_names:
            child_path = f"manifests/{child_manifest_name}"
            assert child_path in read_paths
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
