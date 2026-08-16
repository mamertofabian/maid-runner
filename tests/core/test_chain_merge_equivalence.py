"""Behavioral contract for the chain-merge equivalence gate (child 5)."""

from __future__ import annotations

import pytest


def _acceptance(
    *,
    required=("function:alpha", "function:beta"),
    detecting=None,
    covered=None,
    detection_available=True,
    coverage_available=True,
    unknown_detection=(),
    uncovered=(),
    unknown_coverage=(),
):
    from maid_runner.core.chain_merge import ChainMergeAcceptanceSpec

    return ChainMergeAcceptanceSpec(
        required_artifacts=tuple(required),
        detection_available=detection_available,
        required_detecting_nodeids=dict(
            detecting
            if detecting is not None
            else {
                "function:alpha": ("tests/old_test.py::test_alpha",),
                "function:beta": ("tests/old_test.py::test_beta",),
            }
        ),
        unknown_detection_artifacts=tuple(unknown_detection),
        coverage_available=coverage_available,
        required_covered_artifacts=tuple(covered if covered is not None else required),
        uncovered_coverage_artifacts=tuple(uncovered),
        unknown_coverage_artifacts=tuple(unknown_coverage),
    )


def test_equivalence_accepts_different_candidate_nodeids_and_superset_evidence():
    from maid_runner.core.chain_merge_equivalence import (
        MergeEquivalenceResult,
        check_merge_equivalence,
    )

    baseline = _acceptance()
    candidate = _acceptance(
        required=("function:alpha", "function:beta", "function:gamma"),
        detecting={
            "function:alpha": ("tests/new_test.py::test_consolidated",),
            "function:beta": (
                "tests/new_test.py::test_consolidated",
                "tests/new_test.py::test_beta_edge",
            ),
            "function:gamma": ("tests/new_test.py::test_gamma",),
        },
        covered=("function:alpha", "function:beta", "function:gamma"),
    )

    result = check_merge_equivalence("src/example.py", baseline, candidate)

    assert isinstance(result, MergeEquivalenceResult)
    assert result.file_path == "src/example.py"
    assert result.success is True
    assert result.detection_regressions == ()
    assert result.coverage_regressions == ()
    assert result.evidence_regressions == ()
    assert result.errors == ()


def test_equivalence_blocks_lost_knockout_detection():
    from maid_runner.core.chain_merge_equivalence import check_merge_equivalence
    from maid_runner.core.result import ErrorCode, Severity

    candidate = _acceptance(
        detecting={
            "function:alpha": ("tests/new_test.py::test_alpha",),
            "function:beta": (),
        }
    )

    result = check_merge_equivalence("src/example.py", _acceptance(), candidate)

    assert result.success is False
    assert result.detection_regressions == ("function:beta",)
    assert result.errors
    assert {error.code for error in result.errors} == {
        ErrorCode.CHAIN_MERGE_EQUIVALENCE_REGRESSION
    }
    assert all(error.severity is Severity.ERROR for error in result.errors)


def test_equivalence_blocks_lost_artifact_coverage():
    from maid_runner.core.chain_merge_equivalence import check_merge_equivalence

    candidate = _acceptance(
        covered=("function:alpha",),
        uncovered=("function:beta",),
    )

    result = check_merge_equivalence("src/example.py", _acceptance(), candidate)

    assert result.success is False
    assert result.coverage_regressions == ("function:beta",)
    assert any("coverage" in error.message.lower() for error in result.errors)


@pytest.mark.parametrize(
    ("baseline", "candidate", "expected_marker"),
    [
        (
            _acceptance(
                detection_available=False,
                detecting={},
                unknown_detection=("function:alpha", "function:beta"),
            ),
            _acceptance(),
            "baseline:detection",
        ),
        (
            _acceptance(detecting={"function:alpha": (), "function:beta": ()}),
            _acceptance(),
            "baseline:detection",
        ),
        (
            _acceptance(
                coverage_available=False,
                covered=(),
                unknown_coverage=("function:alpha", "function:beta"),
            ),
            _acceptance(),
            "baseline:coverage",
        ),
        (
            _acceptance(
                covered=("function:alpha",),
                unknown_coverage=("function:beta",),
            ),
            _acceptance(),
            "baseline:coverage:function:beta",
        ),
        (
            _acceptance(
                covered=("function:alpha",),
                uncovered=("function:beta",),
            ),
            _acceptance(),
            "baseline:coverage:function:beta",
        ),
        (
            _acceptance(),
            _acceptance(
                detection_available=False,
                detecting={},
                unknown_detection=("function:alpha", "function:beta"),
            ),
            "candidate:detection",
        ),
        (
            _acceptance(),
            _acceptance(
                detecting={"function:alpha": ("tests/new.py::test_alpha",)},
                unknown_detection=("function:beta",),
            ),
            "candidate:detection:function:beta",
        ),
        (
            _acceptance(),
            _acceptance(
                coverage_available=False,
                covered=(),
                unknown_coverage=("function:alpha", "function:beta"),
            ),
            "candidate:coverage",
        ),
        (
            _acceptance(),
            _acceptance(
                covered=("function:alpha",),
                unknown_coverage=("function:beta",),
            ),
            "candidate:coverage:function:beta",
        ),
        (
            _acceptance(),
            _acceptance(required=("function:alpha",)),
            "candidate:contract:function:beta",
        ),
        (
            _acceptance(required=(), detecting={}, covered=()),
            _acceptance(),
            "baseline:contract",
        ),
        (
            _acceptance(
                detecting={
                    "function:alpha": ("",),
                    "function:beta": ("tests/old.py::test_beta",),
                }
            ),
            _acceptance(),
            "baseline:detection:function:alpha",
        ),
        (
            _acceptance(),
            _acceptance(
                detecting={
                    "function:alpha": ("tests/new.py::test_alpha",),
                    "function:beta": ("",),
                }
            ),
            "candidate:detection:function:beta",
        ),
        (
            _acceptance(
                detecting={
                    "function:alpha": ("tests/old.py::test_alpha",),
                    "function:beta": ("tests/old.py::test_beta",),
                    "function:ghost": ("tests/old.py::test_ghost",),
                }
            ),
            _acceptance(),
            "baseline:contract",
        ),
        (
            _acceptance(),
            _acceptance(
                covered=("function:alpha",),
                uncovered=("function:alpha", "function:beta"),
            ),
            "candidate:contract",
        ),
    ],
)
def test_equivalence_fails_closed_for_incomplete_baseline_or_candidate(
    baseline, candidate, expected_marker
):
    from maid_runner.core.chain_merge_equivalence import check_merge_equivalence

    result = check_merge_equivalence("src/example.py", baseline, candidate)

    assert result.success is False
    assert any(
        marker == expected_marker or marker.startswith(f"{expected_marker}:")
        for marker in result.evidence_regressions
    )
    assert result.errors
    assert {(error.code.value, error.severity.value) for error in result.errors} == {
        ("E715", "error")
    }


def test_equivalence_result_is_deterministic():
    from maid_runner.core.chain_merge_equivalence import check_merge_equivalence

    baseline = _acceptance()
    candidate = _acceptance(
        detecting={"function:beta": (), "function:alpha": ()},
        covered=(),
        uncovered=("function:beta", "function:alpha"),
    )

    first = check_merge_equivalence("src/example.py", baseline, candidate)
    second = check_merge_equivalence("src/example.py", baseline, candidate)

    assert first == second
    assert first.detection_regressions == (
        "function:alpha",
        "function:beta",
    )
    assert first.coverage_regressions == (
        "function:alpha",
        "function:beta",
    )
