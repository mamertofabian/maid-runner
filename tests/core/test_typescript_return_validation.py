"""Behavioral contract for opt-in semantic TypeScript return validation."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest
import yaml

from maid_runner.core._implementation_validation import (
    ImplementationFileValidator,
    compare_artifacts,
)
from maid_runner.core.config import MaidConfig, load_config

try:
    from maid_runner.core.config import TypeScriptReturnContractsConfig
except ImportError:
    pass
from maid_runner.core.diagnostics_registry import get_rule
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, Severity
from maid_runner.core.snapshot import generate_snapshot
from maid_runner.core.ts_return_contracts import (
    ReturnContractItem,
    ReturnContractResult,
)
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.registry import ValidatorRegistry


def _config_api():
    assert (
        "TypeScriptReturnContractsConfig" in globals()
    ), "TypeScript return configuration is not implemented"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"strict": True, "jsx": "preserve", "noEmit": True},
                "include": ["sample.tsx"],
            }
        )
    )
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/sample.test.ts").write_text(
        'import assert from "node:assert/strict";\nimport test from "node:test";\nimport {sample, second, Widget} from "../sample";\ntest("sample", () => { assert.ok(sample); assert.ok(second); assert.ok(Widget); });'
    )
    return tmp_path


def _write(
    project, source, artifacts=None, *, mode="compiler", config="tsconfig.app.json"
):
    (project / "sample.tsx").write_text(source)
    if mode is not None:
        (project / ".maidrc.yaml").write_text(
            yaml.safe_dump(
                {"typescript_return_contracts": {"mode": mode, "tsconfig": config}}
            )
        )
    elif (project / ".maidrc.yaml").exists():
        (project / ".maidrc.yaml").unlink()
    manifest = {
        "schema": "2",
        "goal": "Return contract fixture",
        "type": "feature",
        "created": "2026-09-30",
        "files": {
            "edit": [
                {
                    "path": "sample.tsx",
                    "artifacts": artifacts
                    or [
                        {
                            "kind": "function",
                            "name": "sample",
                            "args": [],
                            "returns": "number",
                        }
                    ],
                }
            ],
            "read": ["tests/sample.test.ts"],
        },
        "validate": ["node --test tests/sample.test.ts"],
    }
    path = project / "manifests/return-contract.manifest.yaml"
    path.write_text(yaml.safe_dump(manifest))
    return path


def _file_errors(project, manifest_path, *, checker=None):
    manifest = load_manifest(manifest_path)
    registry = ValidatorRegistry.with_builtin_validators()
    arguments = {} if checker is None else {"return_contract_checker": checker}
    validator = ImplementationFileValidator(project, registry, **arguments)
    return validator.validate_file_spec(
        manifest.file_spec_for("sample.tsx"), manifest, None
    )


def test_return_configuration_defaults_and_explicit_compiler_mode(project):
    _config_api()
    defaults = TypeScriptReturnContractsConfig()
    assert defaults.mode == "syntax" and defaults.tsconfig is None
    assert MaidConfig().typescript_return_contracts == defaults
    assert load_config(project).typescript_return_contracts == defaults
    _write(project, "export function sample() { return 3; }")
    configured = load_config(project).typescript_return_contracts
    assert isinstance(configured, TypeScriptReturnContractsConfig)
    assert configured.mode == "compiler" and configured.tsconfig == "tsconfig.app.json"


@pytest.mark.parametrize(
    "section",
    [
        "compiler",
        [],
        {"mode": "invented"},
        {"mode": "compiler"},
        {"mode": "compiler", "tsconfig": ""},
        {"mode": "compiler", "tsconfig": True},
        {"mode": "compiler", "tsconfig": "tsconfig.app.json", "typo": True},
        {"mode": True},
    ],
)
def test_invalid_return_configuration_fails_loudly(project, section):
    (project / ".maidrc.yaml").write_text(
        yaml.safe_dump({"typescript_return_contracts": section})
    )
    with pytest.raises(ValueError, match="typescript_return_contracts"):
        load_config(project)


@pytest.mark.parametrize("mode", [None, "syntax"])
def test_syntax_mode_preserves_missing_return_warning_without_node(
    project, monkeypatch, mode
):
    path = _write(project, "export function sample() { return 3; }", mode=mode)
    monkeypatch.setenv("PATH", str(project / "no-node"))
    errors = _file_errors(project, path)
    assert [(error.code.value, error.severity) for error in errors] == [
        ("E304", Severity.WARNING)
    ]


@pytest.mark.parametrize(
    "returns, code",
    [
        ("number", None),
        ("string", "E302"),
        ("number | string", "E302"),
        ("MissingType", "E309"),
    ],
)
def test_compiler_mode_classifies_return_contract_through_file_validator(
    project, returns, code
):
    path = _write(
        project,
        "export function sample() { return 3; }",
        [{"kind": "function", "name": "sample", "args": [], "returns": returns}],
    )
    errors = _file_errors(project, path)
    assert [error.code.value for error in errors] == ([] if code is None else [code])
    if code:
        assert errors[0].severity is Severity.ERROR
        assert errors[0].location.file == "sample.tsx" and errors[0].location.line == 1
        assert "sample" in errors[0].message


@pytest.mark.parametrize(
    "source",
    [
        'export function sample() { return JSON.parse("0"); }',
        "export function sample() { return missing; }",
        "// @ts-nocheck\nexport function sample() { return 3; }",
        "export const sample = () => 3;",
        "export function sample(): number;\nexport function sample() { return 3; }",
    ],
)
def test_unsafe_or_unsupported_return_proofs_are_blocking(project, source):
    path = _write(project, source)
    errors = _file_errors(project, path)
    assert any(
        error.code.value == "E309" and error.severity is Severity.ERROR
        for error in errors
    )
    assert not any(error.code.value == "E304" for error in errors)


@pytest.mark.parametrize("infrastructure", ["node", "config"])
def test_missing_compiler_infrastructure_never_falls_back_to_syntax(
    project, monkeypatch, infrastructure
):
    path = _write(project, "export function sample() { return 3; }")
    if infrastructure == "node":
        monkeypatch.setenv("PATH", str(project / "no-node"))
    else:
        (project / "tsconfig.app.json").unlink()
    errors = _file_errors(project, path)
    assert [error.code.value for error in errors] == ["E309"]
    assert errors[0].severity is Severity.ERROR and errors[0].message


def test_annotated_returns_keep_syntax_comparison_without_compiler(
    project, monkeypatch
):
    path = _write(
        project,
        "export function sample(): number { return 3; }",
        [{"kind": "function", "name": "sample", "args": [], "returns": "string"}],
    )
    monkeypatch.setenv("PATH", str(project / "no-node"))
    errors = _file_errors(project, path)
    assert [error.code.value for error in errors] == ["E302"]
    assert "number" in errors[0].message


@pytest.mark.parametrize("parameter, codes", [("{ value }", []), ("props", ["E303"])])
def test_compiler_return_proof_preserves_exact_binding_pattern_contracts(
    project, parameter, codes
):
    source = "interface Props { value: number }\nexport function sample({ value }: Props) { return value; }"
    path = _write(
        project,
        source,
        [
            {
                "kind": "function",
                "name": "sample",
                "args": [{"name": parameter, "type": "Props"}],
                "returns": "number",
            }
        ],
    )
    assert [error.code.value for error in _file_errors(project, path)] == codes


def test_matched_proof_does_not_suppress_parameter_annotation_warnings(project):
    source = "export function sample(value = 3) { return value; }"
    path = _write(
        project,
        source,
        [
            {
                "kind": "function",
                "name": "sample",
                "args": [{"name": "value", "type": "number"}],
                "returns": "number",
            }
        ],
    )
    errors = _file_errors(project, path)
    assert len(errors) == 1 and errors[0].code is ErrorCode.MISSING_RETURN_TYPE
    assert "parameter 'value'" in errors[0].message


def test_compiler_validation_keeps_raw_collection_snapshots_and_pure_comparison(
    project,
):
    source = "export function sample() { return 3; }"
    path = _write(project, source)
    registry = ValidatorRegistry.with_builtin_validators()
    before = registry.get("sample.tsx").collect_implementation_artifacts(
        source, "sample.tsx"
    )
    assert _file_errors(project, path) == []
    after = registry.get("sample.tsx").collect_implementation_artifacts(
        source, "sample.tsx"
    )
    assert before.artifacts == after.artifacts
    assert (
        next(
            artifact for artifact in after.artifacts if artifact.name == "sample"
        ).returns
        is None
    )
    snapshot = generate_snapshot(project / "sample.tsx", project_root=project)
    assert snapshot.all_file_specs[0].artifacts[0].returns is None
    manifest = load_manifest(path)
    assert [
        error.code.value
        for error in compare_artifacts(
            list(manifest.file_spec_for("sample.tsx").artifacts),
            list(after.artifacts),
            "sample.tsx",
            False,
        )
    ] == ["E304"]
    assert (project / "sample.tsx").read_text() == source


def test_one_batch_checks_all_requested_unannotated_returns(project):
    source = 'export function sample() { return 3; }\nexport function second() { return "text"; }'
    path = _write(
        project,
        source,
        [
            {"kind": "function", "name": "sample", "args": [], "returns": "number"},
            {"kind": "function", "name": "second", "args": [], "returns": "string"},
        ],
    )
    calls = []

    def checker(project_root, source_path, config_path, actual_source, expectations):
        calls.append(
            (project_root, source_path, config_path, actual_source, expectations)
        )
        return ReturnContractResult(
            hashlib.sha256(actual_source.encode()).hexdigest(),
            "5.9.3",
            str(project_root / config_path),
            True,
            tuple(
                ReturnContractItem(
                    item.name, item.line, "matched", item.expected_type, ()
                )
                for item in expectations
            ),
        )

    assert _file_errors(project, path, checker=checker) == []
    assert len(calls) == 1
    root, relative, config, supplied, expectations = calls[0]
    assert (root, relative, config, supplied) == (
        project,
        "sample.tsx",
        "tsconfig.app.json",
        source,
    )
    assert [(item.name, item.line, item.expected_type) for item in expectations] == [
        ("sample", 1, "number"),
        ("second", 2, "string"),
    ]


def test_e309_is_registered_as_a_blocking_diagnostic():
    assert hasattr(
        ErrorCode, "COMPILER_RETURN_CONTRACT_UNAVAILABLE"
    ), "Compiler proof diagnostic is not registered"
    assert ErrorCode.COMPILER_RETURN_CONTRACT_UNAVAILABLE.value == "E309"
    rule = get_rule("E309")
    assert rule.default_severity == "error"
    assert (
        "compiler" in rule.short_description.lower()
        and "return" in rule.description.lower()
    )
    assert rule.help_uri.startswith("docs/troubleshooting.md#")


def test_public_engine_routes_opt_in_proofs_and_strict_warning_policy(project):
    path = _write(project, "export function sample() { return 3; }")
    result = ValidationEngine(project).validate(
        path, use_chain=False, fail_on_warnings=True, include_plugin_diagnostics=False
    )
    assert result.success and result.errors == [] and result.warnings == []


@pytest.mark.parametrize("output", ["text", "json", "packet"])
def test_cli_surfaces_compiler_unavailability_consistently(project, output):
    path = _write(
        project, "export function sample() { return 3; }", config="missing.json"
    )
    arguments = [
        sys.executable,
        "-c",
        "from maid_runner.cli.commands._main import main; raise SystemExit(main())",
        "validate",
        str(path),
        "--mode",
        "implementation",
        "--no-chain",
    ]
    packet = project / "failure.json"
    if output == "json":
        arguments.append("--json")
    if output == "packet":
        arguments.extend(["--packet", str(packet)])
    completed = subprocess.run(
        arguments, cwd=project, text=True, capture_output=True, timeout=15
    )
    assert completed.returncode == 1, completed.stdout + completed.stderr
    if output == "json":
        payload = json.loads(completed.stdout)
        assert any(
            item["code"] == "E309" and item["severity"] == "error"
            for item in payload["errors"]
        )
    elif output == "packet":
        payload = json.loads(packet.read_text())
        assert any(item["code"] == "E309" for item in payload["diagnostics"])
    else:
        assert "E309" in completed.stdout + completed.stderr


def test_requested_method_return_is_explicitly_unsupported(project):
    path = _write(
        project,
        "export class Widget { sample() { return 3; } }",
        [
            {
                "kind": "method",
                "name": "sample",
                "of": "Widget",
                "args": [],
                "returns": "number",
            }
        ],
    )
    assert [error.code.value for error in _file_errors(project, path)] == ["E309"]


def test_contract_without_return_expectation_does_not_invoke_compiler(project):
    path = _write(
        project,
        "export function sample() { return 3; }",
        [{"kind": "function", "name": "sample", "args": []}],
    )

    def checker(*arguments):
        raise AssertionError("No return expectation requires no compiler proof")

    assert _file_errors(project, path, checker=checker) == []


@pytest.mark.parametrize("strict, code", [(True, "E302"), (False, None)])
def test_validation_uses_project_nullability_semantics(project, strict, code):
    (project / "tsconfig.app.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"strict": strict, "jsx": "preserve"},
                "include": ["sample.tsx"],
            }
        )
    )
    path = _write(
        project, "export function sample() { return Math.random() ? 3 : null; }"
    )
    assert [error.code.value for error in _file_errors(project, path)] == (
        [] if code is None else [code]
    )


@pytest.mark.parametrize(
    "mode, config",
    [
        ("compiler", None),
        ("compiler", ""),
        ("invalid", "tsconfig.app.json"),
        ("syntax", True),
    ],
)
def test_return_configuration_constructor_rejects_invalid_settings(mode, config):
    _config_api()
    with pytest.raises(ValueError, match="typescript_return_contracts"):
        TypeScriptReturnContractsConfig(mode=mode, tsconfig=config)


@pytest.mark.parametrize("mode", ["schema", "behavioral"])
def test_nonimplementation_modes_do_not_require_return_compiler(project, mode):
    from maid_runner.core.types import ValidationMode

    path = _write(
        project, "export function sample() { return 3; }", config="missing.json"
    )
    result = ValidationEngine(project).validate(
        path,
        use_chain=False,
        mode=ValidationMode(mode),
        include_plugin_diagnostics=False,
    )
    assert result.success
    assert not any(
        error.code.value == "E309" for error in result.errors + result.warnings
    )
