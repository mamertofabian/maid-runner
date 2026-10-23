"""Official Deno.test registrations are TypeScript behavioral test declarations."""

from pathlib import Path

import pytest
import yaml

from maid_runner import validate
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ArtifactKind, ValidationMode
from maid_runner.validators.typescript import TypeScriptValidator


_TEST_PATH = "tests/env.test.ts"


def _test_labels(source: str) -> list[str]:
    result = TypeScriptValidator().collect_behavioral_artifacts(source, _TEST_PATH)
    return [
        artifact.name
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.TEST_FUNCTION
    ]


@pytest.mark.parametrize(
    "registration",
    [
        'Deno.test("normalizes env", () => { check(); });',
        'Deno.test("normalizes env", async () => { await check(); });',
        'Deno.test("normalizes env", function () { check(); });',
        "Deno.test('normalizes env', { permissions: { read: true } }, () => { check(); });",
        "Deno.test(`normalizes env`, () => { check(); });",
        'Deno.test.only("normalizes env", () => { check(); });',
        'Deno.test.ignore("normalizes env", () => { check(); });',
    ],
)
def test_module_level_deno_test_label_is_a_test_declaration(registration: str) -> None:
    source = f"declare function check(): void;\n{registration}\n"

    labels = _test_labels(source)

    assert labels == ["normalizes env"]


@pytest.mark.parametrize(
    "source",
    [
        'function register() { Deno.test("normalizes env", () => {}); }\n',
        'Deno.bench("normalizes env", () => {});\n',
        'Deno.test.skip("normalizes env", () => {});\n',
        'Deno.test.only.ignore("normalizes env", () => {});\n',
        'Deno.test.todo("normalizes env", () => {});\n',
        'Deno.test.each([1])("normalizes env", () => {});\n',
        'Deno["bench"]("normalizes env", () => {});\n',
        'Bun.test("normalizes env", () => {});\n',
        'Deno.test(`normalizes ${"env"}`, () => {});\n',
    ],
)
def test_non_registering_or_unknown_deno_calls_are_not_declarations(
    source: str,
) -> None:
    labels = _test_labels(source)

    assert labels == []


def test_deno_test_body_is_the_registered_callback_after_options() -> None:
    source = (
        "declare function check(): void;\n"
        'Deno.test("normalizes env", { sanitizeOps: false }, () => {\n'
        "  check();\n"
        "});\n"
    )

    bodies = TypeScriptValidator().get_test_function_bodies(source, _TEST_PATH)

    assert list(bodies) == ["normalizes env"]
    assert "check();" in bodies["normalizes env"]
    assert "sanitizeOps" not in bodies["normalizes env"]


def test_declared_deno_test_label_passes_behavioral_validation(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src/env.ts").write_text(
        "export function normalizeEnv(value: string): string {\n"
        "  return value.trim().toLowerCase();\n"
        "}\n"
    )
    (tmp_path / _TEST_PATH).write_text(
        'import { normalizeEnv } from "../src/env.ts";\n'
        'Deno.test("normalizes env", () => {\n'
        '  if (normalizeEnv(" Live ") !== "live") throw new Error("wrong");\n'
        "});\n"
    )
    manifest = tmp_path / "manifests/deno-label.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Declare an official Deno.test registration",
                "type": "fix",
                "created": "2026-10-23T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "src/env.ts",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "normalizeEnv",
                                    "args": [{"name": "value", "type": "string"}],
                                    "returns": "string",
                                }
                            ],
                        },
                        {
                            "path": _TEST_PATH,
                            "artifacts": [
                                {"kind": "test_function", "name": "normalizes env"}
                            ],
                        },
                    ]
                },
                "validate": [["deno", "test", _TEST_PATH]],
            },
            sort_keys=False,
        )
    )

    result = validate(
        manifest,
        mode=ValidationMode.BEHAVIORAL,
        use_chain=False,
        manifest_dir=tmp_path / "manifests",
        project_root=tmp_path,
    )

    assert [error.code for error in result.errors] == []
    assert result.success is True


def test_undeclared_deno_test_label_is_still_reported_missing(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / _TEST_PATH).write_text('Deno.test("actual label", () => {});\n')
    manifest = tmp_path / "manifests/deno-label.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Declare a missing Deno.test registration",
                "type": "fix",
                "created": "2026-10-23T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": _TEST_PATH,
                            "artifacts": [
                                {"kind": "test_function", "name": "declared label"}
                            ],
                        }
                    ]
                },
                "validate": [["deno", "test", _TEST_PATH]],
            },
            sort_keys=False,
        )
    )

    result = validate(
        manifest,
        mode=ValidationMode.BEHAVIORAL,
        use_chain=False,
        manifest_dir=tmp_path / "manifests",
        project_root=tmp_path,
    )

    assert ErrorCode.TEST_FUNCTION_MISSING_IN_CODE in [
        error.code for error in result.errors
    ]
