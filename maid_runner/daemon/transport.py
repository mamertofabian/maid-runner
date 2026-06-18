"""Transport helpers for the maid serve daemon."""

from __future__ import annotations

import hmac
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


_TCP_HOST = "127.0.0.1"
_PORT_FILE = "serve.port"
_TOKEN_FILE = "serve.token"
_RUNTIME_FILE_MODE = 0o600


@dataclass(frozen=True)
class TcpTransportInfo:
    """Resolved TCP transport identity for one daemon process."""

    host: str
    port: int
    token: str


def generate_token() -> str:
    """Return a cryptographically random per-process TCP auth token."""
    return secrets.token_urlsafe(32)


def write_tcp_runtime_files(
    runtime_dir: Union[str, Path],
    port: int,
    token: str,
) -> None:
    """Publish the TCP daemon port and token for local clients."""
    root = Path(runtime_dir)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    _write_owner_only_file(root / _PORT_FILE, f"{int(port)}\n")
    _write_owner_only_file(root / _TOKEN_FILE, f"{token}\n")


def read_tcp_runtime_files(runtime_dir: Union[str, Path]) -> TcpTransportInfo:
    """Read TCP daemon runtime files, failing loudly for stale or malformed state."""
    root = Path(runtime_dir)
    port_path = root / _PORT_FILE
    token_path = root / _TOKEN_FILE
    if not port_path.exists() or not token_path.exists():
        raise RuntimeError(f"missing TCP runtime files in {root}")

    try:
        port = int(port_path.read_text().strip())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"malformed TCP port file {port_path}: {exc}") from exc
    if port <= 0 or port > 65535:
        raise RuntimeError(f"malformed TCP port file {port_path}: port out of range")

    try:
        token = token_path.read_text().strip()
    except OSError as exc:
        raise RuntimeError(f"cannot read TCP token file {token_path}: {exc}") from exc
    if not token:
        raise RuntimeError(f"malformed TCP token file {token_path}: empty token")

    return TcpTransportInfo(host=_TCP_HOST, port=port, token=token)


def token_is_valid(provided: Optional[str], expected: str) -> bool:
    """Return True only when the provided token exactly matches the expected token."""
    if not isinstance(provided, str):
        return False
    return hmac.compare_digest(provided, expected)


def _write_owner_only_file(path: Path, content: str) -> None:
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _RUNTIME_FILE_MODE)
    try:
        os.write(fd, content.encode("utf-8"))
        try:
            os.fchmod(fd, _RUNTIME_FILE_MODE)
        except OSError:
            pass
    finally:
        os.close(fd)
