import json
from pathlib import Path

import jsonschema
import yaml


def _record(
    *,
    created: str,
    diagnostics: list[dict],
    pattern_tags: list[str],
) -> dict:
    return {
        "incident_version": 1,
        "created": created,
        "manifest": "manifests/example.manifest.yaml",
        "gates": ["E701"],
        "packet": {"diagnostics": diagnostics},
        "rejected_diff": "rejected",
        "chosen_diff": None,
        "pattern_tags": pattern_tags,
        "notes": None,
    }


def _write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")


def _temptation_schema() -> dict:
    schema = json.loads(
        Path("maid_runner/schemas/manifest.v2.schema.json").read_text(encoding="utf-8")
    )
    return schema["definitions"]["TemptationSpec"]


def test_suggest_temptations_filters_by_exact_normalized_diagnostic_path_and_orders_by_frequency_then_tag(
    tmp_path,
):
    from maid_runner.core import incidents

    incidents_dir = tmp_path / ".maid" / "incidents"
    _write_record(
        incidents_dir / "20260615-010203-first.incident.yaml",
        _record(
            created="2026-06-15T01:02:03Z",
            diagnostics=[{"file": "./maid_runner/core/validate.py", "code": "E701"}],
            pattern_tags=["false-done", "test-weakening"],
        ),
    )
    _write_record(
        incidents_dir / "20260615-010204-second.incident.yaml",
        _record(
            created="2026-06-15T01:02:04Z",
            diagnostics=[
                {"file": "maid_runner/core/validate.py", "code": "E711"},
                {"file": "docs/other.md", "code": "E701"},
            ],
            pattern_tags=["false-done", "runner-gaming"],
        ),
    )
    _write_record(
        incidents_dir / "20260615-010205-excluded.incident.yaml",
        _record(
            created="2026-06-15T01:02:05Z",
            diagnostics=[{"file": "maid_runner/core/validate.py.bak", "code": "E701"}],
            pattern_tags=["false-done", "scope-escape"],
        ),
    )

    suggestions = incidents.suggest_temptations(
        incidents_dir, ["maid_runner/core/validate.py"]
    )

    assert [item.tag for item in suggestions] == [
        "false-done",
        "runner-gaming",
        "test-weakening",
    ]
    assert [item.incident_count for item in suggestions] == [2, 1, 1]
    assert suggestions[0].risk == incidents.TEMPTATION_TEMPLATES["false-done"][0]
    assert suggestions[0].instead == incidents.TEMPTATION_TEMPLATES["false-done"][1]


def test_temptation_templates_cover_closed_vocabulary_and_render_schema_shape():
    from maid_runner.core import incidents

    assert set(incidents.TEMPTATION_TEMPLATES) == set(incidents.PATTERN_TAGS)
    suggestions = tuple(
        incidents.TemptationSuggestion(
            tag=tag,
            incident_count=1,
            risk=template[0],
            instead=template[1],
        )
        for tag, template in incidents.TEMPTATION_TEMPLATES.items()
    )

    rendered = incidents.render_temptation_yaml(suggestions)
    entries = yaml.safe_load(rendered)

    assert all(set(entry) == {"risk", "instead"} for entry in entries)
    for entry in entries:
        jsonschema.validate(entry, _temptation_schema())
        assert entry["risk"].strip()
        assert entry["instead"].strip()
    assert rendered == incidents.render_temptation_yaml(suggestions)


def test_suggest_temptations_empty_store_returns_empty_tuple_and_explicit_empty_yaml(
    tmp_path,
):
    from maid_runner.core import incidents

    assert incidents.suggest_temptations(tmp_path / "absent", ["missing.py"]) == ()
    assert incidents.render_temptation_yaml(()) == "[]\n"
