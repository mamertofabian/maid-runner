"""Characterization coverage for TypeScript behavioral artifact collection."""

from __future__ import annotations

from maid_runner.core.types import ArtifactKind
from maid_runner.validators._typescript_behavioral import (
    BehavioralReferenceCollector,
    BehavioralTestBodyCollector,
    collect_behavioral_artifacts,
    collect_test_function_bodies,
)
from maid_runner.validators._typescript_parse import parse_typescript_source
from maid_runner.validators.typescript import TypeScriptValidator


def _parse(source: str, file_path: str = "src/auth/login.test.ts"):
    validator = TypeScriptValidator()
    session = parse_typescript_source(
        source,
        file_path,
        validator._ts_parser,
        validator._tsx_parser,
    )
    assert not session.parse_errors
    return session


def _artifact(artifacts_or_result, name: str, kind: ArtifactKind | None = None):
    artifacts = getattr(artifacts_or_result, "artifacts", artifacts_or_result)
    for artifact in artifacts:
        if artifact.name != name:
            continue
        if kind is not None and artifact.kind != kind:
            continue
        return artifact
    raise AssertionError(f"Artifact {name!r} not found in {artifacts!r}")


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

    session = _parse(source)
    moved_artifacts = collect_behavioral_artifacts(
        session.tree.root_node,
        session.source_bytes,
        "src/auth/login.test.ts",
    )

    assert _artifact(moved_artifacts, "createLogin")


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

    session = _parse(source)
    collector = BehavioralReferenceCollector(
        session.tree.root_node,
        session.source_bytes,
        "src/auth/login.test.ts",
    )
    collected = collector.collect()

    assert _artifact(collected, "login")


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

    session = _parse(source)
    moved_bodies = collect_test_function_bodies(
        session.tree.root_node,
        session.source_bytes,
    )
    collector_bodies = BehavioralTestBodyCollector(
        session.tree.root_node,
        session.source_bytes,
    ).collect()

    assert moved_bodies == bodies
    assert collector_bodies == bodies
