"""Deterministic indexes for explicit manifest Outcome records."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Collection, Iterable, Union

from maid_runner.core.manifest import load_manifest, slug_from_path
from maid_runner.core.types import (
    Manifest,
    OutcomeLesson,
    OutcomeReviewNote,
    OutcomeStatus,
    OutcomeValidationEvidence,
)


@dataclass(frozen=True)
class OutcomeIndexRecord:
    manifest_slug: str
    manifest_path: str
    status: str
    lifecycle_status: str
    superseded_by: str | None
    task_type: str | None
    created: str | None
    completed_at: str | None
    tags: tuple[str, ...]
    declared_paths: tuple[str, ...]
    artifacts: tuple[str, ...]
    validation_commands: tuple[tuple[str, ...], ...]
    validation_evidence: tuple[OutcomeValidationEvidence, ...]
    lessons: tuple[OutcomeLesson, ...]
    review_notes: tuple[OutcomeReviewNote, ...]
    source_fingerprint: str


@dataclass(frozen=True)
class OutcomeIndex:
    schema_version: str
    generated_from: str
    included_statuses: tuple[str, ...]
    manifest_dir: str
    project_root: str
    records: tuple[OutcomeIndexRecord, ...]


def build_outcome_index(
    manifest_dir: Union[str, Path],
    project_root: Union[str, Path] = ".",
    include_statuses: Collection[str] | None = None,
) -> OutcomeIndex:
    index, _skipped = _build_outcome_index_with_stats(
        manifest_dir,
        project_root=project_root,
        include_statuses=include_statuses,
    )
    return index


def write_outcome_index(index: OutcomeIndex, output_path: Union[str, Path]) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_index_to_dict(index), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_outcome_index(index_path: Union[str, Path]) -> OutcomeIndex:
    path = Path(index_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _index_from_dict(data)
    except Exception as exc:
        raise ValueError(f"Malformed Outcome index at {path}: {exc}") from exc


def outcome_index_is_stale(
    index_path: Union[str, Path],
    manifest_dir: Union[str, Path],
    project_root: Union[str, Path] = ".",
) -> bool:
    index = read_outcome_index(index_path)
    checked_manifest_dir = _display_path(Path(manifest_dir), Path(project_root))
    checked_project_root = _display_project_root(Path(project_root))
    if index.manifest_dir != checked_manifest_dir:
        return True
    if index.project_root != checked_project_root:
        return True

    root = Path(project_root)
    for record in index.records:
        source_path = root / record.manifest_path
        if not source_path.exists():
            return True
        if _source_fingerprint(source_path) != record.source_fingerprint:
            return True

    current = build_outcome_index(
        manifest_dir,
        project_root=project_root,
        include_statuses=index.included_statuses,
    )
    return current.generated_from != index.generated_from


def _build_outcome_index_with_stats(
    manifest_dir: Union[str, Path],
    *,
    project_root: Union[str, Path] = ".",
    include_statuses: Collection[str] | None = None,
) -> tuple[OutcomeIndex, int]:
    statuses = _normalize_status_filter(include_statuses)
    root = Path(project_root)
    manifest_root = Path(manifest_dir)
    records: list[OutcomeIndexRecord] = []
    skipped = 0

    loaded_manifests = [
        (path, load_manifest(path)) for path in _manifest_paths(manifest_root)
    ]
    superseded_by = _superseded_by_map(manifest for _path, manifest in loaded_manifests)

    for path, manifest in loaded_manifests:
        if manifest.outcome is None:
            continue

        lifecycle_status = _lifecycle_status(manifest)
        if lifecycle_status in _INACTIVE_LIFECYCLE_STATUSES:
            skipped += 1
            continue
        if manifest.outcome.status.value not in statuses:
            skipped += 1
            continue

        records.append(
            _record_from_manifest(
                manifest,
                path,
                root,
                lifecycle_status,
                superseded_by.get(manifest.slug),
            )
        )

    records.sort(key=lambda record: (record.manifest_slug, record.manifest_path))
    index = OutcomeIndex(
        schema_version=_SCHEMA_VERSION,
        generated_from=_generated_from(records, statuses),
        included_statuses=tuple(sorted(statuses)),
        manifest_dir=_display_path(manifest_root, root),
        project_root=_display_project_root(root),
        records=tuple(records),
    )
    return index, skipped


_SCHEMA_VERSION = "1"
_DEFAULT_STATUSES = frozenset({OutcomeStatus.COMPLETED.value})
_ALL_STATUSES = frozenset(status.value for status in OutcomeStatus)
_INACTIVE_LIFECYCLE_STATUSES = frozenset(
    {"archive", "archived", "draft", "epic", "legacy", "planning"}
)
_INACTIVE_MANIFEST_DIR_NAMES = frozenset({"drafts", "v1-archive"})
_MANIFEST_SUFFIXES = (".manifest.yaml", ".manifest.yml", ".manifest.json")


def _normalize_status_filter(
    include_statuses: Collection[str] | None,
) -> frozenset[str]:
    if include_statuses is None:
        return _DEFAULT_STATUSES

    statuses = frozenset(str(status) for status in include_statuses)
    invalid = sorted(statuses - _ALL_STATUSES)
    if invalid:
        raise ValueError(f"Unsupported Outcome status filter(s): {', '.join(invalid)}")
    return statuses


def _manifest_paths(manifest_dir: Path) -> list[Path]:
    if not manifest_dir.exists():
        raise FileNotFoundError(f"Manifest directory not found: {manifest_dir}")
    if not manifest_dir.is_dir():
        raise NotADirectoryError(
            f"Manifest directory is not a directory: {manifest_dir}"
        )

    return sorted(
        (
            path
            for path in manifest_dir.rglob("*")
            if path.is_file()
            and any(path.name.endswith(suffix) for suffix in _MANIFEST_SUFFIXES)
            and not _is_in_inactive_child_dir(path, manifest_dir)
        ),
        key=lambda path: (slug_from_path(path), str(path)),
    )


def _is_in_inactive_child_dir(path: Path, manifest_dir: Path) -> bool:
    try:
        relative = path.relative_to(manifest_dir)
    except ValueError:
        return False
    return any(part in _INACTIVE_MANIFEST_DIR_NAMES for part in relative.parts[:-1])


def _superseded_by_map(manifests: Iterable[Manifest]) -> dict[str, str]:
    superseded_by: dict[str, str] = {}
    for manifest in manifests:
        for superseded_slug in manifest.supersedes:
            superseded_by[superseded_slug] = manifest.slug
    return superseded_by


def _record_from_manifest(
    manifest: Manifest,
    path: Path,
    project_root: Path,
    lifecycle_status: str,
    superseded_by: str | None,
) -> OutcomeIndexRecord:
    assert manifest.outcome is not None
    return OutcomeIndexRecord(
        manifest_slug=manifest.slug,
        manifest_path=_display_path(path, project_root),
        status=manifest.outcome.status.value,
        lifecycle_status=lifecycle_status,
        superseded_by=superseded_by,
        task_type=manifest.task_type.value if manifest.task_type is not None else None,
        created=manifest.created,
        completed_at=manifest.outcome.completed_at,
        tags=_manifest_tags(manifest),
        declared_paths=tuple(sorted(manifest.all_referenced_paths)),
        artifacts=_artifact_names(manifest),
        validation_commands=manifest.validate_commands,
        validation_evidence=manifest.outcome.validation,
        lessons=manifest.outcome.lessons,
        review_notes=manifest.outcome.review_notes,
        source_fingerprint=_source_fingerprint(path),
    )


def _manifest_tags(manifest: Manifest) -> tuple[str, ...]:
    metadata = manifest.metadata if isinstance(manifest.metadata, dict) else {}
    tags = metadata.get("tags", ())
    if not isinstance(tags, list):
        return ()
    return tuple(sorted(str(tag) for tag in tags))


def _artifact_names(manifest: Manifest) -> tuple[str, ...]:
    names: list[str] = []
    for file_spec in manifest.all_file_specs:
        for artifact in file_spec.artifacts:
            names.append(
                f"{file_spec.path}:{artifact.kind.value}:{artifact.qualified_name}"
            )
    return tuple(sorted(names))


def _lifecycle_status(manifest: Manifest) -> str:
    metadata = manifest.metadata if isinstance(manifest.metadata, dict) else {}
    status = str(metadata.get("status", "")).strip().lower()
    return status or "active"


def _source_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _generated_from(
    records: list[OutcomeIndexRecord],
    included_statuses: Collection[str],
) -> str:
    payload = {
        "included_statuses": sorted(included_statuses),
        "records": [
            {
                "manifest_path": record.manifest_path,
                "manifest_slug": record.manifest_slug,
                "source_fingerprint": record.source_fingerprint,
                "status": record.status,
                "superseded_by": record.superseded_by,
            }
            for record in records
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _display_path(path: Path, project_root: Path) -> str:
    try:
        display = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        display = path
    text = display.as_posix()
    return "." if text in {"", "."} else text


def _display_project_root(project_root: Path) -> str:
    return project_root.resolve().as_posix()


def _index_to_dict(index: OutcomeIndex) -> dict:
    return {
        "generated_from": index.generated_from,
        "included_statuses": list(index.included_statuses),
        "manifest_dir": index.manifest_dir,
        "project_root": index.project_root,
        "records": [_record_to_dict(record) for record in index.records],
        "schema_version": index.schema_version,
    }


def _record_to_dict(record: OutcomeIndexRecord) -> dict:
    return {
        "artifacts": list(record.artifacts),
        "completed_at": record.completed_at,
        "created": record.created,
        "declared_paths": list(record.declared_paths),
        "lifecycle_status": record.lifecycle_status,
        "lessons": [_lesson_to_dict(lesson) for lesson in record.lessons],
        "manifest_path": record.manifest_path,
        "manifest_slug": record.manifest_slug,
        "review_notes": [_review_note_to_dict(note) for note in record.review_notes],
        "source_fingerprint": record.source_fingerprint,
        "status": record.status,
        "superseded_by": record.superseded_by,
        "tags": list(record.tags),
        "task_type": record.task_type,
        "validation_commands": [
            list(command) for command in record.validation_commands
        ],
        "validation_evidence": [
            _validation_evidence_to_dict(evidence)
            for evidence in record.validation_evidence
        ],
    }


def _lesson_to_dict(lesson: OutcomeLesson) -> dict:
    return {
        "lesson_type": lesson.lesson_type,
        "paths": list(lesson.paths),
        "summary": lesson.summary,
        "tags": list(lesson.tags),
    }


def _review_note_to_dict(note: OutcomeReviewNote) -> dict:
    return {
        "severity": note.severity,
        "source": note.source,
        "summary": note.summary,
    }


def _validation_evidence_to_dict(evidence: OutcomeValidationEvidence) -> dict:
    return {
        "command": list(evidence.command),
        "status": evidence.status,
        "summary": evidence.summary,
    }


def _index_from_dict(data: dict) -> OutcomeIndex:
    if not isinstance(data, dict):
        raise ValueError("index root must be an object")
    if data.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version {data.get('schema_version')!r}")
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    return OutcomeIndex(
        schema_version=_expect_str(data, "schema_version"),
        generated_from=_expect_str(data, "generated_from"),
        included_statuses=_expect_status_tuple(data, "included_statuses"),
        manifest_dir=_expect_str(data, "manifest_dir"),
        project_root=_expect_str(data, "project_root"),
        records=tuple(_record_from_dict(record) for record in records),
    )


def _record_from_dict(data: dict) -> OutcomeIndexRecord:
    if not isinstance(data, dict):
        raise ValueError("record must be an object")
    status = _expect_str(data, "status")
    if status not in _ALL_STATUSES:
        raise ValueError(f"unsupported Outcome status {status!r}")
    return OutcomeIndexRecord(
        manifest_slug=_expect_str(data, "manifest_slug"),
        manifest_path=_expect_str(data, "manifest_path"),
        status=status,
        lifecycle_status=_expect_str(data, "lifecycle_status"),
        superseded_by=_expect_optional_str(data, "superseded_by"),
        task_type=_expect_optional_str(data, "task_type"),
        created=_expect_optional_str(data, "created"),
        completed_at=_expect_optional_str(data, "completed_at"),
        tags=_expect_str_tuple(data, "tags"),
        declared_paths=_expect_str_tuple(data, "declared_paths"),
        artifacts=_expect_str_tuple(data, "artifacts"),
        validation_commands=tuple(
            tuple(_expect_sequence_item(command, "validation_commands"))
            for command in _expect_list(data, "validation_commands")
        ),
        validation_evidence=tuple(
            OutcomeValidationEvidence(
                command=tuple(_expect_sequence_item(item.get("command"), "command")),
                status=_expect_str(item, "status"),
                summary=_expect_str(item, "summary"),
            )
            for item in _expect_object_list(data, "validation_evidence")
        ),
        lessons=tuple(
            OutcomeLesson(
                lesson_type=_expect_str(item, "lesson_type"),
                summary=_expect_str(item, "summary"),
                tags=_expect_str_tuple(item, "tags"),
                paths=_expect_str_tuple(item, "paths"),
            )
            for item in _expect_object_list(data, "lessons")
        ),
        review_notes=tuple(
            OutcomeReviewNote(
                source=_expect_str(item, "source"),
                severity=_expect_str(item, "severity"),
                summary=_expect_str(item, "summary"),
            )
            for item in _expect_object_list(data, "review_notes")
        ),
        source_fingerprint=_expect_str(data, "source_fingerprint"),
    )


def _expect_str(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _expect_optional_str(data: dict, key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


def _expect_list(data: dict, key: str) -> list:
    value = data.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _expect_object_list(data: dict, key: str) -> list[dict]:
    values = _expect_list(data, key)
    if not all(isinstance(item, dict) for item in values):
        raise ValueError(f"{key} must contain objects")
    return values


def _expect_str_tuple(data: dict, key: str) -> tuple[str, ...]:
    return tuple(_expect_sequence_item(data.get(key), key))


def _expect_status_tuple(data: dict, key: str) -> tuple[str, ...]:
    statuses = _expect_str_tuple(data, key)
    invalid = sorted(set(statuses) - _ALL_STATUSES)
    if invalid:
        raise ValueError(f"unsupported Outcome status {invalid[0]!r}")
    return tuple(sorted(statuses))


def _expect_sequence_item(value: object, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return value
