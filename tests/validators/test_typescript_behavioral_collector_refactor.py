"""Characterization coverage for TypeScript behavioral artifact collection."""

from __future__ import annotations

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.typescript import TypeScriptValidator


def _artifact(result, name: str, kind: ArtifactKind | None = None):
    for artifact in result.artifacts:
        if artifact.name != name:
            continue
        if kind is not None and artifact.kind != kind:
            continue
        return artifact
    raise AssertionError(f"Artifact {name!r} not found in {result.artifacts!r}")


def test_behavioral_collector_keeps_test_label_separate_from_source_reference() -> None:
    source = """import { createLogin } from "./api";

it("test_successful_login", () => {
  createLogin();
});
"""
    result = TypeScriptValidator().collect_behavioral_artifacts(
        source, "src/auth/login.test.ts"
    )

    label = _artifact(result, "test_successful_login", ArtifactKind.TEST_FUNCTION)
    reference = _artifact(result, "createLogin", ArtifactKind.FUNCTION)

    assert label.kind == ArtifactKind.TEST_FUNCTION
    assert reference.kind == ArtifactKind.FUNCTION
    assert reference.import_source == "src/auth/api"


def test_behavioral_collector_preserves_namespace_member_reference_identity() -> None:
    source = """import * as utils from "./utils";

it("uses namespace import", () => {
  utils.auth.login();
});
"""
    result = TypeScriptValidator().collect_behavioral_artifacts(
        source, "src/auth/login.test.ts"
    )

    login = _artifact(result, "login", ArtifactKind.FUNCTION)

    assert login.import_source == "src/auth/utils/auth"


def test_behavioral_collector_preserves_aliased_import_reference_identity() -> None:
    source = """import { createLogin as login } from "./api";

test("uses alias", () => {
  login();
});
"""
    result = TypeScriptValidator().collect_behavioral_artifacts(
        source, "src/auth/login.test.ts"
    )

    login = _artifact(result, "login", ArtifactKind.FUNCTION)

    assert login.import_source == "src/auth/api"
    assert login.alias_of == "createLogin"


def test_behavioral_collector_preserves_named_test_body_extraction() -> None:
    source = """import { createLogin } from "./api";

describe("login", () => {
  test("test_returns_session", async () => {
    const session = await createLogin();
    expect(session).toBeDefined();
  });
});
"""
    bodies = TypeScriptValidator().get_test_function_bodies(
        source, "src/auth/login.test.ts"
    )

    assert set(bodies) == {"test_returns_session"}
    assert "const session = await createLogin();" in bodies["test_returns_session"]
    assert "expect(session).toBeDefined();" in bodies["test_returns_session"]
