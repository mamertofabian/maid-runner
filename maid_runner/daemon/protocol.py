"""NDJSON protocol primitives for the maid serve daemon."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional


_SUPPORTED_PROTOCOL_VERSION = 1
_ALLOWED_METHODS = ("validate", "ping", "verify")


class ProtocolError(Exception):
    """Raised when an inbound line cannot be parsed as a valid Request."""


class UnsupportedProtocolVersionError(ProtocolError):
    """Raised when a request carries a protocol version this daemon cannot serve."""

    def __init__(self, version: int, request_id: str) -> None:
        self.version = version
        self.request_id = request_id
        super().__init__(
            f"unsupported protocol_version {version}; supported: "
            f"{_SUPPORTED_PROTOCOL_VERSION}"
        )


class DaemonRequestError(Exception):
    """Raised by a handler when the request itself is malformed or rejected.

    Distinct from validation outcomes: this signals a request-layer failure
    (missing/invalid params, path escapes, unknown options) that the server
    must surface as a transport-level error (``ok: false``) rather than as a
    validation result with ``success: false``.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class Request:
    """Parsed NDJSON client request."""

    id: str
    method: str
    params: dict
    protocol_version: int = _SUPPORTED_PROTOCOL_VERSION


@dataclass
class Response:
    """Server response with id, ok flag, and either result or error."""

    id: str
    ok: bool
    result: Optional[dict]
    error: Optional[dict]


def parse_request(line: str) -> Request:
    """Parse one NDJSON line into a Request, raising ProtocolError on malformed input."""
    try:
        payload = json.loads(line)
    except (ValueError, TypeError) as exc:
        raise ProtocolError(f"line is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ProtocolError("payload must be a JSON object")

    request_id = payload.get("id")
    if not isinstance(request_id, str) or not request_id:
        raise ProtocolError("missing or empty 'id' field")

    protocol_version = payload.get("protocol_version", _SUPPORTED_PROTOCOL_VERSION)
    if type(protocol_version) is not int:
        raise ProtocolError("'protocol_version' must be an integer")
    if protocol_version != _SUPPORTED_PROTOCOL_VERSION:
        raise UnsupportedProtocolVersionError(protocol_version, request_id)

    method = payload.get("method")
    if not isinstance(method, str) or method not in _ALLOWED_METHODS:
        raise ProtocolError(
            f"unknown method '{method}'. Allowed: {', '.join(_ALLOWED_METHODS)}"
        )

    params = payload.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise ProtocolError("'params' must be a JSON object")

    return Request(
        id=request_id,
        method=method,
        params=params,
        protocol_version=protocol_version,
    )


def render_response(response: Response) -> str:
    """Render a Response as a single NDJSON line (trailing newline included)."""
    payload: dict[str, Any] = {"id": response.id, "ok": response.ok}
    if response.ok:
        payload["result"] = response.result
    else:
        payload["error"] = response.error
    return json.dumps(payload) + "\n"


def error_response(request_id: str, code: str, message: str) -> Response:
    """Build a structured error Response for a given request id."""
    return Response(
        id=request_id,
        ok=False,
        result=None,
        error={"code": code, "message": message},
    )
