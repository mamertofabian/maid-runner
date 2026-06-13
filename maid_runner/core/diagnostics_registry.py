"""Introspectable diagnostic metadata and repair recipes."""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter

from maid_runner.core.result import ErrorCode, Severity


@dataclass(frozen=True)
class RepairRecipe:
    kind: str
    target: str
    instruction: str


@dataclass(frozen=True)
class DiagnosticRule:
    code: str
    default_severity: str
    short_description: str
    description: str
    help_uri: str
    next_action: RepairRecipe | None = None


def get_rule(code: str) -> DiagnosticRule:
    normalized = _normalize_code(code)
    try:
        return _RULES_BY_CODE[normalized]
    except KeyError as exc:
        raise KeyError(f"Unknown diagnostic code: {normalized}") from exc


def all_rules() -> "tuple[DiagnosticRule, ...]":
    return _ALL_RULES


def render_next_action(code: str, values: dict[str, str]) -> "dict | None":
    recipe = get_rule(code).next_action
    if recipe is None:
        return None
    return {
        "kind": recipe.kind,
        "target": _render_template(recipe.target, values),
        "instruction": _render_template(recipe.instruction, values),
    }


_WARNING_CODES = frozenset(
    {
        ErrorCode.SUPERSEDED_MANIFEST_NOT_FOUND.value,
        ErrorCode.MIXED_SEQUENCE_NUMBERING.value,
        ErrorCode.NON_MONOTONIC_SEQUENCE_ORDER.value,
        ErrorCode.ARTIFACT_DROPPED_BY_SUPERSESSION.value,
        ErrorCode.MISSING_ASSERTIONS.value,
        ErrorCode.IMPRECISE_CREATED_TIMESTAMP.value,
        ErrorCode.DUPLICATE_UNSEQUENCED_CREATED.value,
        ErrorCode.MISSING_RETURN_TYPE.value,
        ErrorCode.VALIDATOR_NOT_AVAILABLE.value,
        ErrorCode.STUB_FUNCTION_DETECTED.value,
        ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH.value,
    }
)

_INFO_CODES = frozenset({ErrorCode.GRANDFATHERED_SUPERSESSION.value})

_HELP_ANCHORS = {
    ErrorCode.FILE_NOT_FOUND.value: "1-manifest-file-is-missing-e001",
    ErrorCode.MANIFEST_PARSE_ERROR.value: "2-manifest-cannot-be-parsed-e003",
    ErrorCode.SCHEMA_VALIDATION_ERROR.value: "3-manifest-schema-validation-fails-e004",
    ErrorCode.SUPERSEDED_MANIFEST_NOT_FOUND.value: (
        "4-a-superseded-manifest-is-missing-e102"
    ),
    ErrorCode.CIRCULAR_SUPERSESSION.value: "5-manifest-supersession-is-circular-e103",
    ErrorCode.EMPTY_MANIFEST_SET.value: "6-no-active-manifests-are-found-e112",
    ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT.value: (
        "7-a-manifest-path-escapes-the-project-e113"
    ),
    ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE.value: "8-worktree-scope-fails-e114",
    ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED.value: (
        "9-changed-scope-baseline-is-required-e115"
    ),
    ErrorCode.CHANGED_SCOPE_BASELINE_INVALID.value: (
        "10-changed-scope-baseline-is-invalid-e116"
    ),
    ErrorCode.ACTIVE_MANIFEST_INACTIVE_STATUS.value: (
        "11-active-manifest-is-marked-inactive-e117"
    ),
    ErrorCode.ARTIFACT_NOT_USED_IN_TESTS.value: (
        "12-artifact-is-not-used-by-behavioral-tests-e200"
    ),
    ErrorCode.TEST_FILE_NOT_FOUND.value: "13-declared-test-file-is-missing-e201",
    ErrorCode.TEST_FILE_NOT_IN_READONLY.value: (
        "14-test-file-is-not-listed-as-read-only-e202"
    ),
    ErrorCode.MISSING_ASSERTIONS.value: "15-tests-have-no-assertions-e210",
    ErrorCode.NO_TEST_FILES.value: "16-no-test-files-are-declared-e220",
    ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS.value: (
        "17-validate-command-does-not-run-tests-e230"
    ),
    ErrorCode.ARTIFACT_NOT_DEFINED.value: "18-declared-artifact-is-not-defined-e300",
    ErrorCode.UNEXPECTED_ARTIFACT.value: "19-unexpected-artifact-is-present-e301",
    ErrorCode.TYPE_MISMATCH.value: "common-issues",
    ErrorCode.SIGNATURE_MISMATCH.value: "20-signature-does-not-match-e303",
    ErrorCode.FILE_SHOULD_BE_PRESENT.value: "21-declared-file-should-be-present-e306",
    ErrorCode.VALIDATOR_NOT_AVAILABLE.value: "22-no-validator-is-available-e307",
    ErrorCode.SOURCE_PARSE_ERROR.value: "23-source-cannot-be-parsed-e308",
    ErrorCode.STUB_FUNCTION_DETECTED.value: "24-stub-implementation-is-detected-e310",
    ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT.value: (
        "25-removed-artifact-still-exists-e311"
    ),
    ErrorCode.MISSING_REQUIRED_IMPORT.value: "26-required-import-is-missing-e320",
    ErrorCode.COHERENCE_DUPLICATE.value: "27-coherence-diagnostics-appear",
    ErrorCode.COHERENCE_SIGNATURE_CONFLICT.value: "27-coherence-diagnostics-appear",
    ErrorCode.COHERENCE_BOUNDARY_VIOLATION.value: "27-coherence-diagnostics-appear",
    ErrorCode.COHERENCE_NAMING_VIOLATION.value: "27-coherence-diagnostics-appear",
    ErrorCode.COHERENCE_DEPENDENCY_MISSING.value: "27-coherence-diagnostics-appear",
    ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND.value: (
        "28-acceptance-test-file-is-missing-e500"
    ),
    ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH.value: (
        "29-test-function-behavior-mismatch-e610"
    ),
}

_DESCRIPTION_OVERRIDES = {
    ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE.value: (
        "Changed file is outside manifest scope",
        "The worktree contains a changed file that is not declared by the "
        "active manifest chain for this task.",
    ),
    ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED.value: (
        "Changed-scope baseline is required",
        "Changed-scope validation needs a baseline from metadata or an explicit "
        "--since or --base-ref value before comparing the current task.",
    ),
    ErrorCode.ARTIFACT_NOT_USED_IN_TESTS.value: (
        "Artifact is not used by behavioral tests",
        "The manifest declares a public artifact, but the declared behavioral "
        "tests do not reference that artifact by name.",
    ),
    ErrorCode.TEST_FILE_NOT_FOUND.value: (
        "Declared test file is missing",
        "A test file referenced by the manifest does not exist at the declared "
        "path.",
    ),
    ErrorCode.MISSING_ASSERTIONS.value: (
        "Tests have no assertions",
        "A behavioral test references declared artifacts but does not assert "
        "observable behavior.",
    ),
    ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS.value: (
        "Validate command does not run tests",
        "A validate command does not invoke a recognized test runner or omits "
        "the declared contextual test files.",
    ),
    ErrorCode.ARTIFACT_NOT_DEFINED.value: (
        "Declared artifact is not defined",
        "Implementation validation could not find a public artifact declared by "
        "the manifest.",
    ),
    ErrorCode.UNEXPECTED_ARTIFACT.value: (
        "Unexpected artifact is present",
        "A strict implementation file exposes a public artifact that is not "
        "declared by the manifest.",
    ),
    ErrorCode.TYPE_MISMATCH.value: (
        "Declared type does not match",
        "A public artifact has a type annotation that differs from the manifest "
        "contract.",
    ),
    ErrorCode.SIGNATURE_MISMATCH.value: (
        "Signature does not match",
        "A function or method signature differs from the arguments declared by "
        "the manifest.",
    ),
}

_RECIPE_TEMPLATES = {
    ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE.value: RepairRecipe(
        kind="edit-implementation",
        target="{file}",
        instruction=(
            "Move or remove the change in {file}, or stop and revise the plan "
            "before expanding manifest scope."
        ),
    ),
    ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED.value: RepairRecipe(
        kind="run-command",
        target="{command}",
        instruction=(
            "Rerun {command} with the intended --base-ref or add the approved "
            "maid_task_base through a deliberate plan revision."
        ),
    ),
    ErrorCode.ARTIFACT_NOT_USED_IN_TESTS.value: RepairRecipe(
        kind="edit-tests",
        target="{test}",
        instruction=(
            "Add behavioral coverage in {test} that exercises {artifact} by "
            "name and asserts observable behavior."
        ),
    ),
    ErrorCode.TEST_FILE_NOT_FOUND.value: RepairRecipe(
        kind="revise-plan",
        target="maid plan revise {manifest}",
        instruction=(
            "Revise the plan deliberately so {test} exists or the approved "
            "manifest points at the correct test path; use maid plan revise "
            "when that command is available."
        ),
    ),
    ErrorCode.MISSING_ASSERTIONS.value: RepairRecipe(
        kind="edit-tests",
        target="{test}",
        instruction=(
            "Add assertions in {test} that prove the observable behavior of "
            "{artifact}."
        ),
    ),
    ErrorCode.VALIDATE_COMMAND_DOES_NOT_RUN_TESTS.value: RepairRecipe(
        kind="revise-plan",
        target="maid plan revise {manifest}",
        instruction=(
            "Revise the manifest validate command deliberately so {command} "
            "runs the declared test file {test}; use maid plan revise when "
            "that command is available."
        ),
    ),
    ErrorCode.ARTIFACT_NOT_DEFINED.value: RepairRecipe(
        kind="edit-implementation",
        target="{file}",
        instruction=(
            "Implement the declared artifact {artifact} in {file} with the "
            "public name required by the manifest."
        ),
    ),
    ErrorCode.UNEXPECTED_ARTIFACT.value: RepairRecipe(
        kind="edit-implementation",
        target="{file}",
        instruction=(
            "Remove the undeclared public artifact {artifact} from {file}, make "
            "it private, or stop for a deliberate plan revision if it is part "
            "of the intended contract."
        ),
    ),
    ErrorCode.TYPE_MISMATCH.value: RepairRecipe(
        kind="edit-implementation",
        target="{file}",
        instruction=(
            "Align the type annotation for {artifact} in {file} with the "
            "approved manifest contract."
        ),
    ),
    ErrorCode.SIGNATURE_MISMATCH.value: RepairRecipe(
        kind="edit-implementation",
        target="{file}",
        instruction=(
            "Align the signature for {artifact} in {file} with the approved "
            "manifest arguments."
        ),
    ),
}


def _normalize_code(code: str) -> str:
    if isinstance(code, ErrorCode):
        return code.value
    return str(code)


def _render_template(template: str, values: dict[str, str]) -> str:
    fields = {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None
    }
    missing = fields.difference(values)
    if missing:
        missing_fields = ", ".join(sorted(missing))
        raise KeyError(f"Missing next_action value(s): {missing_fields}")
    return template.format(**values)


def _description_for(code: ErrorCode) -> tuple[str, str]:
    if code.value in _DESCRIPTION_OVERRIDES:
        return _DESCRIPTION_OVERRIDES[code.value]

    short_description = code.name.replace("_", " ").title()
    description = f"Diagnostic {code.value} reports {short_description.lower()}."
    return short_description, description


def _severity_for(code: ErrorCode) -> str:
    if code.value in _INFO_CODES:
        return Severity.INFO.value
    if code.value in _WARNING_CODES:
        return Severity.WARNING.value
    return Severity.ERROR.value


def _help_uri_for(code: ErrorCode) -> str:
    anchor = _HELP_ANCHORS.get(code.value, "common-issues")
    return f"docs/troubleshooting.md#{anchor}"


def _build_rule(code: ErrorCode) -> DiagnosticRule:
    short_description, description = _description_for(code)
    return DiagnosticRule(
        code=code.value,
        default_severity=_severity_for(code),
        short_description=short_description,
        description=description,
        help_uri=_help_uri_for(code),
        next_action=_RECIPE_TEMPLATES.get(code.value),
    )


_ALL_RULES = tuple(
    _build_rule(code) for code in sorted(ErrorCode, key=lambda c: c.value)
)
_RULES_BY_CODE = {rule.code: rule for rule in _ALL_RULES}
