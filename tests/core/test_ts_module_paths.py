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

    def test_strips_svelte_extension_from_resolved_specifier(self) -> None:
        assert (
            resolve_relative_ts_import("./Foo.svelte", "src/components/test")
            == "src/components/Foo"
        )


# ----------------------------------------------------------------------------
# resolve_ts_import
# ----------------------------------------------------------------------------


class TestResolveTsImport:
    def test_paths_alias_resolves_wildcard_to_project_module(
        self, tmp_path: Path
    ) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )

        assert (
            resolve_ts_import("@/components/Button", "src/App.test", tmp_path)
            == "src/components/Button"
        )

    def test_base_url_resolves_non_relative_specifier(self, tmp_path: Path) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": "src"}}'
        )

        assert (
            resolve_ts_import("components/Button", "src/App.test", tmp_path)
            == "src/components/Button"
        )

    def test_paths_alias_can_resolve_directory_barrel(self, tmp_path: Path) -> None:
        from maid_runner.core.ts_module_paths import resolve_ts_import

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


# ----------------------------------------------------------------------------
# resolve_ts_reexport (one-level barrel)
# ----------------------------------------------------------------------------


class TestResolveTsReexport:
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
