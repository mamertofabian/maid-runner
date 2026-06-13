import pytest

from maid_runner.core.diagnostics_registry import (
    DiagnosticRule,
    RepairRecipe,
    all_rules,
    get_rule,
    render_next_action,
)
from maid_runner.core.result import ErrorCode, Severity


PINNED_RECIPE_CODES = {
    "E114",
    "E115",
    "E200",
    "E201",
    "E210",
    "E230",
    "E300",
    "E301",
    "E302",
    "E303",
}

IMPLEMENTATION_FAILURE_CODES = {"E114", "E115", "E300", "E301", "E302", "E303"}
EMITTED_NON_ERROR_SEVERITIES = {
    ErrorCode.SUPERSEDED_MANIFEST_NOT_FOUND.value: Severity.WARNING.value,
    ErrorCode.MIXED_SEQUENCE_NUMBERING.value: Severity.WARNING.value,
    ErrorCode.NON_MONOTONIC_SEQUENCE_ORDER.value: Severity.WARNING.value,
    ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION.value: Severity.WARNING.value,
    ErrorCode.GRANDFATHERED_SUPERSESSION.value: Severity.INFO.value,
    ErrorCode.MISSING_ASSERTIONS.value: Severity.WARNING.value,
    ErrorCode.IMPRECISE_CREATED_TIMESTAMP.value: Severity.WARNING.value,
    ErrorCode.DUPLICATE_UNSEQUENCED_CREATED.value: Severity.WARNING.value,
    ErrorCode.MISSING_RETURN_TYPE.value: Severity.WARNING.value,
    ErrorCode.VALIDATOR_NOT_AVAILABLE.value: Severity.WARNING.value,
    ErrorCode.STUB_FUNCTION_DETECTED.value: Severity.WARNING.value,
    ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH.value: Severity.WARNING.value,
}
ALLOWED_RECIPE_KINDS = {
    "edit-implementation",
    "edit-tests",
    "edit-manifest",
    "run-command",
    "revise-plan",
    "escalate-human",
}


def test_all_rules_cover_every_error_code_with_rule_metadata() -> None:
    rules = all_rules()
    codes = [rule.code for rule in rules]

    assert codes == sorted(codes)
    assert set(codes) == {code.value for code in ErrorCode}

    for error_code in ErrorCode:
        rule = get_rule(error_code.value)

        assert isinstance(rule, DiagnosticRule)
        assert rule == get_rule(error_code.value)
        assert rule.code == error_code.value
        assert rule.default_severity in {severity.value for severity in Severity}
        assert rule.short_description
        assert rule.description
        assert rule.help_uri.startswith("docs/troubleshooting.md#")


def test_get_rule_unknown_code_fails_loudly() -> None:
    with pytest.raises(KeyError, match="EXXX"):
        get_rule("EXXX")


def test_default_severity_matches_current_non_error_emitters() -> None:
    for code, severity in EMITTED_NON_ERROR_SEVERITIES.items():
        assert get_rule(code).default_severity == severity


def test_type_mismatch_help_uri_does_not_point_to_signature_mismatch() -> None:
    rule = get_rule(ErrorCode.TYPE_MISMATCH.value)

    assert rule.help_uri == "docs/troubleshooting.md#common-issues"
    assert "e303" not in rule.help_uri


def test_pinned_codes_have_structured_repair_recipes() -> None:
    recipes_by_code = {
        rule.code: rule.next_action
        for rule in all_rules()
        if rule.next_action is not None
    }

    assert set(recipes_by_code) == PINNED_RECIPE_CODES

    for code in PINNED_RECIPE_CODES:
        recipe = get_rule(code).next_action

        assert isinstance(recipe, RepairRecipe)
        assert recipe.kind in ALLOWED_RECIPE_KINDS
        assert recipe.kind
        assert recipe.target
        assert recipe.instruction


def test_recipe_templates_render_with_actual_diagnostic_values() -> None:
    values = {
        "artifact": "DiagnosticRule",
        "command": "uv run maid validate manifests/task.manifest.yaml",
        "file": "maid_runner/core/diagnostics_registry.py",
        "manifest": "manifests/task.manifest.yaml",
        "test": "tests/core/test_diagnostics_registry.py",
    }

    for code in PINNED_RECIPE_CODES:
        next_action = render_next_action(code, values)

        assert next_action is not None
        assert next_action["kind"] in ALLOWED_RECIPE_KINDS
        assert "{" not in next_action["target"]
        assert "}" not in next_action["target"]
        assert "{" not in next_action["instruction"]
        assert "}" not in next_action["instruction"]
        assert any(value in next_action["target"] for value in values.values())
        assert any(value in next_action["instruction"] for value in values.values())


def test_codes_without_recipes_render_next_action_as_none() -> None:
    uncovered_codes = [
        code.value for code in ErrorCode if code.value not in PINNED_RECIPE_CODES
    ]

    assert uncovered_codes
    assert render_next_action(uncovered_codes[0], {"file": "manifest.yaml"}) is None


def test_implementation_failure_recipes_do_not_first_edit_tests_or_manifest() -> None:
    for code in IMPLEMENTATION_FAILURE_CODES:
        recipe = get_rule(code).next_action

        assert recipe is not None
        assert recipe.kind not in {"edit-tests", "edit-manifest"}
