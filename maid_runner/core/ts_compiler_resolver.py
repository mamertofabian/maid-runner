"""Compiler-backed TypeScript identity resolution helpers."""

from __future__ import annotations

import json
import shutil
import subprocess
from importlib import resources
from pathlib import Path
from typing import Any, Optional


_REQUEST_TIMEOUT_SECONDS = 5


def resolve_import_with_compiler(
    specifier: str,
    importer_module: str,
    project_root: Path,
) -> Optional[str]:
    """Resolve a TypeScript import through the project compiler, if available."""
    return _resolve_import(specifier, importer_module, str(Path(project_root)))


def resolve_reexport_with_compiler(
    module: str,
    name: str,
    project_root: Path,
) -> Optional[tuple[str, str]]:
    """Resolve an exported symbol through the project compiler, if available."""
    result = _resolve_reexport(module, name, str(Path(project_root)))
    if result is None:
        return None
    resolved_module, resolved_name = result
    return resolved_module, resolved_name


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
