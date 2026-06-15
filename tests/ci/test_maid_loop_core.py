import json
import subprocess
from pathlib import Path
from unittest import mock

from tools.maid_loop_core import (
    CommitPacket,
    RetryLoopResult,
    ask_commit_approval,
    commit_ready_changes,
    find_implementable_drafts,
    git_status_short,
    parse_automation_status,
    parse_commit_packet,
    read_failure_packet,
    run_bounded_retry_loop,
    stage_commit_packet_files,
)


def test_discovery_excludes_epic_drafts(tmp_path: Path) -> None:
    child = tmp_path / "017-01-example.manifest.yaml"
    later_child = tmp_path / "017-02-example.manifest.yaml"
    epic = tmp_path / "000-example.epic.yaml"
    child.write_text("schema: '2'\n", encoding="utf-8")
    later_child.write_text("schema: '2'\n", encoding="utf-8")
    epic.write_text("schema: '2'\n", encoding="utf-8")

    assert find_implementable_drafts(tmp_path) == [child, later_child]


def test_status_and_commit_packet_parsing_preserves_existing_protocol() -> None:
    message = (
        "AUTOMATION_STATUS: READY\n"
        "AUTOMATION_STATUS: BLOCKED\n"
        "AUTOMATION_COMMIT_MESSAGE: test: selected draft\n"
        "AUTOMATION_COMMIT_FILES:\n"
        "- manifests/017-01-selected.manifest.yaml\n"
        "AUTOMATION_COMMIT_MESSAGE: feat: expanded scope\n"
        "AUTOMATION_COMMIT_FILES:\n"
        "- manifests/017-02-unselected.manifest.yaml\n"
        "- tools/codex_maid_loop.py\n"
        "AUTOMATION_STATUS: READY\n"
    )

    packet = parse_commit_packet(message)

    assert parse_automation_status(message) == "READY"
    assert isinstance(packet, CommitPacket)
    assert packet.message == "feat: expanded scope"
    assert packet.files == [
        "manifests/017-02-unselected.manifest.yaml",
        "tools/codex_maid_loop.py",
    ]
    assert parse_commit_packet("AUTOMATION_COMMIT_MESSAGE: missing files\n") is None
    assert CommitPacket(message="feat: x", files=["tools/x.py"]).message == "feat: x"
    assert CommitPacket(message="feat: x", files=["tools/x.py"]).files == ["tools/x.py"]


def test_stage_commit_packet_files_rejects_unsafe_paths(tmp_path: Path) -> None:
    with mock.patch("tools.maid_loop_core.subprocess.run") as run:
        result = stage_commit_packet_files(
            ["/absolute.py", "../escape.py"],
            root=tmp_path,
        )

    assert result == 1
    run.assert_not_called()


def test_read_failure_packet_returns_dict_or_none(tmp_path: Path) -> None:
    packet_path = tmp_path / "last-failure-packet.json"
    packet_path.write_text('{"packet_version": 1, "diagnostics": []}', encoding="utf-8")
    bad_json_path = tmp_path / "bad.json"
    bad_json_path.write_text("{not-json", encoding="utf-8")

    assert read_failure_packet(packet_path) == {
        "packet_version": 1,
        "diagnostics": [],
    }
    assert read_failure_packet(tmp_path / "missing.json") is None
    assert read_failure_packet(bad_json_path) is None


def test_bounded_retry_loop_stops_immediately_when_gate_passes(tmp_path: Path) -> None:
    attempts: list[dict | None] = []

    result = run_bounded_retry_loop(
        run_gate=lambda: 0,
        run_attempt=attempts.append,
        packet_path=tmp_path / "stale-packet.json",
    )

    assert isinstance(result, RetryLoopResult)
    assert result.attempts == 0
    assert result.success is True
    assert result.escalated is False
    assert result.final_packet is None
    assert attempts == []


def test_bounded_retry_loop_passes_packet_to_attempt_and_records_outcomes(
    tmp_path: Path,
    capsys,
) -> None:
    packet_path = tmp_path / "last-failure-packet.json"
    packets_seen: list[dict | None] = []
    gate_results = iter([1, 0])

    def run_gate() -> int:
        packet_path.write_text(
            json.dumps({"packet_version": 1, "diagnostics": [{"code": "E200"}]}),
            encoding="utf-8",
        )
        return next(gate_results)

    def run_attempt(packet: dict | None) -> str:
        packets_seen.append(packet)
        return "fixed E200"

    result = run_bounded_retry_loop(run_gate, run_attempt, packet_path)

    assert result == RetryLoopResult(
        attempts=1,
        success=True,
        escalated=False,
        final_packet={"packet_version": 1, "diagnostics": [{"code": "E200"}]},
    )
    assert packets_seen == [{"packet_version": 1, "diagnostics": [{"code": "E200"}]}]
    assert "attempt 1: fixed E200" in capsys.readouterr().out


def test_bounded_retry_loop_escalates_after_default_attempt_bound(
    tmp_path: Path,
) -> None:
    packet_path = tmp_path / "last-failure-packet.json"

    def run_gate() -> int:
        packet_path.write_text(
            json.dumps({"packet_version": 1, "diagnostics": [{"code": "E300"}]}),
            encoding="utf-8",
        )
        return 1

    result = run_bounded_retry_loop(
        run_gate=run_gate,
        run_attempt=lambda packet: "still failing",
        packet_path=packet_path,
    )

    assert result.attempts == 5
    assert result.success is False
    assert result.escalated is True
    assert result.final_packet == {
        "packet_version": 1,
        "diagnostics": [{"code": "E300"}],
    }


def test_git_commit_helpers_delegate_through_public_commit_packet(
    tmp_path: Path,
    monkeypatch,
) -> None:
    safe_file = tmp_path / "tools" / "core.py"
    safe_file.parent.mkdir()
    safe_file.write_text("print('ok')\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(args, cwd, text, capture_output, check):
        calls.append(args)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=" M x\n")

    monkeypatch.setattr("tools.maid_loop_core.subprocess.run", fake_run)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "commit")

    assert git_status_short(tmp_path) == " M x\n"
    assert (
        commit_ready_changes(
            CommitPacket(message="feat: add core", files=["tools/core.py"]),
            root=tmp_path,
        )
        == 0
    )
    assert ask_commit_approval(pass_number=3, status="READY") is True
    assert calls == [
        ["git", "status", "--short"],
        ["git", "add", "--", "tools/core.py"],
        ["git", "commit", "-m", "feat: add core"],
    ]

    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    assert ask_commit_approval(pass_number=3, status="READY") is False


def test_agent_retry_protocol_document_names_packet_cycle_and_escalation() -> None:
    text = Path("docs/agent-retry-protocol.md").read_text(encoding="utf-8")

    assert "--packet" in text
    assert "read the packet" in text
    assert "next_action" in text
    assert "re-run" in text
    assert "default 5" in text
    assert "human" in text
    assert "final packet" in text
    for key in (
        "packet_version",
        "command",
        "exit_code",
        "project_root",
        "manifest",
        "diagnostics",
        "test_output",
        "environment",
    ):
        assert key in text
