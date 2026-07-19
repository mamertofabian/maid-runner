"""Ground-truth provenance injection coverage for the Codex MAID loop."""

from __future__ import annotations

import sys
from pathlib import Path

from tools import codex_maid_loop


def test_agent_provenance_env_returns_ground_truth_mapping() -> None:
    assert codex_maid_loop.agent_provenance_env("gpt-5.5", "medium") == {
        "MAID_AGENT_MODEL": "gpt-5.5",
        "MAID_AGENT_REASONING_EFFORT": "medium",
        "MAID_AGENT_PROVIDER": "openai",
        "MAID_AGENT_CLIENT": "codex-cli",
    }


def test_run_codex_json_command_injects_extra_env_into_child(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("MAID_AGENT_MODEL", raising=False)
    script = tmp_path / "child.py"
    script.write_text(
        "import os; print(os.environ.get('MAID_AGENT_MODEL', 'absent'))\n"
    )
    output = tmp_path / "run.jsonl"
    result = codex_maid_loop.run_codex_json_command(
        [sys.executable, str(script)],
        output,
        tmp_path / "run.err",
        tmp_path / "final.md",
        False,
        extra_env={"MAID_AGENT_MODEL": "gpt-5.5"},
    )
    assert result.returncode == 0
    assert "gpt-5.5" in output.read_text()

    absent_output = tmp_path / "absent.jsonl"
    absent = codex_maid_loop.run_codex_json_command(
        [sys.executable, str(script)],
        absent_output,
        tmp_path / "absent.err",
        tmp_path / "absent.final.md",
        False,
    )
    assert absent.returncode == 0
    assert "absent" in absent_output.read_text()


def test_implementation_prompt_instructs_env_sourced_outcome_agent(
    tmp_path: Path,
) -> None:
    command = codex_maid_loop.build_implementation_command(
        "codex", tmp_path / "final.md", [Path("manifests/drafts/example.manifest.yaml")]
    )
    assert "MAID_AGENT_MODEL" in command[-1]
    assert "MAID_AGENT_REASONING_EFFORT" in command[-1]
    assert "ground truth" in command[-1]
