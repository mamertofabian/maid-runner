"""Behavioral regressions for deep-verification cache and timeout safety."""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import main
from tests.cli.test_verify_deep_evidence_reuse import _write_project


def test_invalid_cached_coverage_payloads_are_rejected_and_reexecuted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log, assertion="assert True")
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    monkeypatch.chdir(tmp_path)
    packet_path = tmp_path.parent / f"{tmp_path.name}-failure-packet.json"

    assert main(_verify_args("manifests/", packet_path)) == 1
    first = json.loads(capsys.readouterr().out)
    assert _coverage_details(first)["success"] is False
    cache_path = next(
        (tmp_path / ".maid" / "cache").glob("artifact-coverage-evidence-*/*.json")
    )
    original_payload = json.loads(cache_path.read_text(encoding="utf-8"))

    invalid_payloads: tuple[str, ...] = (
        "{}\n",
        json.dumps(
            {
                "schema_version": 2,
                "report": {"success": True, "findings": [], "errors": []},
            }
        ),
        json.dumps(
            {
                "schema_version": 2,
                "report": {
                    **original_payload["report"],
                    "success": True,
                    "errors": [],
                },
            }
        ),
        json.dumps(
            {
                "schema_version": 2,
                "report": {
                    "success": True,
                    "findings": [],
                    "errors": [
                        {
                            "code": "E710",
                            "message": "unexecuted",
                            "severity": "error",
                        }
                    ],
                },
            }
        ),
        json.dumps(
            {
                "schema_version": 999,
                "report": {"success": False, "findings": [], "errors": []},
            }
        ),
        json.dumps(
            {
                "schema_version": 2,
                "report": {"success": True, "findings": [], "errors": []},
                "unexpected": True,
            }
        ),
        json.dumps(
            {
                "schema_version": 2,
                "report": {
                    "success": False,
                    "findings": [],
                    "errors": [
                        {
                            "code": "NOT_A_MAID_ERROR",
                            "message": "invalid enum",
                            "severity": "error",
                        }
                    ],
                },
            }
        ),
        "{",
    )
    for invalid_payload in invalid_payloads:
        cache_path.write_text(invalid_payload, encoding="utf-8")
        log.write_text("", encoding="utf-8")

        assert main(_verify_args("manifests/", packet_path)) == 1
        report = _coverage_details(json.loads(capsys.readouterr().out))

        assert report["success"] is False
        assert report.get("cache_hit", False) is False
        assert log.read_text(encoding="utf-8").splitlines()


def test_custom_manifest_directories_do_not_share_coverage_cache_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    monkeypatch.chdir(tmp_path)
    packet_path = tmp_path.parent / f"{tmp_path.name}-failure-packet.json"
    (tmp_path / "manifests").rename(tmp_path / "green-manifests")

    red_tests = tmp_path / "tests" / "test_uncovered.py"
    red_tests.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from src.target import target\n\n"
        "def test_mentions_without_calling_target():\n"
        "    log = Path(os.environ['MAID_EVIDENCE_EXECUTION_LOG'])\n"
        "    log.write_text(log.read_text() + 'uncovered\\n')\n"
        "    assert target is not None\n",
        encoding="utf-8",
    )
    red_manifests = tmp_path / "red-manifests"
    red_manifests.mkdir()
    red_payload = yaml.safe_load(
        (tmp_path / "green-manifests" / "coverage.manifest.yaml").read_text(
            encoding="utf-8"
        )
    )
    red_payload["goal"] = "Keep an unexecuted artifact red"
    red_payload["files"]["read"] = ["tests/test_uncovered.py"]
    red_payload["validate"] = ["python -m pytest -q tests/test_uncovered.py"]
    (red_manifests / "coverage.manifest.yaml").write_text(
        yaml.safe_dump(red_payload, sort_keys=False), encoding="utf-8"
    )

    assert main(_verify_args("green-manifests/", packet_path)) == 0
    green = json.loads(capsys.readouterr().out)
    assert _coverage_details(green)["success"] is True

    assert main(_verify_args("red-manifests/", packet_path)) == 1
    red = json.loads(capsys.readouterr().out)
    red_report = _coverage_details(red)
    assert red_report["success"] is False
    assert red_report.get("cache_hit", False) is False


@pytest.mark.skipif(
    os.name != "posix" or not sys.platform.startswith("linux"),
    reason="Complete descendant ownership is currently Linux-specific",
)
def test_exact_coverage_timeout_reaps_detached_descendants(tmp_path: Path) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    project = tmp_path / "project"
    source = project / "src" / "target.py"
    test_file = project / "tests" / "test_timeout.py"
    pid_file = project / "descendant.pid"
    source.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    source.write_text("def target():\n    return True\n", encoding="utf-8")
    child_code = "import time; time.sleep(60)"
    test_file.write_text(
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "from pathlib import Path\n\n"
        "def test_timeout():\n"
        f"    child = subprocess.Popen([sys.executable, '-c', {child_code!r}], start_new_session=True)\n"
        f"    Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "    time.sleep(60)\n",
        encoding="utf-8",
    )

    try:
        record = SubprocessRuntimeCommandExecutor().execute(
            ("tests/test_timeout.py", "-q"),
            {str(source.resolve())},
            project,
            timeout_seconds=1,
        )

        assert record.returncode != 0
        assert "timed out" in record.stderr.lower()
        descendant_pid = int(pid_file.read_text(encoding="utf-8"))
        assert _wait_until_process_gone(descendant_pid)
    finally:
        if pid_file.exists():
            _kill_process_group(int(pid_file.read_text(encoding="utf-8")))


def test_exact_coverage_fails_closed_without_descendant_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    project = tmp_path / "project"
    source = project / "src" / "target.py"
    test_file = project / "tests" / "test_target.py"
    source.parent.mkdir(parents=True)
    test_file.parent.mkdir(parents=True)
    source.write_text("def target():\n    return True\n", encoding="utf-8")
    test_file.write_text(
        "from src.target import target\n\n"
        "def test_target():\n"
        "    assert target() is True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "platform", "unsupported")

    record = SubprocessRuntimeCommandExecutor().execute(
        ("tests/test_target.py", "-q"),
        {str(source.resolve())},
        project,
        timeout_seconds=5,
    )

    assert record.returncode != 0
    assert "descendant ownership" in record.stderr.lower()
    assert record.execution_data == {}


def _verify_args(manifest_dir: str, packet_path: Path) -> list[str]:
    return [
        "verify",
        "--manifest-dir",
        manifest_dir,
        "--keep-going",
        "--no-changed-scope",
        "--artifact-coverage",
        "--advisory",
        "--json",
        "--packet",
        str(packet_path),
    ]


def _coverage_details(payload: dict) -> dict:
    return next(
        stage["details"]
        for stage in payload["stages"]
        if stage["name"] == "artifact_coverage"
    )


def _wait_until_process_gone(pid: int, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return True
        time.sleep(0.02)
    return not Path(f"/proc/{pid}").exists()


def _kill_process_group(pid: int) -> None:
    if not Path(f"/proc/{pid}").exists():
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass
