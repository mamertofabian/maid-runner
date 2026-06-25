from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_TERMS = (
    "manifests/drafts/*.manifest.yaml",
    "manifests/drafts/*.epic.yaml",
    "split-before-promote",
    "archived",
    "uv run maid manifest promote manifests/drafts/<slug>.manifest.yaml",
    "Do not manually move or copy draft manifests",
    'uv run maid plan revise <manifest> --reason "<text>" --preserve-red-evidence',
)

STALE_PROMOTION_TERMS = (
    "Promote by moving",
    "Promote one implementation-sized draft into `manifests/`",
    "Promote one implementation-sized draft by moving it",
    "Promote by moving the draft manifest from `manifests/drafts/` to `manifests/`",
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _assert_sanctioned_workflow(text: str) -> None:
    for term in WORKFLOW_TERMS:
        assert term in text
    for stale_term in STALE_PROMOTION_TERMS:
        assert stale_term not in text


def test_init_installs_local_draft_workflow_docs_and_readme(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "codex"]) == 0

    installed_workflow = (tmp_path / "docs/draft-manifest-workflow.md").read_text(
        encoding="utf-8"
    )
    installed_outcome = (tmp_path / "docs/manifest-outcome-records.md").read_text(
        encoding="utf-8"
    )
    installed_readme = (tmp_path / "manifests/drafts/README.md").read_text(
        encoding="utf-8"
    )

    _assert_sanctioned_workflow(installed_workflow)
    _assert_sanctioned_workflow(installed_readme)
    assert "After Outcome capture, run `uv run maid learn`" in installed_outcome
    assert "docs/manifest-outcome-records.md" in installed_workflow
    assert "../../docs/manifest-outcome-records.md" in installed_readme


def test_init_generated_agent_guidance_matches_draft_epic_workflow(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands._main import main

    claude_repo = tmp_path / "claude"
    codex_repo = tmp_path / "codex"
    claude_repo.mkdir()
    codex_repo.mkdir()

    monkeypatch.chdir(claude_repo)
    assert main(["init", "--tool", "claude"]) == 0
    claude_guidance = (claude_repo / "CLAUDE.md").read_text(encoding="utf-8")

    monkeypatch.chdir(codex_repo)
    assert main(["init", "--tool", "codex"]) == 0
    codex_guidance = (codex_repo / "AGENTS.md").read_text(encoding="utf-8")

    for guidance in (claude_guidance, codex_guidance):
        _assert_sanctioned_workflow(guidance)
        assert "epic planning records" in guidance
        assert "Capture Outcome after implementation review" in guidance
        assert "After Outcome capture, run `uv run maid learn`" in guidance
        assert "docs/draft-manifest-workflow.md" in guidance
        assert "docs/manifest-outcome-records.md" in guidance


def test_packaged_workflow_docs_match_source_docs() -> None:
    package_data = tomllib.loads(_read("pyproject.toml"))["tool"]["setuptools"][
        "package-data"
    ]["maid_runner"]

    for pattern in (
        "docs/draft-manifest-workflow.md",
        "docs/manifest-outcome-records.md",
        "manifests/drafts/README.md",
    ):
        assert pattern in package_data

    assert _read("maid_runner/docs/draft-manifest-workflow.md") == _read(
        "docs/draft-manifest-workflow.md"
    )
    assert _read("maid_runner/docs/manifest-outcome-records.md") == _read(
        "docs/manifest-outcome-records.md"
    )
    assert _read("maid_runner/manifests/drafts/README.md") == _read(
        "manifests/drafts/README.md"
    )
