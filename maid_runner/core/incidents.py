"""Deterministic gaming-incident record storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Collection, Union

import yaml

PATTERN_TAGS: tuple[str, ...] = (
    "test-weakening",
    "trivial-test",
    "stub-implementation",
    "contract-renegotiation",
    "scope-escape",
    "runner-gaming",
    "false-done",
)

_RECORD_FIELDS = (
    "incident_version",
    "created",
    "manifest",
    "gates",
    "packet",
    "rejected_diff",
    "chosen_diff",
    "pattern_tags",
    "notes",
)


@dataclass(frozen=True)
class IncidentRecord:
    """One caller-asserted gaming-incident record."""

    incident_version: int
    created: str
    manifest: str
    gates: tuple[str, ...]
    packet: dict
    rejected_diff: str
    chosen_diff: str | None
    pattern_tags: tuple[str, ...]
    notes: str | None


@dataclass(frozen=True)
class StoredIncident:
    """A loaded incident record paired with its storage path."""

    path: str
    record: IncidentRecord


@dataclass(frozen=True)
class DpoExportReport:
    """Deterministic export result with exported and skipped counts."""

    exported_count: int
    skipped_count: int
    output_path: str


def capture_incident(
    incidents_dir: Union[str, Path],
    manifest: str,
    packet: dict,
    rejected_diff: str,
    pattern_tags: Collection[str],
    notes: str | None = None,
    created: str | None = None,
) -> Path:
    manifest_path = Path(manifest)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest path not found: {manifest_path}")
    if not isinstance(packet, dict):
        raise ValueError("packet must be a JSON object")

    created_at = _validate_utc_timestamp(created or _utc_timestamp(), "created")
    record = IncidentRecord(
        incident_version=1,
        created=created_at,
        manifest=_repo_relative_or_original(manifest_path),
        gates=_extract_gates(packet),
        packet=packet,
        rejected_diff=rejected_diff,
        chosen_diff=None,
        pattern_tags=_validate_tags(pattern_tags),
        notes=notes,
    )
    path = (
        Path(incidents_dir)
        / f"{_filename_timestamp(created_at)}-{_manifest_slug(manifest_path)}.incident.yaml"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_record(path, record, overwrite=False)
    return path


def read_incident(incident_path: Union[str, Path]) -> IncidentRecord:
    path = Path(incident_path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Incident path not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: malformed YAML incident record: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"{path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{path}: incident record must be a mapping")
    if set(data.keys()) != set(_RECORD_FIELDS):
        raise ValueError(
            f"{path}: incident record fields must be exactly {', '.join(_RECORD_FIELDS)}"
        )
    try:
        return IncidentRecord(
            incident_version=_require_int(path, data, "incident_version"),
            created=_require_utc_timestamp(path, data, "created"),
            manifest=_require_str(path, data, "manifest"),
            gates=_require_str_list(path, data, "gates"),
            packet=_require_dict(path, data, "packet"),
            rejected_diff=_require_str(path, data, "rejected_diff"),
            chosen_diff=_optional_str(path, data, "chosen_diff"),
            pattern_tags=_validate_tags(_require_str_list(path, data, "pattern_tags")),
            notes=_optional_str(path, data, "notes"),
        )
    except (TypeError, ValueError) as exc:
        if str(exc).startswith(str(path)):
            raise
        raise ValueError(f"{path}: malformed incident record: {exc}") from exc


def update_incident(
    incident_path: Union[str, Path],
    chosen_diff: str,
) -> IncidentRecord:
    path = Path(incident_path)
    record = read_incident(path)
    updated = IncidentRecord(
        incident_version=record.incident_version,
        created=record.created,
        manifest=record.manifest,
        gates=record.gates,
        packet=record.packet,
        rejected_diff=record.rejected_diff,
        chosen_diff=chosen_diff,
        pattern_tags=record.pattern_tags,
        notes=record.notes,
    )
    _write_record(path, updated)
    return updated


def list_incidents(
    incidents_dir: Union[str, Path],
    tag: str | None = None,
) -> "tuple[StoredIncident, ...]":
    if tag is not None:
        _validate_tags((tag,))
    directory = Path(incidents_dir)
    if not directory.exists():
        return ()
    if not directory.is_dir():
        raise ValueError(f"Incident path is not a directory: {directory}")

    records = []
    for path in sorted(directory.glob("*.incident.yaml")):
        record = read_incident(path)
        if tag is None or tag in record.pattern_tags:
            records.append(StoredIncident(path=str(path), record=record))
    return tuple(records)


def export_incidents_dpo(
    incidents_dir: Union[str, Path],
    output_path: Union[str, Path],
) -> DpoExportReport:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    exported_count = 0
    skipped_count = 0
    lines: list[str] = []
    for stored in list_incidents(Path(incidents_dir).resolve()):
        record = stored.record
        if record.chosen_diff is None:
            skipped_count += 1
            continue
        lines.append(
            json.dumps(
                {
                    "context": record.packet.get("diagnostics", []),
                    "rejected": record.rejected_diff,
                    "chosen": record.chosen_diff,
                },
                sort_keys=True,
            )
        )
        exported_count += 1

    output.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return DpoExportReport(
        exported_count=exported_count,
        skipped_count=skipped_count,
        output_path=str(output),
    )


def _write_record(
    path: Path, record: IncidentRecord, *, overwrite: bool = True
) -> None:
    text = yaml.safe_dump(_record_to_dict(record), sort_keys=False)
    if overwrite:
        path.write_text(text, encoding="utf-8")
        return
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
    except FileExistsError as exc:
        raise FileExistsError(f"Incident record already exists: {path}") from exc


def _record_to_dict(record: IncidentRecord) -> dict:
    return {
        "incident_version": record.incident_version,
        "created": record.created,
        "manifest": record.manifest,
        "gates": list(record.gates),
        "packet": record.packet,
        "rejected_diff": record.rejected_diff,
        "chosen_diff": record.chosen_diff,
        "pattern_tags": list(record.pattern_tags),
        "notes": record.notes,
    }


def _validate_tags(tags: Collection[str]) -> tuple[str, ...]:
    normalized = tuple(tags)
    unknown = [tag for tag in normalized if tag not in PATTERN_TAGS]
    if unknown:
        raise ValueError(
            "Unknown pattern tag(s) "
            f"{', '.join(unknown)}. Valid tags: {', '.join(PATTERN_TAGS)}"
        )
    return normalized


def _extract_gates(packet: dict) -> tuple[str, ...]:
    gates: list[str] = []
    for diagnostic in packet.get("diagnostics", ()):
        if not isinstance(diagnostic, dict):
            continue
        code = diagnostic.get("code")
        if code is None:
            continue
        code_text = str(code)
        if code_text not in gates:
            gates.append(code_text)
    return tuple(gates)


def _utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _filename_timestamp(created: str) -> str:
    parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _manifest_slug(manifest_path: Path) -> str:
    name = manifest_path.name
    for suffix in (".manifest.yaml", ".manifest.yml", ".manifest.json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return manifest_path.stem


def _repo_relative_or_original(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _require_str(path: Path, data: dict, key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{path}: field {key} must be a string")
    return value


def _require_int(path: Path, data: dict, key: str) -> int:
    value = data[key]
    if type(value) is not int:
        raise ValueError(f"{path}: field {key} must be an integer")
    return value


def _require_utc_timestamp(path: Path, data: dict, key: str) -> str:
    return _validate_utc_timestamp(
        _require_str(path, data, key), f"{path}: field {key}"
    )


def _validate_utc_timestamp(value: str, label: str) -> str:
    if not value.endswith("Z"):
        raise ValueError(f"{label} must be a UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be a valid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be a UTC timestamp")
    return value


def _optional_str(path: Path, data: dict, key: str) -> str | None:
    value = data[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{path}: field {key} must be a string or null")
    return value


def _require_str_list(path: Path, data: dict, key: str) -> tuple[str, ...]:
    value = data[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{path}: field {key} must be a list of strings")
    return tuple(value)


def _require_dict(path: Path, data: dict, key: str) -> dict:
    value = data[key]
    if not isinstance(value, dict):
        raise ValueError(f"{path}: field {key} must be a mapping")
    return value
