from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from maid_runner.core.incidents import (
        IncidentRecord,
        PATTERN_TAGS,
        StoredIncident,
        capture_incident,
        list_incidents,
        read_incident,
        update_incident,
    )


def _packet(*codes: str) -> dict:
    return {
        "packet_version": 1,
        "diagnostics": [
            {"code": code, "message": f"{code} fired", "severity": "error"}
            for code in codes
        ],
    }


def _incident_api():
    try:
        import maid_runner.core.incidents as incidents
    except ModuleNotFoundError:
        pytest.fail("maid_runner.core.incidents module is missing")
    return incidents


def test_capture_incident_writes_exact_record_and_deterministic_filename(
    tmp_path,
):
    if TYPE_CHECKING:
        assert PATTERN_TAGS
        assert IncidentRecord
        assert capture_incident
        assert read_incident
    incidents = _incident_api()
    manifest = tmp_path / "manifests" / "070-02-example.manifest.yaml"
    manifest.parent.mkdir()
    manifest.write_text("schema: '2'\n", encoding="utf-8")

    path = incidents.capture_incident(
        tmp_path / ".maid" / "incidents",
        manifest=str(manifest),
        packet=_packet("E701", "E711"),
        rejected_diff="--- a/test.py\n+++ b/test.py\n",
        pattern_tags=["test-weakening", "runner-gaming"],
        notes="caught during verify",
        created="2026-06-15T01:02:03Z",
    )

    assert path.name == "20260615-010203-070-02-example.incident.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert list(data) == [
        "incident_version",
        "created",
        "manifest",
        "gates",
        "packet",
        "rejected_diff",
        "chosen_diff",
        "pattern_tags",
        "notes",
    ]
    assert data == {
        "incident_version": 1,
        "created": "2026-06-15T01:02:03Z",
        "manifest": str(manifest),
        "gates": ["E701", "E711"],
        "packet": _packet("E701", "E711"),
        "rejected_diff": "--- a/test.py\n+++ b/test.py\n",
        "chosen_diff": None,
        "pattern_tags": ["test-weakening", "runner-gaming"],
        "notes": "caught during verify",
    }

    record = incidents.read_incident(path)
    assert isinstance(record, incidents.IncidentRecord)
    assert record.incident_version == 1
    assert record.gates == ("E701", "E711")
    assert record.pattern_tags == ("test-weakening", "runner-gaming")
    assert record.notes == "caught during verify"


def test_capture_incident_rejects_unknown_tags_and_names_vocabulary(tmp_path):
    incidents = _incident_api()
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("schema: '2'\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        incidents.capture_incident(
            tmp_path / ".maid" / "incidents",
            manifest=str(manifest),
            packet=_packet("E701"),
            rejected_diff="diff",
            pattern_tags=["surprise-taxonomy"],
            created="2026-06-15T01:02:03Z",
        )

    message = str(excinfo.value)
    assert "surprise-taxonomy" in message
    for tag in incidents.PATTERN_TAGS:
        assert tag in message


def test_capture_incident_rejects_missing_manifest_path(tmp_path):
    incidents = _incident_api()
    manifest = tmp_path / "missing.manifest.yaml"

    with pytest.raises(FileNotFoundError) as excinfo:
        incidents.capture_incident(
            tmp_path / ".maid" / "incidents",
            manifest=str(manifest),
            packet=_packet("E701"),
            rejected_diff="diff",
            pattern_tags=["false-done"],
            created="2026-06-15T01:02:03Z",
        )

    assert str(manifest) in str(excinfo.value)


def test_capture_incident_rejects_non_utc_created_timestamp(tmp_path):
    incidents = _incident_api()
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("schema: '2'\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        incidents.capture_incident(
            tmp_path / ".maid" / "incidents",
            manifest=str(manifest),
            packet=_packet("E701"),
            rejected_diff="diff",
            pattern_tags=["false-done"],
            created="2026-06-15T09:02:03+08:00",
        )

    assert "created" in str(excinfo.value)
    assert "UTC" in str(excinfo.value)


def test_capture_incident_rejects_duplicate_deterministic_filename(tmp_path):
    incidents = _incident_api()
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("schema: '2'\n", encoding="utf-8")
    incidents_dir = tmp_path / ".maid" / "incidents"

    first = incidents.capture_incident(
        incidents_dir,
        manifest=str(manifest),
        packet=_packet("E701"),
        rejected_diff="first",
        pattern_tags=["false-done"],
        created="2026-06-15T01:02:03Z",
    )
    with pytest.raises(FileExistsError) as excinfo:
        incidents.capture_incident(
            incidents_dir,
            manifest=str(manifest),
            packet=_packet("E711"),
            rejected_diff="second",
            pattern_tags=["runner-gaming"],
            created="2026-06-15T01:02:03Z",
        )

    assert str(first) in str(excinfo.value)
    assert incidents.read_incident(first).rejected_diff == "first"


def test_capture_incident_rejects_concurrent_duplicate_filename(tmp_path):
    incidents = _incident_api()
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("schema: '2'\n", encoding="utf-8")
    incidents_dir = tmp_path / ".maid" / "incidents"

    def capture(index: int) -> tuple[str, str]:
        try:
            path = incidents.capture_incident(
                incidents_dir,
                manifest=str(manifest),
                packet=_packet("E701"),
                rejected_diff=f"attempt-{index}",
                pattern_tags=["false-done"],
                created="2026-06-15T01:02:03Z",
            )
        except FileExistsError as exc:
            return ("duplicate", str(exc))
        return ("created", str(path))

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(capture, range(8)))

    created = [value for status, value in results if status == "created"]
    duplicates = [value for status, value in results if status == "duplicate"]
    assert len(created) == 1
    assert len(duplicates) == 7
    assert all(created[0] in duplicate for duplicate in duplicates)
    assert incidents.read_incident(created[0]).rejected_diff.startswith("attempt-")


def test_read_incident_rejects_scalar_gates_field(tmp_path):
    incidents = _incident_api()
    path = tmp_path / "bad.incident.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "incident_version": 1,
                "created": "2026-06-15T01:02:03Z",
                "manifest": "manifest.yaml",
                "gates": "E701",
                "packet": {"diagnostics": [{"code": "E701"}]},
                "rejected_diff": "rejected",
                "chosen_diff": None,
                "pattern_tags": ["false-done"],
                "notes": None,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        incidents.read_incident(path)

    assert str(path) in str(excinfo.value)
    assert "gates" in str(excinfo.value)
    assert "list of strings" in str(excinfo.value)


def test_read_incident_wraps_malformed_yaml_with_path(tmp_path):
    incidents = _incident_api()
    path = tmp_path / "bad.incident.yaml"
    path.write_text("[unclosed", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        incidents.read_incident(path)

    assert str(path) in str(excinfo.value)
    assert "malformed YAML" in str(excinfo.value)


def test_read_incident_rejects_malformed_created_timestamp(tmp_path):
    incidents = _incident_api()
    path = tmp_path / "bad.incident.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "incident_version": 1,
                "created": "not-a-timestamp",
                "manifest": "manifest.yaml",
                "gates": ["E701"],
                "packet": {"diagnostics": [{"code": "E701"}]},
                "rejected_diff": "rejected",
                "chosen_diff": None,
                "pattern_tags": ["false-done"],
                "notes": None,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        incidents.read_incident(path)

    assert str(path) in str(excinfo.value)
    assert "created" in str(excinfo.value)
    assert "UTC" in str(excinfo.value)


@pytest.mark.parametrize("version", ["1", True])
def test_read_incident_rejects_non_integer_version(tmp_path, version):
    incidents = _incident_api()
    path = tmp_path / "bad.incident.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "incident_version": version,
                "created": "2026-06-15T01:02:03Z",
                "manifest": "manifest.yaml",
                "gates": ["E701"],
                "packet": {"diagnostics": [{"code": "E701"}]},
                "rejected_diff": "rejected",
                "chosen_diff": None,
                "pattern_tags": ["false-done"],
                "notes": None,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        incidents.read_incident(path)

    assert str(path) in str(excinfo.value)
    assert "incident_version" in str(excinfo.value)
    assert "integer" in str(excinfo.value)


def test_update_incident_attaches_chosen_diff_and_preserves_fields(tmp_path):
    if TYPE_CHECKING:
        assert update_incident
    incidents = _incident_api()
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("schema: '2'\n", encoding="utf-8")
    path = incidents.capture_incident(
        tmp_path / ".maid" / "incidents",
        manifest=str(manifest),
        packet=_packet("E704"),
        rejected_diff="rejected",
        pattern_tags=["false-done"],
        notes=None,
        created="2026-06-15T01:02:03Z",
    )

    updated = incidents.update_incident(path, chosen_diff="chosen")

    assert updated.chosen_diff == "chosen"
    reloaded = incidents.read_incident(path)
    assert reloaded.rejected_diff == "rejected"
    assert reloaded.chosen_diff == "chosen"
    assert reloaded.created == "2026-06-15T01:02:03Z"


def test_update_incident_missing_path_names_path(tmp_path):
    incidents = _incident_api()
    missing = tmp_path / ".maid" / "incidents" / "missing.incident.yaml"

    with pytest.raises(FileNotFoundError) as excinfo:
        incidents.update_incident(missing, chosen_diff="chosen")

    assert str(missing) in str(excinfo.value)


def test_list_incidents_orders_by_timestamp_filters_by_tag_and_handles_empty(
    tmp_path,
):
    if TYPE_CHECKING:
        assert StoredIncident
        assert list_incidents
    incidents = _incident_api()
    incidents_dir = tmp_path / ".maid" / "incidents"
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("schema: '2'\n", encoding="utf-8")
    later = incidents.capture_incident(
        incidents_dir,
        manifest=str(manifest),
        packet=_packet("E705"),
        rejected_diff="later",
        pattern_tags=["false-done"],
        created="2026-06-15T01:02:04Z",
    )
    earlier = incidents.capture_incident(
        incidents_dir,
        manifest=str(manifest),
        packet=_packet("E701"),
        rejected_diff="earlier",
        pattern_tags=["test-weakening"],
        created="2026-06-15T01:02:03Z",
    )

    assert incidents.list_incidents(tmp_path / "absent") == ()
    assert [stored.path for stored in incidents.list_incidents(incidents_dir)] == [
        str(earlier),
        str(later),
    ]
    filtered = incidents.list_incidents(incidents_dir, tag="false-done")
    assert len(filtered) == 1
    assert isinstance(filtered[0], incidents.StoredIncident)
    assert filtered[0].record.rejected_diff == "later"
