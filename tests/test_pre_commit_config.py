"""Behavioral contract for the repository's pre-commit hook configuration."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / ".pre-commit-config.yaml"


def _hooks() -> list[dict]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return [hook for repo in config["repos"] for hook in repo["hooks"]]


def test_pre_commit_uses_single_fail_fast_maid_verify_gate() -> None:
    hooks = _hooks()
    hooks_by_id = {hook["id"]: hook for hook in hooks}

    assert "maid-validate" not in hooks_by_id
    assert "maid-test" not in hooks_by_id
    assert hooks_by_id["maid-verify"] == {
        "id": "maid-verify",
        "name": "MAID verification (fail-fast handoff gates)",
        "entry": (
            "uv run maid verify --profile handoff --fail-fast --no-changed-scope"
        ),
        "language": "system",
        "pass_filenames": False,
        "always_run": True,
        "stages": ["pre-commit"],
    }


def test_pre_commit_preserves_format_lint_and_sync_hooks() -> None:
    hooks = _hooks()

    assert [hook["id"] for hook in hooks] == [
        "black",
        "ruff",
        "maid-verify",
        "sync-claude",
    ]
    assert hooks[0]["entry"] == "uv run black"
    assert hooks[1]["entry"] == "uv run ruff check"
    assert hooks[3]["entry"] == "make sync-claude"
    assert hooks[3]["files"] == r"^\.claude/"
