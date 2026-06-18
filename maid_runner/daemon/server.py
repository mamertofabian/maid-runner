"""Unix-socket NDJSON server for the maid serve daemon."""

from __future__ import annotations

import os
import json
import signal
import socket
import stat
import sys
import threading
import traceback
from pathlib import Path

from maid_runner.daemon import handlers as _handlers
from maid_runner.daemon.handlers import HANDLERS
from maid_runner.daemon.protocol import (
    DaemonRequestError,
    ProtocolError,
    Response,
    UnsupportedProtocolVersionError,
    error_response,
    parse_request,
    render_response,
)
from maid_runner.daemon.transport import (
    TcpTransportInfo,
    generate_token,
    token_is_valid,
    write_tcp_runtime_files,
)


_DEFAULT_TIMEOUT_S = 30.0
_MAX_FRAME_BYTES = 1 * 1024 * 1024
_ACCEPT_POLL_S = 0.5
_SOCKET_DIR_MODE = 0o700
_SOCKET_FILE_MODE = 0o600
_TCP_HOST = "127.0.0.1"


def check_stale_pidfile(pidfile_path: Path) -> bool:
    """Return True (and remove the pidfile) if the pidfile points to a non-running process.

    Only touches the pidfile. Socket cleanup is the caller's responsibility
    and goes through :func:`_clear_existing_socket`, which verifies the
    target is actually a socket before unlinking. This avoids deleting
    unrelated sockets that happen to share a basename with the pidfile.
    """
    if not pidfile_path.exists():
        return True

    try:
        pid_text = pidfile_path.read_text().strip()
        pid = int(pid_text)
    except (OSError, ValueError):
        try:
            pidfile_path.unlink()
        except OSError:
            pass
        return True

    if _process_alive(pid):
        return False

    try:
        pidfile_path.unlink()
    except OSError:
        pass

    return True


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _prepare_runtime_directory(directory: Path) -> None:
    """Create the daemon's runtime directory with restrictive ownership/mode."""
    if not directory.exists():
        directory.mkdir(parents=True, mode=_SOCKET_DIR_MODE, exist_ok=True)
        try:
            os.chmod(str(directory), _SOCKET_DIR_MODE)
        except OSError:
            pass
        return

    try:
        st = os.lstat(str(directory))
    except OSError as exc:
        raise RuntimeError(f"cannot stat runtime directory {directory}: {exc}") from exc

    if not stat.S_ISDIR(st.st_mode):
        raise RuntimeError(f"runtime path {directory} exists but is not a directory")

    current_uid = _current_effective_uid()
    if current_uid is not None and st.st_uid != current_uid:
        raise RuntimeError(
            f"runtime directory {directory} is owned by uid {st.st_uid}, "
            f"refusing to use it (expected uid {current_uid})"
        )

    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise RuntimeError(
            f"runtime directory {directory} has group/world permissions "
            f"(mode {oct(st.st_mode & 0o777)}); refusing to use it. "
            f"Run `chmod 700 {directory}` and retry."
        )


def _current_effective_uid() -> int | None:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return None
    return int(geteuid())


def _clear_existing_socket(socket_path: Path) -> None:
    """Remove an existing socket file, but refuse to delete non-socket entries."""
    try:
        st = os.lstat(str(socket_path))
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeError(f"cannot stat socket path {socket_path}: {exc}") from exc

    if not stat.S_ISSOCK(st.st_mode):
        raise RuntimeError(
            f"refusing to start: {socket_path} exists but is not a socket "
            f"(mode {oct(stat.S_IFMT(st.st_mode))}). "
            f"Move or delete it manually before retrying."
        )

    try:
        os.unlink(str(socket_path))
    except OSError as exc:
        raise RuntimeError(f"cannot remove stale socket {socket_path}: {exc}") from exc


def _acquire_pidfile(pidfile_path: Path) -> bool:
    """Atomically claim the pidfile. Return True on success, False if another live daemon owns it."""
    for _ in range(2):
        claim_path = pidfile_path.with_name(
            f".{pidfile_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            claim_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            return False

        try:
            fd = os.open(str(claim_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except OSError:
            return False

        try:
            os.write(fd, str(os.getpid()).encode("ascii"))
        finally:
            os.close(fd)

        try:
            os.link(str(claim_path), str(pidfile_path))
        except FileExistsError:
            try:
                claim_path.unlink()
            except OSError:
                pass
            if not check_stale_pidfile(pidfile_path):
                return False
            continue
        except OSError:
            try:
                claim_path.unlink()
            except OSError:
                pass
            return False

        try:
            claim_path.unlink()
        except OSError:
            pass
        return True
    return False


class Server:
    """Unix-socket NDJSON server that dispatches validate and ping requests."""

    def __init__(
        self,
        socket_path: Path,
        pidfile_path: Path,
        client_timeout_s: float = _DEFAULT_TIMEOUT_S,
        project_root: Path | str = ".",
        transport: str = "unix",
    ) -> None:
        if transport not in {"unix", "tcp"}:
            raise ValueError("transport must be 'unix' or 'tcp'")
        self.socket_path: Path = Path(socket_path)
        self.pidfile_path: Path = Path(pidfile_path)
        self.client_timeout_s: float = float(client_timeout_s)
        self.project_root: Path = Path(project_root).resolve()
        self.transport: str = transport
        self._tcp_info: TcpTransportInfo | None = None
        self._listening: socket.socket | None = None
        self._running: bool = False
        self._pidfile_owned: bool = False
        self._client_threads: list[threading.Thread] = []

    def start(self) -> None:
        """Bind the socket, write the pidfile, install signal handlers, and enter the accept loop."""
        _prepare_runtime_directory(self.socket_path.parent)
        _prepare_runtime_directory(self.pidfile_path.parent)

        if not _acquire_pidfile(self.pidfile_path):
            raise RuntimeError(
                f"another maid serve daemon is already running (pidfile: {self.pidfile_path})"
            )
        self._pidfile_owned = True

        if self.transport == "unix":
            _clear_existing_socket(self.socket_path)

        _handlers.configure_context(self.project_root)

        if self.transport == "tcp":
            listening = self._bind_tcp_listener()
        else:
            listening = self._bind_unix_listener()

        listening.listen(16)
        listening.settimeout(_ACCEPT_POLL_S)
        self._listening = listening
        self._running = True

        signal.signal(signal.SIGTERM, self._signal_shutdown)
        signal.signal(signal.SIGINT, self._signal_shutdown)

        try:
            while self._running:
                try:
                    conn, _ = listening.accept()
                except socket.timeout:
                    self._reap_finished_threads()
                    continue
                except OSError:
                    break

                conn.settimeout(self.client_timeout_s)
                thread = threading.Thread(
                    target=self._serve_client,
                    args=(conn,),
                    daemon=True,
                )
                self._client_threads.append(thread)
                thread.start()
                self._reap_finished_threads()
        finally:
            self.shutdown()
            self._join_client_threads(timeout=2.0)

    def shutdown(self) -> None:
        """Close the listening socket, remove the pidfile and socket file, and exit the accept loop."""
        self._running = False
        if self._listening is not None:
            try:
                self._listening.close()
            except OSError:
                pass
            self._listening = None
        if self.transport == "unix" and self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass
        if self.transport == "tcp":
            for name in ("serve.port", "serve.token"):
                path = self.socket_path.parent / name
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass
        if self._pidfile_owned and self.pidfile_path.exists():
            try:
                self.pidfile_path.unlink()
            except OSError:
                pass
            self._pidfile_owned = False

    def handle_client(self, conn: socket.socket) -> None:
        """Read NDJSON lines from one client, dispatch to handlers, write back NDJSON responses."""
        buffer = b""
        while True:
            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                return
            except OSError:
                return
            if not chunk:
                return
            buffer += chunk

            while b"\n" in buffer:
                line_bytes, buffer = buffer.split(b"\n", 1)
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                response = self._dispatch(line)
                try:
                    conn.sendall(render_response(response).encode("utf-8"))
                except OSError:
                    return

            if len(buffer) > _MAX_FRAME_BYTES:
                response = error_response(
                    "",
                    code="FRAME_TOO_LARGE",
                    message=(
                        f"request frame exceeded {_MAX_FRAME_BYTES} bytes "
                        "without newline terminator"
                    ),
                )
                try:
                    conn.sendall(render_response(response).encode("utf-8"))
                except OSError:
                    pass
                return

    def _serve_client(self, conn: socket.socket) -> None:
        try:
            self.handle_client(conn)
        except Exception:
            traceback.print_exc()
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _reap_finished_threads(self) -> None:
        self._client_threads = [t for t in self._client_threads if t.is_alive()]

    def _join_client_threads(self, *, timeout: float) -> None:
        deadline_per_thread = max(0.05, timeout / max(1, len(self._client_threads)))
        for t in self._client_threads:
            t.join(timeout=deadline_per_thread)
        self._client_threads = []

    def _dispatch(self, line: str) -> Response:
        token_error = self._tcp_token_error(line)
        if token_error is not None:
            return token_error

        try:
            request = parse_request(line)
        except UnsupportedProtocolVersionError as exc:
            return error_response(
                exc.request_id,
                code="UNSUPPORTED_PROTOCOL_VERSION",
                message=str(exc),
            )
        except ProtocolError as exc:
            return error_response("", code="PROTOCOL_ERROR", message=str(exc))

        handler = HANDLERS.get(request.method)
        if handler is None:
            return error_response(
                request.id,
                code="UNKNOWN_METHOD",
                message=f"unknown method '{request.method}'",
            )

        try:
            result = handler(request.params)
        except DaemonRequestError as exc:
            return error_response(request.id, code=exc.code, message=exc.message)
        except Exception as exc:
            return error_response(
                request.id,
                code="HANDLER_ERROR",
                message=f"{type(exc).__name__}: {exc}",
            )

        return Response(id=request.id, ok=True, result=result, error=None)

    def _bind_unix_listener(self) -> socket.socket:
        prev_umask = os.umask(0o077)
        try:
            listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listening.bind(str(self.socket_path))
            os.chmod(str(self.socket_path), _SOCKET_FILE_MODE)
        finally:
            os.umask(prev_umask)
        return listening

    def _bind_tcp_listener(self) -> socket.socket:
        token = generate_token()
        listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listening.bind((_TCP_HOST, 0))
            host, port = listening.getsockname()[:2]
            self._tcp_info = TcpTransportInfo(host=host, port=int(port), token=token)
            write_tcp_runtime_files(self.socket_path.parent, int(port), token)
            return listening
        except Exception:
            listening.close()
            raise

    def _tcp_token_error(self, line: str) -> Response | None:
        if self.transport != "tcp":
            return None
        expected = self._tcp_info.token if self._tcp_info is not None else ""
        try:
            payload = json.loads(line)
        except (ValueError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None
        request_id = payload.get("id")
        response_id = request_id if isinstance(request_id, str) else ""
        if token_is_valid(payload.get("token"), expected):
            return None
        return error_response(
            response_id,
            code="BAD_TOKEN",
            message="missing or invalid TCP transport token",
        )

    def _signal_shutdown(self, signum, frame) -> None:
        del signum, frame
        self._running = False
        if self._listening is not None:
            try:
                self._listening.close()
            except OSError:
                pass


def serve(
    socket_path: Path,
    pidfile_path: Path,
    client_timeout_s: float,
    project_root: Path | str = ".",
    transport: str = "unix",
) -> int:
    """Top-level entrypoint: construct a Server, start it, and return a process exit code.

    The daemon binds to ``project_root`` at startup. Client-supplied
    ``project_root`` values in requests are ignored.
    """
    socket_path = Path(socket_path)
    pidfile_path = Path(pidfile_path)

    server = Server(
        socket_path,
        pidfile_path,
        client_timeout_s,
        project_root,
        transport=transport,
    )
    try:
        server.start()
    except RuntimeError as exc:
        sys.stderr.write(f"maid serve: {exc}\n")
        return 1
    except Exception:
        traceback.print_exc()
        server.shutdown()
        return 1
    return 0
