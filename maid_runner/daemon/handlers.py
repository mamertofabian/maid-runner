"""Request handlers for the maid serve daemon."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Union

from maid_runner.__version__ import __version__
from maid_runner.daemon.cache import DaemonValidationCacheScope
from maid_runner.daemon.protocol import DaemonRequestError


_START_TIME = time.monotonic()
_DAEMON_CONTEXT: dict = {"project_root": "."}
_VALIDATION_CACHE_SCOPE: DaemonValidationCacheScope | None = None


def configure_context(project_root: Union[str, Path]) -> None:
    """Bind the daemon to a startup project_root. Client-supplied values are ignored."""
    global _VALIDATION_CACHE_SCOPE
    if _VALIDATION_CACHE_SCOPE is not None:
        _VALIDATION_CACHE_SCOPE._close_scope()
    _DAEMON_CONTEXT["project_root"] = str(Path(project_root).resolve())
    _VALIDATION_CACHE_SCOPE = None


def handle_ping(params: dict) -> dict:
    """Return a liveness payload with pid, version, and uptime_s."""
    del params
    return {
        "pid": os.getpid(),
        "version": __version__,
        "uptime_s": round(time.monotonic() - _START_TIME, 3),
        "cache_stats": _validation_cache_scope().stats(),
    }


def handle_validate(params: dict) -> dict:
    """Dispatch a validate request and return its JSON-mode result dict.

    Client-supplied ``project_root`` keys are deliberately ignored. The
    daemon validates only inside the project root it was started with.
    ``manifest_path`` is resolved relative to that root; absolute paths
    and traversals outside the root are rejected.
    """
    from maid_runner.core.types import ValidationMode

    manifest_path = params.get("manifest_path")
    if not isinstance(manifest_path, str) or not manifest_path:
        raise DaemonRequestError("MISSING_PARAM", "'manifest_path' is required")

    mode_value = params.get("mode", "implementation")
    try:
        mode = ValidationMode(mode_value)
    except ValueError:
        raise DaemonRequestError(
            "BAD_MODE",
            f"unknown mode '{mode_value}'. Allowed: schema, behavioral, implementation",
        )

    project_root = Path(_DAEMON_CONTEXT["project_root"]).resolve()
    resolved_manifest = _resolve_within_root(manifest_path, project_root)
    if resolved_manifest is None:
        raise DaemonRequestError(
            "PATH_ESCAPE",
            f"manifest_path '{manifest_path}' escapes daemon project root",
        )

    use_chain = not bool(params.get("no_chain", False))
    manifest_dir = params.get("manifest_dir", "manifests/")

    return _validation_cache_scope().validate(
        str(resolved_manifest),
        mode=mode.value,
        use_chain=use_chain,
        manifest_dir=manifest_dir,
        check_assertions=bool(params.get("check_assertions", False)),
        check_stubs=bool(params.get("check_stubs", False)),
        fail_on_warnings=bool(params.get("fail_on_warnings", False)),
    )


def _resolve_within_root(manifest_path: str, project_root: Path) -> Path | None:
    candidate = Path(manifest_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None

    try:
        resolved.relative_to(project_root)
    except ValueError:
        return None
    return resolved


def _result_to_dict(result: Any, manifest_path: str) -> dict:
    if hasattr(result, "to_dict"):
        try:
            return result.to_dict()
        except Exception:
            pass

    return {
        "success": bool(getattr(result, "success", False)),
        "manifest": str(manifest_path),
        "mode": getattr(getattr(result, "mode", None), "value", None),
        "errors": [_error_to_dict(e) for e in getattr(result, "errors", []) or []],
        "warnings": [_error_to_dict(w) for w in getattr(result, "warnings", []) or []],
    }


def _error_to_dict(err: Any) -> dict:
    code = getattr(err, "code", None)
    return {
        "code": getattr(code, "value", str(code)) if code is not None else None,
        "message": getattr(err, "message", str(err)),
        "severity": getattr(getattr(err, "severity", None), "value", None),
    }


HANDLERS: dict = {
    "validate": handle_validate,
    "ping": handle_ping,
}


def _validation_cache_scope() -> DaemonValidationCacheScope:
    global _VALIDATION_CACHE_SCOPE
    if _VALIDATION_CACHE_SCOPE is None:
        _VALIDATION_CACHE_SCOPE = DaemonValidationCacheScope(
            project_root=_DAEMON_CONTEXT["project_root"]
        )
    return _VALIDATION_CACHE_SCOPE
