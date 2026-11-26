"""Implementation validation for named TypeScript function re-exports."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


def _write_project(
    root: Path,
    *,
    exporter: str,
    source: str = (
        "export function isBrowserOnlyUrl(url: string): boolean "
        "{ return url.startsWith('blob:'); }\n"
    ),
    name: str = "isBrowserOnlyUrl",
    argument_type: str = "string",
    returns: str = "boolean",
    exporter_path: str = "src/export.ts",
    source_path: str = "src/helper.ts",
) -> Path:
    export_file = root / exporter_path
    export_file.parent.mkdir(parents=True, exist_ok=True)
    export_file.write_text(exporter)
    helper_file = root / source_path
    helper_file.parent.mkdir(parents=True, exist_ok=True)
    helper_file.write_text(source)
    test_file = root / "tests" / "reexport.test.ts"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    import_path = os.path.relpath(export_file.with_suffix(""), test_file.parent)
    if not import_path.startswith("."):
        import_path = "./" + import_path
    test_file.write_text(
        f"import {{ {name} }} from '{import_path}';\n"
        f"test('url', () => expect({name}('blob:a')).toBe(true));\n"
    )
    manifest = root / "reexport.manifest.yaml"
    manifest.write_text(
        f"""schema: "2"
goal: Validate exported URL predicate
type: fix
files:
  edit:
    - path: {exporter_path}
      artifacts:
        - kind: function
          name: {name}
          args:
            - name: url
              type: {argument_type}
          returns: {returns}
validate:
  - node tests/reexport.test.ts
"""
    )
    return manifest


def _validate(root: Path, manifest: Path, *, check_stubs: bool = False):
    return ValidationEngine(project_root=root).validate(
        manifest, mode=ValidationMode.IMPLEMENTATION, check_stubs=check_stubs
    )


def test_named_import_reexport_uses_real_function_contract(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []
    assert result.warnings == []


def test_renamed_import_and_export_use_public_identity(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl as internalGuard } from './helper';\n"
        "export { internalGuard as publicGuard };\n",
        name="publicGuard",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize(
    ("argument_type", "returns"), [("number", "boolean"), ("string", "string")]
)
def test_reexport_signature_mismatch_is_rejected(
    tmp_path: Path, argument_type: str, returns: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        argument_type=argument_type,
        returns=returns,
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)
    assert not any(
        error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors
    )


@pytest.mark.parametrize(
    ("exporter", "source"),
    [
        (
            "import { isBrowserOnlyUrl } from './helper';\n",
            "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }",
        ),
        (
            "import { isBrowserOnlyUrl } from './helper';\n"
            "export { isBrowserOnlyUrl as differentName };\n",
            "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }",
        ),
        (
            "import type { isBrowserOnlyUrl } from './helper';\n"
            "export { isBrowserOnlyUrl };\n",
            "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }",
        ),
        (
            "import { type isBrowserOnlyUrl } from './helper';\n"
            "export { isBrowserOnlyUrl };\n",
            "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }",
        ),
        (
            "import { isBrowserOnlyUrl } from './helper';\n"
            "export type { isBrowserOnlyUrl };\n",
            "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }",
        ),
        (
            "import { isBrowserOnlyUrl } from './helper';\n"
            "export { type isBrowserOnlyUrl };\n",
            "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }",
        ),
        (
            "import { isBrowserOnlyUrl } from './helper';\n"
            "export { isBrowserOnlyUrl };\n",
            "function isBrowserOnlyUrl(url: string): boolean { return !!url; }",
        ),
        (
            "import { isBrowserOnlyUrl } from './missing';\n"
            "export { isBrowserOnlyUrl };\n",
            "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }",
        ),
        (
            "import { isBrowserOnlyUrl } from './helper';\n"
            "export { isBrowserOnlyUrl };\n",
            "export const isBrowserOnlyUrl: string = 'not a function';",
        ),
    ],
)
def test_non_runtime_or_unavailable_bindings_are_rejected(
    tmp_path: Path, exporter: str, source: str
) -> None:
    manifest = _write_project(tmp_path, exporter=exporter, source=source)

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_nested_inherited_tsconfig_alias_resolves_real_declaration(
    tmp_path: Path,
) -> None:
    try:
        available = (
            subprocess.run(
                ["node", "-e", "require.resolve('typescript')"],
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
    except OSError:
        available = False
    if not available:
        pytest.skip("Node and the TypeScript compiler are needed for config resolution")

    package = tmp_path / "apps" / "frontend"
    generated = package / ".svelte-kit"
    generated.mkdir(parents=True)
    (package / "tsconfig.json").write_text(
        json.dumps({"extends": "./.svelte-kit/tsconfig.json"})
    )
    (generated / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"paths": {"$lib/*": ["../src/lib/*"]}}})
    )
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from '$lib/helper';\n"
        "export { isBrowserOnlyUrl };\n",
        exporter_path="apps/frontend/src/lib/export.ts",
        source_path="apps/frontend/src/lib/helper.ts",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


def test_reexport_outside_project_via_symlink_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    manifest = _write_project(
        project,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )
    helper = project / "src" / "helper.ts"
    outside = tmp_path / "outside.ts"
    helper.rename(outside)
    helper.symlink_to(outside)

    result = _validate(project, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_reexported_stub_is_reported(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: string): boolean { return false; }",
    )

    result = _validate(tmp_path, manifest, check_stubs=True)

    assert result.errors == []
    assert any(
        warning.code == ErrorCode.STUB_FUNCTION_DETECTED for warning in result.warnings
    )


def test_reexport_source_changes_are_not_cached_as_stale_contracts(
    tmp_path: Path,
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )
    engine = ValidationEngine(project_root=tmp_path)

    before = engine.validate(manifest, mode=ValidationMode.IMPLEMENTATION)
    (tmp_path / "src" / "helper.ts").write_text(
        "export function isBrowserOnlyUrl(url: number): boolean { return !!url; }"
    )
    after = engine.validate(manifest, mode=ValidationMode.IMPLEMENTATION)

    assert before.errors == []
    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in after.errors)


def test_origin_alias_selects_its_actual_local_declaration(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="function internal(url: string): boolean { return !!url; }\n"
        "export { internal as isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize(
    ("other_declaration", "expected_code"),
    [
        ("const other = 42;", ErrorCode.ARTIFACT_NOT_DEFINED),
        (
            "function other(url: number): number { return url + 1; }",
            ErrorCode.TYPE_MISMATCH,
        ),
    ],
)
def test_origin_public_export_cannot_credit_a_different_declaration(
    tmp_path: Path, other_declaration: str, expected_code: ErrorCode
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
        "export default isBrowserOnlyUrl;\n"
        f"{other_declaration}\n"
        "export { other as isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == expected_code for error in result.errors)


def test_inherited_alias_ignores_misrebased_decoy(tmp_path: Path) -> None:
    try:
        subprocess.run(
            ["node", "-e", "require.resolve('typescript')"],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("Node and the TypeScript compiler are needed for config resolution")
    package = tmp_path / "apps" / "frontend"
    generated = package / ".svelte-kit"
    generated.mkdir(parents=True)
    (package / "tsconfig.json").write_text(
        json.dumps({"extends": "./.svelte-kit/tsconfig.json"})
    )
    (generated / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"paths": {"$lib/*": ["../src/lib/*"]}}})
    )
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from '$lib/helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: number): number { return url + 1; }",
        exporter_path="apps/frontend/src/lib/export.ts",
        source_path="apps/frontend/src/lib/helper.ts",
    )
    decoy = tmp_path / "apps" / "src" / "lib" / "helper.ts"
    decoy.parent.mkdir(parents=True)
    decoy.write_text(
        "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }"
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


@pytest.mark.parametrize("specifier", ["./helper.ts", "./helper"])
def test_typescript_file_precedence_rejects_a_matching_sibling_decoy(
    tmp_path: Path, specifier: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter=f"import {{ isBrowserOnlyUrl }} from '{specifier}';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: number): number { return url + 1; }",
    )
    (tmp_path / "src" / "helper.tsx").write_text(
        "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }"
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


@pytest.mark.parametrize(
    ("returns", "expected_code"),
    [("boolean", None), ("string", ErrorCode.TYPE_MISMATCH)],
)
def test_reexport_uses_origin_for_compiler_return_proof(
    tmp_path: Path, returns: str, expected_code: ErrorCode | None
) -> None:
    try:
        subprocess.run(
            ["node", "-e", "require.resolve('typescript')"],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("Node and the TypeScript compiler are needed for return proofs")
    manifest = _write_project(
        tmp_path,
        exporter="import { internalGuard as guard } from './helper';\n"
        "export { guard as publicGuard };\n",
        source="export function internalGuard(url: string) { return !!url; }\n",
        name="publicGuard",
        returns=returns,
    )
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps({"compilerOptions": {"strict": True}, "include": ["src/**/*.ts"]})
    )
    (tmp_path / ".maidrc.yaml").write_text(
        "typescript_return_contracts:\n  mode: compiler\n  tsconfig: tsconfig.app.json\n"
    )

    result = _validate(tmp_path, manifest)

    if expected_code is None:
        assert result.errors == []
        assert result.warnings == []
    else:
        assert any(error.code == expected_code for error in result.errors)


def test_same_named_interface_does_not_hide_function_reexport(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n"
        "export interface isBrowserOnlyUrl { reason: string }\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize(
    "exporter",
    [
        "import { 'something-else' as isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        "import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl as 'something-else' };\n",
    ],
)
def test_string_literal_specifiers_do_not_certify_wrong_bindings(
    tmp_path: Path, exporter: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter=exporter,
        source="export function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
        "const other = 42; export { other as 'something-else' };\n",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_extensionless_import_does_not_claim_mts_source(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source_path="src/helper.mts",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_mjs_import_uses_the_mts_declaration(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper.mjs';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: number): number { return url + 1; }",
        source_path="src/helper.mts",
    )
    (tmp_path / "src" / "helper.ts").write_text(
        "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }"
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


def _require_compiler() -> None:
    try:
        subprocess.run(
            ["node", "-e", "require.resolve('typescript')"],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("Node and the TypeScript compiler are needed for this case")


@pytest.mark.parametrize(
    ("import_suffix", "source_suffix"), [("mjs", "mts"), ("cjs", "cts")]
)
def test_aliased_module_extensions_use_compiler_resolved_file(
    tmp_path: Path, import_suffix: str, source_suffix: str
) -> None:
    _require_compiler()
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"paths": {"@/*": ["src/*"]}}})
    )
    manifest = _write_project(
        tmp_path,
        exporter=f"import {{ isBrowserOnlyUrl }} from '@/helper.{import_suffix}';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: number): number { return url + 1; }",
        source_path=f"src/helper.{source_suffix}",
    )
    (tmp_path / "src" / "helper.ts").write_text(
        "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }"
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


@pytest.mark.parametrize(
    "source",
    [
        "export const isBrowserOnlyUrl = 42;\n"
        "{ function isBrowserOnlyUrl(url: string): boolean { return !!url; } }\n",
        "export const isBrowserOnlyUrl = 42;\n"
        "export const obj = { isBrowserOnlyUrl(url: string): boolean { return !!url; } };\n",
        "export interface isBrowserOnlyUrl { reason: string }\n"
        "export declare function isBrowserOnlyUrl(url: string): boolean;\n",
    ],
)
def test_nested_and_ambient_functions_do_not_satisfy_value_export(
    tmp_path: Path, source: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source=source,
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_top_level_exported_arrow_function_is_recognized(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export const isBrowserOnlyUrl = (url: string): boolean => !!url;\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize(
    ("package_type", "valid"), [("module", False), ("commonjs", True)]
)
def test_nodenext_requires_resolvable_import_for_package_mode(
    tmp_path: Path, package_type: str, valid: bool
) -> None:
    _require_compiler()
    (tmp_path / "package.json").write_text(json.dumps({"type": package_type}))
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {"compilerOptions": {"module": "NodeNext", "moduleResolution": "NodeNext"}}
        )
    )
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    if valid:
        assert result.errors == []
    else:
        assert any(
            error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors
        )


def test_nested_config_alias_can_resolve_project_sibling(tmp_path: Path) -> None:
    _require_compiler()
    package = tmp_path / "apps" / "frontend"
    package.mkdir(parents=True)
    (package / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"paths": {"@shared/*": ["../shared/*"]}}})
    )
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from '@shared/helper';\n"
        "export { isBrowserOnlyUrl };\n",
        exporter_path="apps/frontend/src/export.ts",
        source_path="apps/shared/helper.ts",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


def test_unconfigured_package_import_uses_compiler_target(tmp_path: Path) -> None:
    _require_compiler()
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: number): number { return url + 1; }",
        source_path="src/helper/actual.ts",
    )
    package = tmp_path / "src" / "helper"
    (package / "package.json").write_text(json.dumps({"types": "./actual.ts"}))
    (package / "index.ts").write_text(
        "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }"
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


def test_no_compiler_relative_resolution_rejects_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source_path="src/helper/index.ts",
    )
    (tmp_path / "src" / "helper" / "package.json").write_text(
        json.dumps({"types": "./actual.ts"})
    )
    monkeypatch.setenv("PATH", "")

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_no_compiler_relative_file_resolution_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )
    monkeypatch.setenv("PATH", "")

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize(
    "source",
    [
        "export function isBrowserOnlyUrl(url: number): number;\n"
        "export function isBrowserOnlyUrl(url: string | number): number { return 1; }\n",
        "export const isBrowserOnlyUrl: (url: number) => number = "
        "(url: string | number): number => 1;\n",
    ],
)
def test_unsupported_callable_contracts_do_not_match_implementation(
    tmp_path: Path, source: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source=source,
        argument_type="string | number",
        returns="number",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_exporter_nested_function_cannot_mask_imported_binding(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n"
        "{ function isBrowserOnlyUrl(url: string): boolean { return !!url; } }\n",
        source="export function isBrowserOnlyUrl(url: number): number { return url + 1; }",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


def test_invalid_inherited_tsconfig_does_not_resolve_alias(tmp_path: Path) -> None:
    _require_compiler()
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "extends": "./missing.json",
                "compilerOptions": {"paths": {"@/*": ["src/*"]}},
            }
        )
    )
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from '@/helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_strict_manifest_rejects_undeclared_function_reexport(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl, other } from './helper';\n"
        "export { isBrowserOnlyUrl, other };\n",
        source="export function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
        "export function other(url: string): boolean { return !!url; }\n",
    )
    manifest.write_text(manifest.read_text().replace("  edit:", "  create:"))

    result = _validate(tmp_path, manifest)

    assert any(
        error.code == ErrorCode.UNEXPECTED_ARTIFACT and "other" in error.message
        for error in result.errors
    )


@pytest.mark.parametrize(
    "exporter",
    [
        "import { isBrowserOnlyUrl } from './helper';\n"
        "export type { isBrowserOnlyUrl };\n",
        "import type { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        "import isBrowserOnlyUrl from './helper';\n" "export { isBrowserOnlyUrl };\n",
        "import { 'different-name' as isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        "import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl as 'different-name' };\n",
        "import { isBrowserOnlyUrl } from './helper';\n"
        "export default isBrowserOnlyUrl;\n",
        "import { isBrowserOnlyUrl } from './helper';\n" "export = isBrowserOnlyUrl;\n",
    ],
)
def test_unsupported_imports_and_exports_do_not_credit_nested_functions(
    tmp_path: Path, exporter: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter=exporter
        + "{ function isBrowserOnlyUrl(url: string): boolean { return !!url; } }\n",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_type_only_import_does_not_hide_real_local_function(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import type { isBrowserOnlyUrl } from './helper';\n"
        "function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
        "export { isBrowserOnlyUrl };\n",
        source="export interface isBrowserOnlyUrl { reason: string }\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


def test_repeated_value_declarations_do_not_certify_function(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="var isBrowserOnlyUrl = (url: string): boolean => !!url;\n"
        "var isBrowserOnlyUrl = 42 as unknown as (url: string) => boolean;\n"
        "export { isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_no_compiler_prefers_direct_typescript_file_to_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )
    directory = tmp_path / "src" / "helper"
    directory.mkdir()
    (directory / "index.ts").write_text("export const other = 1;\n")
    monkeypatch.setenv("PATH", "")

    result = _validate(tmp_path, manifest)

    assert result.errors == []


def test_javascript_jsdoc_return_type_is_compared(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper.js';\n"
        "export { isBrowserOnlyUrl };\n",
        source="/** @returns {string} */\n"
        "export function isBrowserOnlyUrl(url) { return String(url); }\n",
        source_path="src/helper.js",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


def test_parenthesized_arrow_function_is_recognized(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export const isBrowserOnlyUrl = ((url: string): boolean => !!url);\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize(
    "redeclaration",
    [
        "var {isBrowserOnlyUrl} = {isBrowserOnlyUrl: 42 as any};",
        "var {value: isBrowserOnlyUrl} = {value: 42 as any};",
        "var [isBrowserOnlyUrl = 42 as any] = [42 as any];",
    ],
)
def test_destructured_redeclarations_do_not_certify_function(
    tmp_path: Path, redeclaration: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="var isBrowserOnlyUrl = (url: string): boolean => !!url;\n"
        f"{redeclaration}\n"
        "export { isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_inline_javascript_jsdoc_return_type_is_compared(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper.js';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export const isBrowserOnlyUrl = /** @returns {string} */ "
        "(url) => String(url);\n",
        source_path="src/helper.js",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


@pytest.mark.parametrize(
    ("returns", "mismatch"), [("string", False), ("boolean", True)]
)
def test_mjs_source_preserves_jsdoc_contract(
    tmp_path: Path, returns: str, mismatch: bool
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper.mjs';\n"
        "export { isBrowserOnlyUrl };\n",
        source="/** @returns {string} */\n"
        "export function isBrowserOnlyUrl(url) { return String(url); }\n",
        source_path="src/helper.mjs",
        returns=returns,
    )

    result = _validate(tmp_path, manifest)

    assert (
        any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)
        == mismatch
    )
    if not mismatch:
        assert result.errors == []


@pytest.mark.parametrize(
    ("source_suffix", "import_suffix"), [("mts", "mjs"), ("cts", "cjs")]
)
def test_mts_and_cts_origin_supports_compiler_return_proof(
    tmp_path: Path, source_suffix: str, import_suffix: str
) -> None:
    _require_compiler()
    manifest = _write_project(
        tmp_path,
        exporter=f"import {{ isBrowserOnlyUrl }} from './helper.{import_suffix}';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: string) { return !!url; }\n",
        source_path=f"src/helper.{source_suffix}",
    )
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps({"compilerOptions": {"strict": True}, "include": ["src/**/*"]})
    )
    (tmp_path / ".maidrc.yaml").write_text(
        "typescript_return_contracts:\n  mode: compiler\n  tsconfig: tsconfig.app.json\n"
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []
    assert result.warnings == []


def test_shared_import_source_is_resolved_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _require_compiler()
    if os.name != "posix":
        pytest.skip("This process-count probe uses a POSIX node wrapper")
    node = shutil.which("node")
    assert node is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    count_file = tmp_path / "node-invocations"
    wrapper = bin_dir / "node"
    wrapper.write_text(
        '#!/bin/sh\nprintf "x\\n" >> "$MAID_TEST_NODE_COUNT"\n'
        f'exec {shlex.quote(node)} "$@"\n'
    )
    wrapper.chmod(0o755)
    monkeypatch.setenv("MAID_TEST_NODE_COUNT", str(count_file))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    names = ["isBrowserOnlyUrl", "otherA", "otherB", "otherC"]
    bindings = ", ".join(names)
    declarations = "\n".join(
        f"export function {name}(url: string): boolean {{ return !!url; }}"
        for name in names
    )
    manifest = _write_project(
        tmp_path,
        exporter=f"import {{ {bindings} }} from './helper';\nexport {{ {bindings} }};\n",
        source=declarations,
    )
    manifest.write_text(manifest.read_text().replace("  edit:", "  create:"))

    result = _validate(tmp_path, manifest)

    assert (
        sum(error.code == ErrorCode.UNEXPECTED_ARTIFACT for error in result.errors) == 3
    )
    assert count_file.read_text().splitlines() == ["x"]


@pytest.mark.parametrize("placement", ["exporter", "origin", "unresolved"])
def test_normalized_typescript_syntax_preserves_binding_validation(
    tmp_path: Path, placement: str
) -> None:
    extra = (
        "declare function fetchJson<T>(): T;\n"
        "const value = fetchJson<import('./helper').Foo>();\n"
    )
    exporter = (
        "import { isBrowserOnlyUrl } from './helper';\nexport { isBrowserOnlyUrl };\n"
    )
    source = "export interface Foo { value: string }\n" + (
        "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
    )
    if placement == "exporter":
        exporter += extra
    elif placement == "origin":
        source += extra
    else:
        exporter = (
            "import { isBrowserOnlyUrl } from './missing';\n"
            "export { isBrowserOnlyUrl };\n"
            "{ function isBrowserOnlyUrl(url: string): boolean { return !!url; } }\n"
            + extra
        )
    manifest = _write_project(tmp_path, exporter=exporter, source=source)

    result = _validate(tmp_path, manifest)

    if placement == "unresolved":
        assert any(
            error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors
        )
    else:
        assert result.errors == []


@pytest.mark.parametrize(
    "redeclaration",
    [
        "for (var isBrowserOnlyUrl = 42; false;) {}",
        "if (false) { var isBrowserOnlyUrl = 42; }",
        "for (var isBrowserOnlyUrl of [42]) {}",
    ],
)
def test_module_scoped_var_redeclarations_do_not_certify_function(
    tmp_path: Path, redeclaration: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper.js';\n"
        "export { isBrowserOnlyUrl };\n",
        source="var isBrowserOnlyUrl = (url) => !!url;\n"
        f"{redeclaration}\n"
        "export { isBrowserOnlyUrl };\n",
        source_path="src/helper.js",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_parenthesized_inline_jsdoc_return_type_is_compared(tmp_path: Path) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper.js';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export const isBrowserOnlyUrl = "
        "(/** @returns {string} */ (url) => String(url));\n",
        source_path="src/helper.js",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.TYPE_MISMATCH for error in result.errors)


def test_referenced_project_config_resolves_owning_alias(tmp_path: Path) -> None:
    _require_compiler()
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"files": [], "references": [{"path": "./tsconfig.app.json"}]})
    )
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps(
            {
                "include": ["src/**/*.ts"],
                "compilerOptions": {"paths": {"@/*": ["src/*"]}},
            }
        )
    )
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from '@/helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize(
    ("package_type", "valid"), [("module", False), ("commonjs", True)]
)
def test_referenced_nodenext_project_uses_owning_module_mode(
    tmp_path: Path, package_type: str, valid: bool
) -> None:
    _require_compiler()
    (tmp_path / "package.json").write_text(json.dumps({"type": package_type}))
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"files": [], "references": [{"path": "./tsconfig.app.json"}]})
    )
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps(
            {
                "include": ["src/**/*.ts"],
                "compilerOptions": {
                    "module": "NodeNext",
                    "moduleResolution": "NodeNext",
                },
            }
        )
    )
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    if valid:
        assert result.errors == []
    else:
        assert any(
            error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors
        )


def test_ambiguous_referenced_project_ownership_fails_closed(tmp_path: Path) -> None:
    _require_compiler()
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "files": [],
                "references": [
                    {"path": "./tsconfig.a.json"},
                    {"path": "./tsconfig.b.json"},
                ],
            }
        )
    )
    (tmp_path / "tsconfig.a.json").write_text(json.dumps({"include": ["src/**/*.ts"]}))
    (tmp_path / "tsconfig.b.json").write_text(json.dumps({"include": ["src/**/*.ts"]}))
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


@pytest.mark.parametrize(
    "pattern",
    [
        "{isBrowserOnlyUrl: another}",
        "{[String(isBrowserOnlyUrl)]: another}",
    ],
)
@pytest.mark.parametrize("nested", [False, True])
def test_destructuring_property_keys_do_not_shadow_function(
    tmp_path: Path, pattern: str, nested: bool
) -> None:
    declaration = f"var {pattern} = {{}} as any;"
    if nested:
        declaration = f"if (false) {{ {declaration} }}"
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
        f"{declaration}\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize("case", ["nodenext", "ambiguous"])
def test_no_compiler_referenced_ownership_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    references = [{"path": "./tsconfig.app.json"}]
    if case == "ambiguous":
        references.append({"path": "./tsconfig.other.json"})
        (tmp_path / "tsconfig.other.json").write_text(
            json.dumps({"include": ["src/**/*.ts"]})
        )
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"files": [], "references": references})
    )
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps(
            {
                "include": ["src/**/*.ts"],
                "compilerOptions": {
                    "module": "NodeNext",
                    "moduleResolution": "NodeNext",
                },
            }
        )
    )
    (tmp_path / "package.json").write_text(json.dumps({"type": "module"}))
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )
    monkeypatch.setenv("PATH", "")

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_no_compiler_simple_config_keeps_relative_file_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tsconfig.json").write_text(json.dumps({"include": ["src/**/*.ts"]}))
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )
    monkeypatch.setenv("PATH", "")

    result = _validate(tmp_path, manifest)

    assert result.errors == []


@pytest.mark.parametrize(
    "config",
    [
        {"files": ["src/other.ts"]},
        {"include": ["other/**/*.ts"]},
        {"include": ["src/**/*.ts"], "exclude": ["src/export.ts"]},
    ],
)
def test_no_compiler_config_rejects_nonmember_importer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: dict
) -> None:
    (tmp_path / "tsconfig.json").write_text(json.dumps(config))
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )
    (tmp_path / "src" / "other.ts").write_text("export {};\n")
    monkeypatch.setenv("PATH", "")

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


def test_compiler_project_transitively_includes_reexporter(tmp_path: Path) -> None:
    _require_compiler()
    (tmp_path / "tsconfig.json").write_text(json.dumps({"files": ["src/main.ts"]}))
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
    )
    (tmp_path / "src" / "main.ts").write_text("import './export';\n")

    result = _validate(tmp_path, manifest)

    assert result.errors == []


def test_compiler_return_proof_accepts_transitive_origin(tmp_path: Path) -> None:
    _require_compiler()
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: string) { return !!url; }\n",
    )
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps({"files": ["src/export.ts"], "compilerOptions": {"strict": True}})
    )
    (tmp_path / ".maidrc.yaml").write_text(
        "typescript_return_contracts:\n  mode: compiler\n  tsconfig: tsconfig.app.json\n"
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []
    assert result.warnings == []


@pytest.mark.parametrize(
    "case",
    ["exporter_function", "origin_class", "origin_import", "origin_string_export"],
)
def test_conflicting_value_bindings_do_not_certify_function(
    tmp_path: Path, case: str
) -> None:
    exporter = (
        "import { isBrowserOnlyUrl } from './helper';\nexport { isBrowserOnlyUrl };\n"
    )
    source = (
        "export function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
    )
    if case == "exporter_function":
        exporter += (
            "function isBrowserOnlyUrl(url: number): number { return url + 1; }\n"
        )
    elif case == "origin_class":
        source += "class isBrowserOnlyUrl {}\n"
    elif case == "origin_import":
        source = (
            "import { isBrowserOnlyUrl } from './other';\n"
            "function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
            "export { isBrowserOnlyUrl };\n"
        )
    else:
        source += "const wrong = 42; export { wrong as 'isBrowserOnlyUrl' };\n"
    manifest = _write_project(tmp_path, exporter=exporter, source=source)

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


@pytest.mark.parametrize(
    "source",
    [
        "/** @type {(url: string) => string} */\n"
        "export const isBrowserOnlyUrl = (url) => url;\n",
        "export const isBrowserOnlyUrl = /** @type {(url: string) => string} */ "
        "(url) => url;\n",
        "/** @overload @param {string} url @returns {string} */\n"
        "/** @param {string} url @returns {string} */\n"
        "export function isBrowserOnlyUrl(url) { return url; }\n",
    ],
)
def test_jsdoc_callable_type_and_overload_are_unsupported(
    tmp_path: Path, source: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper.js';\n"
        "export { isBrowserOnlyUrl };\n",
        source=source,
        source_path="src/helper.js",
    )

    result = _validate(tmp_path, manifest)

    assert any(error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors)


@pytest.mark.parametrize(
    "declaration",
    [
        "namespace Other { var isBrowserOnlyUrl = 42; }",
        "declare namespace Other { var isBrowserOnlyUrl: number; }",
        "declare global { var isBrowserOnlyUrl: number; }",
    ],
)
def test_namespace_and_ambient_var_do_not_shadow_top_level_function(
    tmp_path: Path, declaration: str
) -> None:
    manifest = _write_project(
        tmp_path,
        exporter="import { isBrowserOnlyUrl } from './helper';\n"
        "export { isBrowserOnlyUrl };\n",
        source="export function isBrowserOnlyUrl(url: string): boolean { return !!url; }\n"
        f"{declaration}\n",
    )

    result = _validate(tmp_path, manifest)

    assert result.errors == []
