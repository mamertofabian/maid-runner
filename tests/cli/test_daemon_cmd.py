"""Behavioral tests for the maid daemon client CLI."""

from __future__ import annotations

import argparse
import json


def test_daemon_parser_exposes_ping_validate_and_verify_subcommands():
    from maid_runner.cli.commands._main import build_parser
    from maid_runner.cli.commands.daemon import register_daemon_subparser

    standalone = argparse.ArgumentParser()
    subparsers = standalone.add_subparsers(dest="command")
    register_daemon_subparser(subparsers)

    parser = build_parser()
    ping = parser.parse_args(
        [
            "daemon",
            "ping",
            "--transport",
            "tcp",
            "--runtime-dir",
            ".maid",
            "--json",
        ]
    )
    validate = parser.parse_args(
        [
            "daemon",
            "validate",
            "manifests/demo.manifest.yaml",
            "--mode",
            "schema",
        ]
    )
    verify = standalone.parse_args(
        ["daemon", "verify", "--manifest-dir", "manifests/", "--allow-empty"]
    )

    assert ping.command == "daemon"
    assert ping.daemon_command == "ping"
    assert ping.transport == "tcp"
    assert ping.runtime_dir == ".maid"
    assert ping.json is True
    assert validate.daemon_command == "validate"
    assert validate.manifest_path == "manifests/demo.manifest.yaml"
    assert validate.mode == "schema"
    assert verify.daemon_command == "verify"
    assert verify.manifest_dir == "manifests/"
    assert verify.allow_empty is True


def test_cmd_daemon_prints_json_payload_for_success(monkeypatch, capsys):
    from maid_runner.cli.commands import daemon as daemon_cmd
    from maid_runner.cli.commands.daemon import cmd_daemon
    from maid_runner.daemon.client import DaemonEndpoint

    class FakeClient:
        def __init__(self, endpoint, timeout_s):
            assert isinstance(endpoint, DaemonEndpoint)
            assert timeout_s == 5.0

        def ping(self):
            return {"ok": "pong"}

    monkeypatch.setattr(
        daemon_cmd,
        "resolve_daemon_endpoint",
        lambda **kwargs: DaemonEndpoint(
            transport="tcp",
            socket_path=None,
            host="127.0.0.1",
            port=49152,
            token="secret-token",
        ),
    )
    monkeypatch.setattr(daemon_cmd, "DaemonClient", FakeClient)

    args = argparse.Namespace(
        daemon_command="ping",
        runtime_dir=".maid",
        socket=".maid/serve.sock",
        transport="tcp",
        timeout=5.0,
        json=True,
    )

    assert cmd_daemon(args) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": "pong"}


def test_cmd_daemon_returns_nonzero_for_request_error(monkeypatch, capsys):
    from maid_runner.cli.commands import daemon as daemon_cmd
    from maid_runner.cli.commands.daemon import cmd_daemon
    from maid_runner.daemon.client import DaemonClientError, DaemonEndpoint

    class FakeClient:
        def __init__(self, endpoint, timeout_s):
            del endpoint, timeout_s

        def validate(self, manifest_path, *, mode):
            del manifest_path, mode
            raise DaemonClientError("BAD_TOKEN", "missing token")

    monkeypatch.setattr(
        daemon_cmd,
        "resolve_daemon_endpoint",
        lambda **kwargs: DaemonEndpoint(
            transport="tcp",
            socket_path=None,
            host="127.0.0.1",
            port=49152,
            token="secret-token",
        ),
    )
    monkeypatch.setattr(daemon_cmd, "DaemonClient", FakeClient)

    args = argparse.Namespace(
        daemon_command="validate",
        manifest_path="manifests/demo.manifest.yaml",
        mode="schema",
        runtime_dir=".maid",
        socket=".maid/serve.sock",
        transport="tcp",
        timeout=5.0,
        json=True,
    )

    assert cmd_daemon(args) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["code"] == "BAD_TOKEN"
    assert payload["error"]["message"] == "missing token"
