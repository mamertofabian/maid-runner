"""Behavioral tests for the public validator conformance kit."""

from __future__ import annotations

from dataclasses import replace

import pytest

from maid_runner.core.types import ArtifactKind
from maid_runner.testing import make_conformance_suite as package_make_conformance_suite
from maid_runner.testing.validator_conformance import (
    ConformanceArtifactSample,
    ConformanceFixtures,
    make_conformance_suite,
)
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact
from maid_runner.validators.python import PythonValidator


def _python_fixtures() -> ConformanceFixtures:
    return ConformanceFixtures(
        extension=".py",
        artifact_samples={
            "class": ConformanceArtifactSample(
                source="class ExampleService:\n    pass\n",
                expected_name="ExampleService",
            ),
            "function": ConformanceArtifactSample(
                source="def build_widget():\n    return 1\n",
                expected_name="build_widget",
            ),
            "method": ConformanceArtifactSample(
                source="class ExampleService:\n    def run(self):\n        return 1\n",
                expected_name="run",
                expected_of="ExampleService",
            ),
            "attribute": ConformanceArtifactSample(
                source="class ExampleService:\n    enabled: bool\n",
                expected_name="enabled",
                expected_of="ExampleService",
            ),
        },
        private_artifact_source="def _hidden_helper():\n    return 1\n",
        behavioral_target_kind="function",
        behavioral_target_name="build_widget",
        behavioral_target_of=None,
        behavioral_correct_source=(
            "from app.service import build_widget\n\n"
            "def test_build_widget():\n"
            "    build_widget()\n"
        ),
        behavioral_wrong_identity_source=(
            "from app.service import other_widget\n\n"
            "def test_other_widget():\n"
            "    other_widget()\n"
        ),
        unparseable_source="def broken(:\n",
        empty_source="",
    )


TestPythonValidatorConformance = make_conformance_suite(
    PythonValidator,
    _python_fixtures(),
)


class _PrivateLeakingValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".py",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name="hidden_helper",
                )
            ],
            language="mock",
            file_path=str(file_path),
        )

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="mock", file_path=str(file_path))


class _WrongIdentityValidator(PythonValidator):
    def collect_behavioral_artifacts(self, source, file_path):
        if "other_widget" in source:
            return CollectionResult(
                artifacts=[
                    FoundArtifact(
                        kind=ArtifactKind.FUNCTION,
                        name="build_widget",
                    )
                ],
                language="python",
                file_path=str(file_path),
            )
        return super().collect_behavioral_artifacts(source, file_path)


class _StringKindValidator(PythonValidator):
    def collect_implementation_artifacts(self, source, file_path):
        if "build_widget" in source:
            return CollectionResult(
                artifacts=[
                    FoundArtifact(
                        kind="function",  # type: ignore[arg-type]
                        name="build_widget",
                    )
                ],
                language="python",
                file_path=str(file_path),
            )
        return super().collect_implementation_artifacts(source, file_path)


class _PrivateStringKindValidator(PythonValidator):
    def collect_implementation_artifacts(self, source, file_path):
        if source == _python_fixtures().private_artifact_source:
            return CollectionResult(
                artifacts=[
                    FoundArtifact(
                        kind="function",  # type: ignore[arg-type]
                        name="_hidden_helper",
                    )
                ],
                language="python",
                file_path=str(file_path),
            )
        return super().collect_implementation_artifacts(source, file_path)


class _ExtraBehavioralStringKindValidator(PythonValidator):
    def collect_behavioral_artifacts(self, source, file_path):
        result = super().collect_behavioral_artifacts(source, file_path)
        if source == _python_fixtures().behavioral_correct_source:
            result.artifacts.append(
                FoundArtifact(
                    kind="function",  # type: ignore[arg-type]
                    name="extra_helper",
                )
            )
        return result


class _ParseErrorSwallowingValidator(PythonValidator):
    def collect_implementation_artifacts(self, source, file_path):
        if source == _python_fixtures().unparseable_source:
            return CollectionResult(
                artifacts=[],
                language="python",
                file_path=str(file_path),
            )
        return super().collect_implementation_artifacts(source, file_path)


class _MismatchedExtensionValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".mock",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[],
            language="mock",
            file_path=str(file_path),
        )

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="mock", file_path=str(file_path))


def test_testing_package_reexports_make_conformance_suite():
    assert package_make_conformance_suite is make_conformance_suite


def test_make_conformance_suite_requires_wrong_identity_sample():
    fixtures = replace(_python_fixtures(), behavioral_wrong_identity_source="")

    with pytest.raises(ValueError, match="behavioral_wrong_identity_source"):
        make_conformance_suite(PythonValidator, fixtures)


def test_make_conformance_suite_requires_supported_fixture_extension():
    with pytest.raises(ValueError, match="extension"):
        make_conformance_suite(_MismatchedExtensionValidator, _python_fixtures())


def test_make_conformance_suite_requires_empty_source_to_be_empty():
    fixtures = replace(_python_fixtures(), empty_source="pass\n")

    with pytest.raises(ValueError, match="empty_source"):
        make_conformance_suite(PythonValidator, fixtures)


def test_make_conformance_suite_requires_core_artifact_kind_samples():
    function_sample = _python_fixtures().artifact_samples["function"]
    fixtures = replace(
        _python_fixtures(), artifact_samples={"function": function_sample}
    )

    with pytest.raises(ValueError, match="artifact_samples"):
        make_conformance_suite(PythonValidator, fixtures)


def test_broken_validator_reporting_private_artifact_as_public_fails_private_case():
    suite = make_conformance_suite(_PrivateLeakingValidator, _python_fixtures())

    with pytest.raises(AssertionError, match="private"):
        suite().test_private_artifacts_stay_private_and_out_of_snapshot()


def test_broken_validator_returning_string_kind_fails_identity_case():
    suite = make_conformance_suite(_StringKindValidator, _python_fixtures())

    with pytest.raises(AssertionError, match="ArtifactKind"):
        suite().test_collects_declared_implementation_artifact(
            "function",
            _python_fixtures().artifact_samples["function"],
        )


def test_broken_validator_returning_private_string_kind_fails_private_case():
    suite = make_conformance_suite(_PrivateStringKindValidator, _python_fixtures())

    with pytest.raises(AssertionError, match="ArtifactKind"):
        suite().test_private_artifacts_stay_private_and_out_of_snapshot()


def test_broken_validator_returning_extra_behavioral_string_kind_fails_behavioral_case():
    suite = make_conformance_suite(
        _ExtraBehavioralStringKindValidator, _python_fixtures()
    )

    with pytest.raises(AssertionError, match="ArtifactKind"):
        suite().test_behavioral_sample_references_declared_target()


def test_broken_validator_accepting_wrong_identity_fails_behavioral_case():
    suite = make_conformance_suite(_WrongIdentityValidator, _python_fixtures())

    with pytest.raises(AssertionError, match="wrong-identity"):
        suite().test_wrong_identity_behavioral_sample_does_not_match_target()


def test_broken_validator_swallowing_parse_errors_fails_parse_error_case():
    suite = make_conformance_suite(_ParseErrorSwallowingValidator, _python_fixtures())

    with pytest.raises(AssertionError, match="parse error"):
        suite().test_unparseable_source_reports_errors_without_artifacts()
