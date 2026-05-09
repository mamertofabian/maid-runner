"""Behavioral tests for TypeScript module path helpers.

Covers maid_runner.core.ts_module_paths:
    - ts_file_to_module_path: project-relative POSIX path, extensionless
    - resolve_relative_ts_import: resolve "./x" / "../y/z" against importer
    - resolve_ts_reexport: one-level barrel through index.ts(x) for
      `export { Foo } from './y'` and `export { Foo as Bar } from './y'`
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.ts_module_paths import (
    resolve_relative_ts_import,
    resolve_ts_reexport,
    ts_file_to_module_path,
)


# ----------------------------------------------------------------------------
# ts_file_to_module_path
# ----------------------------------------------------------------------------


class TestTsFileToModulePath:
    def test_strips_ts_extension(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "models" / "user.ts"
        target.parent.mkdir(parents=True)
        target.write_text("")
        assert ts_file_to_module_path(target, tmp_path) == "src/models/user"

    def test_strips_tsx_extension(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "components" / "Button.tsx"
        target.parent.mkdir(parents=True)
        target.write_text("")
        assert ts_file_to_module_path(target, tmp_path) == "src/components/Button"

    def test_strips_js_and_jsx(self, tmp_path: Path) -> None:
        a = tmp_path / "lib" / "a.js"
        b = tmp_path / "lib" / "b.jsx"
        a.parent.mkdir(parents=True)
        a.write_text("")
        b.write_text("")
        assert ts_file_to_module_path(a, tmp_path) == "lib/a"
        assert ts_file_to_module_path(b, tmp_path) == "lib/b"

    def test_strips_mts_and_cts(self, tmp_path: Path) -> None:
        m = tmp_path / "lib" / "esm.mts"
        c = tmp_path / "lib" / "cjs.cts"
        m.parent.mkdir(parents=True)
        m.write_text("")
        c.write_text("")
        assert ts_file_to_module_path(m, tmp_path) == "lib/esm"
        assert ts_file_to_module_path(c, tmp_path) == "lib/cjs"

    def test_strips_mjs_and_cjs(self, tmp_path: Path) -> None:
        m = tmp_path / "lib" / "esm.mjs"
        c = tmp_path / "lib" / "cjs.cjs"
        m.parent.mkdir(parents=True)
        m.write_text("")
        c.write_text("")
        assert ts_file_to_module_path(m, tmp_path) == "lib/esm"
        assert ts_file_to_module_path(c, tmp_path) == "lib/cjs"

    def test_index_file_keeps_directory_path(self, tmp_path: Path) -> None:
        # Unlike Python __init__.py (which collapses), TS index.ts is just
        # a file. Its module identity is the full path including "index"
        # so the file itself can be matched. resolve_ts_reexport handles
        # the barrel semantics separately.
        target = tmp_path / "src" / "models" / "index.ts"
        target.parent.mkdir(parents=True)
        target.write_text("")
        assert ts_file_to_module_path(target, tmp_path) == "src/models/index"

    def test_accepts_relative_path(self, tmp_path: Path) -> None:
        # Relative path passed through with same normalization.
        assert ts_file_to_module_path("src/a/b.ts", tmp_path) == "src/a/b"

    def test_posix_normalization(self, tmp_path: Path) -> None:
        # Backslashes (Windows-style) normalize to forward slashes.
        assert ts_file_to_module_path("src\\a\\b.ts", tmp_path) == "src/a/b"


# ----------------------------------------------------------------------------
# resolve_relative_ts_import
# ----------------------------------------------------------------------------


class TestResolveRelativeTsImport:
    def test_dot_slash_resolves_to_sibling(self) -> None:
        # `./user` from src/models/index → src/models/user
        assert (
            resolve_relative_ts_import("./user", "src/models/index")
            == "src/models/user"
        )

    def test_dotdot_walks_up_one_directory(self) -> None:
        # `../utils/date` from src/models/user → src/utils/date
        assert (
            resolve_relative_ts_import("../utils/date", "src/models/user")
            == "src/utils/date"
        )

    def test_multiple_dotdot_walks_up_multiple(self) -> None:
        # `../../shared/x` from src/a/b/c → src/shared/x
        assert (
            resolve_relative_ts_import("../../shared/x", "src/a/b/c") == "src/shared/x"
        )

    def test_non_relative_specifier_returned_unchanged(self) -> None:
        # Bare specifiers and absolute-style imports pass through.
        # tsconfig path aliases are deferred to a follow-up manifest.
        assert resolve_relative_ts_import("react", "src/a") == "react"
        assert resolve_relative_ts_import("@scoped/pkg", "src/a") == "@scoped/pkg"

    def test_strips_trailing_slash(self) -> None:
        # `./user/` should resolve to the directory module path.
        assert (
            resolve_relative_ts_import("./user/", "src/models/index")
            == "src/models/user"
        )

    def test_strips_ts_extension_from_resolved_specifier(self) -> None:
        assert (
            resolve_relative_ts_import("./user.ts", "src/models/index")
            == "src/models/user"
        )

    def test_strips_mjs_extension_from_resolved_specifier(self) -> None:
        assert (
            resolve_relative_ts_import("./user.mjs", "src/models/index")
            == "src/models/user"
        )

    def test_strips_svelte_extension_from_resolved_specifier(self) -> None:
        assert (
            resolve_relative_ts_import("./Foo.svelte", "src/components/test")
            == "src/components/Foo"
        )


# ----------------------------------------------------------------------------
# resolve_ts_import
# ----------------------------------------------------------------------------


class TestResolveTsImport:
    def test_relative_import_uses_path_resolver_without_compiler(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from maid_runner.core import ts_module_paths

        def fail_compiler(*args) -> str:
            raise AssertionError("compiler should not run for relative imports")

        monkeypatch.setattr(
            ts_module_paths, "resolve_import_with_compiler", fail_compiler
        )

        assert (
            ts_module_paths.resolve_ts_import(
                "../../src/lib/db", "tests/lib/db.test", tmp_path
            )
            == "src/lib/db"
        )

    def test_paths_alias_resolves_wildcard_to_project_module(
        self, tmp_path: Path
    ) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        button = tmp_path / "src" / "components" / "Button.ts"
        button.parent.mkdir(parents=True)
        button.write_text("export function Button() {}\n")
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )

        assert (
            resolve_ts_import("@/components/Button", "src/App.test", tmp_path)
            == "src/components/Button"
        )

    def test_paths_alias_resolves_without_compiler(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from maid_runner.core import ts_module_paths

        def fail_compiler(*args) -> str:
            raise AssertionError("compiler should not run for tsconfig paths aliases")

        monkeypatch.setattr(
            ts_module_paths, "resolve_import_with_compiler", fail_compiler
        )
        button = tmp_path / "src" / "components" / "Button.ts"
        button.parent.mkdir(parents=True)
        button.write_text("export function Button() {}\n")
        test_utils = tmp_path / "src" / "test-utils"
        test_utils.mkdir(parents=True)
        (test_utils / "vitest.ts").write_text("export function describe() {}\n")
        package_dir = tmp_path / "node_modules" / "vitest"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text('{"name": "vitest"}')
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["missing/*", "src/*"], "vitest": ["src/test-utils/vitest.ts"]}}}'
        )

        assert (
            ts_module_paths.resolve_ts_import(
                "@/components/Button", "src/App.test", tmp_path
            )
            == "src/components/Button"
        )
        assert (
            ts_module_paths.resolve_ts_import("vitest", "src/App.test", tmp_path)
            == "src/test-utils/vitest"
        )

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"*": ["src/*"]}}}'
        )
        assert (
            ts_module_paths.resolve_ts_import("vitest", "src/App.test", tmp_path)
            == "vitest"
        )

        generated = tmp_path / "src" / "generated" / "models"
        generated.mkdir(parents=True)
        (generated / "Foo.ts").write_text("export class Foo {}\n")
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "Foo.ts").write_text("export class Foo {}\n")
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/generated/*"], "@/models/*": ["src/models/*"]}}}'
        )
        assert (
            ts_module_paths.resolve_ts_import("@/models/Foo", "src/App.test", tmp_path)
            == "src/models/Foo"
        )

        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"baseUrl": "."}}')
        foo = tmp_path / "src" / "foo.ts"
        foo.write_text("export function foo() {}\n")
        assert (
            ts_module_paths.resolve_ts_import("src/foo", "src/App.test", tmp_path)
            == "src/foo"
        )
        app_test = tmp_path / "src" / "App.test.ts"
        app_test.write_text("export function appTest() {}\n")
        assert (
            ts_module_paths.resolve_ts_import("src/App.test", "src/App.test", tmp_path)
            == "src/App.test"
        )

        lodash = tmp_path / "src" / "lodash.ts"
        lodash.write_text("export function debounce() {}\n")
        lodash_package = tmp_path / "node_modules" / "lodash"
        lodash_package.mkdir(parents=True)
        (lodash_package / "package.json").write_text('{"name": "lodash"}')
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": "src"}}'
        )
        assert (
            ts_module_paths.resolve_ts_import("lodash", "src/App.test", tmp_path)
            == "src/lodash"
        )

        (tmp_path / "tsconfig.json").write_text(
            """
{
  // TypeScript accepts JSONC tsconfig files.
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "vitest": ["src/test-utils/vitest.ts"],
    },
  },
}
"""
        )
        assert (
            ts_module_paths.resolve_ts_import("vitest", "src/App.test", tmp_path)
            == "src/test-utils/vitest"
        )

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@missing/*": ["src/missing/*"]}}}'
        )

        def fallback_compiler(specifier, importer_module, root):
            assert specifier == "@missing/Button"
            assert importer_module == "src/App.test"
            assert root == tmp_path
            return None

        app_test.write_text("import '@/missing/Button';\n")
        monkeypatch.setattr(
            ts_module_paths, "resolve_import_with_compiler", fallback_compiler
        )
        assert (
            ts_module_paths.resolve_ts_import(
                "@missing/Button", "src/App.test", tmp_path
            )
            == "@missing/Button"
        )

    def test_base_url_resolves_non_relative_specifier(self, tmp_path: Path) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        button = tmp_path / "src" / "components" / "Button.ts"
        button.parent.mkdir(parents=True)
        button.write_text("export function Button() {}\n")
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": "src"}}'
        )

        assert (
            resolve_ts_import("components/Button", "src/App.test", tmp_path)
            == "src/components/Button"
        )

    def test_paths_alias_can_resolve_directory_barrel(self, tmp_path: Path) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        components = tmp_path / "src" / "components"
        components.mkdir(parents=True)
        (components / "index.ts").write_text("export function Button() {}\n")
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@components": ["src/components"]}}}'
        )

        assert (
            resolve_ts_import("@components", "src/App.test", tmp_path)
            == "src/components"
        )

    def test_unmatched_alias_passes_through_unchanged(self, tmp_path: Path) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )

        assert resolve_ts_import("#/unknown", "src/App.test", tmp_path) == "#/unknown"

    def test_extends_paths_alias_resolves_from_base_config(
        self, tmp_path: Path
    ) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        button = tmp_path / "src" / "components" / "Button.ts"
        button.parent.mkdir(parents=True)
        button.write_text("export function Button() {}\n")
        (tmp_path / "tsconfig.base.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )
        (tmp_path / "tsconfig.json").write_text('{"extends": "./tsconfig.base.json"}')

        assert (
            resolve_ts_import("@/components/Button", "src/App.test", tmp_path)
            == "src/components/Button"
        )

    def test_extends_base_url_resolves_from_base_config(self, tmp_path: Path) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        button = tmp_path / "src" / "components" / "Button.ts"
        button.parent.mkdir(parents=True)
        button.write_text("export function Button() {}\n")
        (tmp_path / "tsconfig.base.json").write_text(
            '{"compilerOptions": {"baseUrl": "src"}}'
        )
        (tmp_path / "tsconfig.json").write_text('{"extends": "./tsconfig.base.json"}')

        assert (
            resolve_ts_import("components/Button", "src/App.test", tmp_path)
            == "src/components/Button"
        )

    def test_package_style_extends_does_not_resolve_node_modules(
        self, tmp_path: Path
    ) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        base = tmp_path / "node_modules" / "@scope" / "tsconfig" / "base.json"
        base.parent.mkdir(parents=True)
        base.write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )
        (tmp_path / "tsconfig.json").write_text(
            '{"extends": "@scope/tsconfig/base.json"}'
        )

        assert resolve_ts_import("@/components/Button", "src/App.test", tmp_path) == (
            "@/components/Button"
        )

    def test_package_style_tsconfig_extends_fallback_keeps_local_alias_resolution(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from maid_runner.core import ts_module_paths

        def unavailable_compiler(*args):
            return None

        monkeypatch.setattr(
            ts_module_paths, "resolve_import_with_compiler", unavailable_compiler
        )
        button = tmp_path / "src" / "components" / "Button.ts"
        button.parent.mkdir(parents=True)
        button.write_text("export function Button() {}\n")
        (tmp_path / "tsconfig.json").write_text(
            '{"extends": "@scope/tsconfig/base.json", "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )

        assert (
            ts_module_paths.resolve_ts_import(
                "@/components/Button", "src/App.test", tmp_path
            )
            == "src/components/Button"
        )

    def test_package_style_tsconfig_extends_does_not_require_compiler_for_relative_imports(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from maid_runner.core import ts_module_paths

        def fail_compiler(*args):
            raise AssertionError("compiler should not run for relative imports")

        monkeypatch.setattr(
            ts_module_paths, "resolve_import_with_compiler", fail_compiler
        )
        (tmp_path / "tsconfig.json").write_text(
            '{"extends": "@scope/tsconfig/base.json"}'
        )

        assert (
            ts_module_paths.resolve_ts_import(
                "../components/Button", "src/pages/App.test", tmp_path
            )
            == "src/components/Button"
        )

    def test_bare_package_import_passes_through_unchanged(self, tmp_path: Path) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )

        assert resolve_ts_import("react", "src/App.test", tmp_path) == "react"

    def test_installed_external_package_import_skips_compiler(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from maid_runner.core import ts_module_paths

        def fail_compiler(*args) -> str:
            raise AssertionError("compiler should not run for external packages")

        monkeypatch.setattr(
            ts_module_paths, "resolve_import_with_compiler", fail_compiler
        )
        package_dir = tmp_path / "node_modules" / "vitest"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text('{"name": "vitest"}')
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )

        assert (
            ts_module_paths.resolve_ts_import("vitest", "tests/app.test", tmp_path)
            == "vitest"
        )

    def test_scoped_package_import_passes_through_unchanged(
        self, tmp_path: Path
    ) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )

        assert (
            resolve_ts_import("@testing-library/react", "src/App.test", tmp_path)
            == "@testing-library/react"
        )

    def test_package_json_exports_are_not_resolved(self, tmp_path: Path) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        package_dir = tmp_path / "node_modules" / "@scope" / "ui"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            '{"exports": {"./Button": "./dist/Button.js"}}'
        )

        assert (
            resolve_ts_import("@scope/ui/Button", "src/App.test", tmp_path)
            == "@scope/ui/Button"
        )

    def test_workspace_package_exports_resolve_to_workspace_source(
        self, tmp_path: Path
    ) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"moduleResolution": "Bundler", "module": "ESNext", "baseUrl": "."}, "include": ["src/**/*", "packages/**/*"]}'
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "App.test.ts").write_text(
            "import { Button } from '@scope/ui/Button';\nButton();\n"
        )
        package_dir = tmp_path / "packages" / "ui"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            '{"name": "@scope/ui", "exports": {"./Button": "./src/Button.ts"}}'
        )
        button = package_dir / "src" / "Button.ts"
        button.parent.mkdir()
        button.write_text("export function Button() {}\n")
        scope_dir = tmp_path / "node_modules" / "@scope"
        scope_dir.mkdir(parents=True)
        (scope_dir / "ui").symlink_to(package_dir, target_is_directory=True)

        assert (
            resolve_ts_import("@scope/ui/Button", "src/App.test", tmp_path)
            == "packages/ui/src/Button"
        )


# ----------------------------------------------------------------------------
# resolve_ts_reexport (one-level barrel)
# ----------------------------------------------------------------------------


class TestResolveTsReexport:
    def test_external_package_reexport_skips_compiler(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from maid_runner.core import ts_module_paths

        def fail_compiler(*args):
            raise AssertionError("compiler should not run for external packages")

        monkeypatch.setattr(
            ts_module_paths, "resolve_reexport_with_compiler", fail_compiler
        )

        assert (
            ts_module_paths.resolve_ts_reexport("vitest", "describe", tmp_path) is None
        )

    def test_named_reexport_resolves_to_defining_module(self, tmp_path: Path) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { Foo } from './user';\n")
        (models / "user.ts").write_text("export class Foo {}\n")

        assert resolve_ts_reexport("src/models", "Foo", tmp_path) == (
            "src/models/user",
            "Foo",
        )

    def test_aliased_named_reexport_matches_alias(self, tmp_path: Path) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { Foo as Bar } from './user';\n")
        (models / "user.ts").write_text("export class Foo {}\n")

        # Looking up Bar (the alias) returns (source_module, original_name).
        # The original name "Foo" is what the matcher needs to bridge an
        # aliased barrel re-export back to the artifact's true identity.
        assert resolve_ts_reexport("src/models", "Bar", tmp_path) == (
            "src/models/user",
            "Foo",
        )

    def test_returns_none_when_name_not_reexported(self, tmp_path: Path) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { Bar } from './user';\n")
        (models / "user.ts").write_text("export class Bar {}\n")

        assert resolve_ts_reexport("src/models", "Foo", tmp_path) is None

    def test_returns_none_when_no_index_file(self, tmp_path: Path) -> None:
        # No index.ts(x) exists → not a barrel.
        (tmp_path / "lonely.ts").write_text("export class Foo {}\n")
        assert resolve_ts_reexport("lonely", "Foo", tmp_path) is None

    def test_index_tsx_also_recognized(self, tmp_path: Path) -> None:
        models = tmp_path / "src" / "components"
        models.mkdir(parents=True)
        (models / "index.tsx").write_text("export { Button } from './Button';\n")
        (models / "Button.tsx").write_text("export const Button = ...;\n")

        assert resolve_ts_reexport("src/components", "Button", tmp_path) == (
            "src/components/Button",
            "Button",
        )

    def test_star_reexport_resolves_requested_name_to_defining_module(
        self, tmp_path: Path
    ) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export * from './user';\n")
        (models / "user.ts").write_text("export class Foo {}\n")

        assert resolve_ts_reexport("src/models", "Foo", tmp_path) == (
            "src/models/user",
            "Foo",
        )

    def test_namespace_star_reexport_does_not_resolve_member_name(
        self, tmp_path: Path
    ) -> None:
        components = tmp_path / "src" / "components"
        components.mkdir(parents=True)
        (components / "index.ts").write_text("export * as Icons from './icons';\n")
        (components / "icons.ts").write_text("export function Camera() {}\n")

        assert resolve_ts_reexport("src/components", "Camera", tmp_path) is None

    def test_namespace_star_reexport_does_not_resolve_namespace_binding(
        self, tmp_path: Path
    ) -> None:
        components = tmp_path / "src" / "components"
        components.mkdir(parents=True)
        (components / "index.ts").write_text("export * as Icons from './icons';\n")
        (components / "icons.ts").write_text("export function Camera() {}\n")

        assert resolve_ts_reexport("src/components", "Icons", tmp_path) is None

    def test_default_as_reexport_resolves_to_visible_name(self, tmp_path: Path) -> None:
        components = tmp_path / "src" / "components"
        components.mkdir(parents=True)
        (components / "index.ts").write_text(
            "export { default as Button } from './Button';\n"
        )
        (components / "Button.tsx").write_text("export default class Button {}\n")

        assert resolve_ts_reexport("src/components", "Button", tmp_path) == (
            "src/components/Button",
            "Button",
        )

    def test_recursive_barrel_reexport_resolves_to_final_module(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"moduleResolution": "Bundler", "module": "ESNext", "baseUrl": "."}, "include": ["src/**/*"]}'
        )
        components = tmp_path / "src" / "components"
        nested = components / "nested"
        nested.mkdir(parents=True)
        (components / "index.ts").write_text("export { Button } from './nested';\n")
        (nested / "index.ts").write_text("export { Button } from './Button';\n")
        (nested / "Button.tsx").write_text("export function Button() {}\n")

        assert resolve_ts_reexport("src/components", "Button", tmp_path) == (
            "src/components/nested/Button",
            "Button",
        )

    def test_recursive_barrel_reexport_resolves_without_compiler(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from maid_runner.core import ts_module_paths

        def fail_compiler(*args):
            raise AssertionError("compiler should not run for static recursive barrels")

        monkeypatch.setattr(
            ts_module_paths, "resolve_reexport_with_compiler", fail_compiler
        )
        components = tmp_path / "src" / "components"
        nested = components / "nested"
        nested.mkdir(parents=True)
        (components / "index.ts").write_text("export { Button } from './nested';\n")
        (nested / "index.ts").write_text("export { Button } from './Button';\n")
        (nested / "Button.tsx").write_text("export function Button() {}\n")

        assert ts_module_paths.resolve_ts_reexport(
            "src/components", "Button", tmp_path
        ) == (
            "src/components/nested/Button",
            "Button",
        )

        src = tmp_path / "src"
        (src / "api.ts").write_text("export { Foo } from './foo';\n")
        (src / "foo.ts").write_text("export function Foo() {}\n")
        assert ts_module_paths.resolve_ts_reexport("src/api", "Foo", tmp_path) == (
            "src/foo",
            "Foo",
        )
        assert ts_module_paths.resolve_ts_reexport("src/foo", "Foo", tmp_path) is None

        models = src / "models"
        models.mkdir()
        (models / "index.ts").write_text("export { Model } from '@/models/Model';\n")
        (models / "Model.ts").write_text("export class Model {}\n")
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )
        assert ts_module_paths.resolve_ts_reexport("src/models", "Model", tmp_path) == (
            "src/models/Model",
            "Model",
        )

        (src / "mixed.ts").write_text(
            "export { z } from 'zod';\n"
            "export { Button } from './components/nested/Button';\n"
        )
        assert ts_module_paths.resolve_ts_reexport("src/mixed", "Button", tmp_path) == (
            "src/components/nested/Button",
            "Button",
        )

        (src / "icons.ts").write_text("export function Camera() {}\n")
        (src / "star-mixed.ts").write_text(
            "export * from './icons';\n"
            "export { Button } from './components/nested/Button';\n"
        )
        assert ts_module_paths.resolve_ts_reexport(
            "src/star-mixed", "Button", tmp_path
        ) == (
            "src/components/nested/Button",
            "Button",
        )

        (src / "star-chain.ts").write_text(
            "export * from './icons';\n" "export * from './components/nested/Button';\n"
        )
        assert ts_module_paths.resolve_ts_reexport(
            "src/star-chain", "Button", tmp_path
        ) == (
            "src/components/nested/Button",
            "Button",
        )

        (src / "default-button.ts").write_text("export default function Button() {}\n")
        (src / "star-default.ts").write_text(
            "export * from './default-button';\n"
            "export { Button } from './components/nested/Button';\n"
        )
        assert ts_module_paths.resolve_ts_reexport(
            "src/star-default", "Button", tmp_path
        ) == (
            "src/components/nested/Button",
            "Button",
        )

        (src / "early-button.ts").write_text("export function Button() {}\n")
        (src / "star-override.ts").write_text(
            "export * from './early-button';\n"
            "export { Button } from './components/nested/Button';\n"
        )
        assert ts_module_paths.resolve_ts_reexport(
            "src/star-override", "Button", tmp_path
        ) == (
            "src/components/nested/Button",
            "Button",
        )

        (src / "leaf.ts").write_text("export class Foo {}\n")
        (src / "middle.ts").write_text(
            "import { Foo } from './leaf';\n" "export { Foo };\n"
        )
        (src / "imported-binding.ts").write_text("export { Foo } from './middle';\n")
        (src / "star-imported-binding.ts").write_text("export * from './middle';\n")

        (src / "missing-barrel.ts").write_text(
            "export { Missing } from './does-not-exist';\n"
        )
        (src / "wrong.ts").write_text("export function Bar() {}\n")
        (src / "wrong-barrel.ts").write_text("export { Foo } from './wrong';\n")
        (src / "alt-button.ts").write_text("export function Button() {}\n")
        (src / "star-ambiguous.ts").write_text(
            "export * from './components/nested/Button';\n"
            "export * from './alt-button';\n"
        )
        (src / "missing-default.ts").write_text(
            "export { default as Button } from './does-not-exist';\n"
        )
        (src / "cjs-missing.cjs").write_text(
            "exports.Foo = require('./does-not-exist.cjs').Foo;\n"
        )
        (src / "wrong.cjs").write_text("exports.Bar = 1;\n")
        (src / "cjs-wrong.cjs").write_text(
            "exports.Foo = require('./wrong.cjs').Foo;\n"
        )

        fallback_requests: list[tuple[str, str]] = []

        def fallback_compiler(module, name, root):
            fallback_requests.append((module, name))
            assert root == tmp_path
            if module in {
                "src/imported-binding",
                "src/middle",
                "src/star-imported-binding",
            }:
                return ("src/leaf", "Foo")
            return None

        monkeypatch.setattr(
            ts_module_paths, "resolve_reexport_with_compiler", fallback_compiler
        )
        assert ts_module_paths.resolve_ts_reexport(
            "src/imported-binding", "Foo", tmp_path
        ) == (
            "src/leaf",
            "Foo",
        )
        assert ts_module_paths.resolve_ts_reexport("src/middle", "Foo", tmp_path) == (
            "src/leaf",
            "Foo",
        )
        assert ts_module_paths.resolve_ts_reexport(
            "src/star-imported-binding", "Foo", tmp_path
        ) == (
            "src/leaf",
            "Foo",
        )
        assert (
            ts_module_paths.resolve_ts_reexport(
                "src/star-ambiguous", "Button", tmp_path
            )
            is None
        )
        assert (
            ts_module_paths.resolve_ts_reexport(
                "src/missing-barrel", "Missing", tmp_path
            )
            is None
        )
        assert (
            ts_module_paths.resolve_ts_reexport("src/wrong-barrel", "Foo", tmp_path)
            is None
        )
        assert (
            ts_module_paths.resolve_ts_reexport(
                "src/missing-default", "Button", tmp_path
            )
            is None
        )
        assert (
            ts_module_paths.resolve_ts_reexport("src/cjs-missing", "Foo", tmp_path)
            is None
        )
        assert (
            ts_module_paths.resolve_ts_reexport("src/cjs-wrong", "Foo", tmp_path)
            is None
        )
        assert fallback_requests == [
            ("src/imported-binding", "Foo"),
            ("src/middle", "Foo"),
            ("src/star-imported-binding", "Foo"),
            ("src/star-ambiguous", "Button"),
            ("src/missing-barrel", "Missing"),
            ("src/wrong-barrel", "Foo"),
            ("src/missing-default", "Button"),
            ("src/cjs-missing", "Foo"),
            ("src/cjs-wrong", "Foo"),
        ]

        package_dir = tmp_path / "node_modules" / "vitest"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text('{"name": "vitest"}')
        (src / "test-helpers.ts").write_text("export { describe } from 'vitest';\n")
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"*": ["src/*"]}}}'
        )

        def external_fallback_compiler(module, name, root):
            assert module == "src/test-helpers"
            assert name == "describe"
            return None

        monkeypatch.setattr(
            ts_module_paths,
            "resolve_reexport_with_compiler",
            external_fallback_compiler,
        )
        assert (
            ts_module_paths.resolve_ts_reexport(
                "src/test-helpers", "describe", tmp_path
            )
            is None
        )

    def test_type_only_reexport_resolves_to_defining_module(
        self, tmp_path: Path
    ) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export type { Foo } from './types';\n")
        (models / "types.ts").write_text("export interface Foo {}\n")

        assert resolve_ts_reexport("src/models", "Foo", tmp_path) == (
            "src/models/types",
            "Foo",
        )

    def test_export_specifier_type_modifier_resolves_to_defining_module(
        self, tmp_path: Path
    ) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { type Foo } from './types';\n")
        (models / "types.ts").write_text("export interface Foo {}\n")

        assert resolve_ts_reexport("src/models", "Foo", tmp_path) == (
            "src/models/types",
            "Foo",
        )

    def test_supported_index_js_barrel_resolves_reexport(self, tmp_path: Path) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.js").write_text("export { Foo } from './user.js';\n")
        (models / "user.js").write_text("export class Foo {}\n")

        assert resolve_ts_reexport("src/models", "Foo", tmp_path) == (
            "src/models/user",
            "Foo",
        )

    def test_supported_index_mjs_barrel_resolves_reexport(self, tmp_path: Path) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.mjs").write_text("export { Foo } from './user.mjs';\n")
        (models / "user.mjs").write_text("export class Foo {}\n")

        assert resolve_ts_reexport("src/models", "Foo", tmp_path) == (
            "src/models/user",
            "Foo",
        )

    def test_supported_index_cjs_exports_assignment_resolves_reexport(
        self, tmp_path: Path
    ) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.cjs").write_text("exports.Foo = require('./user.cjs').Foo;\n")
        (models / "user.cjs").write_text("exports.Foo = class Foo {};\n")

        assert resolve_ts_reexport("src/models", "Foo", tmp_path) == (
            "src/models/user",
            "Foo",
        )
