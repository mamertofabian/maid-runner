from argparse import Namespace
from pathlib import Path

from maid_runner.cli.commands.howto import cmd_howto


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
WORKFLOW_DOC = ROOT / "docs/draft-manifest-workflow.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return " ".join(text.split())


def test_workflow_doc_describes_from_diff_draft_promotion_boundary() -> None:
    workflow = _read(WORKFLOW_DOC)

    assert "maid manifest from-diff" in workflow
    assert "manifests/drafts/<slug>.manifest.yaml" in workflow
    assert "metadata.needs_review: true" in workflow
    assert "do not self-promote" in workflow
    assert "clears `needs_review: true`" in workflow
    assert "does not guess `main`, `dev`, or a remote branch" in workflow


def test_readme_quick_start_presents_brownfield_entry() -> None:
    readme = _read(README)
    normalized = _normalize(readme)

    assert "Brownfield entry" in readme
    assert "maid bootstrap --rank" in readme
    assert "maid manifest from-diff" in readme
    assert "reviewed drafts per change" in readme
    assert "Generated manifests land in `manifests/drafts/`" in normalized


def test_howto_content_covers_rank_from_diff_and_baseline_rule(capsys) -> None:
    exit_code = cmd_howto(Namespace(topic="commands"))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "maid bootstrap --rank" in output
    assert "maid manifest from-diff" in output
    assert "Exactly one of --since, --base-ref, or --worktree is required" in output
    assert "metadata.needs_review: true" in output
    assert "orders by churn descending" in output
    assert "inbound_refs descending" in output
    assert "public_artifacts descending" in output
    assert "path ascending" in output
