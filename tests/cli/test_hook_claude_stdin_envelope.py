"""Regression coverage for Claude Code hook stdin envelopes."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands.hook import cmd_hook


def _write_active_manifest(project_root: Path, relative_path: str) -> None:
    path = project_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """schema: "2"
goal: "Demo Claude hook task"
type: feature
created: "2026-06-24T04:00:00Z"
files:
  edit:
    - path: src/lib/seo/canonical.ts
      artifacts:
        - kind: function
          name: canonical
validate:
  - uv run python -m pytest -q tests/cli/test_hook_claude_stdin_envelope.py
"""
    )


def _payload(output: str) -> dict:
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert set(payload) == {"decision", "reason", "active_manifest"}
    return payload


def test_scope_check_accepts_claude_pretooluse_stdin_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", "manifests/demo.manifest.yaml")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "src/lib/seo/canonical.ts"},
                }
            )
        ),
    )
    _write_active_manifest(tmp_path, "manifests/demo.manifest.yaml")
    args = SimpleNamespace(
        hook_command="scope-check",
        stdin=True,
        path=None,
        strict=False,
    )

    exit_code = cmd_hook(args)
    payload = _payload(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == {
        "decision": "allow",
        "reason": "in-scope",
        "active_manifest": "manifests/demo.manifest.yaml",
    }
