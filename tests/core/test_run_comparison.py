"""Behavioral tests for cross-run evaluation aggregation."""

from __future__ import annotations

from maid_runner.core.types import AgentProvenance


def test_compare_runs_groups_by_provenance_with_correct_counts() -> None:
    from maid_runner.core.run_evaluation import (
        RunComparisonRow,
        compare_runs,
    )

    first_agent = AgentProvenance(
        model="gpt-5-codex", provider="openai", client="codex-cli"
    )
    second_agent = AgentProvenance(
        model="claude-sonnet-4", provider="anthropic", client="claude-code"
    )

    rows = compare_runs(
        (
            _evaluation(
                provenance=first_agent,
                outcome_status="completed",
                revisions_narrowing=1,
                revisions_unclassified=2,
                red_evidence_status="valid",
                incidents_total=3,
            ),
            _evaluation(
                provenance=first_agent,
                outcome_status="failed",
                revisions_narrowing=4,
                revisions_unclassified=5,
                red_evidence_status="missing",
                incidents_total=6,
            ),
            _evaluation(
                provenance=second_agent,
                outcome_status="completed",
                red_evidence_status="valid",
            ),
        )
    )

    assert rows == (
        RunComparisonRow(
            provider="openai",
            model="gpt-5-codex",
            client="codex-cli",
            runs=2,
            outcomes_completed=1,
            outcomes_other=1,
            revisions_narrowing_total=5,
            revisions_unclassified_total=7,
            red_evidence_valid=1,
            incidents_total=9,
        ),
        RunComparisonRow(
            provider="anthropic",
            model="claude-sonnet-4",
            client="claude-code",
            runs=1,
            outcomes_completed=1,
            outcomes_other=0,
            revisions_narrowing_total=0,
            revisions_unclassified_total=0,
            red_evidence_valid=1,
            incidents_total=0,
        ),
    )


def test_compare_runs_buckets_anonymous_runs_explicitly() -> None:
    from maid_runner.core.run_evaluation import RunComparisonRow, compare_runs

    rows = compare_runs(
        (
            _evaluation(provenance=None, outcome_status="completed"),
            _evaluation(provenance=None, outcome_status=None),
        )
    )

    assert rows == (
        RunComparisonRow(
            provider=None,
            model=None,
            client=None,
            runs=2,
            outcomes_completed=1,
            outcomes_other=1,
            revisions_narrowing_total=0,
            revisions_unclassified_total=0,
            red_evidence_valid=0,
            incidents_total=0,
        ),
    )


def test_compare_runs_orders_rows_deterministically() -> None:
    from maid_runner.core.run_evaluation import compare_runs

    low_agent = AgentProvenance(model="b-model", provider="openai", client="codex")
    alpha_agent = AgentProvenance(model="a-model", provider="openai", client="codex")
    beta_agent = AgentProvenance(model="b-model", provider="anthropic", client="claude")

    rows = compare_runs(
        (
            _evaluation(provenance=low_agent),
            _evaluation(provenance=alpha_agent),
            _evaluation(provenance=beta_agent),
            _evaluation(provenance=alpha_agent),
            _evaluation(provenance=beta_agent),
        )
    )

    assert [(row.runs, row.model, row.provider) for row in rows] == [
        (2, "a-model", "openai"),
        (2, "b-model", "anthropic"),
        (1, "b-model", "openai"),
    ]
    assert rows == compare_runs(
        (
            _evaluation(provenance=low_agent),
            _evaluation(provenance=alpha_agent),
            _evaluation(provenance=beta_agent),
            _evaluation(provenance=alpha_agent),
            _evaluation(provenance=beta_agent),
        )
    )


def test_compare_runs_empty_input_yields_empty_tuple() -> None:
    from maid_runner.core.run_evaluation import compare_runs

    assert compare_runs(()) == ()


def _evaluation(
    *,
    provenance: AgentProvenance | None,
    outcome_status: str | None = "completed",
    revisions_narrowing: int = 0,
    revisions_unclassified: int = 0,
    red_evidence_status: str = "missing",
    incidents_total: int = 0,
):
    from maid_runner.core.run_evaluation import RunEvaluation

    return RunEvaluation(
        manifest_path="manifests/demo.manifest.yaml",
        manifest_slug="demo",
        provenance=provenance,
        provenance_source="outcome" if provenance is not None else None,
        outcome_status=outcome_status,
        outcome_uncorroborated_commands=(),
        unevidenced_validate_commands=(),
        lock_present=True,
        red_evidence_status=red_evidence_status,
        revisions_total=revisions_narrowing + revisions_unclassified,
        revisions_strengthening=0,
        revisions_neutral=0,
        revisions_narrowing=revisions_narrowing,
        revisions_unclassified=revisions_unclassified,
        incidents_total=incidents_total,
        findings=(),
    )
