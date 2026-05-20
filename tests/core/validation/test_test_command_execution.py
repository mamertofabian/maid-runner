import subprocess
from types import SimpleNamespace

from maid_runner.core._test_command_execution import (
    _run_test_command,
    _test_command_environment,
)
from maid_runner.core.types import TestStream


def test_test_command_environment_removes_ambient_pytest_addopts(monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k skipped")
    monkeypatch.setenv("MAID_KEEP", "1")

    env = _test_command_environment()

    assert "PYTEST_ADDOPTS" not in env
    assert env["MAID_KEEP"] == "1"


def test_run_test_command_converts_completed_process(monkeypatch, tmp_path):
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return SimpleNamespace(returncode=7, stdout="out", stderr="err")

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.run",
        fake_run,
    )

    result = _run_test_command(
        ("echo", "hello"),
        cwd=tmp_path,
        timeout=12,
        manifest_slug="slug",
        stream=TestStream.ACCEPTANCE,
    )

    assert observed["command"] == ("echo", "hello")
    assert observed["kwargs"]["capture_output"] is True
    assert observed["kwargs"]["text"] is True
    assert observed["kwargs"]["cwd"] == str(tmp_path)
    assert observed["kwargs"]["timeout"] == 12
    assert result.manifest_slug == "slug"
    assert result.command == ("echo", "hello")
    assert result.exit_code == 7
    assert result.stdout == "out"
    assert result.stderr == "err"
    assert result.stream == TestStream.ACCEPTANCE
    assert result.duration_ms >= 0


def test_run_test_command_strips_pytest_addopts_from_subprocess_env(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k skipped")

    def fake_run(command, **kwargs):
        assert "PYTEST_ADDOPTS" not in kwargs["env"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.run",
        fake_run,
    )

    result = _run_test_command(("pytest", "tests/test_a.py"), cwd=tmp_path)

    assert result.success is True


def test_run_test_command_maps_timeout_to_exit_code_minus_one(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs["timeout"])

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.run",
        fake_run,
    )

    result = _run_test_command(("sleep", "10"), cwd=tmp_path, timeout=3)

    assert result.success is False
    assert result.exit_code == -1
    assert result.stdout == ""
    assert result.stderr == "Command timed out after 3s"


def test_run_test_command_maps_unexpected_exception_to_exit_code_minus_two(
    monkeypatch,
    tmp_path,
):
    def fake_run(command, **kwargs):
        raise OSError("missing executable")

    monkeypatch.setattr(
        "maid_runner.core._test_command_execution.subprocess.run",
        fake_run,
    )

    result = _run_test_command(("missing",), cwd=tmp_path)

    assert result.success is False
    assert result.exit_code == -2
    assert result.stdout == ""
    assert result.stderr == "missing executable"
