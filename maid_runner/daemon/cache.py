"""Daemon-resident validation cache scope and request accounting."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

from maid_runner.__version__ import __version__
from maid_runner.core.manifest import load_manifest
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


def content_cache_key(content: bytes, version: str) -> str:
    """Return a version-scoped sha256 cache identity for content bytes."""
    return f"{version}:{hashlib.sha256(content).hexdigest()}"


class DaemonValidationCacheScope:
    """Hold validation caches open across daemon validate requests."""

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = Path(project_root).resolve()
        self._lock = threading.RLock()
        self._request_keys: set[tuple[Any, ...]] = set()
        self._hits = 0
        self._misses = 0
        self._engine: ValidationEngine
        self._cache_scope: Any | None = None
        self._open_scope()

    def __del__(self) -> None:
        try:
            self._close_scope()
        except Exception:
            pass

    def validate(
        self,
        manifest_path: str,
        mode: str = "implementation",
        use_chain: bool = True,
        manifest_dir: str = "manifests/",
        check_assertions: bool = False,
        check_stubs: bool = False,
        fail_on_warnings: bool = False,
    ) -> dict:
        """Run validation while keeping the engine's cache scope alive."""
        validation_mode = ValidationMode(mode)
        resolved_manifest = self._resolve_manifest_path(manifest_path)
        with self._lock:
            key = self._request_identity(
                manifest_path=str(resolved_manifest),
                mode=validation_mode.value,
                use_chain=use_chain,
                manifest_dir=manifest_dir,
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            if key in self._request_keys:
                self._hits += 1
            else:
                self._request_keys.add(key)
                self._misses += 1

            result = self._engine.validate(
                str(resolved_manifest),
                mode=validation_mode,
                use_chain=use_chain,
                manifest_dir=manifest_dir,
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            if hasattr(result, "to_dict"):
                return result.to_dict()
            return dict(result)

    def stats(self) -> dict:
        """Return cache observability counters since the current daemon start."""
        with self._lock:
            return {
                "entries": len(self._request_keys),
                "hits": self._hits,
                "misses": self._misses,
            }

    def clear(self) -> None:
        """Reset request accounting and reopen the held validation cache scope."""
        with self._lock:
            self._close_scope()
            self._request_keys.clear()
            self._hits = 0
            self._misses = 0
            self._open_scope()

    def _open_scope(self) -> None:
        self._engine = ValidationEngine(project_root=str(self._project_root))
        self._cache_scope = self._engine.validation_cache_scope()
        self._cache_scope.__enter__()

    def _resolve_manifest_path(self, manifest_path: str) -> Path:
        manifest = Path(manifest_path)
        if not manifest.is_absolute():
            manifest = self._project_root / manifest
        return manifest.resolve()

    def _close_scope(self) -> None:
        if self._cache_scope is None:
            return
        scope = self._cache_scope
        self._cache_scope = None
        scope.__exit__(None, None, None)

    def _request_identity(
        self,
        *,
        manifest_path: str,
        mode: str,
        use_chain: bool,
        manifest_dir: str,
        check_assertions: bool,
        check_stubs: bool,
        fail_on_warnings: bool,
    ) -> tuple[Any, ...]:
        manifest = self._resolve_manifest_path(manifest_path)

        files = [manifest]
        files.extend(self._declared_files(manifest))
        files.extend(self._tsconfig_files())
        if use_chain:
            files.extend(self._chain_manifest_files(manifest_dir))

        return (
            __version__,
            self._relative_or_absolute(manifest),
            mode,
            bool(use_chain),
            str(manifest_dir),
            bool(check_assertions),
            bool(check_stubs),
            bool(fail_on_warnings),
            tuple(self._file_signature(path) for path in self._unique_existing(files)),
        )

    def _declared_files(self, manifest_path: Path) -> list[Path]:
        try:
            manifest = load_manifest(manifest_path)
        except Exception:
            return []

        paths: list[Path] = []
        for spec in (
            *manifest.files_create,
            *manifest.files_edit,
            *manifest.files_snapshot,
        ):
            paths.append(self._project_root / spec.path)
        for read_path in manifest.files_read:
            paths.append(self._project_root / read_path)
        for delete_spec in manifest.files_delete:
            paths.append(self._project_root / delete_spec.path)
        return paths

    def _tsconfig_files(self) -> list[Path]:
        return sorted(self._project_root.rglob("tsconfig*.json"))

    def _chain_manifest_files(self, manifest_dir: str) -> list[Path]:
        root = Path(manifest_dir)
        if not root.is_absolute():
            root = self._project_root / root
        if not root.exists():
            return []
        return sorted(root.rglob("*.manifest.yaml"))

    def _unique_existing(self, paths: list[Path]) -> list[Path]:
        unique: dict[str, Path] = {}
        for path in paths:
            try:
                resolved = path.resolve()
            except (OSError, RuntimeError):
                continue
            if not resolved.is_file():
                continue
            unique[str(resolved)] = resolved
        return [unique[key] for key in sorted(unique)]

    def _file_signature(self, path: Path) -> tuple[str, str]:
        try:
            content = path.read_bytes()
        except OSError:
            return (self._relative_or_absolute(path), "missing")
        return (
            self._relative_or_absolute(path),
            content_cache_key(content, __version__),
        )

    def _relative_or_absolute(self, path: Path) -> str:
        try:
            return path.relative_to(self._project_root).as_posix()
        except ValueError:
            return str(path)
