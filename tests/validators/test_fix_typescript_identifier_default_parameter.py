"""Default expression identifiers must never replace TypeScript binding names."""

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
import tree_sitter_typescript
import yaml
from tree_sitter import Language, Parser

from maid_runner.core.manifest import load_manifest, save_manifest
from maid_runner.core.snapshot import generate_snapshot
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators._typescript_implementation import (
    collect_implementation_artifacts,
)
from maid_runner.validators.typescript import TypeScriptValidator


@pytest.mark.parametrize(
    "header,kind",
    [
        (
            "export function read(windowMs: number = W): number { return windowMs; }",
            "read",
        ),
        ("export function read(windowMs = W): number { return windowMs; }", "read"),
        ("export const read = (windowMs: number = W): number => windowMs;", "read"),
        ("export const read = (windowMs = W): number => windowMs;", "read"),
        (
            "export class Reader { read(windowMs: number = W): number { return windowMs; } }",
            "read",
        ),
        (
            "export class Reader { static read(windowMs: number = W): number { return windowMs; } }",
            "read",
        ),
    ],
)
def test_identifier_initializer_keeps_binding_name_type_and_default(
    header: str, kind: str
) -> None:
    source = "const W = 10;\n" + header
    result = TypeScriptValidator().collect_implementation_artifacts(source, "sample.ts")
    assert not result.errors
    encoded = source.encode()
    parser = Parser(Language(tree_sitter_typescript.language_typescript()))
    direct = collect_implementation_artifacts(parser.parse(encoded).root_node, encoded)
    for artifacts in (result.artifacts, direct):
        artifact = next(a for a in artifacts if a.name == kind)
        (argument,) = artifact.args
        assert argument.name == "windowMs"
        assert argument.default == "W"
        assert argument.type == ("number" if "windowMs: number" in header else None)


@pytest.mark.parametrize(
    "default",
    [
        "10",
        "600_000",
        "-1",
        "options.windowMs",
        "W + 1",
        "getWindow()",
        "'long'",
        "true",
        "{ value: W }",
        "[W]",
    ],
)
def test_literal_and_expression_default_compatibility_is_preserved(
    default: str,
) -> None:
    source = f"export function read(windowMs = {default}): number {{ return 1; }}"
    result = TypeScriptValidator().collect_implementation_artifacts(source, "sample.ts")
    assert not result.errors
    (argument,) = result.artifacts[0].args
    assert (argument.name, argument.default) == ("windowMs", default)


def test_constructor_property_keeps_its_declared_name() -> None:
    source = "const W = 10; export class Reader { constructor(public windowMs: number = W) {} }"
    result = TypeScriptValidator().collect_implementation_artifacts(source, "sample.ts")
    assert not result.errors
    properties = [a for a in result.artifacts if a.of == "Reader"]
    assert [(a.name, a.type_annotation) for a in properties] == [("windowMs", "number")]


def test_optional_destructured_and_rest_parameters_remain_unchanged() -> None:
    source = "export function read({ value }: Config, optional?: string, ...items: number[]): number { return items.length; }"
    result = TypeScriptValidator().collect_implementation_artifacts(source, "sample.ts")
    assert not result.errors
    assert [(a.name, a.type, a.default) for a in result.artifacts[0].args] == [
        ("{ value }", "Config", None),
        ("optional", "string", None),
        ("items", "number[]", None),
    ]


def _test_context(root: Path) -> None:
    (root / "sample.test.ts").write_text(
        "import test from 'node:test';\nimport assert from 'node:assert/strict';\n"
        "import { read } from './sample.ts';\n"
        "test('read uses identifier default and explicit input', () => {\n"
        "  assert.equal(read(), 10); assert.equal(read(5), 5);\n});\n"
    )
    executed = subprocess.run(
        ["node", "--test", "sample.test.ts"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr


def test_identifier_default_validates_and_snapshot_roundtrips(tmp_path: Path) -> None:
    source = "const W = 10; export function read(windowMs: number = W): number { return windowMs; }"
    (tmp_path / "sample.ts").write_text(source)
    _test_context(tmp_path)
    path = tmp_path / "sample.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Contract TS defaults",
                "type": "fix",
                "created": "2026-10-21T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "sample.ts",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "read",
                                    "args": [
                                        {
                                            "name": "windowMs",
                                            "type": "number",
                                            "default": "W",
                                        }
                                    ],
                                    "returns": "number",
                                }
                            ],
                        }
                    ]
                },
                "validate": [["node", "--test", "sample.test.ts"]],
            }
        )
    )
    engine = ValidationEngine(project_root=tmp_path)
    result = engine.validate(path, mode=ValidationMode.IMPLEMENTATION)
    assert result.success, result.errors
    snapshot = generate_snapshot(tmp_path / "sample.ts", project_root=tmp_path)
    snapshot = replace(
        snapshot,
        files_read=snapshot.files_read + ("sample.test.ts",),
        validate_commands=(("node", "--test", "sample.test.ts"),),
    )
    saved = tmp_path / "snapshot.manifest.yaml"
    save_manifest(snapshot, saved)
    restored = load_manifest(saved)
    spec = next(a for a in restored.files_snapshot[0].artifacts if a.name == "read")
    assert [(a.name, a.type, a.default) for a in spec.args] == [
        ("windowMs", "number", "W")
    ]
    result = engine.validate(saved, mode=ValidationMode.IMPLEMENTATION)
    assert result.success, result.errors


def test_initializer_name_cannot_satisfy_the_parameter_contract(tmp_path: Path) -> None:
    (tmp_path / "sample.ts").write_text(
        "const W = 10; export function read(windowMs: number = W): number { return windowMs; }"
    )
    _test_context(tmp_path)
    path = tmp_path / "sample.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Reject initializer as binding",
                "type": "fix",
                "created": "2026-10-21T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "sample.ts",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "read",
                                    "args": [{"name": "W", "type": "number"}],
                                    "returns": "number",
                                }
                            ],
                        }
                    ]
                },
                "validate": [["node", "--test", "sample.test.ts"]],
            }
        )
    )
    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )
    assert not result.success
    assert result.errors and all(
        error.code.value == "E303" for error in result.errors
    ), result.errors
