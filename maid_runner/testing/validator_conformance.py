"""Pytest conformance suite factory for third-party validator plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import pytest

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact

_CORE_ARTIFACT_KINDS = (
    ArtifactKind.CLASS.value,
    ArtifactKind.FUNCTION.value,
    ArtifactKind.METHOD.value,
    ArtifactKind.ATTRIBUTE.value,
)


@dataclass(frozen=True)
class ConformanceArtifactSample:
    """One implementation sample and the public artifact identity it yields."""

    source: str
    expected_name: str
    expected_of: str | None = None


@dataclass(frozen=True)
class ConformanceFixtures:
    """Fixture contract for a validator language conformance suite."""

    extension: str
    artifact_samples: Mapping[str, ConformanceArtifactSample]
    private_artifact_source: str
    behavioral_target_kind: str
    behavioral_target_name: str
    behavioral_target_of: str | None
    behavioral_correct_source: str
    behavioral_wrong_identity_source: str
    unparseable_source: str
    empty_source: str


def make_conformance_suite(
    validator_cls: type[BaseValidator],
    fixtures: ConformanceFixtures,
) -> type:
    """Return pytest cases that verify a validator honors MAID semantics."""

    _validate_fixture_contract(validator_cls, fixtures)
    artifact_params = tuple(fixtures.artifact_samples.items())
    artifact_ids = tuple(kind for kind, _sample in artifact_params)

    class TestValidatorConformance:
        __test__ = True

        def _validator(self) -> BaseValidator:
            return validator_cls()

        @pytest.mark.parametrize(
            ("artifact_kind", "sample"),
            artifact_params,
            ids=artifact_ids,
        )
        def test_collects_declared_implementation_artifact(
            self,
            artifact_kind: str,
            sample: ConformanceArtifactSample,
        ) -> None:
            result = _collect_implementation(
                self._validator(),
                sample.source,
                fixtures,
                f"implementation_{artifact_kind}",
            )
            _assert_successful_result(result)
            assert _contains_identity(
                result.artifacts,
                artifact_kind,
                sample.expected_name,
                sample.expected_of,
            ), (
                "implementation collector did not return expected "
                f"{artifact_kind}:{sample.expected_name}"
            )

        @pytest.mark.parametrize(
            ("artifact_kind", "sample"),
            artifact_params,
            ids=artifact_ids,
        )
        def test_declared_artifact_identity_fields_are_exact(
            self,
            artifact_kind: str,
            sample: ConformanceArtifactSample,
        ) -> None:
            result = _collect_implementation(
                self._validator(),
                sample.source,
                fixtures,
                f"identity_{artifact_kind}",
            )
            matches = [
                artifact
                for artifact in result.artifacts
                if _kind_value(artifact.kind) == artifact_kind
                and artifact.name == sample.expected_name
            ]
            assert matches, (
                "implementation collector did not return an artifact with "
                f"kind {artifact_kind!r} and name {sample.expected_name!r}"
            )
            assert any(artifact.of == sample.expected_of for artifact in matches), (
                "implementation collector returned the expected kind and name "
                f"without exact parent {sample.expected_of!r}"
            )

        @pytest.mark.parametrize(
            ("artifact_kind", "sample"),
            artifact_params,
            ids=artifact_ids,
        )
        def test_collecting_same_sample_is_deterministic(
            self,
            artifact_kind: str,
            sample: ConformanceArtifactSample,
        ) -> None:
            validator = self._validator()
            first = _collect_implementation(
                validator,
                sample.source,
                fixtures,
                f"deterministic_{artifact_kind}",
            )
            second = _collect_implementation(
                validator,
                sample.source,
                fixtures,
                f"deterministic_{artifact_kind}",
            )
            assert first == second

        def test_private_artifacts_stay_private_and_out_of_snapshot(self) -> None:
            validator = self._validator()
            result = _collect_implementation(
                validator,
                fixtures.private_artifact_source,
                fixtures,
                "private_artifact",
            )
            _assert_successful_result(result)
            assert result.artifacts, "private sample must produce private artifacts"
            assert all(
                artifact.is_private for artifact in result.artifacts
            ), "private sample produced a non-private artifact"
            snapshot = validator.generate_snapshot(
                fixtures.private_artifact_source,
                _sample_path(fixtures, "private_artifact"),
            )
            assert snapshot == [], "private artifacts leaked into generate_snapshot"

        def test_behavioral_sample_references_declared_target(self) -> None:
            result = _collect_behavioral(
                self._validator(),
                fixtures.behavioral_correct_source,
                fixtures,
                "behavioral_correct",
            )
            _assert_successful_result(result)
            assert _contains_target_identity(
                result.artifacts, fixtures
            ), "behavioral collector did not return the declared target identity"

        def test_wrong_identity_behavioral_sample_does_not_match_target(self) -> None:
            result = _collect_behavioral(
                self._validator(),
                fixtures.behavioral_wrong_identity_source,
                fixtures,
                "behavioral_wrong_identity",
            )
            _assert_successful_result(result)
            assert not _contains_target_identity(
                result.artifacts, fixtures
            ), "wrong-identity behavioral sample matched the declared target"

        def test_unparseable_source_reports_errors_without_artifacts(self) -> None:
            try:
                result = self._validator().collect_implementation_artifacts(
                    fixtures.unparseable_source,
                    _sample_path(fixtures, "unparseable"),
                )
            except Exception as exc:  # pragma: no cover - exercised by plugins.
                raise AssertionError(
                    "parse error sample raised instead of returning CollectionResult"
                ) from exc
            assert isinstance(
                result, CollectionResult
            ), "parse error sample did not return CollectionResult"
            assert result.errors, "parse error sample returned no parse errors"
            assert (
                result.artifacts == []
            ), "parse error sample returned artifacts despite parse errors"

        def test_empty_source_returns_no_artifacts_or_errors(self) -> None:
            result = _collect_implementation(
                self._validator(),
                fixtures.empty_source,
                fixtures,
                "empty",
            )
            assert result.artifacts == []
            assert result.errors == []

    TestValidatorConformance.__name__ = f"Test{validator_cls.__name__}Conformance"
    TestValidatorConformance.__qualname__ = TestValidatorConformance.__name__
    return TestValidatorConformance


def _validate_fixture_contract(
    validator_cls: type[BaseValidator],
    fixtures: ConformanceFixtures,
) -> None:
    if not isinstance(validator_cls, type) or not issubclass(
        validator_cls,
        BaseValidator,
    ):
        raise TypeError("validator_cls must be a BaseValidator subclass")

    _require_non_empty_string(fixtures.extension, "extension")
    if not fixtures.extension.startswith("."):
        raise ValueError("extension must start with '.'")
    if fixtures.extension not in validator_cls.supported_extensions():
        raise ValueError(
            "extension must be included in validator_cls.supported_extensions()"
        )
    if not fixtures.artifact_samples:
        raise ValueError("artifact_samples must include at least one sample")
    for artifact_kind in _CORE_ARTIFACT_KINDS:
        if artifact_kind not in fixtures.artifact_samples:
            raise ValueError(
                f"artifact_samples must include a {artifact_kind!r} sample"
            )

    for artifact_kind, sample in fixtures.artifact_samples.items():
        _require_non_empty_string(artifact_kind, "artifact_samples key")
        if not isinstance(sample, ConformanceArtifactSample):
            raise ValueError(
                f"artifact_samples[{artifact_kind!r}] must be "
                "ConformanceArtifactSample"
            )
        _require_non_empty_string(
            sample.source,
            f"artifact_samples[{artifact_kind!r}].source",
        )
        _require_non_empty_string(
            sample.expected_name,
            f"artifact_samples[{artifact_kind!r}].expected_name",
        )

    _require_non_empty_string(
        fixtures.private_artifact_source,
        "private_artifact_source",
    )
    _require_non_empty_string(
        fixtures.behavioral_target_kind,
        "behavioral_target_kind",
    )
    _require_non_empty_string(
        fixtures.behavioral_target_name,
        "behavioral_target_name",
    )
    _require_non_empty_string(
        fixtures.behavioral_correct_source,
        "behavioral_correct_source",
    )
    _require_non_empty_string(
        fixtures.behavioral_wrong_identity_source,
        "behavioral_wrong_identity_source",
    )
    _require_non_empty_string(fixtures.unparseable_source, "unparseable_source")
    if fixtures.empty_source != "":
        raise ValueError("empty_source must be an empty string")


def _require_non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")


def _collect_implementation(
    validator: BaseValidator,
    source: str,
    fixtures: ConformanceFixtures,
    name: str,
) -> CollectionResult:
    result = validator.collect_implementation_artifacts(
        source,
        _sample_path(fixtures, name),
    )
    assert isinstance(
        result, CollectionResult
    ), "implementation collector did not return CollectionResult"
    return result


def _collect_behavioral(
    validator: BaseValidator,
    source: str,
    fixtures: ConformanceFixtures,
    name: str,
) -> CollectionResult:
    result = validator.collect_behavioral_artifacts(
        source,
        _sample_path(fixtures, name),
    )
    assert isinstance(
        result, CollectionResult
    ), "behavioral collector did not return CollectionResult"
    return result


def _assert_successful_result(result: CollectionResult) -> None:
    assert result.errors == []
    _assert_artifact_kinds(result.artifacts)


def _assert_artifact_kinds(artifacts: list[FoundArtifact]) -> None:
    for artifact in artifacts:
        assert isinstance(
            artifact.kind, ArtifactKind
        ), "validator artifacts must use ArtifactKind enum values"


def _contains_target_identity(
    artifacts: list[FoundArtifact],
    fixtures: ConformanceFixtures,
) -> bool:
    return _contains_identity(
        artifacts,
        fixtures.behavioral_target_kind,
        fixtures.behavioral_target_name,
        fixtures.behavioral_target_of,
    )


def _contains_identity(
    artifacts: list[FoundArtifact],
    kind: str,
    name: str,
    parent: str | None,
) -> bool:
    return any(
        _kind_value(artifact.kind) == kind
        and artifact.name == name
        and artifact.of == parent
        for artifact in artifacts
    )


def _kind_value(kind: object) -> str:
    assert isinstance(
        kind, ArtifactKind
    ), "validator artifacts must use ArtifactKind enum values"
    return kind.value


def _sample_path(fixtures: ConformanceFixtures, name: str) -> str:
    return f"{name}{fixtures.extension}"
