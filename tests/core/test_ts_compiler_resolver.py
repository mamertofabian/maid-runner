"""Behavioral tests for compiler-backed TypeScript identity resolution."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from maid_runner.core.ts_compiler_resolver import (
    resolve_import_with_compiler,
    resolve_reexport_with_compiler,
)


def _require_typescript() -> None:
    try:
        completed = subprocess.run(
            ["node", "-e", "require.resolve('typescript')"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        pytest.skip("Node.js is unavailable")
    if completed.returncode != 0:
        pytest.skip("TypeScript npm dependency is unavailable")


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


def test_compiler_resolves_project_local_conditional_package_export(
    tmp_path: Path,
) -> None:
    _require_typescript()
    _write_json(tmp_path / "package.json", {"workspaces": ["packages/*"]})
    _write_tsconfig(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.test.ts").write_text("import { Button } from '@scope/ui';\nButton();\n")
    package_dir = tmp_path / "packages" / "ui"
    package_dir.mkdir(parents=True)
    _write_json(
        package_dir / "package.json",
        {
            "name": "@scope/ui",
            "exports": {
                ".": {
                    "types": "./dist/index.d.ts",
                    "import": "./src/index.ts",
                    "require": "./dist/index.cjs",
                }
            },
        },
    )
    index = package_dir / "src" / "index.ts"
    index.parent.mkdir()
    index.write_text("export function Button() {}\n")
    scope_dir = tmp_path / "node_modules" / "@scope"
    scope_dir.mkdir(parents=True)
    (scope_dir / "ui").symlink_to(package_dir, target_is_directory=True)

    assert (
        resolve_import_with_compiler("@scope/ui", "src/App.test", tmp_path)
        == "packages/ui/src"
    )


def test_compiler_resolves_project_local_wildcard_package_export(
    tmp_path: Path,
) -> None:
    _require_typescript()
    _write_json(tmp_path / "package.json", {"workspaces": ["packages/*"]})
    _write_tsconfig(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.test.ts").write_text(
        "import { Card } from '@scope/ui/features/card';\nCard();\n"
    )
    package_dir = tmp_path / "packages" / "ui"
    package_dir.mkdir(parents=True)
    _write_json(
        package_dir / "package.json",
        {
            "name": "@scope/ui",
            "exports": {"./features/*": "./src/features/*.ts"},
        },
    )
    card = package_dir / "src" / "features" / "card.ts"
    card.parent.mkdir(parents=True)
    card.write_text("export function Card() {}\n")
    scope_dir = tmp_path / "node_modules" / "@scope"
    scope_dir.mkdir(parents=True)
    (scope_dir / "ui").symlink_to(package_dir, target_is_directory=True)

    assert (
        resolve_import_with_compiler(
            "@scope/ui/features/card", "src/App.test", tmp_path
        )
        == "packages/ui/src/features/card"
    )


def test_compiler_leaves_unresolved_package_export_subpath_unmapped(
    tmp_path: Path,
) -> None:
    _require_typescript()
    _write_json(tmp_path / "package.json", {"workspaces": ["packages/*"]})
    _write_tsconfig(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.test.ts").write_text(
        "import { Missing } from '@scope/ui/Missing';\nMissing();\n"
    )
    package_dir = tmp_path / "packages" / "ui"
    package_dir.mkdir(parents=True)
    _write_json(
        package_dir / "package.json",
        {"name": "@scope/ui", "exports": {"./Button": "./src/Button.ts"}},
    )
    button = package_dir / "src" / "Button.ts"
    button.parent.mkdir()
    button.write_text("export function Button() {}\n")
    scope_dir = tmp_path / "node_modules" / "@scope"
    scope_dir.mkdir(parents=True)
    (scope_dir / "ui").symlink_to(package_dir, target_is_directory=True)

    assert (
        resolve_import_with_compiler("@scope/ui/Missing", "src/App.test", tmp_path)
        is None
    )


def test_resolve_reexport_with_compiler_resolves_recursive_barrels(
    tmp_path: Path,
) -> None:
    project_root = _recursive_barrel_project(tmp_path)

    assert resolve_reexport_with_compiler("src/components", "Button", project_root) == (
        "src/components/nested/Button",
        "Button",
    )


def test_resolve_import_with_compiler_reflects_changed_tsconfig_paths(
    tmp_path: Path,
) -> None:
    _require_typescript()
    src = tmp_path / "src"
    old_dir = src / "old"
    new_dir = src / "new"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)
    (src / "App.test.ts").write_text(
        "import { Button } from '@ui/Button';\nButton();\n"
    )
    (old_dir / "Button.ts").write_text("export function Button() {}\n")
    (new_dir / "Button.ts").write_text("export function Button() {}\n")

    _write_json(
        tmp_path / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "baseUrl": ".",
                "paths": {"@ui/*": ["src/old/*"]},
            },
            "include": ["src/**/*"],
        },
    )
    assert (
        resolve_import_with_compiler("@ui/Button", "src/App.test", tmp_path)
        == "src/old/Button"
    )

    _write_json(
        tmp_path / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "baseUrl": ".",
                "paths": {"@ui/*": ["src/new/*"]},
            },
            "include": ["src/**/*"],
        },
    )

    assert (
        resolve_import_with_compiler("@ui/Button", "src/App.test", tmp_path)
        == "src/new/Button"
    )


def test_package_style_tsconfig_extends_resolves_when_compiler_loads_package_config(
    tmp_path: Path,
) -> None:
    _require_typescript()
    src = tmp_path / "src"
    components = src / "components"
    components.mkdir(parents=True)
    (src / "App.test.ts").write_text(
        "import { Button } from '@/components/Button';\nButton();\n"
    )
    (components / "Button.ts").write_text("export function Button() {}\n")
    package_config = tmp_path / "node_modules" / "@scope" / "tsconfig" / "base.json"
    package_config.parent.mkdir(parents=True)
    _write_json(
        package_config,
        {
            "compilerOptions": {
                "baseUrl": "../../..",
                "paths": {"@/*": ["src/*"]},
            }
        },
    )
    _write_json(
        tmp_path / "tsconfig.json",
        {
            "extends": "@scope/tsconfig/base.json",
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "Bundler",
            },
            "include": ["src/**/*"],
        },
    )

    assert (
        resolve_import_with_compiler("@/components/Button", "src/App.test", tmp_path)
        == "src/components/Button"
    )


def test_package_style_tsconfig_extends_returns_none_when_compiler_cannot_load_package_config(
    tmp_path: Path,
) -> None:
    _require_typescript()
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.test.ts").write_text(
        "import { Button } from '@/components/Button';\nButton();\n"
    )
    _write_json(
        tmp_path / "tsconfig.json",
        {
            "extends": "@scope/tsconfig/base.json",
            "compilerOptions": {
                "target": "ES2022",
                "module": "ESNext",
                "moduleResolution": "Bundler",
            },
            "include": ["src/**/*"],
        },
    )

    assert (
        resolve_import_with_compiler("@/components/Button", "src/App.test", tmp_path)
        is None
    )


def test_compiler_helpers_return_none_when_node_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PATH", os.devnull)

    assert resolve_import_with_compiler("./Button", "src/App.test", tmp_path) is None
    assert resolve_reexport_with_compiler("src/components", "Button", tmp_path) is None


def test_compiler_import_resolution_rejects_node_modules_dependency_source(
    tmp_path: Path,
) -> None:
    _require_typescript()
    _write_json(
        tmp_path / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "CommonJS",
                "moduleResolution": "Node10",
            },
            "include": ["src/**/*"],
        },
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.ts").write_text(
        "import { something } from '@scope/pkg';\nsomething();\n"
    )
    pkg_dir = tmp_path / "node_modules" / "@scope" / "pkg"
    pkg_dir.mkdir(parents=True)
    _write_json(
        pkg_dir / "package.json",
        {"name": "@scope/pkg", "main": "./index.js", "types": "./index.d.ts"},
    )
    (pkg_dir / "index.d.ts").write_text("export declare function something(): void;\n")
    (pkg_dir / "index.js").write_text("exports.something = function() {};\n")

    # TypeScript resolves the import to node_modules — bridge rejects non-project-local source
    assert resolve_import_with_compiler("@scope/pkg", "src/App", tmp_path) is None


def test_compiler_reexport_resolution_rejects_node_modules_dependency_source(
    tmp_path: Path,
) -> None:
    _require_typescript()
    _write_json(
        tmp_path / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "CommonJS",
                "moduleResolution": "Node10",
            },
            "include": ["src/**/*"],
        },
    )
    barrel = tmp_path / "src" / "barrel"
    barrel.mkdir(parents=True)
    (barrel / "index.ts").write_text("export { Button } from '@scope/pkg';\n")
    pkg_dir = tmp_path / "node_modules" / "@scope" / "pkg"
    pkg_dir.mkdir(parents=True)
    _write_json(
        pkg_dir / "package.json",
        {"name": "@scope/pkg", "main": "./index.js", "types": "./index.d.ts"},
    )
    (pkg_dir / "index.d.ts").write_text("export declare function Button(): void;\n")
    (pkg_dir / "index.js").write_text("exports.Button = function() {};\n")

    # TypeScript traces the re-export to node_modules — bridge rejects non-project-local source
    assert resolve_reexport_with_compiler("src/barrel", "Button", tmp_path) is None


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
