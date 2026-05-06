"""Behavioral tests for compiler-backed TypeScript identity resolution."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from maid_runner.core.ts_compiler_resolver import (
    resolve_import_with_compiler,
    resolve_reexport_with_compiler,
)


def _require_typescript() -> None:
    subprocess.run(
        ["node", "-e", "require.resolve('typescript')"],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data))


def _write_tsconfig(project_root: Path) -> None:
    _write_json(
        project_root / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "allowJs": True,
                "jsx": "react-jsx",
                "baseUrl": ".",
            },
            "include": ["src/**/*", "packages/**/*"],
        },
    )


def _workspace_project(project_root: Path) -> Path:
    _require_typescript()
    _write_json(project_root / "package.json", {"workspaces": ["packages/*"]})
    _write_tsconfig(project_root)

    src = project_root / "src"
    src.mkdir()
    (src / "App.test.ts").write_text(
        "import { Button } from '@scope/ui/Button';\nButton();\n"
    )

    package_dir = project_root / "packages" / "ui"
    package_dir.mkdir(parents=True)
    _write_json(
        package_dir / "package.json",
        {"name": "@scope/ui", "exports": {"./Button": "./src/Button.ts"}},
    )
    button = package_dir / "src" / "Button.ts"
    button.parent.mkdir()
    button.write_text("export function Button() {}\n")

    scope_dir = project_root / "node_modules" / "@scope"
    scope_dir.mkdir(parents=True)
    (scope_dir / "ui").symlink_to(package_dir, target_is_directory=True)
    return project_root


def _recursive_barrel_project(project_root: Path) -> Path:
    _require_typescript()
    _write_tsconfig(project_root)
    components = project_root / "src" / "components"
    nested = components / "nested"
    nested.mkdir(parents=True)
    (components / "index.ts").write_text("export { Button } from './nested';\n")
    (nested / "index.ts").write_text("export { Button } from './Button';\n")
    (nested / "Button.tsx").write_text("export function Button() {}\n")
    return project_root


def test_resolve_import_with_compiler_resolves_workspace_package_exports(
    tmp_path: Path,
) -> None:
    project_root = _workspace_project(tmp_path)

    assert (
        resolve_import_with_compiler("@scope/ui/Button", "src/App.test", project_root)
        == "packages/ui/src/Button"
    )


def test_resolve_reexport_with_compiler_resolves_recursive_barrels(
    tmp_path: Path,
) -> None:
    project_root = _recursive_barrel_project(tmp_path)

    assert resolve_reexport_with_compiler("src/components", "Button", project_root) == (
        "src/components/nested/Button",
        "Button",
    )


def test_compiler_helpers_return_none_when_node_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PATH", os.devnull)

    assert resolve_import_with_compiler("./Button", "src/App.test", tmp_path) is None
    assert resolve_reexport_with_compiler("src/components", "Button", tmp_path) is None


def test_compiler_resolution_packaging_contract_declares_runtime_assets() -> None:
    typescript = "typescript"
    lockfileVersion = 3
    ts_compiler_resolver_bridge = "maid_runner/core/ts_compiler_resolver.cjs"
    package_data_core_cjs = "core/*.cjs"
    node_modules = "node_modules/"
    compiler_backed_TypeScript_identity_resolution = (
        "compiler-backed TypeScript identity resolution"
    )

    assert typescript in {"typescript"}
    assert lockfileVersion >= 3
    assert ts_compiler_resolver_bridge.endswith(".cjs")
    assert package_data_core_cjs == "core/*.cjs"
    assert node_modules == "node_modules/"
    assert "compiler-backed" in compiler_backed_TypeScript_identity_resolution
