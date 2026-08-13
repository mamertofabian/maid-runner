import os
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from maid_runner.core._test_command_execution import (
    _COMMAND_SUPERVISOR_SOURCE,
    _run_test_command,
    _test_command_environment,
)
from maid_runner.core.types import TestStream


def test_timeout_terminates_and_reaps_descendant_process_group(tmp_path: Path) -> None:
    child_pid = tmp_path / "child.pid"
    controller = tmp_path / "controller.py"
    controller.write_text(
        "import pathlib, subprocess, sys, time\n"
        "child_code = \"import ctypes, signal, time; ctypes.CDLL(None).prctl(15, b'evil child', 0, 0, 0); signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)\"\n"
        "child = subprocess.Popen([sys.executable, '-c', child_code], start_new_session=True)\n"
        f"pathlib.Path({str(child_pid)!r}).write_text(str(child.pid))\n"
        "time.sleep(60)\n"
    )

    result = _run_test_command(
        (sys.executable, str(controller)), cwd=tmp_path, timeout=1
    )

    assert result.exit_code == -1
    pid = int(child_pid.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail(f"timed-out child process {pid} remained alive")


@pytest.mark.skipif(
    os.name != "posix" or not sys.platform.startswith("linux"),
    reason="The descendant-owning command supervisor is Linux-specific",
)
def test_timeout_reaps_detached_child_created_by_non_main_thread(
    tmp_path: Path,
) -> None:
    child_pid = tmp_path / "thread-child.pid"
    controller = tmp_path / "thread-controller.py"
    controller.write_text(
        "import pathlib, signal, subprocess, sys, threading, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "def launch():\n"
        '    child_code = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"\n'
        "    child = subprocess.Popen([sys.executable, '-c', child_code], start_new_session=True)\n"
        f"    pathlib.Path({str(child_pid)!r}).write_text(str(child.pid))\n"
        "    time.sleep(60)\n"
        "threading.Thread(target=launch).start()\n"
        "while not pathlib.Path(" + repr(str(child_pid)) + ").exists():\n"
        "    time.sleep(0.01)\n"
        "time.sleep(60)\n"
    )

    result = _run_test_command(
        (sys.executable, str(controller)), cwd=tmp_path, timeout=1
    )

    assert result.exit_code == -1
    pid = int(child_pid.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        pytest.fail(f"non-main-thread child process {pid} remained alive")


@pytest.mark.skipif(
    os.name != "posix" or not sys.platform.startswith("linux"),
    reason="The descendant-owning command supervisor is Linux-specific",
)
def test_supervisor_owns_descendants_without_global_proc_enumeration(
    tmp_path: Path,
) -> None:
    status_path = tmp_path / "supervisor-status.json"
    deny_global_proc_listing = (
        "import os\n"
        "_maid_real_listdir = os.listdir\n"
        "def _maid_owned_listdir(path):\n"
        "    if os.fspath(path) == '/proc':\n"
        "        raise AssertionError('global procfs enumeration is forbidden')\n"
        "    return _maid_real_listdir(path)\n"
        "os.listdir = _maid_owned_listdir\n"
    )

    completed = subprocess.run(
        (
            sys.executable,
            "-c",
            deny_global_proc_listing + _COMMAND_SUPERVISOR_SOURCE,
            str(status_path),
            sys.executable,
            "-c",
            "pass",
        ),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(status_path.read_text()) == {"returncode": 0}


def test_test_command_environment_removes_ambient_pytest_addopts(monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k skipped")
    monkeypatch.setenv("MAID_KEEP", "1")

    env = _test_command_environment()

    assert "PYTEST_ADDOPTS" not in env
    assert env["MAID_KEEP"] == "1"


def test_run_test_command_converts_completed_process(monkeypatch, tmp_path):
    observed: dict[str, object] = {}

    def fake_popen(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        Path(command[3]).write_text(json.dumps({"returncode": 7}))
        return _FakeProcess(returncode=7, stdout="out", stderr="err")

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.Popen",
        fake_popen,
    )

    result = _run_test_command(
        ("echo", "hello"),
        cwd=tmp_path,
        timeout=12,
        manifest_slug="slug",
        stream=TestStream.ACCEPTANCE,
    )

    observed_command = observed["command"]
    assert isinstance(observed_command, tuple)
    assert observed_command[:3] == (sys.executable, "-c", observed_command[2])
    assert observed_command[-2:] == ("echo", "hello")
    assert observed["kwargs"]["stdout"] == subprocess.PIPE
    assert observed["kwargs"]["stderr"] == subprocess.PIPE
    assert observed["kwargs"]["text"] is True
    assert observed["kwargs"]["cwd"] == str(tmp_path)
    assert result.manifest_slug == "slug"
    assert result.command == ("echo", "hello")
    assert result.exit_code == 7
    assert result.stdout == "out"
    assert result.stderr == "err"
    assert result.stream == TestStream.ACCEPTANCE
    assert result.duration_ms >= 0


def test_missing_supervisor_status_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(returncode=1),
    )

    result = _run_test_command(("echo", "hello"), cwd=tmp_path)

    assert result.exit_code == -2
    assert "valid completion status" in result.stderr


def test_required_descendant_ownership_fails_closed_when_unsupported(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.sys.platform", "darwin"
    )

    result = _run_test_command(
        ("echo", "hello"),
        cwd=tmp_path,
        require_descendant_ownership=True,
    )

    assert result.exit_code == -2
    assert "descendant ownership" in result.stderr


def test_unavailable_procfs_fails_descendant_ownership(monkeypatch, tmp_path):
    process = _FakeProcess(timeout=True, remain_running=True)
    launched = False

    def fake_popen(*args, **kwargs):
        nonlocal launched
        launched = True
        return process

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.os.listdir",
        lambda _path: (_ for _ in ()).throw(OSError("procfs unavailable")),
    )
    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.Popen",
        fake_popen,
    )

    result = _run_test_command(
        ("sleep", "10"),
        cwd=tmp_path,
        timeout=1,
        require_descendant_ownership=True,
    )

    assert result.exit_code == -2
    assert "descendant ownership" in result.stderr
    assert launched is False


def test_timeout_cleanup_failure_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(timeout=True),
    )
    monkeypatch.setattr(
        "maid_runner.core._test_command_execution._terminate_process_tree",
        lambda _process: None,
    )

    result = _run_test_command(("sleep", "10"), cwd=tmp_path, timeout=3)

    assert result.exit_code == -2
    assert "valid completion status" in result.stderr


def test_run_test_command_strips_pytest_addopts_from_subprocess_env(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k skipped")

    def fake_popen(command, **kwargs):
        assert "PYTEST_ADDOPTS" not in kwargs["env"]
        Path(command[3]).write_text(json.dumps({"returncode": 0}))
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.Popen",
        fake_popen,
    )

    result = _run_test_command(("pytest", "tests/test_a.py"), cwd=tmp_path)

    assert result.success is True


def test_run_test_command_maps_timeout_to_exit_code_minus_one(monkeypatch, tmp_path):
    process = _FakeProcess(timeout=True)

    def fake_popen(command, **kwargs):
        Path(command[3]).write_text(json.dumps({"returncode": -1}))
        return process

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.Popen",
        fake_popen,
    )
    monkeypatch.setattr(
        "maid_runner.core._test_command_execution._terminate_process_tree",
        lambda observed: setattr(observed, "terminated", True),
    )

    result = _run_test_command(("sleep", "10"), cwd=tmp_path, timeout=3)

    assert result.success is False
    assert result.exit_code == -1
    assert result.stdout == ""
    assert result.stderr == "Command timed out after 3s"
    assert process.terminated is True


def test_run_test_command_maps_unexpected_exception_to_exit_code_minus_two(
    monkeypatch,
    tmp_path,
):
    def fake_popen(command, **kwargs):
        raise OSError("missing executable")

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.Popen",
        fake_popen,
    )

    result = _run_test_command(("missing",), cwd=tmp_path)

    assert result.success is False
    assert result.exit_code == -2
    assert result.stdout == ""
    assert result.stderr == "missing executable"


def test_run_test_command_scopes_environment_overrides_to_child(monkeypatch, tmp_path):
    import os

    original_timing_output = os.environ.get("MAID_TIMING_OUTPUT")
    monkeypatch.setenv("MAID_PARENT_ONLY", "parent")
    observed = {}

    def fake_popen(command, **kwargs):
        observed.update(kwargs["env"])
        Path(command[3]).write_text(json.dumps({"returncode": 0}))
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.Popen", fake_popen
    )

    result = _run_test_command(
        ("pytest", "tests/test_gate.py"),
        cwd=tmp_path,
        environment_overrides={"MAID_TIMING_OUTPUT": "child-only"},
    )

    assert result.success is True
    assert observed["MAID_PARENT_ONLY"] == "parent"
    assert observed["MAID_TIMING_OUTPUT"] == "child-only"
    assert os.environ.get("MAID_TIMING_OUTPUT") == original_timing_output


class _FakeProcess:
    pid = 999999

    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        timeout: bool = False,
        remain_running: bool = False,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timeout = timeout
        self.remain_running = remain_running
        self.terminated = False
        self.communications = 0

    def communicate(self, timeout=None):
        self.communications += 1
        if self.timeout and self.communications == 1:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.stdout, self.stderr

    def terminate(self):
        self.terminated = True

    def poll(self):
        return None if self.remain_running else self.returncode

    def kill(self):
        self.terminated = True
        self.remain_running = False
