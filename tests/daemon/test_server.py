"""Behavioral tests for the maid serve daemon Server lifecycle and request handling."""

from __future__ import annotations

import json
import multiprocessing
import os
import signal
import socket as socket_module
import stat
import threading
import time
from pathlib import Path

import pytest

from maid_runner.daemon import handlers as daemon_handlers
from maid_runner.daemon.handlers import (
    HANDLERS,
    configure_context,
    handle_ping,
    handle_validate,
)
from maid_runner.daemon.server import Server, check_stale_pidfile, serve


def _read_one_response(conn: socket_module.socket, timeout: float = 5.0) -> dict:
    conn.settimeout(timeout)
    chunks: list[bytes] = []
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    data = b"".join(chunks)
    line = data.split(b"\n", 1)[0]
    return json.loads(line.decode("utf-8"))


def _send_request(socket_path: Path, payload: dict, timeout: float = 5.0) -> dict:
    conn = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
    conn.settimeout(timeout)
    try:
        conn.connect(str(socket_path))
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        return _read_one_response(conn, timeout=timeout)
    finally:
        conn.close()


def _run_serve_in_process(
    socket_path: str,
    pidfile_path: str,
    client_timeout_s: float,
    project_root: str = ".",
):
    from maid_runner.daemon.server import serve as _serve

    _serve(Path(socket_path), Path(pidfile_path), client_timeout_s, project_root)


@pytest.fixture
def daemon_runtime(tmp_path):
    socket_path = tmp_path / "serve.sock"
    pidfile_path = tmp_path / "serve.pid"

    proc = multiprocessing.Process(
        target=_run_serve_in_process,
        args=(str(socket_path), str(pidfile_path), 2.0, str(tmp_path)),
    )
    proc.start()

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if socket_path.exists() and pidfile_path.exists():
            break
        time.sleep(0.05)
    else:
        proc.terminate()
        proc.join(timeout=2.0)
        pytest.fail("Daemon did not start within 5s")

    yield {"socket": socket_path, "pidfile": pidfile_path, "proc": proc}

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=2.0)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=2.0)


class TestServerLifecycle:
    def test_server_starts_and_accepts_connection_on_unix_socket(self, daemon_runtime):
        assert daemon_runtime["socket"].exists()
        conn = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        try:
            conn.connect(str(daemon_runtime["socket"]))
        finally:
            conn.close()

    def test_sigterm_triggers_clean_shutdown_and_removes_pidfile_and_socket(
        self, daemon_runtime
    ):
        pid = int(daemon_runtime["pidfile"].read_text().strip())
        os.kill(pid, signal.SIGTERM)
        daemon_runtime["proc"].join(timeout=5.0)
        assert not daemon_runtime["proc"].is_alive()
        assert not daemon_runtime["pidfile"].exists()
        assert not daemon_runtime["socket"].exists()


class TestPing:
    def test_ping_returns_pid_version_and_uptime(self, daemon_runtime):
        response = _send_request(
            daemon_runtime["socket"],
            {"id": "p-1", "method": "ping", "params": {}},
        )

        assert response["ok"] is True
        assert response["id"] == "p-1"
        payload = response["result"]
        assert "pid" in payload
        assert "version" in payload
        assert "uptime_s" in payload
        assert isinstance(payload["uptime_s"], (int, float))


class TestValidateOverSocket:
    def test_validate_request_returns_same_json_shape_as_cli_for_single_manifest(
        self, daemon_runtime, tmp_path
    ):
        manifest_path = tmp_path / "demo.manifest.yaml"
        manifest_path.write_text(
            "schema: '2'\n"
            "goal: demo\n"
            "type: feature\n"
            "files:\n"
            "  create: []\n"
            "validate:\n"
            "  - python -c 'pass'\n"
        )

        response = _send_request(
            daemon_runtime["socket"],
            {
                "id": "v-1",
                "method": "validate",
                "params": {
                    "manifest_path": str(manifest_path),
                    "mode": "schema",
                },
            },
        )

        assert response["ok"] is True
        result = response["result"]
        assert "success" in result
        assert "errors" in result
        assert "warnings" in result

    def test_validate_request_returns_errors_for_invalid_manifest(
        self, daemon_runtime, tmp_path
    ):
        manifest_path = tmp_path / "bad.manifest.yaml"
        manifest_path.write_text("schema: '2'\ngoal: bad\n")

        response = _send_request(
            daemon_runtime["socket"],
            {
                "id": "v-2",
                "method": "validate",
                "params": {
                    "manifest_path": str(manifest_path),
                    "mode": "schema",
                },
            },
        )

        result = response["result"]
        assert result["success"] is False
        assert len(result["errors"]) > 0


class TestRobustness:
    def test_malformed_request_returns_error_response_and_connection_stays_open(
        self, daemon_runtime
    ):
        conn = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        conn.settimeout(5.0)
        try:
            conn.connect(str(daemon_runtime["socket"]))
            conn.sendall(b"not json at all {{{\n")
            err = _read_one_response(conn, timeout=5.0)
            assert err["ok"] is False
            assert err["error"]["code"]

            conn.sendall(
                (json.dumps({"id": "x", "method": "ping", "params": {}}) + "\n").encode(
                    "utf-8"
                )
            )
            ok = _read_one_response(conn, timeout=5.0)
            assert ok["ok"] is True
        finally:
            conn.close()

    def test_client_read_timeout_closes_slow_connection_but_keeps_daemon_running(
        self, daemon_runtime
    ):
        conn = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        try:
            conn.connect(str(daemon_runtime["socket"]))
            time.sleep(2.5)
        finally:
            conn.close()

        response = _send_request(
            daemon_runtime["socket"],
            {"id": "p-after", "method": "ping", "params": {}},
        )
        assert response["ok"] is True


class TestPidfileBehavior:
    def test_double_launch_with_live_daemon_exits_non_zero(self, daemon_runtime):
        rc = serve(
            daemon_runtime["socket"],
            daemon_runtime["pidfile"],
            client_timeout_s=2.0,
        )
        assert rc != 0

    def test_stale_pidfile_from_dead_process_is_removed_and_daemon_starts(
        self, tmp_path
    ):
        pidfile = tmp_path / "stale.pid"
        socket_path = tmp_path / "stale.sock"
        pidfile.write_text("999999")
        socket_path.touch()

        result = check_stale_pidfile(pidfile)
        assert result is True
        assert not pidfile.exists()


class TestHandlersRegistry:
    def test_handlers_registry_dispatches_ping_to_handle_ping(self):
        assert HANDLERS["ping"] is handle_ping
        payload = HANDLERS["ping"]({})
        assert set(payload.keys()) >= {"pid", "version", "uptime_s"}
        assert payload["pid"] == os.getpid()
        assert isinstance(payload["uptime_s"], (int, float))

    def test_handlers_registry_dispatches_validate_via_handle_validate(self, tmp_path):
        manifest = tmp_path / "stub.manifest.yaml"
        manifest.write_text(
            'schema: "2"\n'
            "goal: stub\n"
            "type: feature\n"
            "files:\n"
            "  create: []\n"
            "  edit: []\n"
            "  read: []\n"
            "validate: []\n"
        )
        configure_context(tmp_path)

        assert HANDLERS["validate"] is handle_validate
        result = HANDLERS["validate"]({"manifest_path": "stub.manifest.yaml"})
        assert isinstance(result, dict)
        assert "success" in result


class TestServerClass:
    def test_server_shutdown_releases_socket_and_pidfile(self, tmp_path):
        socket_path = tmp_path / "shutdown.sock"
        pidfile_path = tmp_path / "shutdown.pid"
        server = Server(socket_path, pidfile_path, client_timeout_s=1.0)

        listening = socket_module.socket(
            socket_module.AF_UNIX, socket_module.SOCK_STREAM
        )
        listening.bind(str(socket_path))
        listening.listen(1)
        server._listening = listening
        server._running = True
        server._pidfile_owned = True
        pidfile_path.write_text(str(os.getpid()))

        server.shutdown()

        assert not socket_path.exists()
        assert not pidfile_path.exists()
        assert server._running is False

    def test_server_handle_client_processes_ndjson_request_over_socketpair(
        self, tmp_path
    ):
        socket_path = tmp_path / "handle.sock"
        pidfile_path = tmp_path / "handle.pid"
        server = Server(socket_path, pidfile_path, client_timeout_s=1.0)
        configure_context(tmp_path)

        server_side, client_side = socket_module.socketpair()
        server_side.settimeout(1.0)
        client_side.settimeout(1.0)

        worker = threading.Thread(target=server.handle_client, args=(server_side,))
        worker.start()
        try:
            client_side.sendall(b'{"id":"r1","method":"ping","params":{}}\n')
            response = _read_one_response(client_side)
        finally:
            client_side.close()
            worker.join(timeout=2.0)
            server_side.close()

        assert response["id"] == "r1"
        assert response["ok"] is True
        assert "pid" in response["result"]

    def test_daemon_package_reexports_public_api(self):
        from maid_runner.daemon import (
            DaemonRequestError as _DaemonRequestError,
            ProtocolError as _ProtocolError,
            Request as _Request,
            Response as _Response,
            Server as _Server,
            serve as _serve,
        )

        assert _Server is Server
        assert _serve is serve
        assert _Request is not None
        assert _Response is not None
        assert _ProtocolError is not None
        assert _DaemonRequestError is not None


class TestConcurrentClients:
    def test_idle_client_does_not_block_other_requests(self, daemon_runtime):
        idle = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        try:
            idle.connect(str(daemon_runtime["socket"]))

            response = _send_request(
                daemon_runtime["socket"],
                {"id": "concurrent-1", "method": "ping", "params": {}},
                timeout=3.0,
            )

            assert response["ok"] is True
            assert response["id"] == "concurrent-1"
        finally:
            idle.close()


class TestFrameSizeLimit:
    def test_oversized_unterminated_request_is_rejected_and_daemon_survives(
        self, daemon_runtime
    ):
        conn = socket_module.socket(socket_module.AF_UNIX, socket_module.SOCK_STREAM)
        conn.settimeout(5.0)
        try:
            conn.connect(str(daemon_runtime["socket"]))
            payload = b"A" * (2 * 1024 * 1024)
            try:
                conn.sendall(payload)
            except OSError:
                pass
            try:
                err = _read_one_response(conn, timeout=5.0)
                assert err["ok"] is False
                assert err["error"]["code"] == "FRAME_TOO_LARGE"
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        finally:
            conn.close()

        followup = _send_request(
            daemon_runtime["socket"],
            {"id": "after-oversize", "method": "ping", "params": {}},
        )
        assert followup["ok"] is True


class TestAtomicPidfile:
    def test_concurrent_serve_calls_only_one_succeeds(self, tmp_path):
        from maid_runner.daemon.server import _acquire_pidfile

        pidfile = tmp_path / "race.pid"

        results: list[bool] = []
        lock = threading.Lock()

        def claim():
            ok = _acquire_pidfile(pidfile)
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=claim) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)

        assert results.count(True) == 1
        assert results.count(False) == len(results) - 1
        assert pidfile.exists()
        assert pidfile.read_text().strip() == str(os.getpid())

    def test_pidfile_contenders_do_not_remove_claim_before_pid_is_written(
        self, tmp_path, monkeypatch
    ):
        from maid_runner.daemon import server as daemon_server

        pidfile = tmp_path / "claim-before-write.pid"
        original_write = daemon_server.os.write
        first_write_started = threading.Event()
        release_first_write = threading.Event()
        blocked_first_write = False

        def slow_first_write(fd, data):
            nonlocal blocked_first_write
            if not blocked_first_write:
                blocked_first_write = True
                first_write_started.set()
                assert release_first_write.wait(timeout=2.0)
            return original_write(fd, data)

        monkeypatch.setattr(daemon_server.os, "write", slow_first_write)

        results: list[bool] = []
        lock = threading.Lock()

        def claim():
            ok = daemon_server._acquire_pidfile(pidfile)
            with lock:
                results.append(ok)

        first = threading.Thread(target=claim)
        first.start()
        assert first_write_started.wait(timeout=2.0)

        second = threading.Thread(target=claim)
        second.start()
        second.join(timeout=2.0)

        release_first_write.set()
        first.join(timeout=2.0)

        assert results.count(True) == 1
        assert results.count(False) == len(results) - 1
        assert pidfile.exists()
        assert pidfile.read_text().strip() == str(os.getpid())

    def test_acquire_pidfile_replaces_stale_pidfile(self, tmp_path):
        from maid_runner.daemon.server import _acquire_pidfile

        pidfile = tmp_path / "stale.pid"
        pidfile.write_text("999999")

        assert _acquire_pidfile(pidfile) is True
        assert pidfile.read_text().strip() == str(os.getpid())


class TestSocketPermissions:
    def test_socket_file_has_owner_only_permissions(self, daemon_runtime):
        st = os.lstat(str(daemon_runtime["socket"]))
        assert stat.S_ISSOCK(st.st_mode)
        assert (st.st_mode & 0o777) == 0o600

    def test_startup_refuses_group_writable_runtime_directory(self, tmp_path):
        bad_dir = tmp_path / "insecure"
        bad_dir.mkdir(mode=0o770)
        os.chmod(str(bad_dir), 0o770)
        socket_path = bad_dir / "serve.sock"
        pidfile_path = bad_dir / "serve.pid"

        server = Server(socket_path, pidfile_path, client_timeout_s=1.0)
        with pytest.raises(RuntimeError, match="group/world permissions"):
            server.start()

        try:
            os.chmod(str(bad_dir), 0o700)
        except OSError:
            pass


class TestNonSocketCollision:
    def test_startup_refuses_to_unlink_regular_file_at_socket_path(self, tmp_path):
        runtime_dir = tmp_path / ".maid"
        runtime_dir.mkdir(mode=0o700)
        socket_path = runtime_dir / "serve.sock"
        socket_path.write_text("important user data — not a socket")
        pidfile_path = runtime_dir / "serve.pid"

        rc = serve(socket_path, pidfile_path, client_timeout_s=1.0)

        assert rc != 0
        assert socket_path.exists()
        assert socket_path.read_text() == "important user data — not a socket"

    def test_startup_refuses_to_unlink_directory_at_socket_path(self, tmp_path):
        runtime_dir = tmp_path / ".maid"
        runtime_dir.mkdir(mode=0o700)
        socket_path = runtime_dir / "serve.sock"
        socket_path.mkdir()
        pidfile_path = runtime_dir / "serve.pid"

        rc = serve(socket_path, pidfile_path, client_timeout_s=1.0)

        assert rc != 0
        assert socket_path.exists()
        assert socket_path.is_dir()


class TestProjectRootIsolation:
    def test_configure_context_sets_validation_project_root(self, tmp_path):
        configure_context(tmp_path)
        assert daemon_handlers._DAEMON_CONTEXT["project_root"] == str(
            tmp_path.resolve()
        )

    def test_validate_handler_ignores_client_supplied_project_root(self, tmp_path):
        good_root = tmp_path / "good"
        good_root.mkdir()
        (good_root / "demo.manifest.yaml").write_text(
            "schema: '2'\n"
            "goal: demo\n"
            "type: feature\n"
            "files:\n  create: []\n"
            "validate:\n  - python -c 'pass'\n"
        )

        bad_root = tmp_path / "bad"
        bad_root.mkdir()

        configure_context(good_root)

        result = handle_validate(
            {
                "manifest_path": "demo.manifest.yaml",
                "mode": "schema",
                "project_root": str(bad_root),
            }
        )

        assert result.get("success") is True

    def test_server_exposes_project_root_attribute(self, tmp_path):
        runtime_dir = tmp_path / "rt"
        runtime_dir.mkdir(mode=0o700)
        server = Server(
            runtime_dir / "serve.sock",
            runtime_dir / "serve.pid",
            client_timeout_s=1.0,
            project_root=tmp_path,
        )
        assert server.project_root == tmp_path.resolve()

    def test_validate_handler_rejects_manifest_path_escaping_root(self, tmp_path):
        from maid_runner.daemon.protocol import DaemonRequestError

        good_root = tmp_path / "good"
        good_root.mkdir()
        configure_context(good_root)

        with pytest.raises(DaemonRequestError) as excinfo:
            handle_validate(
                {
                    "manifest_path": "../../etc/passwd",
                    "mode": "schema",
                }
            )
        assert excinfo.value.code == "PATH_ESCAPE"
        assert "escapes daemon project root" in excinfo.value.message


class TestRequestErrorSemantics:
    def test_path_escape_returns_ok_false_at_protocol_layer(self, daemon_runtime):
        response = _send_request(
            daemon_runtime["socket"],
            {
                "id": "esc-1",
                "method": "validate",
                "params": {
                    "manifest_path": "../../etc/passwd",
                    "mode": "schema",
                },
            },
        )
        assert response["ok"] is False
        assert response["error"]["code"] == "PATH_ESCAPE"
        assert "result" not in response

    def test_missing_param_returns_ok_false_at_protocol_layer(self, daemon_runtime):
        response = _send_request(
            daemon_runtime["socket"],
            {"id": "mp-1", "method": "validate", "params": {}},
        )
        assert response["ok"] is False
        assert response["error"]["code"] == "MISSING_PARAM"

    def test_bad_mode_returns_ok_false_at_protocol_layer(
        self, daemon_runtime, tmp_path
    ):
        manifest_path = tmp_path / "x.manifest.yaml"
        manifest_path.write_text("schema: '2'\ngoal: x\n")
        response = _send_request(
            daemon_runtime["socket"],
            {
                "id": "bm-1",
                "method": "validate",
                "params": {
                    "manifest_path": str(manifest_path),
                    "mode": "nonsense",
                },
            },
        )
        assert response["ok"] is False
        assert response["error"]["code"] == "BAD_MODE"

    def test_validation_failure_stays_ok_true_at_protocol_layer(
        self, daemon_runtime, tmp_path
    ):
        bad_manifest = tmp_path / "bad.manifest.yaml"
        bad_manifest.write_text("schema: '2'\ngoal: bad\n")

        response = _send_request(
            daemon_runtime["socket"],
            {
                "id": "vf-1",
                "method": "validate",
                "params": {
                    "manifest_path": str(bad_manifest),
                    "mode": "schema",
                },
            },
        )

        assert response["ok"] is True
        assert response["result"]["success"] is False
        assert response["result"]["errors"]


class TestPidfileSocketIndependence:
    def test_check_stale_pidfile_does_not_unlink_unrelated_socket(self, tmp_path):
        pidfile = tmp_path / "project.pid"
        unrelated_socket = tmp_path / "project.sock"
        pidfile.write_text("999999")
        unrelated_socket.write_text("not this daemon's socket")

        result = check_stale_pidfile(pidfile)

        assert result is True
        assert not pidfile.exists()
        assert unrelated_socket.exists()
        assert unrelated_socket.read_text() == "not this daemon's socket"

    def test_serve_with_distinct_socket_and_pidfile_basenames(self, tmp_path):
        runtime_dir = tmp_path / "rt"
        runtime_dir.mkdir(mode=0o700)
        socket_path = runtime_dir / "alpha.sock"
        pidfile_path = runtime_dir / "beta.pid"

        proc = multiprocessing.Process(
            target=_run_serve_in_process,
            args=(str(socket_path), str(pidfile_path), 2.0, str(tmp_path)),
        )
        proc.start()

        try:
            deadline = time.time() + 5.0
            while time.time() < deadline:
                if socket_path.exists() and pidfile_path.exists():
                    break
                time.sleep(0.05)
            else:
                pytest.fail("daemon failed to start with custom basenames")

            response = _send_request(
                socket_path,
                {"id": "dist", "method": "ping", "params": {}},
            )
            assert response["ok"] is True
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=2.0)
