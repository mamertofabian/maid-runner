"""Behavioral contract for optional TypeScript semantic return proofs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest

try:
    from maid_runner.core.ts_return_contracts import (
        ReturnContractExpectation,
        ReturnContractItem,
        ReturnContractResult,
        check_return_contracts,
    )
except ModuleNotFoundError as error:
    if error.name != "maid_runner.core.ts_return_contracts":
        raise
    pass


def _api():
    assert (
        "check_return_contracts" in globals()
    ), "Compiler return proof API is not implemented"


@pytest.fixture
def project(tmp_path):
    (tmp_path / "tsconfig.app.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"strict": True, "noEmit": True, "jsx": "preserve"},
                "include": ["*.tsx", "*.ts"],
            }
        )
    )
    (tmp_path / "sample.tsx").write_text('export function sample() { return "stale"; }')
    return tmp_path


def _check(
    project,
    source,
    expected="number",
    *,
    name="sample",
    line=1,
    transport=None,
    config="tsconfig.app.json",
):
    _api()
    expectation = ReturnContractExpectation(
        name=name, line=line, expected_type=expected
    )
    assert (expectation.name, expectation.line, expectation.expected_type) == (
        name,
        line,
        expected,
    )
    result: ReturnContractResult = check_return_contracts(
        project_root=project,
        source_path="sample.tsx",
        config_path=config,
        source=source,
        expectations=(expectation,),
        transport=transport,
    )
    assert isinstance(result, ReturnContractResult)
    assert result.source_sha256 == hashlib.sha256(source.encode()).hexdigest()
    assert len(result.items) == 1
    item: ReturnContractItem = result.items[0]
    assert isinstance(item, ReturnContractItem)
    assert (item.name, item.line) == (name, line)
    assert item.status in {"matched", "mismatched", "unavailable"}
    assert item.inferred_type is None or isinstance(item.inferred_type, str)
    assert isinstance(item.diagnostics, tuple)
    if item.status == "unavailable":
        assert item.diagnostics and all(
            isinstance(message, str) and message for message in item.diagnostics
        )
    else:
        assert result.compiler_version
        assert Path(result.config_path) == project / config
        assert isinstance(result.strict_null_checks, bool)
        assert item.inferred_type
    return result


def _compiler():
    assert shutil.which("node"), "Node is required for real compiler contract tests"


def test_proof_records_expose_exact_typed_fields(project):
    _api()
    item = ReturnContractItem(
        name="sample",
        line=1,
        status="unavailable",
        inferred_type=None,
        diagnostics=("offline",),
    )
    result = ReturnContractResult(
        source_sha256="a" * 64,
        compiler_version=None,
        config_path=None,
        strict_null_checks=None,
        items=(item,),
    )
    assert (
        result.source_sha256,
        result.compiler_version,
        result.config_path,
        result.strict_null_checks,
        result.items,
    ) == ("a" * 64, None, None, None, (item,))
    assert (
        item.name,
        item.line,
        item.status,
        item.inferred_type,
        item.diagnostics,
    ) == ("sample", 1, "unavailable", None, ("offline",))


def test_compiler_matches_semantic_alias_without_changing_disk(project):
    _compiler()
    before = {p.name: p.read_bytes() for p in project.iterdir()}
    source = "export namespace JSX { export interface Element { value: number } }\nexport function sample() { return {value: 3}; }"
    result = _check(project, source, "JSX.Element", line=2)
    assert result.items[0].status == "matched"
    assert result.strict_null_checks is True
    assert {p.name: p.read_bytes() for p in project.iterdir()} == before


@pytest.mark.parametrize(
    "source, expected, status",
    [
        ("export function sample() { return 3; }", "number", "matched"),
        ("export function sample() { return 3; }", "string", "mismatched"),
        ("export function sample() { return 3; }", "number | string", "mismatched"),
        (
            "export function sample() { return Math.random() ? 3 : null; }",
            "number",
            "mismatched",
        ),
        (
            'export function sample() { return JSON.parse("0"); }',
            "number",
            "unavailable",
        ),
        ("export function sample() { return 3 as unknown; }", "number", "unavailable"),
        ("export function sample() { return missing; }", "number", "unavailable"),
        ("export function sample() { return 3; }", "any", "unavailable"),
        ("export function sample() { return 3; }", "unknown", "unavailable"),
        ("export function sample() { return 3; }", "MissingType", "unavailable"),
        (
            "export function sample() { return 3; }",
            'number; console.log("injection")',
            "unavailable",
        ),
        ("export function sample() { return 3; }", "number |", "unavailable"),
        ("export function sample(): number { return 3; }", "number", "unavailable"),
        ("export const sample = () => 3;", "number", "unavailable"),
        (
            "export function sample(): number;\nexport function sample() { return 3; }",
            "number",
            "unavailable",
        ),
    ],
)
def test_real_compiler_distinguishes_match_mismatch_and_unavailable(
    project, source, expected, status
):
    _compiler()
    assert _check(project, source, expected).items[0].status == status


def test_explicit_config_controls_nullability(project):
    config = project / "tsconfig.app.json"
    config.write_text(
        json.dumps({"compilerOptions": {"strict": False}, "include": ["*.tsx"]})
    )
    result = _check(
        project, "export function sample() { return Math.random() ? 3 : null; }"
    )
    assert result.strict_null_checks is False
    assert result.items[0].status == "matched"


@pytest.mark.parametrize(
    "change", ["missing", "excluded", "malformed", "references-only"]
)
def test_unusable_owning_config_is_unavailable(project, change):
    config = project / "tsconfig.app.json"
    if change == "missing":
        config.unlink()
    elif change == "excluded":
        config.write_text('{"files": ["other.ts"]}')
        (project / "other.ts").write_text("export {};")
    elif change == "malformed":
        config.write_text('{"compilerOptions": {"strict": "not a boolean"}}')
    else:
        config.write_text('{"files": [], "references": []}')
    assert (
        _check(project, "export function sample() { return 3; }").items[0].status
        == "unavailable"
    )


def test_wrong_declaration_line_is_unavailable(project):
    assert (
        _check(project, "export function sample() { return 3; }", line=9)
        .items[0]
        .status
        == "unavailable"
    )


def test_dependency_change_is_not_hidden_by_semantic_cache(project):
    dependency = project / "dependency.ts"
    source = 'import {value} from "./dependency";\nexport function sample() { return value; }'
    dependency.write_text("export const value: number = 3;")
    assert _check(project, source, line=2).items[0].status == "matched"
    dependency.write_text('export const value: string = "changed";')
    assert _check(project, source, line=2).items[0].status == "mismatched"


def _reply(request):
    return {
        "ok": True,
        "result": {
            "sourceSha256": request["sourceSha256"],
            "requestSha256": request["requestSha256"],
            "compilerVersion": "5.9.3",
            "configPath": str(Path(request["projectRoot"]) / request["configPath"]),
            "strictNullChecks": True,
            "items": [
                {
                    "name": "sample",
                    "line": 1,
                    "status": "matched",
                    "inferredType": "number",
                    "diagnostics": [],
                }
            ],
        },
    }


def test_transport_receives_source_batch_and_hash(project):
    source = "export function sample() { return 3; }"
    seen = []

    def transport(serialized):
        request = json.loads(serialized)
        seen.append(request)
        return json.dumps(_reply(request))

    assert _check(project, source, transport=transport).items[0].status == "matched"
    assert len(seen) == 1
    assert seen[0] == {
        "command": "checkReturnContracts",
        "projectRoot": str(project),
        "sourcePath": "sample.tsx",
        "configPath": "tsconfig.app.json",
        "source": source,
        "sourceSha256": hashlib.sha256(source.encode()).hexdigest(),
        "requestSha256": hashlib.sha256(
            json.dumps(
                [
                    hashlib.sha256(source.encode()).hexdigest(),
                    os.path.abspath(project / "sample.tsx"),
                    os.path.abspath(project / "tsconfig.app.json"),
                    [["sample", 1, "number"]],
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "expectations": [{"name": "sample", "line": 1, "expectedType": "number"}],
    }


@pytest.mark.parametrize(
    "corruption",
    [
        "hash",
        "identity",
        "line",
        "boolean-line",
        "status",
        "items",
        "version",
        "config",
        "strict",
        "inferred",
        "diagnostics",
        "envelope",
    ],
)
def test_invalid_proof_reply_never_becomes_match(project, corruption):
    def transport(serialized):
        reply = _reply(json.loads(serialized))
        data = reply["result"]
        item = data["items"][0]
        if corruption == "hash":
            data["sourceSha256"] = "0" * 64
        elif corruption == "identity":
            item["name"] = "other"
        elif corruption == "line":
            item["line"] = 9
        elif corruption == "boolean-line":
            item["line"] = True
        elif corruption == "status":
            item["status"] = "success"
        elif corruption == "items":
            data["items"] *= 2
        elif corruption == "version":
            data["compilerVersion"] = None
        elif corruption == "config":
            data["configPath"] = str(project / "wrong.json")
        elif corruption == "strict":
            data["strictNullChecks"] = "true"
        elif corruption == "inferred":
            item["inferredType"] = None
        elif corruption == "diagnostics":
            item["diagnostics"] = ["type error"]
        else:
            reply["ok"] = False
        return json.dumps(reply)

    assert (
        _check(project, "export function sample() { return 3; }", transport=transport)
        .items[0]
        .status
        == "unavailable"
    )


@pytest.mark.parametrize("reply", [None, "", "not JSON", "[]", '{"ok": true}'])
def test_failed_transport_is_explicitly_unavailable(project, reply):
    assert (
        _check(
            project,
            "export function sample() { return 3; }",
            transport=lambda request: reply,
        )
        .items[0]
        .status
        == "unavailable"
    )


def test_source_batch_returns_one_proof_per_declaration(project):
    _api()
    source = 'export function sample() { return 3; }\nexport function second() { return "hello"; }'
    result = check_return_contracts(
        project_root=project,
        source_path="sample.tsx",
        config_path="tsconfig.app.json",
        source=source,
        expectations=(
            ReturnContractExpectation(name="sample", line=1, expected_type="number"),
            ReturnContractExpectation(name="second", line=2, expected_type="string"),
        ),
        transport=None,
    )
    assert [(item.name, item.line, item.status) for item in result.items] == [
        ("sample", 1, "matched"),
        ("second", 2, "matched"),
    ]


def test_missing_node_is_explicitly_unavailable(project, monkeypatch):
    monkeypatch.setenv("PATH", str(project / "no-executables"))
    assert (
        _check(project, "export function sample() { return 3; }").items[0].status
        == "unavailable"
    )


def test_compiler_proof_does_not_run_inherited_node_preload(project, monkeypatch):
    marker = project / "executed.txt"
    preload = project / "preload.cjs"
    preload.write_text(
        'require("fs").writeFileSync(' + json.dumps(str(marker)) + ', "executed");'
    )
    monkeypatch.setenv("NODE_OPTIONS", "--require=" + str(preload))
    assert (
        _check(project, "export function sample() { return 3; }").items[0].status
        == "matched"
    )
    assert not marker.exists()


def test_session_bridge_supports_return_proof_requests(project):
    import subprocess

    _compiler()
    bridge = (
        Path(__file__).resolve().parents[2]
        / "maid_runner/core/ts_compiler_resolver.cjs"
    )
    source = "export function sample() { return 3; }"
    request = {
        "command": "checkReturnContracts",
        "projectRoot": str(project),
        "sourcePath": "sample.tsx",
        "configPath": "tsconfig.app.json",
        "source": source,
        "sourceSha256": hashlib.sha256(source.encode()).hexdigest(),
        "expectations": [{"name": "sample", "line": 1, "expectedType": "number"}],
    }
    completed = subprocess.run(
        [shutil.which("node"), str(bridge), "--session"],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    )
    reply = json.loads(completed.stdout)
    assert reply["ok"] is True
    assert isinstance(
        reply["result"], dict
    ), "Session bridge does not support compiler return proofs"
    assert reply["result"]["items"][0]["status"] == "matched"


def test_generated_aliases_do_not_trigger_unused_local_errors(project):
    config = project / "tsconfig.app.json"
    config.write_text(
        json.dumps(
            {
                "compilerOptions": {"strict": True, "noUnusedLocals": True},
                "include": ["*.tsx"],
            }
        )
    )
    assert (
        _check(project, "export function sample() { return 3; }").items[0].status
        == "matched"
    )


@pytest.mark.parametrize(
    "exception", [TimeoutError("timed out"), OSError("bridge failed")]
)
def test_transport_io_failure_is_unavailable(project, exception):
    def transport(serialized):
        raise exception

    assert (
        _check(project, "export function sample() { return 3; }", transport=transport)
        .items[0]
        .status
        == "unavailable"
    )


@pytest.mark.parametrize(
    "suppression",
    ["config", "source", "expected-directive", "trailing-directive", "no-default-lib"],
)
def test_disabled_semantic_checking_cannot_establish_proof(project, suppression):
    source = "export function sample() { const x: string = 123; return 3; }"
    line = 1
    expected = "number"
    if suppression == "config":
        (project / "tsconfig.app.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {"strict": True, "noCheck": True},
                    "include": ["*.tsx"],
                }
            )
        )
    elif suppression == "no-default-lib":
        (project / "tsconfig.app.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {"strict": True, "skipDefaultLibCheck": True},
                    "include": ["*.tsx"],
                }
            )
        )
        source = '/// <reference no-default-lib="true"/>\n' + source
        line = 2
    elif suppression == "source":
        source = "// @ts-nocheck\n" + source
        line = 2
    else:
        source = "export function sample() { return {v: 3}; }"
        if suppression == "expected-directive":
            expected = "{\n// @ts-ignore\nv: MissingType\n}"
        else:
            source += "\n// @ts-ignore"
            expected = "{v: MissingType}"
    assert _check(project, source, expected, line=line).items[0].status == "unavailable"


@pytest.mark.parametrize("changed", ["expectation", "source-path"])
def test_stale_reply_for_different_request_is_unavailable(project, changed):
    _api()
    source = "export function sample() { return 3; }"
    replies = []

    def first_transport(serialized):
        reply = json.dumps(_reply(json.loads(serialized)))
        replies.append(reply)
        return reply

    assert (
        _check(project, source, transport=first_transport).items[0].status == "matched"
    )
    result = check_return_contracts(
        project_root=project,
        source_path="other.tsx" if changed == "source-path" else "sample.tsx",
        config_path="tsconfig.app.json",
        source=source,
        expectations=(
            ReturnContractExpectation(
                name="sample",
                line=1,
                expected_type="string" if changed == "expectation" else "number",
            ),
        ),
        transport=lambda serialized: replies[0],
    )
    assert result.items[0].status == "unavailable"
    assert result.items[0].diagnostics


def test_declaration_files_cannot_hide_ambient_errors(project):
    _api()
    source = "export function sample() { return 3; }"
    (project / "sample.d.ts").write_text(source)
    (project / "tsconfig.app.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"strict": True, "skipLibCheck": True},
                "include": ["*.ts"],
            }
        )
    )
    result = check_return_contracts(
        project_root=project,
        source_path="sample.d.ts",
        config_path="tsconfig.app.json",
        source=source,
        expectations=(
            ReturnContractExpectation(name="sample", line=1, expected_type="number"),
        ),
        transport=None,
    )
    assert result.items[0].status == "unavailable"
    assert result.items[0].diagnostics
