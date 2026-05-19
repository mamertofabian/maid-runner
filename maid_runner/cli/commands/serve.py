"""CLI handler for 'maid serve' command."""

from __future__ import annotations

import argparse
from pathlib import Path

from maid_runner.daemon.server import _DEFAULT_TIMEOUT_S


_DEFAULT_SOCKET = ".maid/serve.sock"
_DEFAULT_PIDFILE = ".maid/serve.pid"


def register_serve_subparser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    """Register the `maid serve` subcommand on the top-level parser."""
    parser = subparsers.add_parser(
        "serve",
        help="Run maid-runner as a long-lived validator daemon over a Unix socket",
    )
    parser.add_argument(
        "--socket",
        default=_DEFAULT_SOCKET,
        help=f"Unix socket path (default: {_DEFAULT_SOCKET})",
    )
    parser.add_argument(
        "--pidfile",
        default=_DEFAULT_PIDFILE,
        help=f"PID file path (default: {_DEFAULT_PIDFILE})",
    )
    parser.add_argument(
        "--client-timeout",
        type=float,
        default=_DEFAULT_TIMEOUT_S,
        dest="client_timeout",
        help=f"Per-client read timeout in seconds (default: {_DEFAULT_TIMEOUT_S})",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        dest="project_root",
        help="Project root the daemon is bound to (default: current directory)",
    )
    return parser


def cmd_serve(args: argparse.Namespace) -> int:
    """CLI handler for `maid serve`: resolve socket/pidfile paths and start the daemon."""
    from maid_runner.daemon.server import serve as _serve

    socket_path = Path(getattr(args, "socket", _DEFAULT_SOCKET))
    pidfile_path = Path(getattr(args, "pidfile", _DEFAULT_PIDFILE))
    client_timeout_s = float(getattr(args, "client_timeout", _DEFAULT_TIMEOUT_S))
    project_root = getattr(args, "project_root", ".")

    return _serve(socket_path, pidfile_path, client_timeout_s, project_root)
