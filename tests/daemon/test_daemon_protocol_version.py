"""Behavioral tests for daemon protocol version negotiation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.daemon.protocol import ProtocolError, parse_request
from maid_runner.daemon.server import Server


def test_parse_request_defaults_absent_protocol_version_to_one():
    request = parse_request('{"id":"p1","method":"ping","params":{}}')

    assert request.protocol_version == 1


def test_parse_request_accepts_supported_protocol_version():
    request = parse_request(
        '{"id":"p1","method":"ping","protocol_version":1,"params":{}}'
    )

    assert request.protocol_version == 1


def test_parse_request_rejects_non_integer_protocol_version():
    with pytest.raises(ProtocolError, match="protocol_version"):
        parse_request('{"id":"p1","method":"ping","protocol_version":"1"}')


def test_parse_request_raises_specific_error_for_unsupported_protocol_version():
    from maid_runner.daemon import protocol

    with pytest.raises(protocol.UnsupportedProtocolVersionError) as exc:
        parse_request('{"id":"p99","method":"future_verify","protocol_version":99}')

    assert exc.value.version == 99
    assert exc.value.request_id == "p99"


def test_server_dispatch_reports_unsupported_protocol_version_with_request_id(
    tmp_path,
):
    server = Server(tmp_path / "serve.sock", tmp_path / "serve.pid")
    response = server._dispatch(
        json.dumps(
            {
                "id": "p99",
                "method": "ping",
                "protocol_version": 99,
                "params": {},
            }
        )
    )

    assert response.id == "p99"
    assert response.ok is False
    assert response.error["code"] == "UNSUPPORTED_PROTOCOL_VERSION"


def test_parse_request_allows_verify_method():
    request = parse_request(
        '{"id":"v1","method":"verify","protocol_version":1,"params":{}}'
    )

    assert request.method == "verify"
    assert request.protocol_version == 1


def test_maid_serve_docs_describe_verify_protocol_version_and_error_code():
    docs = Path("docs/maid-serve.md").read_text()

    assert "protocol_version" in docs
    assert "validate|ping|verify" in docs
    assert "UNSUPPORTED_PROTOCOL_VERSION" in docs
    assert "### `verify`" in docs
