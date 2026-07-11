from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
BACKLOG = ROOT / "docs/plans/strict-coverage-migration-backlog.md"


def _read_backlog() -> str:
    return BACKLOG.read_text(encoding="utf-8")


def _count_for(backlog: str, code: str) -> int:
    pattern = rf"^\|\s*{re.escape(code)}\s*\|[^|]*\|\s*(\d+)\s*\|"
    match = re.search(pattern, backlog, flags=re.MULTILINE)
    assert match is not None, f"missing numeric count row for {code}"
    return int(match.group(1))


def _metadata_value(backlog: str, label: str) -> str:
    match = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$", backlog, re.MULTILINE)
    assert match is not None, f"missing metadata field {label}"
    value = match.group(1).strip()
    assert value
    for placeholder in ("TBD", "TODO", "unknown", "n/a", "manual"):
        assert placeholder.lower() not in value.lower()
    return value


def test_strict_coverage_migration_backlog_records_regenerable_inventory() -> None:
    backlog = _read_backlog()

    assert "`uv run maid validate --strict-delta --json`" in backlog
    generated_from = _metadata_value(backlog, "Generated from")
    run_date = _metadata_value(backlog, "Run date")
    observed_runtime = _metadata_value(backlog, "Observed runtime")
    source_snapshot = _metadata_value(backlog, "Source snapshot")

    assert generated_from == "`uv run maid validate --strict-delta --json`"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", run_date)
    assert re.fullmatch(r"\d+(\.\d+)?s", observed_runtime)
    assert re.search(r"\b[0-9a-f]{12,40}\b", source_snapshot)

    assert "Per-Code Counts" in backlog
    assert _count_for(backlog, "E710") == 0
    assert "ARTIFACT_NOT_EXECUTED_BY_TESTS" in backlog
    assert _count_for(backlog, "E900") == 0
    assert "INTERNAL_ERROR" in backlog
    assert "not hand estimates" in backlog
    assert "Per-Manifest / Cohort Breakdown" in backlog
    assert "No manifest cohorts were present in the cited strict-delta run." in backlog


def test_strict_coverage_migration_backlog_plans_e710_batches_and_deferrals() -> None:
    backlog = _read_backlog()

    assert "Zero-E900 Completion Evidence" in backlog
    assert "E900 count: 0" in backlog
    assert "demonstrated by the cited strict-delta run" in backlog
    assert "E710 Burn-Down Batch Plan" in backlog
    assert "No E710 burn-down batches are required" in backlog
    assert "Deferral Rationale" in backlog
    assert "No artifact-coverage gate weakening" in backlog
