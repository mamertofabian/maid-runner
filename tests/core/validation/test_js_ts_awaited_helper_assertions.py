"""Behavioral regressions for assertions inside awaited local JS/TS helpers."""

import sys

import pytest

from maid_runner.core._test_assertions import check_test_assertions
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


@pytest.mark.parametrize("extension", ["js", "jsx", "ts", "tsx"])
@pytest.mark.parametrize("declaration_scope", ["module", "suite"])
def test_awaited_local_helpers_with_direct_expect_are_recognized(
    extension, declaration_scope
):
    helper = "async function verify(value) { expect(value).toBe(4); }\n"
    suite_helper = helper if declaration_scope == "suite" else ""
    module_helper = helper if declaration_scope == "module" else ""
    source = (
        "// 🧪 Unicode before helper and callback\n"
        + module_helper
        + "describe('outer', () => {\n"
        + suite_helper
        + "describe('inner', () => {\n"
        + "it('checks behavior', async () => { await verify(4); });\n"
        + "});\n});\n"
    )

    errors = check_test_assertions(source, f"tests/example.test.{extension}")

    assert errors == []


@pytest.mark.parametrize(
    "helper,body",
    [
        ("async function verify() { doWork(); }", "await verify();"),
        ("async function verify() { expect(1).toBe(1); }", "verify();"),
        ("async function verify() { expect(1).toBe(1); }", "await verify?.();"),
        ("async function verify() { expect(1).toBe(1); }", "await other();"),
        ("async function verify() { /* expect(1).toBe(1) */ }", "await verify();"),
        (
            "async function verify() { const s = 'expect(1).toBe(1)'; }",
            "await verify();",
        ),
        (
            "async function verify() { function unused() { expect(1).toBe(1); } }",
            "await verify();",
        ),
        ("async function verify() { expect(1); }", "await verify();"),
        ("async function verify() { expect(1).toBe; }", "await verify();"),
        (
            "async function verify() { expect(1).toBe(1); }",
            "const later = async () => { await verify(); };",
        ),
        (
            "async function verify() { expect(1).toBe(1); }",
            "if (false) { await verify(); }",
        ),
    ],
)
def test_nonasserting_or_indirect_helpers_keep_e210(helper, body):
    source = f"{helper}\nit('missing', async () => {{ {body} }});\n"

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert errors[0].location.line == 2
    assert "missing" in errors[0].message


@pytest.mark.parametrize(
    "source",
    [
        "describe('a', () => { async function verify() { expect(1).toBe(1); } });\n"
        "describe('b', () => { it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', (verify) => { it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "it('missing', async () => { const verify = other; await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "it('missing', async () => { verify = other; await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "beforeEach(() => { verify = other; });\n"
        "it('missing', async () => { await verify(); });",
        "describe('a', () => { async function verify() { expect(1).toBe(1); }\n"
        "beforeEach(() => { verify = other; });\n"
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "it('missing', async () => { for (verify of [other]) {} await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "beforeEach(() => { for (verify in other) {} });\n"
        "it('missing', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "globalThis.verify = other; it('missing', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "globalThis['verify'] = other; it('missing', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "delete globalThis.verify; it('missing', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('other', () => { beforeEach(() => { verify = fake; }); });\n"
        "it('missing', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('suite', () => { if (true) { var verify = fake; } "
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', () => { async function verify() { doWork(); } "
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', () => { function* verify() { yield 1; } "
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', () => { enum verify { x = 1 } "
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', () => { class verify {} "
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', () => { abstract class verify {} "
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', function verify() { "
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', () => { function v\\u0065rify() {} "
        "it('missing', async () => { await verify(); }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "describe('a', () => { let {v\\u0065rify} = {verify: fake}; "
        "it('missing', async () => { await verify(); }); });",
    ],
)
def test_lexical_scope_and_shadowing_keep_e210(source):
    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert "missing" in errors[0].message


def test_duplicate_labels_and_unicode_keep_precise_diagnostics():
    source = (
        "// 🧪\n"
        "async function verify() { expect(1).toBe(1); }\n"
        "it('same', async () => { await verify(); });\n"
        "it('same', async () => { await other(); });\n"
    )

    errors = check_test_assertions(source, "tests/🧪.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert errors[0].location.file == "tests/🧪.test.ts"
    assert errors[0].location.line == 4


def test_missing_parser_retains_legacy_warning_and_e210(monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter", None)
    monkeypatch.setitem(sys.modules, "tree_sitter_typescript", None)
    source = (
        "async function verify() { expect(1).toBe(1); }\n"
        "it('helper', async () => { await verify(); });\n"
        "it('direct', () => { expect(1).toBe(1); });\n"
    )

    with pytest.warns(RuntimeWarning, match="legacy.*scanner"):
        errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert errors[0].location.line == 2


@pytest.mark.parametrize(
    "helper",
    [
        "async function verify() { expect(1).toString(); }",
        "async function verify() { expect(1).toUnknownMatcher(); }",
        "async function verify() { expect(1).unknown.toBe(1); }",
        "async function verify() { expect(1).toSatisfy?.(() => false); }",
        "async function verify() { expect?.(1).toBe(1); }",
        "async function verify() { expect(1)?.toBe(1); }",
        "async function verify() { expect(1).not?.toBe(1); }",
        "async function verify() { expect(/* no subject */).toBe(1); }",
        "async function verify(expect) { expect(1).toBe(1); }",
        "async function verify() { const expect = fake; expect(1).toBe(1); }",
        "const expect = fake; async function verify() { expect(1).toBe(1); }",
        "namespace expect { export const value = 1; } "
        "async function verify() { expect(1).toBe(1); }",
        "class expect {} async function verify() { expect(1).toBe(1); }",
        "abstract class expect {} async function verify() { expect(1).toBe(1); }",
        "import expect = fake.expect; "
        "async function verify() { expect(1).toBe(1); }",
        "globalThis.expect = fake; async function verify() { expect(1).toBe(1); }",
        "globalThis.ex\\u0070ect = fake; async function verify() { expect(1).toBe(1); }",
        "(globalThis).expect = fake; async function verify() { expect(1).toBe(1); }",
        "(globalThis as any).expect = fake; async function verify() { expect(1).toBe(1); }",
        "(globalThis as any)[key] = fake; async function verify() { expect(1).toBe(1); }",
        "(<any>globalThis).expect = fake; async function verify() { expect(1).toBe(1); }",
        "globalThis!.expect = fake; async function verify() { expect(1).toBe(1); }",
        "globalThis['expect'] = fake; async function verify() { expect(1).toBe(1); }",
        "window[key] = fake; async function verify() { expect(1).toBe(1); }",
        "global.expect++; async function verify() { expect(1).toBe(1); }",
        "delete globalThis.expect; async function verify() { expect(1).toBe(1); }",
        "import { fake as expect } from 'unknown'; "
        "async function verify() { expect(1).toBe(1); }",
    ],
)
def test_non_matchers_and_shadowed_expect_keep_e210(helper):
    source = f"{helper}\nit('missing', async () => {{ await verify(); }});\n"

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS


def test_suite_parameter_shadowing_expect_keeps_e210():
    source = (
        "describe('suite', (expect) => {\n"
        "async function verify() { expect(1).toBe(1); }\n"
        "it('missing', async () => { await verify(); });\n"
        "});\n"
    )

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS


def test_top_level_block_var_shadowing_does_not_reuse_program_scope():
    source = (
        "{ var expect = () => ({ toBe() {} }); "
        "describe('suite', () => { async function verify() { expect(1).toBe(1); } "
        "it('missing', async () => { await verify(); }); }); }"
    )

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS


@pytest.mark.parametrize(
    "source",
    [
        "describe('first', () => { async function verify() { expect(1).toBe(1); } "
        "it('valid', async () => { await verify(); }); });\n"
        "describe('second', () => { let verify; beforeEach(() => { verify = fake; }); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "{ const verify = 5; } it('valid', async () => { await verify(); });",
        "async function verify() { { const expect = fake; } expect(1).toBe(1); }\n"
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "const obj = {}; obj[verify] = 1; it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "const obj = {}; obj[expect] = 1; it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "const cache = {}; cache[globalThis[key]] = 1; "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "globalThis.verify.extra = true; it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "for (let verify = 0; verify < 1; verify++) {} "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "switch (x) { case 1: let verify = 2; break; } "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "const unrelated = function* () { var verify; }; "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "const unrelated = class { static { var verify; } }; "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "const unrelated = function* () { var expect; }; "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "function local(window, key, value) { window[key] = value; } "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "function local() { const globalThis = {}; globalThis.verify = fake; } "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "{ const globalThis = {}; globalThis[key] = fake; } "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "const unrelated = class verify { update() { verify = fake; } }; "
        "it('valid', async () => { await verify(); });",
        "async function verify() { expect(1).toBe(1); }\n"
        "const unrelated = class expect { update() { expect = fake; } }; "
        "it('valid', async () => { await verify(); });",
    ],
)
def test_unrelated_scopes_and_property_reads_do_not_hide_helper(source):
    assert check_test_assertions(source, "tests/example.test.ts") == []


@pytest.mark.parametrize(
    "call",
    [
        "await verify();",
        "await /* comment */ verify();",
        "await (verify());",
        "return await verify();",
        "return /* comment */ await verify();",
        "return (await verify());",
        "const value = await verify();",
    ],
)
@pytest.mark.parametrize(
    "matcher",
    [
        "expect(1).toBe(1);",
        "return expect(1).toBe(1);",
        "return /* comment */ expect(1).toBe(1);",
        "return (expect(1).toBe(1));",
        "await expect(Promise.resolve(1)).resolves.toBe(1);",
        "await expect(data).toMatchFileSnapshot('data.txt');",
        "expect(metric).toBeFasterThan(other);",
        "expect(metric).toBeSlowerThan(other);",
        "expect(spy).toHaveBeenExhausted();",
    ],
)
def test_awaited_calls_and_matchers_in_direct_statement_forms_count(call, matcher):
    source = f"async function verify() {{ {matcher} }}\nit('valid', async () => {{ {call} }});\n"

    assert check_test_assertions(source, "tests/example.test.ts") == []


@pytest.mark.parametrize(
    "suite",
    [
        "describe",
        "describe.only",
        "describe.each([1])",
        "describe.for([1])",
        "describe.runIf(true)",
        "describe.skipIf(false)",
        "describe.skipIf(false).concurrent",
    ],
)
def test_exported_helpers_work_through_suite_modifiers(suite):
    source = (
        "export async function verify() { expect(1).toBe(1); }\n"
        f"{suite}('suite', () => {{ it('valid', async () => {{ await verify(); }}); }});\n"
    )

    assert check_test_assertions(source, "tests/example.test.ts") == []


@pytest.mark.parametrize(
    "registration",
    [
        "const registered = it('valid', async () => { await verify(); });",
        "const registered = describe('suite', () => { it('valid', async () => { await verify(); }); });",
        "export const registered = describe('suite', () => { it('valid', async () => { await verify(); }); });",
        "{ it('valid', async () => { await verify(); }); }",
        "if (true) { it('valid', async () => { await verify(); }); }",
        "describe('suite', () => { { it('valid', async () => { await verify(); }); } });",
    ],
)
def test_assigned_test_and_suite_registrations_remain_supported(registration):
    source = "async function verify() { expect(1).toBe(1); }\n" + registration

    assert check_test_assertions(source, "tests/example.test.ts") == []


def test_many_tests_share_local_helper_without_losing_individual_results():
    source = "async function verify() { expect(1).toBe(1); }\n" + "".join(
        f"it('case {index}', async () => {{ await verify(); }});\n"
        for index in range(300)
    )
    source += "it('missing', async () => { await other(); });\n"

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert errors[0].location.line == 302


def test_many_scoped_helpers_do_not_cross_contaminate():
    source = "".join(
        f"describe('suite {index}', () => {{ "
        "async function verify() { expect(1).toBe(1); } "
        "function unrelated(verify) { verify = other; } "
        "it('valid', async () => { await verify(); }); });\n"
        for index in range(200)
    )

    assert check_test_assertions(source, "tests/example.test.ts") == []


def test_behavioral_validation_accepts_awaited_helper_assertion(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "double.ts").write_text(
        "export function double(value: number): number { return value * 2; }\n"
    )
    (tmp_path / "src" / "double.test.ts").write_text(
        "import { describe, expect, it } from 'vitest';\n"
        "import { double } from './double';\n"
        "describe('double', () => {\n"
        "async function verify() { expect(double(2)).toBe(4); }\n"
        "it('doubles a number', async () => { await verify(); });\n"
        "});\n"
    )
    manifest = tmp_path / "repro.manifest.yaml"
    manifest.write_text(
        'schema: "2"\ngoal: Verify double\ntype: fix\nfiles:\n  edit:\n'
        "  - path: src/double.ts\n    artifacts:\n    - kind: function\n"
        "      name: double\n      args:\n      - name: value\n"
        "        type: number\n      returns: number\n"
        "validate:\n- npx vitest run src/double.test.ts\n"
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest, mode=ValidationMode.BEHAVIORAL, check_assertions=True
    )

    assert result.success is True
    assert ErrorCode.MISSING_ASSERTIONS not in {
        warning.code for warning in result.warnings
    }
