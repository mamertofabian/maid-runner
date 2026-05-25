"""Compiler-backed TypeScript identity resolution helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from atexit import register as register_atexit
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from importlib import resources
from pathlib import Path
from typing import Any, Optional


_REQUEST_TIMEOUT_SECONDS = 5
_COMPILER_SESSIONS: dict[str, "TypeScriptCompilerResolverSession"] = {}
_COMPILER_SESSIONS_LOCK = threading.Lock()


class TypeScriptCompilerResolverSession:
    """Validation-run scoped TypeScript compiler bridge process."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self._process = _start_session_process()
        self._reader = ThreadPoolExecutor(max_workers=1)
        self._lock = threading.Lock()
        self._closed = False

    def resolve_import(
        self,
        specifier: str,
        importer_module: str,
    ) -> Optional[str]:
        response = self._request(
            {
                "command": "resolveImport",
                "specifier": specifier,
                "importerModule": importer_module,
                "projectRoot": str(self.project_root),
            }
        )
        result = response.get("result") if response is not None else None
        return result if isinstance(result, str) and result else None

    def resolve_reexport(
        self,
        module: str,
        name: str,
    ) -> Optional[tuple[str, str]]:
        response = self._request(
            {
                "command": "resolveReexport",
                "module": module,
                "name": name,
                "projectRoot": str(self.project_root),
            }
        )
        result = response.get("result") if response is not None else None
        if not isinstance(result, dict):
            return None
        resolved_module = result.get("module")
        resolved_name = result.get("name")
        if not isinstance(resolved_module, str) or not isinstance(resolved_name, str):
            return None
        if not resolved_module or not resolved_name:
            return None
        return resolved_module, resolved_name

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is not None:
            stdin = process.stdin
            try:
                if stdin is not None:
                    stdin.close()
            except OSError:
                pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
        self._reader.shutdown(wait=False, cancel_futures=True)

    def _request(self, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        with self._lock:
            if self._closed or self._process is None:
                return None
            process = self._process
            if process.poll() is not None or process.stdin is None:
                self.close()
                return None
            if process.stdout is None:
                self.close()
                return None

            try:
                process.stdin.write(json.dumps(payload) + "\n")
                process.stdin.flush()
                future = self._reader.submit(process.stdout.readline)
                line = future.result(timeout=_REQUEST_TIMEOUT_SECONDS)
            except (OSError, TimeoutError):
                self.close()
                return None

            if not line:
                self.close()
                return None

            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                self.close()
                return None

            if not isinstance(response, dict) or response.get("ok") is not True:
                return None
            return response


def resolve_import_with_compiler(
    specifier: str,
    importer_module: str,
    project_root: Path,
) -> Optional[str]:
    """Resolve a TypeScript import through the project compiler, if available."""
    return _session_for_project(project_root).resolve_import(specifier, importer_module)


def resolve_reexport_with_compiler(
    module: str,
    name: str,
    project_root: Path,
) -> Optional[tuple[str, str]]:
    """Resolve an exported symbol through the project compiler, if available."""
    return _session_for_project(project_root).resolve_reexport(module, name)


def clear_ts_compiler_resolver_session() -> None:
    """Close and forget validation-run scoped compiler resolver sessions."""
    with _COMPILER_SESSIONS_LOCK:
        sessions = tuple(_COMPILER_SESSIONS.values())
        _COMPILER_SESSIONS.clear()
    for session in sessions:
        session.close()


def _resolve_import(
    specifier: str,
    importer_module: str,
    project_root: str,
) -> Optional[str]:
    response = _run_compiler_request(
        {
            "command": "resolveImport",
            "specifier": specifier,
            "importerModule": importer_module,
            "projectRoot": project_root,
        }
    )
    result = response.get("result") if response is not None else None
    return result if isinstance(result, str) and result else None


def _resolve_reexport(
    module: str,
    name: str,
    project_root: str,
) -> Optional[tuple[str, str]]:
    response = _run_compiler_request(
        {
            "command": "resolveReexport",
            "module": module,
            "name": name,
            "projectRoot": project_root,
        }
    )
    result = response.get("result") if response is not None else None
    if not isinstance(result, dict):
        return None
    resolved_module = result.get("module")
    resolved_name = result.get("name")
    if not isinstance(resolved_module, str) or not isinstance(resolved_name, str):
        return None
    if not resolved_module or not resolved_name:
        return None
    return resolved_module, resolved_name


def _run_compiler_request(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    node = shutil.which("node")
    if node is None:
        return None

    try:
        bridge = resources.files("maid_runner.core").joinpath(
            "ts_compiler_resolver.cjs"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return None

    try:
        completed = subprocess.run(
            [node, str(bridge)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None

    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None

    if not isinstance(response, dict) or response.get("ok") is not True:
        return None
    return response


def _session_for_project(project_root: Path) -> TypeScriptCompilerResolverSession:
    root = Path(project_root)
    key = str(root)
    with _COMPILER_SESSIONS_LOCK:
        session = _COMPILER_SESSIONS.get(key)
        if session is None or session._closed:
            session = TypeScriptCompilerResolverSession(root)
            _COMPILER_SESSIONS[key] = session
        return session


def _start_session_process() -> Optional[subprocess.Popen[str]]:
    node = shutil.which("node")
    if node is None:
        return None

    try:
        bridge = resources.files("maid_runner.core").joinpath(
            "ts_compiler_resolver.cjs"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return None

    try:
        return subprocess.Popen(
            [node, str(bridge), "--session"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return None


register_atexit(clear_ts_compiler_resolver_session)
