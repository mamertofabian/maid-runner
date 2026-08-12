"""Subprocess execution for resolved maid test commands."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, Union

from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream


_COMMAND_SUPERVISOR_SOURCE = r"""
import ctypes
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

status_path = sys.argv[1]
command = sys.argv[2:]
child = None

def descendants(parent):
    children = {}
    try:
        entries = os.listdir('/proc')
    except OSError as exc:
        raise RuntimeError('could not prove descendant ownership') from exc
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open('/proc/' + entry + '/stat', encoding='utf-8') as stream:
                stat = stream.read()
            closing = stat.rfind(')')
            fields = stat[closing + 2:].split()
            if closing < 0 or len(fields) < 2:
                raise ValueError('malformed proc stat')
            children.setdefault(int(fields[1]), set()).add(int(entry))
        except FileNotFoundError:
            continue
        except (OSError, ValueError, IndexError) as exc:
            raise RuntimeError('could not prove descendant ownership') from exc
    found = set()
    pending = [parent]
    while pending:
        current = pending.pop()
        for child in children.get(current, ()):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found

def signal_all(sig):
    pids = descendants(os.getpid())
    groups = set()
    if child is not None:
        pids.add(child.pid)
    for pid in pids:
        try:
            groups.add(os.getpgid(pid))
        except (OSError, ProcessLookupError):
            pass
    own_group = os.getpgrp()
    for group in groups:
        if group != own_group:
            try:
                os.killpg(group, sig)
            except (OSError, ProcessLookupError):
                pass
    for pid in pids:
        try:
            os.kill(pid, sig)
        except (OSError, ProcessLookupError):
            pass

def reap():
    while True:
        try:
            pid, _status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid <= 0:
            return

def cleanup():
    signal_all(signal.SIGTERM)
    deadline = time.monotonic() + 0.25
    while time.monotonic() < deadline and descendants(os.getpid()):
        reap()
        time.sleep(0.01)
    signal_all(signal.SIGKILL)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        reap()
        if not descendants(os.getpid()):
            break
        time.sleep(0.01)
    reap()

def terminate(_signum, _frame):
    try:
        cleanup()
        payload = {'returncode': -1}
    except Exception as exc:
        payload = {'error': 'could not prove descendant cleanup: ' + str(exc)}
    with open(status_path, 'w', encoding='utf-8') as stream:
        json.dump(payload, stream)
    os._exit(124)

if os.name == 'posix' and sys.platform.startswith('linux'):
    try:
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            raise OSError('could not enable per-command child subreaper')
    except Exception as exc:
        with open(status_path, 'w', encoding='utf-8') as stream:
            json.dump({'error': str(exc)}, stream)
        sys.exit(0)

try:
    descendants(os.getpid())
except Exception as exc:
    with open(status_path, 'w', encoding='utf-8') as stream:
        json.dump({'error': 'could not prove descendant ownership: ' + str(exc)}, stream)
    sys.exit(0)

signal.signal(signal.SIGTERM, terminate)
try:
    creation = {'start_new_session': True} if os.name != 'nt' else {
        'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP
    }
    stdout_file = tempfile.TemporaryFile()
    stderr_file = tempfile.TemporaryFile()
    child = subprocess.Popen(
        command,
        stdout=stdout_file,
        stderr=stderr_file,
        **creation,
    )
except Exception as exc:
    with open(status_path, 'w', encoding='utf-8') as stream:
        json.dump({'error': str(exc)}, stream)
    sys.exit(0)

returncode = child.wait()
cleanup()
stdout_file.seek(0)
stderr_file.seek(0)
sys.stdout.buffer.write(stdout_file.read())
sys.stderr.buffer.write(stderr_file.read())
with open(status_path, 'w', encoding='utf-8') as stream:
    json.dump({'returncode': returncode}, stream)
sys.exit(0)
"""


_strict_validation_for_tests: ContextVar[bool] = ContextVar(
    "maid_strict_validation_for_tests",
    default=False,
)
_strict_validation_process_lock = threading.Lock()
_strict_validation_process_depth = 0


@contextmanager
def _strict_validation_test_environment(
    enabled: bool,
    *,
    process_wide: bool = False,
) -> Iterator[None]:
    global _strict_validation_process_depth

    context_token = _strict_validation_for_tests.set(enabled)
    if enabled and process_wide:
        with _strict_validation_process_lock:
            _strict_validation_process_depth += 1
    try:
        yield
    finally:
        if enabled and process_wide:
            with _strict_validation_process_lock:
                _strict_validation_process_depth -= 1
        _strict_validation_for_tests.reset(context_token)


def _inherited_strict_validation() -> bool:
    if _strict_validation_for_tests.get():
        return True
    with _strict_validation_process_lock:
        return _strict_validation_process_depth > 0


def _strict_validation_test_active() -> bool:
    return _inherited_strict_validation()


def _run_test_command(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path] = ".",
    timeout: int = 300,
    manifest_slug: str = "",
    stream: TestStream = TestStream.IMPLEMENTATION,
    environment_overrides: Mapping[str, str] | None = None,
    environment_removals: Sequence[str] = (),
    require_descendant_ownership: bool = False,
) -> TestRunResult:
    env = _test_command_environment()
    for name in environment_removals:
        env.pop(name, None)
    if environment_overrides:
        env.update(environment_overrides)
    start = time.monotonic()
    if not _descendant_ownership_supported():
        if require_descendant_ownership:
            return TestRunResult(
                manifest_slug=manifest_slug,
                command=command,
                exit_code=-2,
                stdout="",
                stderr=(
                    "Complete descendant ownership is unavailable on "
                    f"platform {sys.platform}"
                ),
                duration_ms=(time.monotonic() - start) * 1000,
                stream=stream,
            )
        return _run_test_command_legacy(
            command,
            cwd=cwd,
            timeout=timeout,
            manifest_slug=manifest_slug,
            stream=stream,
            env=env,
            start=start,
        )
    status_path = ""
    try:
        status_fd, status_path = tempfile.mkstemp(
            prefix="maid-command-", suffix=".json"
        )
        os.close(status_fd)
        creation = {}
        if os.name == "nt":
            creation["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            creation["start_new_session"] = True
        supervised_command = (
            sys.executable,
            "-c",
            _COMMAND_SUPERVISOR_SOURCE,
            status_path,
            *command,
        )
        proc = subprocess.Popen(
            supervised_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(cwd),
            env=env,
            **creation,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(proc)
            _bounded_communicate(proc)
            _cleanup_code, cleanup_error = _supervised_status(
                status_path, proc.returncode
            )
            duration = (time.monotonic() - start) * 1000
            if cleanup_error is not None:
                return TestRunResult(
                    manifest_slug=manifest_slug,
                    command=command,
                    exit_code=-2,
                    stdout="",
                    stderr=cleanup_error,
                    duration_ms=duration,
                    stream=stream,
                )
            return TestRunResult(
                manifest_slug=manifest_slug,
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration_ms=duration,
                stream=stream,
            )
        returncode, execution_error = _supervised_status(status_path, proc.returncode)
        duration = (time.monotonic() - start) * 1000
        if execution_error is not None:
            return TestRunResult(
                manifest_slug=manifest_slug,
                command=command,
                exit_code=-2,
                stdout="",
                stderr=execution_error,
                duration_ms=duration,
                stream=stream,
            )
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration,
            stream=stream,
        )
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=-2,
            stdout="",
            stderr=str(e),
            duration_ms=duration,
            stream=stream,
        )
    finally:
        if status_path:
            try:
                os.unlink(status_path)
            except FileNotFoundError:
                pass


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ("taskkill", "/PID", str(process.pid), "/T", "/F"),
            capture_output=True,
            check=False,
        )
        if process.poll() is None:
            process.kill()
        return
    try:
        process.terminate()
    except (OSError, ProcessLookupError):
        return
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.02)

    pids = _descendant_pids(process.pid)
    groups: set[int] = set()
    for pid in (*pids, process.pid):
        try:
            groups.add(os.getpgid(pid))
        except (OSError, ProcessLookupError):
            pass
    own_group = os.getpgrp()
    for group in groups:
        if group != own_group:
            try:
                os.killpg(group, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
    for pid in (*pids, process.pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass


def _descendant_pids(parent: int) -> tuple[int, ...]:
    children: dict[int, list[int]] = {}
    try:
        entries = os.listdir("/proc")
    except OSError as exc:
        raise RuntimeError("could not prove descendant ownership") from exc
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry}/stat").read_text()
            closing = stat.rfind(")")
            fields = stat[closing + 2 :].split()
            if closing < 0 or len(fields) < 2:
                raise ValueError("malformed proc stat")
            children.setdefault(int(fields[1]), []).append(int(entry))
        except FileNotFoundError:
            continue
        except (OSError, ValueError, IndexError) as exc:
            raise RuntimeError("could not prove descendant ownership") from exc
    found: list[int] = []
    pending = [parent]
    while pending:
        direct = children.get(pending.pop(), ())
        found.extend(direct)
        pending.extend(direct)
    return tuple(found)


def _bounded_communicate(process: subprocess.Popen[str]) -> None:
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            pass
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


def _supervised_status(
    status_path: str,
    supervisor_returncode: int,
) -> tuple[int, str | None]:
    try:
        import json

        payload = json.loads(Path(status_path).read_text())
    except Exception:
        return -2, "Command supervisor did not produce valid completion status"
    error = payload.get("error")
    if isinstance(error, str):
        return -2, error
    returncode = payload.get("returncode")
    if isinstance(returncode, int):
        return returncode, None
    return -2, (
        "Command supervisor did not produce valid completion status "
        f"(exit {supervisor_returncode})"
    )


def _descendant_ownership_supported() -> bool:
    if os.name != "posix" or not sys.platform.startswith("linux"):
        return False
    try:
        entries = os.listdir("/proc")
        stat = Path(f"/proc/{os.getpid()}/stat").read_text()
        closing = stat.rfind(")")
        fields = stat[closing + 2 :].split()
    except OSError:
        return False
    return str(os.getpid()) in entries and closing >= 0 and len(fields) >= 2


def _run_test_command_legacy(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path],
    timeout: int,
    manifest_slug: str,
    stream: TestStream,
    env: Mapping[str, str],
    start: float,
) -> TestRunResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
            env=env,
        )
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_ms=(time.monotonic() - start) * 1000,
            stream=stream,
        )
    except subprocess.TimeoutExpired:
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            duration_ms=(time.monotonic() - start) * 1000,
            stream=stream,
        )
    except Exception as exc:
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=-2,
            stdout="",
            stderr=str(exc),
            duration_ms=(time.monotonic() - start) * 1000,
            stream=stream,
        )


def _test_command_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    return env
