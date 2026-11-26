"""Behavioral tests for Antigravity PreToolUse envelopes and output format in `maid hook scope-check`."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.cli.commands.hook import cmd_hook


def _write_active_manifest(project_root: Path, relative_path: str) -> None:
    path = project_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """schema: "2"
goal: "Demo Antigravity hook task"
type: feature
created: "2026-11-26T12:40:00Z"
files:
  edit:
    - path: src/allowed.py
      artifacts:
        - kind: function
          name: allowed
  read:
    - src/read_only.py
validate:
  - uv run python -m pytest -q tests/cli/test_hook_antigravity_envelope.py
"""
    )


def _write_active_task_file(project_root: Path, manifest_rel: str) -> None:
    active_file = project_root / ".maid" / "active-manifest"
    active_file.parent.mkdir(parents=True, exist_ok=True)
    active_file.write_text(f"{manifest_rel}\n")


def _parse_single_json_line(output: str) -> dict:
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert isinstance(payload, dict)
    return payload


def _antigravity_envelope(
    tool_name: str, args: dict[str, object], cwd: str | None = None
) -> str:
    payload: dict[str, object] = {
        "hookEventName": "PreToolUse",
        "stepIdx": 7,
        "toolCall": {
            "id": "toolu_agy_01",
            "name": tool_name,
            "args": args,
        },
    }
    if cwd is not None:
        payload["cwd"] = cwd
    return json.dumps(payload)


def test_build_parser_registers_hook_scope_check_format_option() -> None:
    parser = build_parser()

    default_args = parser.parse_args(["hook", "scope-check", "--stdin"])
    agy_args = parser.parse_args(
        ["hook", "scope-check", "--stdin", "--format", "antigravity"]
    )
    explicit_default = parser.parse_args(
        ["hook", "scope-check", "--path", "src/allowed.py", "--format", "default"]
    )

    assert default_args.format == "default"
    assert agy_args.format == "antigravity"
    assert explicit_default.format == "default"

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["hook", "scope-check", "--stdin", "--format", "unknown"])
    assert exc_info.value.code == 2


def test_scope_check_accepts_antigravity_pretooluse_envelopes_with_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    agents_dir = repo / ".agents"
    agents_dir.mkdir(parents=True)
    _write_active_manifest(repo, "manifests/demo.manifest.yaml")
    _write_active_task_file(repo, "manifests/demo.manifest.yaml")
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)
    # Antigravity runs command hooks with CWD set to the folder containing hooks.json.
    monkeypatch.chdir(agents_dir)

    for tool_name, arg_key in (
        ("write_file", "Path"),
        ("edit_file", "Path"),
        ("replace_file_content", "TargetFile"),
        ("custom_write", "path"),
        ("custom_edit", "file_path"),
    ):
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(
                _antigravity_envelope(
                    tool_name,
                    {arg_key: str(repo / "src" / "allowed.py")},
                    cwd=str(repo),
                )
            ),
        )
        exit_code = main(["hook", "scope-check", "--stdin", "--format", "antigravity"])
        payload = _parse_single_json_line(capsys.readouterr().out)

        assert exit_code == 0
        assert set(payload) == {"decision", "reason"}
        assert payload == {"decision": "allow", "reason": "in-scope"}

    # Relative target path must resolve against stdin `cwd`, not process CWD (`.agents/`).
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "edit_file",
                {"Path": "src/allowed.py"},
                cwd=str(repo),
            )
        ),
    )
    rel_exit = main(["hook", "scope-check", "--stdin", "--format", "antigravity"])
    rel_payload = _parse_single_json_line(capsys.readouterr().out)
    assert rel_exit == 0
    assert rel_payload == {"decision": "allow", "reason": "in-scope"}

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "edit_file",
                {"Path": str(repo / "src" / "read_only.py")},
                cwd=str(repo),
            )
        ),
    )
    deny_exit = main(["hook", "scope-check", "--stdin", "--format", "antigravity"])
    denied = _parse_single_json_line(capsys.readouterr().out)

    assert deny_exit == 0
    assert set(denied) == {"decision", "reason"}
    assert denied["decision"] == "deny"
    assert "manifests/demo.manifest.yaml" in denied["reason"]
    assert "src/allowed.py" in denied["reason"]


def test_scope_check_antigravity_envelope_default_format_preserves_legacy_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    agents_dir = repo / ".agents"
    agents_dir.mkdir(parents=True)
    _write_active_manifest(repo, "manifests/demo.manifest.yaml")
    _write_active_task_file(repo, "manifests/demo.manifest.yaml")
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)
    monkeypatch.chdir(agents_dir)

    # Also verifies backward compatibility when callers omit `format` on args.
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "edit_file",
                {"Path": str(repo / "src" / "allowed.py")},
                cwd=str(repo),
            )
        ),
    )
    allow_args = SimpleNamespace(
        hook_command="scope-check",
        stdin=True,
        path=None,
        strict=False,
    )
    assert cmd_hook(allow_args) == 0
    allow_payload = _parse_single_json_line(capsys.readouterr().out)
    assert allow_payload == {
        "decision": "allow",
        "reason": "in-scope",
        "active_manifest": "manifests/demo.manifest.yaml",
    }

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "write_file",
                {"Path": str(repo / "src" / "read_only.py")},
                cwd=str(repo),
            )
        ),
    )
    assert main(["hook", "scope-check", "--stdin", "--format", "default"]) == 2
    deny_payload = _parse_single_json_line(capsys.readouterr().out)
    assert set(deny_payload) == {"decision", "reason", "active_manifest"}
    assert deny_payload["decision"] == "deny"
    assert deny_payload["active_manifest"] == "manifests/demo.manifest.yaml"


def test_scope_check_antigravity_format_respects_outside_root_and_subdir_cwd_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    agents_dir = repo / ".agents"
    subdir = repo / "sub"
    agents_dir.mkdir(parents=True)
    subdir.mkdir(parents=True)
    _write_active_manifest(repo, "manifests/demo.manifest.yaml")
    _write_active_task_file(repo, "manifests/demo.manifest.yaml")
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)
    monkeypatch.chdir(agents_dir)

    outside_file = tmp_path / "external_notes.md"
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "write_file",
                {"Path": str(outside_file)},
                cwd=str(repo),
            )
        ),
    )
    assert (
        main(["hook", "scope-check", "--stdin", "--strict", "--format", "antigravity"])
        == 0
    )
    outside_payload = _parse_single_json_line(capsys.readouterr().out)
    assert outside_payload == {
        "decision": "allow",
        "reason": "outside-project-root",
    }

    # Subdirectory cwd does not own manifests/, so undeclared repo files must still deny under --strict.
    monkeypatch.setenv(
        "MAID_ACTIVE_MANIFEST", str(repo / "manifests" / "demo.manifest.yaml")
    )
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "edit_file",
                {"Path": str(repo / "src" / "read_only.py")},
                cwd=str(subdir),
            )
        ),
    )
    assert (
        main(["hook", "scope-check", "--stdin", "--strict", "--format", "antigravity"])
        == 0
    )
    subdir_payload = _parse_single_json_line(capsys.readouterr().out)
    assert set(subdir_payload) == {"decision", "reason"}
    assert subdir_payload["decision"] == "deny"
    assert subdir_payload["reason"].startswith("out-of-scope for ")
    assert "manifests/demo.manifest.yaml" in subdir_payload["reason"]


def test_scope_check_antigravity_format_no_active_task_and_internal_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    agents_dir = repo / ".agents"
    agents_dir.mkdir(parents=True)
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)
    monkeypatch.chdir(agents_dir)

    # No active task: fail-open by default, deny under --strict; exit 0 in both cases.
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "write_file",
                {"Path": str(repo / "src" / "anything.py")},
                cwd=str(repo),
            )
        ),
    )
    assert main(["hook", "scope-check", "--stdin", "--format", "antigravity"]) == 0
    assert _parse_single_json_line(capsys.readouterr().out) == {
        "decision": "allow",
        "reason": "no-active-task",
    }

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "write_file",
                {"Path": str(repo / "src" / "anything.py")},
                cwd=str(repo),
            )
        ),
    )
    assert (
        main(["hook", "scope-check", "--stdin", "--strict", "--format", "antigravity"])
        == 0
    )
    assert _parse_single_json_line(capsys.readouterr().out) == {
        "decision": "deny",
        "reason": "no-active-task",
    }

    # Explicit `cwd: null` falls back to process CWD (repo root).
    monkeypatch.chdir(repo)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "hookEventName": "PreToolUse",
                    "cwd": None,
                    "toolCall": {
                        "name": "write_file",
                        "args": {"Path": str(repo / "src" / "anything.py")},
                    },
                }
            )
        ),
    )
    assert main(["hook", "scope-check", "--stdin", "--format", "antigravity"]) == 0
    assert _parse_single_json_line(capsys.readouterr().out) == {
        "decision": "allow",
        "reason": "no-active-task",
    }
    monkeypatch.chdir(agents_dir)

    # Malformed envelopes: empty Path, missing path keys, empty/whitespace/falsy/non-string cwd.
    for bad_envelope in (
        _antigravity_envelope("write_file", {"Path": ""}, cwd=str(repo)),
        _antigravity_envelope("write_file", {"Content": "hello"}, cwd=str(repo)),
        _antigravity_envelope(
            "write_file",
            {"Path": str(repo / "src" / "anything.py")},
            cwd="",
        ),
        _antigravity_envelope(
            "write_file",
            {"Path": str(repo / "src" / "anything.py")},
            cwd="   ",
        ),
        json.dumps(
            {
                "hookEventName": "PreToolUse",
                "cwd": False,
                "toolCall": {
                    "name": "write_file",
                    "args": {"Path": str(repo / "src" / "anything.py")},
                },
            }
        ),
        json.dumps(
            {
                "hookEventName": "PreToolUse",
                "cwd": 123,
                "toolCall": {
                    "name": "write_file",
                    "args": {"Path": str(repo / "src" / "anything.py")},
                },
            }
        ),
    ):
        monkeypatch.setattr("sys.stdin", io.StringIO(bad_envelope))
        assert main(["hook", "scope-check", "--stdin", "--format", "antigravity"]) == 0
        fail_open = _parse_single_json_line(capsys.readouterr().out)
        assert set(fail_open) == {"decision", "reason"}
        assert fail_open["decision"] == "allow"
        assert fail_open["reason"].startswith("internal-error:")

        monkeypatch.setattr("sys.stdin", io.StringIO(bad_envelope))
        assert (
            main(
                [
                    "hook",
                    "scope-check",
                    "--stdin",
                    "--strict",
                    "--format",
                    "antigravity",
                ]
            )
            == 0
        )
        fail_closed = _parse_single_json_line(capsys.readouterr().out)
        assert set(fail_closed) == {"decision", "reason"}
        assert fail_closed["decision"] == "deny"
        assert fail_closed["reason"].startswith("internal-error:")

    # Missing/unloadable active manifest exercises scope_check_path's internal-error return branch.
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", "manifests/missing.manifest.yaml")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "write_file",
                {"Path": str(repo / "src" / "anything.py")},
                cwd=str(repo),
            )
        ),
    )
    assert main(["hook", "scope-check", "--stdin", "--format", "antigravity"]) == 0
    missing_open = _parse_single_json_line(capsys.readouterr().out)
    assert set(missing_open) == {"decision", "reason"}
    assert missing_open["decision"] == "allow"
    assert missing_open["reason"].startswith("internal-error:")

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "write_file",
                {"Path": str(repo / "src" / "anything.py")},
                cwd=str(repo),
            )
        ),
    )
    assert (
        main(
            [
                "hook",
                "scope-check",
                "--stdin",
                "--strict",
                "--format",
                "antigravity",
            ]
        )
        == 0
    )
    missing_closed = _parse_single_json_line(capsys.readouterr().out)
    assert set(missing_closed) == {"decision", "reason"}
    assert missing_closed["decision"] == "deny"
    assert missing_closed["reason"].startswith("internal-error:")
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)

    # Corrupt .maid/active-manifest state still emits one antigravity JSON object.
    corrupt_active = repo / ".maid" / "active-manifest"
    corrupt_active.mkdir(parents=True)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            _antigravity_envelope(
                "write_file",
                {"Path": str(repo / "src" / "anything.py")},
                cwd=str(repo),
            )
        ),
    )
    assert main(["hook", "scope-check", "--stdin", "--format", "antigravity"]) == 0
    corrupt_payload = _parse_single_json_line(capsys.readouterr().out)
    assert set(corrupt_payload) == {"decision", "reason"}
    assert corrupt_payload["decision"] == "allow"
    assert corrupt_payload["reason"].startswith("internal-error:")

    # Programmatic invalid format falls through internal-error handling cleanly.
    invalid_fmt_args = SimpleNamespace(
        hook_command="scope-check",
        stdin=False,
        path=str(repo / "src" / "anything.py"),
        strict=False,
        format="bogus",
    )
    assert cmd_hook(invalid_fmt_args) == 1
    invalid_fmt_payload = _parse_single_json_line(capsys.readouterr().out)
    assert set(invalid_fmt_payload) == {"decision", "reason", "active_manifest"}
    assert invalid_fmt_payload["decision"] == "allow"
    assert invalid_fmt_payload["reason"].startswith("internal-error:")
