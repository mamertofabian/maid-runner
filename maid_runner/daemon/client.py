"""Reusable client for the maid serve daemon protocol."""

from __future__ import annotations

import json
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from maid_runner.daemon.transport import read_tcp_runtime_files


_PROTOCOL_VERSION = 1
_DEFAULT_RUNTIME_DIR = ".maid"
_DEFAULT_SOCKET_PATH = ".maid/serve.sock"
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class DaemonEndpoint:
    """Immutable connection details for one daemon transport endpoint."""

    transport: str
    socket_path: Optional[Path]
    host: Optional[str]
    port: Optional[int]
    token: Optional[str]


class DaemonClientError(Exception):
    """Structured daemon client error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def resolve_daemon_endpoint(
    runtime_dir: Union[str, Path] = _DEFAULT_RUNTIME_DIR,
    socket_path: Union[str, Path] = _DEFAULT_SOCKET_PATH,
    transport: str = "auto",
) -> DaemonEndpoint:
    """Resolve a daemon endpoint from local runtime files."""
    runtime_root = Path(runtime_dir)
    socket = Path(socket_path)

    if transport not in {"auto", "unix", "tcp"}:
        raise DaemonClientError("BAD_TRANSPORT", f"unknown transport '{transport}'")

    if transport in {"auto", "unix"} and socket.exists():
        return DaemonEndpoint(
            transport="unix",
            socket_path=socket,
            host=None,
            port=None,
            token=None,
        )

    if transport in {"auto", "tcp"}:
        try:
            info = read_tcp_runtime_files(runtime_root)
        except RuntimeError as exc:
            if transport == "tcp":
                raise DaemonClientError("DAEMON_UNAVAILABLE", str(exc)) from exc
        else:
            return DaemonEndpoint(
                transport="tcp",
                socket_path=None,
                host=info.host,
                port=info.port,
                token=info.token,
            )

    if transport == "unix":
        raise DaemonClientError("DAEMON_UNAVAILABLE", f"missing Unix socket {socket}")
    raise DaemonClientError(
        "DAEMON_UNAVAILABLE",
        f"no daemon endpoint found at {socket} or {runtime_root}",
    )


class DaemonClient:
    """Reusable daemon protocol client for long-lived integrations."""

    def __init__(self, endpoint: DaemonEndpoint, timeout_s: float = 30.0) -> None:
        self._endpoint = endpoint
        self._timeout_s = float(timeout_s)

    def request(self, method: str, params: Optional[dict] = None) -> dict:
        """Send one daemon request and return the result payload."""
        request_id = f"client-{uuid.uuid4().hex}"
        payload = {
            "id": request_id,
            "method": method,
            "protocol_version": _PROTOCOL_VERSION,
            "params": params or {},
        }
        if self._endpoint.transport == "tcp":
            if not self._endpoint.token:
                raise DaemonClientError("BAD_ENDPOINT", "TCP endpoint is missing token")
            payload["token"] = self._endpoint.token

        response = self._round_trip(payload)
        if response.get("ok") is True:
            result = response.get("result")
            if isinstance(result, dict):
                return result
            raise DaemonClientError("BAD_RESPONSE", "daemon result is not an object")

        error = response.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            if isinstance(code, str) and isinstance(message, str):
                raise DaemonClientError(code, message)
        raise DaemonClientError("BAD_RESPONSE", "daemon error response is malformed")

    def ping(self) -> dict:
        """Return the daemon ping payload."""
        return self.request("ping", {})

    def validate(self, manifest_path: str, mode: str = "implementation") -> dict:
        """Validate one manifest through the daemon."""
        return self.request(
            "validate",
            {
                "manifest_path": manifest_path,
                "mode": mode,
            },
        )

    def verify(
        self, manifest_dir: str = "manifests/", allow_empty: bool = False
    ) -> dict:
        """Run the daemon-supported verify subset."""
        return self.request(
            "verify",
            {
                "manifest_dir": manifest_dir,
                "allow_empty": allow_empty,
            },
        )

    def _round_trip(self, payload: dict) -> dict:
        data = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            with self._connect() as conn:
                conn.settimeout(self._timeout_s)
                conn.sendall(data)
                raw = self._read_response(conn)
        except OSError as exc:
            raise DaemonClientError("DAEMON_UNAVAILABLE", str(exc)) from exc

        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise DaemonClientError(
                "BAD_RESPONSE", f"invalid daemon JSON: {exc}"
            ) from exc
        if not isinstance(response, dict):
            raise DaemonClientError("BAD_RESPONSE", "daemon response is not an object")
        return response

    def _connect(self) -> socket.socket:
        if self._endpoint.transport == "unix":
            if self._endpoint.socket_path is None:
                raise DaemonClientError(
                    "BAD_ENDPOINT", "Unix endpoint is missing socket"
                )
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(self._timeout_s)
            try:
                conn.connect(str(self._endpoint.socket_path))
            except OSError:
                conn.close()
                raise
            return conn

        if self._endpoint.transport == "tcp":
            if self._endpoint.host is None or self._endpoint.port is None:
                raise DaemonClientError(
                    "BAD_ENDPOINT", "TCP endpoint is missing host/port"
                )
            return socket.create_connection(
                (self._endpoint.host, self._endpoint.port),
                timeout=self._timeout_s,
            )

        raise DaemonClientError(
            "BAD_ENDPOINT",
            f"unknown endpoint transport '{self._endpoint.transport}'",
        )

    def _read_response(self, conn: socket.socket) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if b"\n" in chunk:
                break
            if total > _MAX_RESPONSE_BYTES:
                raise DaemonClientError(
                    "BAD_RESPONSE",
                    f"daemon response exceeded {_MAX_RESPONSE_BYTES} bytes",
                )
        if not chunks:
            raise DaemonClientError("BAD_RESPONSE", "daemon closed without a response")
        return b"".join(chunks).split(b"\n", 1)[0]
