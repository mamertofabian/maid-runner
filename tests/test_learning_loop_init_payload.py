import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SKILLS = (
    "maid-planner",
    "maid-plan-review",
    "maid-implementer",
    "maid-implementation-review",
)
GENERIC_CODEX_SKILLS = [
    "maid-auditor",
    "maid-implementation-review",
    "maid-implementer",
    "maid-outcome-enrich",
    "maid-plan-review",
    "maid-planner",
]
REPO_INTERNAL_CODEX_SKILLS = (
    "maid-runner-cleanup-and-refactor",
    "maid-runner-draft-implement",
    "maid-runner-performance-optimization",
    "maid-runner-self-improvement",
    "maid-validate-hardening",
)
DIGEST_ANCHORS = (
    "Learning Evidence Digestion",
    "identify applicable lessons",
    "reject stale or irrelevant lessons",
    "state what changed because of the evidence",
)
PHASE_ANCHORS = {
    "maid-planner": (
        "manifest scope",
        "behavioral tests",
        "temptations",
        "open questions",
    ),
    "maid-plan-review": (
        "review findings",
        "approval questions",
        "requested revisions",
    ),
    "maid-implementer": (
        "focused tests",
        "implementation approach",
        "risk controls",
    ),
    "maid-implementation-review": (
        "review focus",
        "Outcome capture",
        "candidate follow-up work",
    ),
}


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _init_repo(tmp_path: Path, monkeypatch, tool: str) -> Path:
    from maid_runner.cli.commands._main import main

    repo = tmp_path / tool
    repo.mkdir()
    monkeypatch.chdir(repo)
    assert main(["init", "--tool", tool]) == 0
    return repo


def _assert_workflow_learning_loop(text: str) -> None:
    normalized = _normalized(text)
    normalized_lower = normalized.lower()
    for anchor in (
        "review recurring Outcome lessons with `maid insights`",
        "maid recall --for-manifest <path>",
        "maid recall --for-manifest <path> --plan-packet",
        "maid learn --include-status completed --include-status abandoned",
        "failed or abandoned Outcome lessons",
        "completed-only default",
    ):
        assert anchor in text
    for anchor in DIGEST_ANCHORS:
        assert anchor.lower() in normalized_lower
    for boundary in (
        "planning evidence only",
        "behavioral tests",
        "declared scope",
        "validation",
        "review",
        "do not create an approval, promotion, done, or review gate",
    ):
        assert boundary in normalized


def test_init_installs_learning_digest_workflow_skills(
    tmp_path: Path, monkeypatch
) -> None:
    claude_repo = _init_repo(tmp_path, monkeypatch, "claude")
    codex_repo = _init_repo(tmp_path, monkeypatch, "codex")

    for skill_name in WORKFLOW_SKILLS:
        claude_text = (
            claude_repo / ".claude" / "skills" / skill_name / "SKILL.md"
        ).read_text(encoding="utf-8")
        codex_text = (
            codex_repo / ".codex" / "skills" / skill_name / "SKILL.md"
        ).read_text(encoding="utf-8")

        _assert_workflow_learning_loop(claude_text)
        _assert_workflow_learning_loop(codex_text)
        for phase_anchor in PHASE_ANCHORS[skill_name]:
            assert phase_anchor in claude_text
            assert phase_anchor in codex_text


def test_init_generated_guidance_requires_learning_digest(
    tmp_path: Path, monkeypatch
) -> None:
    claude_repo = _init_repo(tmp_path, monkeypatch, "claude")
    codex_repo = _init_repo(tmp_path, monkeypatch, "codex")

    for guidance_path in (claude_repo / "CLAUDE.md", codex_repo / "AGENTS.md"):
        guidance = guidance_path.read_text(encoding="utf-8")
        normalized = _normalized(guidance)

        assert "related Outcome evidence" in guidance
        assert "name applicable lessons" in guidance
        assert "reject stale or irrelevant lessons with a reason" in guidance
        assert "state what changed because of the evidence" in guidance
        assert "raw recall or insights transcript" in guidance
        for boundary in (
            "advisory planning context only",
            "does not expand scope",
            "replace red evidence",
            "behavioral validation",
            "plan lock",
            "implementation validation",
            "review",
        ):
            assert boundary in normalized


def test_init_installed_docs_close_the_outcome_learning_loop(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _init_repo(tmp_path, monkeypatch, "codex")

    installed_docs = {
        "draft": (repo / "docs" / "draft-manifest-workflow.md").read_text(
            encoding="utf-8"
        ),
        "outcome": (repo / "docs" / "manifest-outcome-records.md").read_text(
            encoding="utf-8"
        ),
        "readme": (repo / "manifests" / "drafts" / "README.md").read_text(
            encoding="utf-8"
        ),
    }

    for text in installed_docs.values():
        normalized = _normalized(text)
        assert "close the loop" in normalized
        assert "completed Outcome records" in text
        assert "current agent decisions" in text
        assert "applicable lessons" in text
        assert "stale or irrelevant lessons" in text
        assert "what changed because of the evidence" in text
        assert "advisory" in normalized
        assert "does not replace" in normalized

    assert "manifest scope" in installed_docs["draft"]
    assert "implementation risks" in installed_docs["draft"]
    assert "review focus" in installed_docs["draft"]
    assert "follow-up work" in installed_docs["draft"]


def test_agent_skill_docs_describe_current_init_distribution() -> None:
    text = _read("docs/agent-skills.md")
    normalized = _normalized(text)

    assert "maid init --tool claude" in text
    assert "maid init --tool codex" in text
    assert "maid-auditor" in text
    assert "Repo-internal maid-runner skills remain packaged" in text
    assert "excluded from the distributable list" in text
    assert "Learning evidence digestion" in text
    assert "applicable lessons" in text
    assert "rejected stale or irrelevant lessons" in text
    assert "what changed because of the evidence" in text
    for phase_term in (
        "manifest scope",
        "behavioral tests",
        "review findings",
        "implementation approach",
        "review focus",
        "follow-up work",
    ):
        assert phase_term in normalized


def test_learning_digest_payload_sources_and_packages_match() -> None:
    for relative_path in (
        "docs/draft-manifest-workflow.md",
        "docs/manifest-outcome-records.md",
        "manifests/drafts/README.md",
    ):
        assert _read(f"maid_runner/{relative_path}") == _read(relative_path)

    for tool in ("claude", "codex"):
        source = _read(f".{tool}/skills/maid-onboard/SKILL.md")
        packaged = _read(f"maid_runner/user_skills/{tool}/maid-onboard/SKILL.md")
        assert packaged == source
        assert "Outcome learning-digestion workflow" in packaged
        assert "maid init" in packaged
        assert "`maid-auditor`" in packaged
        assert (
            "only the 6 generic skills, including maid-auditor and maid-outcome-enrich"
            in packaged
        )
        assert "only the 4 generic skills" not in packaged


def test_init_learning_digest_guidance_stays_advisory(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _init_repo(tmp_path, monkeypatch, "codex")
    manifest = json.loads((repo / ".codex" / "manifest.json").read_text())
    skills_dir = repo / ".codex" / "skills"
    agents_md = (repo / "AGENTS.md").read_text(encoding="utf-8")
    all_guidance = "\n".join(
        [
            agents_md,
            (repo / "docs" / "draft-manifest-workflow.md").read_text(encoding="utf-8"),
            (repo / "docs" / "manifest-outcome-records.md").read_text(encoding="utf-8"),
            (repo / "manifests" / "drafts" / "README.md").read_text(encoding="utf-8"),
        ]
    )
    normalized_guidance = _normalized(all_guidance)

    assert sorted(manifest["skills"]["distributable"]) == GENERIC_CODEX_SKILLS
    assert sorted(path.name for path in skills_dir.iterdir()) == GENERIC_CODEX_SKILLS
    for internal_skill in REPO_INTERNAL_CODEX_SKILLS:
        assert internal_skill not in manifest["skills"]["distributable"]
        assert not (skills_dir / internal_skill).exists()
        assert internal_skill not in agents_md

    assert "Recall is advisory planning context only" in all_guidance
    assert "does not expand scope" in normalized_guidance
    assert "does not replace behavioral tests" in normalized_guidance
    assert "do not create an approval, promotion, done, or review gate" in all_guidance
    for forbidden in (
        "recall approval gate",
        "insights approval gate",
        "learning digestion gate",
    ):
        assert forbidden not in all_guidance.lower()
