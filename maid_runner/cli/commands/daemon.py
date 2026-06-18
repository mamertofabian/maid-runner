"""CLI handler for diagnostic maid daemon client commands."""

from __future__ import annotations

import argparse
import json

from maid_runner.daemon.client import (
    DaemonClient,
    DaemonClientError,
    resolve_daemon_endpoint,
)


_DEFAULT_RUNTIME_DIR = ".maid"
_DEFAULT_SOCKET = ".maid/serve.sock"
_DEFAULT_TIMEOUT_S = 30.0


def register_daemon_subparser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    """Register the diagnostic `maid daemon` subcommand."""
    parser = subparsers.add_parser(
        "daemon",
        help="Call a running maid serve daemon directly",
    )
    daemon_sub = parser.add_subparsers(dest="daemon_command")

    ping = daemon_sub.add_parser("ping", help="Ping a running daemon")
    _add_common_options(ping)

    validate = daemon_sub.add_parser(
        "validate",
        help="Validate one manifest through a running daemon",
    )
    validate.add_argument("manifest_path")
    validate.add_argument(
        "--mode",
        default="implementation",
        choices=["schema", "behavioral", "implementation"],
    )
    _add_common_options(validate)

    verify = daemon_sub.add_parser(
        "verify",
        help="Run the daemon-supported verify subset",
    )
    verify.add_argument("--manifest-dir", default="manifests/")
    verify.add_argument("--allow-empty", action="store_true")
    _add_common_options(verify)

    return parser


def cmd_daemon(args: argparse.Namespace) -> int:
    """CLI handler for diagnostic daemon client commands."""
    try:
        endpoint = resolve_daemon_endpoint(
            runtime_dir=getattr(args, "runtime_dir", _DEFAULT_RUNTIME_DIR),
            socket_path=getattr(args, "socket", _DEFAULT_SOCKET),
            transport=getattr(args, "transport", "auto"),
        )
        client = DaemonClient(endpoint, timeout_s=getattr(args, "timeout", 30.0))
        command = getattr(args, "daemon_command", None)
        if command == "ping":
            payload = client.ping()
        elif command == "validate":
            payload = client.validate(
                getattr(args, "manifest_path"),
                mode=getattr(args, "mode", "implementation"),
            )
        elif command == "verify":
            payload = client.verify(
                getattr(args, "manifest_dir", "manifests/"),
                allow_empty=getattr(args, "allow_empty", False),
            )
        else:
            raise DaemonClientError("BAD_COMMAND", "missing daemon subcommand")
    except DaemonClientError as exc:
        error_payload = {"error": {"code": exc.code, "message": exc.message}}
        if getattr(args, "json", False):
            print(json.dumps(error_payload))
        else:
            print(f"{exc.code}: {exc.message}")
        return 2

    if getattr(args, "json", False):
        print(json.dumps(payload))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--transport",
        choices=("auto", "unix", "tcp"),
        default="auto",
        help="Daemon transport to use (default: auto)",
    )
    parser.add_argument(
        "--runtime-dir",
        default=_DEFAULT_RUNTIME_DIR,
        dest="runtime_dir",
        help=f"Daemon runtime directory for TCP files (default: {_DEFAULT_RUNTIME_DIR})",
    )
    parser.add_argument(
        "--socket",
        default=_DEFAULT_SOCKET,
        help=f"Unix socket path (default: {_DEFAULT_SOCKET})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=_DEFAULT_TIMEOUT_S,
        help=f"Daemon client timeout in seconds (default: {_DEFAULT_TIMEOUT_S})",
    )
    parser.add_argument("--json", action="store_true")
