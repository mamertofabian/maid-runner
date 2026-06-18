"""Behavioral tests for the reusable maid serve daemon client."""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path


def _serve_one_tcp_response(response: dict):
    captured: list[dict] = []
    ready = threading.Event()

    def run(listener: socket.socket) -> None:
        with listener:
            listener.listen(1)
            ready.set()
            conn, _ = listener.accept()
            with conn:
                data = b""
                while b"\n" not in data:
                    data += conn.recv(4096)
                captured.append(json.loads(data.split(b"\n", 1)[0].decode("utf-8")))
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    host, port = listener.getsockname()[:2]
    thread = threading.Thread(target=run, args=(listener,), daemon=True)
    thread.start()
    assert ready.wait(timeout=2.0)
    return str(host), int(port), captured, thread


def test_resolve_daemon_endpoint_uses_unix_socket_by_default(tmp_path):
    from maid_runner.daemon.client import DaemonEndpoint, resolve_daemon_endpoint

    socket_path = tmp_path / "serve.sock"
    socket_path.write_text("placeholder")

    endpoint = resolve_daemon_endpoint(
        runtime_dir=tmp_path,
        socket_path=socket_path,
        transport="auto",
    )

    assert isinstance(endpoint, DaemonEndpoint)
    assert endpoint.transport == "unix"
    assert endpoint.socket_path == socket_path
    assert endpoint.host is None
    assert endpoint.port is None
    assert endpoint.token is None


def test_resolve_daemon_endpoint_loads_tcp_runtime_files(tmp_path):
    from maid_runner.daemon.client import resolve_daemon_endpoint
    from maid_runner.daemon.transport import write_tcp_runtime_files

    write_tcp_runtime_files(tmp_path, 49152, "secret-token")

    endpoint = resolve_daemon_endpoint(runtime_dir=tmp_path, transport="tcp")

    assert endpoint.transport == "tcp"
    assert endpoint.host == "127.0.0.1"
    assert endpoint.port == 49152
    assert endpoint.token == "secret-token"
    assert endpoint.socket_path is None


def test_daemon_client_request_sends_protocol_version_and_tcp_token():
    from maid_runner.daemon.client import DaemonClient, DaemonEndpoint

    host, port, captured, thread = _serve_one_tcp_response(
        {"id": "client-1", "ok": True, "result": {"pong": True}}
    )
    client = DaemonClient(
        DaemonEndpoint(
            transport="tcp",
            socket_path=None,
            host=host,
            port=port,
            token="secret-token",
        ),
        timeout_s=2.0,
    )

    result = client.request("ping", {"extra": True})

    thread.join(timeout=2.0)
    assert result == {"pong": True}
    assert captured[0]["method"] == "ping"
    assert captured[0]["params"] == {"extra": True}
    assert captured[0]["protocol_version"] == 1
    assert captured[0]["token"] == "secret-token"


def test_daemon_client_raises_structured_error_for_request_failure():
    from maid_runner.daemon.client import (
        DaemonClient,
        DaemonClientError,
        DaemonEndpoint,
    )

    host, port, _captured, thread = _serve_one_tcp_response(
        {
            "id": "client-1",
            "ok": False,
            "error": {"code": "BAD_TOKEN", "message": "missing token"},
        }
    )
    client = DaemonClient(
        DaemonEndpoint(
            transport="tcp",
            socket_path=None,
            host=host,
            port=port,
            token="secret-token",
        ),
        timeout_s=2.0,
    )

    try:
        client.request("ping")
    except DaemonClientError as exc:
        assert exc.code == "BAD_TOKEN"
        assert exc.message == "missing token"
    else:
        raise AssertionError("DaemonClientError was not raised")
    finally:
        thread.join(timeout=2.0)


def test_daemon_client_ping_validate_and_verify_helpers_send_expected_params():
    from maid_runner.daemon.client import DaemonClient, DaemonEndpoint

    responses = [
        {"id": "client-1", "ok": True, "result": {"uptime_s": 1.0}},
        {"id": "client-2", "ok": True, "result": {"success": True}},
        {"id": "client-3", "ok": True, "result": {"success": True, "stages": []}},
    ]
    captured: list[dict] = []
    ready = threading.Event()

    def run(listener: socket.socket) -> None:
        with listener:
            listener.listen(3)
            ready.set()
            for response in responses:
                conn, _ = listener.accept()
                with conn:
                    data = b""
                    while b"\n" not in data:
                        data += conn.recv(4096)
                    captured.append(json.loads(data.split(b"\n", 1)[0].decode("utf-8")))
                    conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    host, port = listener.getsockname()[:2]
    thread = threading.Thread(target=run, args=(listener,), daemon=True)
    thread.start()
    assert ready.wait(timeout=2.0)
    client = DaemonClient(
        DaemonEndpoint(
            transport="tcp",
            socket_path=None,
            host=str(host),
            port=int(port),
            token="secret-token",
        ),
        timeout_s=2.0,
    )

    assert client.ping() == {"uptime_s": 1.0}
    assert client.validate("manifests/demo.manifest.yaml", mode="schema") == {
        "success": True
    }
    assert client.verify("manifests/", allow_empty=True) == {
        "success": True,
        "stages": [],
    }

    thread.join(timeout=2.0)
    assert [payload["method"] for payload in captured] == [
        "ping",
        "validate",
        "verify",
    ]
    assert captured[1]["params"] == {
        "manifest_path": "manifests/demo.manifest.yaml",
        "mode": "schema",
    }
    assert captured[2]["params"] == {
        "manifest_dir": "manifests/",
        "allow_empty": True,
    }


def test_daemon_client_connects_to_unix_socket(tmp_path):
    from maid_runner.daemon.client import DaemonClient, DaemonEndpoint

    socket_path = tmp_path / "serve.sock"
    captured: list[dict] = []
    ready = threading.Event()

    def run() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            listener.listen(1)
            ready.set()
            conn, _ = listener.accept()
            with conn:
                data = b""
                while b"\n" not in data:
                    data += conn.recv(4096)
                captured.append(json.loads(data.split(b"\n", 1)[0].decode("utf-8")))
                conn.sendall(
                    b'{"id": "client-1", "ok": true, "result": {"pong": true}}\n'
                )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(timeout=2.0)
    client = DaemonClient(
        DaemonEndpoint(
            transport="unix",
            socket_path=socket_path,
            host=None,
            port=None,
            token=None,
        ),
        timeout_s=2.0,
    )

    assert client.request("ping") == {"pong": True}

    thread.join(timeout=2.0)
    assert "token" not in captured[0]
    assert captured[0]["protocol_version"] == 1
    assert captured[0]["method"] == "ping"


def test_daemon_client_docs_describe_long_lived_protocol_usage():
    docs = Path("docs/maid-serve.md").read_text()

    assert "DaemonClient" in docs
    assert "resolve_daemon_endpoint" in docs
    assert "long-lived" in docs
