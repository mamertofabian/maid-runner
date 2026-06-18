"""Behavioral tests for TCP transport support in the maid serve daemon."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import socket
import time
from pathlib import Path

import pytest

from maid_runner.cli.commands._main import build_parser


def _run_tcp_serve(
    socket_path: str,
    pidfile_path: str,
    client_timeout_s: float,
    project_root: str,
    transport: str,
) -> None:
    from maid_runner.daemon.server import serve

    serve(
        Path(socket_path),
        Path(pidfile_path),
        client_timeout_s,
        project_root,
        transport=transport,
    )


def _run_tcp_serve_without_geteuid(
    socket_path: str,
    pidfile_path: str,
    client_timeout_s: float,
    project_root: str,
    transport: str,
) -> None:
    from maid_runner.daemon import server as daemon_server

    if hasattr(daemon_server.os, "geteuid"):
        delattr(daemon_server.os, "geteuid")
    daemon_server.serve(
        Path(socket_path),
        Path(pidfile_path),
        client_timeout_s,
        project_root,
        transport=transport,
    )


def _wait_for_file(path: Path, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    pytest.fail(f"{path} was not created within {timeout}s")


def _read_one_response(conn: socket.socket, timeout: float = 5.0) -> dict:
    conn.settimeout(timeout)
    chunks: list[bytes] = []
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        if b"\n" in chunk:
            break
    return json.loads(b"".join(chunks).split(b"\n", 1)[0].decode("utf-8"))


def _tcp_request(info, payload: dict, timeout: float = 5.0) -> dict:
    with socket.create_connection((info.host, info.port), timeout=timeout) as conn:
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        return _read_one_response(conn, timeout=timeout)


@pytest.fixture
def tcp_daemon(tmp_path):
    runtime_dir = tmp_path / ".maid"
    socket_path = runtime_dir / "serve.sock"
    pidfile_path = runtime_dir / "serve.pid"

    proc = multiprocessing.Process(
        target=_run_tcp_serve,
        args=(str(socket_path), str(pidfile_path), 2.0, str(tmp_path), "tcp"),
    )
    proc.start()
    _wait_for_file(runtime_dir / "serve.port")
    _wait_for_file(runtime_dir / "serve.token")

    from maid_runner.daemon.transport import read_tcp_runtime_files

    info = read_tcp_runtime_files(runtime_dir)
    yield {"info": info, "pidfile": pidfile_path, "proc": proc, "runtime": runtime_dir}

    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=2.0)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=2.0)


def _write_schema_manifest(project: Path) -> Path:
    manifest = project / "demo.manifest.yaml"
    manifest.write_text(
        "schema: '2'\n"
        "goal: demo\n"
        "type: feature\n"
        "files:\n"
        "  create: []\n"
        "validate:\n"
        "  - python -c 'pass'\n"
    )
    return manifest


def test_generate_token_returns_distinct_nonempty_tokens():
    from maid_runner.daemon.transport import generate_token

    first = generate_token()
    second = generate_token()

    assert isinstance(first, str)
    assert isinstance(second, str)
    assert len(first) >= 32
    assert len(second) >= 32
    assert first != second


def test_write_tcp_runtime_files_records_port_and_owner_only_token(tmp_path):
    from maid_runner.daemon.transport import write_tcp_runtime_files

    write_tcp_runtime_files(tmp_path, 49152, "secret-token")

    assert (tmp_path / "serve.port").read_text().strip() == "49152"
    assert (tmp_path / "serve.token").read_text().strip() == "secret-token"
    assert (os.stat(tmp_path / "serve.token").st_mode & 0o777) == 0o600


def test_read_tcp_runtime_files_fails_loudly_for_missing_or_malformed_files(tmp_path):
    from maid_runner.daemon.transport import TcpTransportInfo, read_tcp_runtime_files

    with pytest.raises(RuntimeError, match="missing"):
        read_tcp_runtime_files(tmp_path)

    (tmp_path / "serve.port").write_text("not-a-port")
    (tmp_path / "serve.token").write_text("token")

    with pytest.raises(RuntimeError, match="port"):
        read_tcp_runtime_files(tmp_path)

    (tmp_path / "serve.port").write_text("49152")
    info = read_tcp_runtime_files(tmp_path)
    assert isinstance(info, TcpTransportInfo)
    assert info.host == "127.0.0.1"


def test_token_is_valid_requires_exact_constant_time_match():
    from maid_runner.daemon.transport import token_is_valid

    assert token_is_valid("secret", "secret") is True
    assert token_is_valid("Secret", "secret") is False
    assert token_is_valid(None, "secret") is False


def test_serve_parser_accepts_transport_choice_defaulting_to_unix():
    from maid_runner.cli.commands.serve import register_serve_subparser

    standalone = argparse.ArgumentParser()
    subparsers = standalone.add_subparsers(dest="command")
    register_serve_subparser(subparsers)

    parser = build_parser()

    direct = standalone.parse_args(["serve", "--transport", "tcp"])
    default = parser.parse_args(["serve"])
    tcp = parser.parse_args(["serve", "--transport", "tcp"])

    assert direct.transport == "tcp"
    assert default.transport == "unix"
    assert tcp.transport == "tcp"
    with pytest.raises(SystemExit):
        parser.parse_args(["serve", "--transport", "public"])


def test_cmd_serve_forwards_transport_selection(monkeypatch, tmp_path):
    from maid_runner.cli.commands.serve import cmd_serve
    from maid_runner.daemon import server as daemon_server

    observed: dict[str, object] = {}

    def fake_serve(
        socket_path, pidfile_path, client_timeout_s, project_root, transport
    ):
        observed["socket_path"] = socket_path
        observed["pidfile_path"] = pidfile_path
        observed["client_timeout_s"] = client_timeout_s
        observed["project_root"] = project_root
        observed["transport"] = transport
        return 0

    monkeypatch.setattr(daemon_server, "serve", fake_serve)
    args = argparse.Namespace(
        socket=tmp_path / "serve.sock",
        pidfile=tmp_path / "serve.pid",
        client_timeout=1.5,
        project_root=str(tmp_path),
        transport="tcp",
    )

    assert cmd_serve(args) == 0
    assert observed["transport"] == "tcp"
    assert observed["project_root"] == str(tmp_path)


def test_tcp_server_binds_loopback_and_requires_token_before_dispatch(tcp_daemon):
    info = tcp_daemon["info"]

    assert info.host == "127.0.0.1"
    missing = _tcp_request(info, {"id": "bad-1", "method": "ping", "params": {}})
    wrong = _tcp_request(
        info,
        {
            "id": "bad-2",
            "method": "ping",
            "token": "wrong",
            "params": {},
        },
    )

    assert missing["id"] == "bad-1"
    assert missing["ok"] is False
    assert missing["error"]["code"] == "BAD_TOKEN"
    assert wrong["id"] == "bad-2"
    assert wrong["ok"] is False
    assert wrong["error"]["code"] == "BAD_TOKEN"


def test_tcp_request_with_valid_token_round_trips_ping_and_validate(
    tcp_daemon,
    tmp_path,
):
    info = tcp_daemon["info"]
    manifest = _write_schema_manifest(tmp_path)

    ping = _tcp_request(
        info,
        {
            "id": "ping-1",
            "method": "ping",
            "token": info.token,
            "params": {},
        },
    )
    validate = _tcp_request(
        info,
        {
            "id": "validate-1",
            "method": "validate",
            "token": info.token,
            "params": {"manifest_path": str(manifest), "mode": "schema"},
        },
    )

    assert ping["ok"] is True
    assert {"pid", "version", "uptime_s"} <= set(ping["result"])
    assert validate["ok"] is True
    assert validate["result"]["success"] is True
    assert validate["result"]["mode"] == "schema"


def test_tcp_server_starts_when_geteuid_is_unavailable(tmp_path):
    runtime_dir = tmp_path / ".maid"
    socket_path = runtime_dir / "serve.sock"
    pidfile_path = runtime_dir / "serve.pid"

    proc = multiprocessing.Process(
        target=_run_tcp_serve_without_geteuid,
        args=(str(socket_path), str(pidfile_path), 2.0, str(tmp_path), "tcp"),
    )
    proc.start()
    try:
        _wait_for_file(runtime_dir / "serve.port")
        _wait_for_file(runtime_dir / "serve.token")
        assert proc.is_alive()
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2.0)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2.0)


def test_tcp_shutdown_preserves_socket_path_placeholder(tmp_path):
    from maid_runner.daemon.server import Server

    runtime_dir = tmp_path / ".maid"
    runtime_dir.mkdir()
    placeholder = runtime_dir / "serve.sock"
    placeholder.write_text("not a tcp socket")

    server = Server(
        placeholder,
        runtime_dir / "serve.pid",
        project_root=tmp_path,
        transport="tcp",
    )
    server.shutdown()

    assert placeholder.read_text() == "not a tcp socket"


def test_unix_transport_remains_default_and_writes_no_tcp_runtime_files(tmp_path):
    from maid_runner.daemon.server import Server

    runtime_dir = tmp_path / ".maid"
    server = Server(
        runtime_dir / "serve.sock",
        runtime_dir / "serve.pid",
        project_root=tmp_path,
    )

    assert server.transport == "unix"
    assert not (runtime_dir / "serve.port").exists()
    assert not (runtime_dir / "serve.token").exists()


def test_maid_serve_docs_describe_tcp_transport_and_token():
    docs = Path("docs/maid-serve.md").read_text()

    assert "--transport" in docs
    assert "unix|tcp" in docs
    assert "serve.port" in docs
    assert "serve.token" in docs
    assert '"token"' in docs
    assert 'transport="unix"' in docs
    assert "BAD_TOKEN" in docs
