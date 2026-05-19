"""Behavioral tests for the maid serve NDJSON protocol layer."""

from __future__ import annotations

import json

import pytest

from maid_runner.daemon.protocol import (
    ProtocolError,
    Request,
    Response,
    error_response,
    parse_request,
    render_response,
)


class TestParseRequest:
    def test_parse_request_accepts_well_formed_validate_call(self):
        line = json.dumps(
            {
                "id": "abc-1",
                "method": "validate",
                "params": {"manifest_path": "manifests/foo.manifest.yaml"},
            }
        )

        result = parse_request(line)

        assert isinstance(result, Request)
        assert result.id == "abc-1"
        assert result.method == "validate"
        assert result.params == {"manifest_path": "manifests/foo.manifest.yaml"}

    def test_parse_request_rejects_missing_id_with_protocol_error(self):
        line = json.dumps({"method": "ping", "params": {}})

        with pytest.raises(ProtocolError):
            parse_request(line)

    def test_parse_request_rejects_unknown_method_with_protocol_error(self):
        line = json.dumps({"id": "x", "method": "delete_universe", "params": {}})

        with pytest.raises(ProtocolError):
            parse_request(line)

    def test_parse_request_rejects_non_json_line_with_protocol_error(self):
        with pytest.raises(ProtocolError):
            parse_request("this is not JSON at all {{{")


class TestRenderResponse:
    def test_render_response_emits_single_ndjson_line(self):
        response = Response(id="r-1", ok=True, result={"value": 1}, error=None)

        rendered = render_response(response)

        assert rendered.endswith("\n")
        assert rendered.count("\n") == 1
        parsed = json.loads(rendered)
        assert parsed == {"id": "r-1", "ok": True, "result": {"value": 1}}

    def test_render_response_preserves_validate_json_shape_under_result_key(self):
        validate_payload = {
            "success": True,
            "manifest": "manifests/x.manifest.yaml",
            "errors": [],
            "warnings": [],
        }
        response = Response(id="r-2", ok=True, result=validate_payload, error=None)

        rendered = render_response(response)
        parsed = json.loads(rendered)

        assert parsed["result"] == validate_payload


class TestErrorResponse:
    def test_error_response_has_code_and_message_fields(self):
        response = error_response("r-3", code="BAD_INPUT", message="malformed")

        assert isinstance(response, Response)
        assert response.id == "r-3"
        assert response.ok is False
        assert response.result is None
        assert response.error == {"code": "BAD_INPUT", "message": "malformed"}
