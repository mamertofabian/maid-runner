"""Behavioral accuracy contract for the chain-merge documentation."""

from __future__ import annotations

from pathlib import Path
import re

import pytest
import yaml


def _section(document: str, heading: str) -> str:
    start = document.index(heading)
    remainder = document[start + len(heading) :]
    level = len(heading) - len(heading.lstrip("#"))
    next_heading = re.search(rf"\n#{{1,{level}}} ", remainder)
    return remainder if next_heading is None else remainder[: next_heading.start()]


def _bold_bullet_section(document: str, label: str) -> str:
    start = document.index(label)
    remainder = document[start + len(label) :]
    next_bullet = re.search(r"\n\s*\* \*\*", remainder)
    return remainder if next_bullet is None else remainder[: next_bullet.start()]


def test_chain_merge_reference_covers_shipped_modes_and_safety_boundaries(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from maid_runner.cli.commands._main import main

    with pytest.raises(SystemExit) as exc_info:
        main(["chain", "merge", "--help"])
    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    _maid_chain_merge_command_reference = Path("docs/maid-chain-merge.md").read_text()

    for option in (
        "--all",
        "--manifest-dir",
        "--dry-run",
        "--apply",
        "--verify-equivalence",
        "--json",
    ):
        assert option in help_text
        assert option in _maid_chain_merge_command_reference

    exact_equivalence_option = "--verify-equivalence BASELINE_REPORT"
    assert exact_equivalence_option in help_text
    assert exact_equivalence_option in _maid_chain_merge_command_reference

    report = _section(_maid_chain_merge_command_reference, "### Report")
    apply = _section(_maid_chain_merge_command_reference, "### Materialize")
    equivalence = _section(
        _maid_chain_merge_command_reference, "### Verify test equivalence"
    )
    assert "current recorded evidence" in report
    assert "never runs coverage or knockout" in report
    assert "never retires tests" in apply
    assert "complete baseline report" in equivalence
    assert "artifact identity" in equivalence
    assert "coverage superset" in equivalence
    assert "knockout-detection superset" in equivalence
    assert "new nodeids" in equivalence
    assert "E715" in equivalence
    assert "not yet shipped" not in _maid_chain_merge_command_reference.lower()


def test_chain_merge_spec_and_design_record_the_implemented_workflow() -> None:
    canonical_spec = Path("docs/maid_specs.md").read_text()
    _chain_merge_consolidated_snapshots_spec = _bold_bullet_section(
        canonical_spec, "* **Consolidated Snapshots:**"
    )
    _chain_merge_consolidation_design_resolution = Path(
        "docs/plans/maid-runner-manifest-test-consolidation.md"
    ).read_text()

    spec = _chain_merge_consolidated_snapshots_spec
    for phrase in (
        "maid chain merge",
        "--apply",
        "--verify-equivalence",
        "--all",
        "recorded evidence",
        "coverage superset",
        "knockout-detection superset",
    ):
        assert phrase in spec

    for text in (_chain_merge_consolidation_design_resolution,):
        assert "maid chain merge" in text
        assert "--apply" in text
        assert "--verify-equivalence" in text
        assert "--all" in text
        assert "recorded" in text.lower()
        assert "coverage" in text.lower()
        assert "knockout" in text.lower()

    design = _chain_merge_consolidation_design_resolution
    assert "Status: Implemented" in design
    assert "6× declaration redundancy" in design
    assert "opposite retention logic" in design
    assert "coverage alone is insufficient" in design.lower()
    assert "artifact identity" in design.lower()
    assert "superset" in design.lower()
    assert "## Remaining operational limits" in design
    assert "not scheduled" not in design.lower()


def test_chain_merge_spec_mirrors_and_epic_closeout_are_current() -> None:
    canonical = Path("docs/maid_specs.md").read_bytes()
    assert Path("maid_runner/docs/maid_specs.md").read_bytes() == canonical
    assert Path(".maid/docs/maid_specs.md").read_bytes() == canonical

    epic_path = Path("manifests/drafts/chain-merge-defragmentation.epic.yaml")
    epic_text = epic_path.read_text()
    epic = yaml.safe_load(epic_text)
    assert epic["metadata"]["status"] == "completed"
    active_children = (
        "chain-merge-fragmentation-report",
        "chain-merge-evidence-sources",
        "chain-merge-report-consumes-evidence",
        "chain-merge-coverage-evidence",
        "chain-merge-apply-materialize",
        "chain-merge-equivalence-gate",
        "chain-merge-repo-wide-sweep",
        "chain-merge-docs",
    )
    for slug in active_children:
        assert f"manifests/{slug}.manifest.yaml" in epic_text
    assert not re.search(
        r"manifests/drafts/chain-merge-[^\s'\"]+\.manifest\.yaml", epic_text
    )
