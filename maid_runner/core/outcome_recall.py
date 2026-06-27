"""Deterministic search over learned Outcome index records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
from typing import Union

from maid_runner.core.manifest import load_manifest_raw
from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord


_PARTIAL_PATH_SHARED_PARENT_WEIGHT = 20
_PARTIAL_TAG_CONTAINMENT_WEIGHT = 10


@dataclass(frozen=True)
class OutcomeRecallQuery:
    text: str | None = None
    tags: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    validation_commands: tuple[str, ...] = ()
    review_text: str | None = None
    manifest_slugs: tuple[str, ...] = ()
    project_root: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "paths", tuple(self.paths))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(
            self,
            "validation_commands",
            tuple(self.validation_commands),
        )
        object.__setattr__(self, "manifest_slugs", tuple(self.manifest_slugs))


@dataclass(frozen=True)
class OutcomeRecallMatch:
    record: OutcomeIndexRecord
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ManifestQuerySignal:
    value: str
    dimension: str
    source_field: str


@dataclass(frozen=True)
class ManifestRecallDerivation:
    manifest_path: str
    signals: tuple[ManifestQuerySignal, ...]
    query: OutcomeRecallQuery


@dataclass(frozen=True)
class PlanPacketSection:
    title: str
    entries: tuple[str, ...]
    omitted_count: int


@dataclass(frozen=True)
class PlanPacket:
    manifest_path: str
    sections: tuple[PlanPacketSection, ...]


def derive_recall_query(
    manifest_path: Union[str, Path],
    project_root: Union[str, Path] = ".",
) -> ManifestRecallDerivation:
    manifest_file = Path(manifest_path)
    root = Path(project_root)
    load_path = manifest_file if manifest_file.is_absolute() else root / manifest_file
    try:
        manifest_data = load_manifest_raw(load_path)
    except Exception as exc:
        raise ValueError(f"Failed to load manifest {manifest_file}: {exc}") from exc
    if not isinstance(manifest_data, dict):
        raise ValueError(f"Manifest {manifest_file} root must be an object")

    signals: list[ManifestQuerySignal] = []

    files = manifest_data.get("files", {})
    if not isinstance(files, dict):
        files = {}

    for section_name, file_specs in (
        ("create", files.get("create", [])),
        ("edit", files.get("edit", [])),
    ):
        if not isinstance(file_specs, list):
            continue
        for file_index, file_spec in enumerate(file_specs):
            if not isinstance(file_spec, dict):
                continue
            file_path = _non_empty_string(file_spec.get("path"))
            if file_path is None:
                continue
            signals.append(
                ManifestQuerySignal(
                    value=file_path,
                    dimension="path",
                    source_field=f"files.{section_name}[{file_index}].path",
                )
            )
            artifacts = file_spec.get("artifacts", [])
            if not isinstance(artifacts, list):
                continue
            for artifact_index, artifact in enumerate(artifacts):
                if not isinstance(artifact, dict):
                    continue
                artifact_kind = _non_empty_string(artifact.get("kind"))
                artifact_name = _non_empty_string(artifact.get("name"))
                if artifact_kind is None or artifact_name is None:
                    continue
                artifact_owner = _non_empty_string(artifact.get("of"))
                qualified_name = (
                    f"{artifact_owner}.{artifact_name}"
                    if artifact_owner is not None
                    else artifact_name
                )
                signals.append(
                    ManifestQuerySignal(
                        value=f"{file_path}:{artifact_kind}:{qualified_name}",
                        dimension="artifact",
                        source_field=(
                            f"files.{section_name}[{file_index}]"
                            f".artifacts[{artifact_index}].name"
                        ),
                    )
                )

    delete_specs = files.get("delete", [])
    if not isinstance(delete_specs, list):
        delete_specs = []
    for file_index, delete_spec in enumerate(delete_specs):
        if not isinstance(delete_spec, dict):
            continue
        delete_path = _non_empty_string(delete_spec.get("path"))
        if delete_path is None:
            continue
        signals.append(
            ManifestQuerySignal(
                value=delete_path,
                dimension="path",
                source_field=f"files.delete[{file_index}].path",
            )
        )

    metadata = manifest_data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    tags = metadata.get("tags", ())
    if isinstance(tags, list):
        for tag_index, tag in enumerate(tags):
            tag_value = _non_empty_string(tag)
            if tag_value is not None:
                signals.append(
                    ManifestQuerySignal(
                        value=tag_value,
                        dimension="tag",
                        source_field=f"metadata.tags[{tag_index}]",
                    )
                )

    validate_commands = manifest_data.get("validate", [])
    if not isinstance(validate_commands, list):
        validate_commands = []
    for command_index, command in enumerate(validate_commands):
        for token in _validate_command_tokens(command):
            token_value = _non_empty_string(token)
            if token_value is not None:
                signals.append(
                    ManifestQuerySignal(
                        value=token_value,
                        dimension="validation-command",
                        source_field=f"validate[{command_index}]",
                    )
                )

    if not signals:
        raise ValueError(
            f"Manifest-derived recall query for {manifest_file} has no recall "
            "query signals"
        )

    project_root_text = str(root)
    query = OutcomeRecallQuery(
        paths=_values_for_dimension(signals, "path"),
        artifacts=_values_for_dimension(signals, "artifact"),
        tags=_values_for_dimension(signals, "tag"),
        validation_commands=_values_for_dimension(signals, "validation-command"),
        project_root=project_root_text,
    )
    return ManifestRecallDerivation(
        manifest_path=_normalize_path(str(load_path), project_root_text),
        signals=tuple(signals),
        query=query,
    )


def build_plan_packet(
    index: OutcomeIndex,
    derivation: ManifestRecallDerivation,
    limit_per_section: int = 5,
) -> PlanPacket:
    matches = recall_outcomes(index, derivation.query, limit=len(index.records))
    query_paths = {
        _normalize_path(path, derivation.query.project_root)
        for path in derivation.query.paths
    }

    related_entries = [
        f"{match.record.manifest_slug} ({match.record.manifest_path})"
        for match in matches
    ]
    status_entries = [
        f"{match.record.manifest_slug}: {match.record.status}" for match in matches
    ]
    lesson_entries: list[str] = []
    for match in matches:
        for lesson in match.record.lessons:
            lesson_paths = tuple(
                _normalize_path(path, derivation.query.project_root)
                for path in lesson.paths
            )
            overlapping_paths = tuple(
                path for path in lesson_paths if path in query_paths
            )
            if overlapping_paths:
                lesson_entries.append(
                    f"{match.record.manifest_slug}: {lesson.summary} "
                    f"(paths: {', '.join(overlapping_paths)})"
                )

    failed_validation_entries: list[str] = []
    for match in matches:
        for evidence in match.record.validation_evidence:
            if evidence.status.lower() == "passed":
                continue
            failed_validation_entries.append(
                f"{match.record.manifest_slug}: {evidence.status}: "
                f"{' '.join(evidence.command)} - {evidence.summary}"
            )

    return PlanPacket(
        manifest_path=derivation.manifest_path,
        sections=(
            _plan_packet_section(
                "Related manifests",
                related_entries,
                limit_per_section,
            ),
            _plan_packet_section(
                "Outcome statuses",
                status_entries,
                limit_per_section,
            ),
            _plan_packet_section(
                "Recurring lessons touching the same paths",
                lesson_entries,
                limit_per_section,
            ),
            _plan_packet_section(
                "Prior validation-command failures",
                failed_validation_entries,
                limit_per_section,
            ),
        ),
    )


def render_plan_packet(packet: PlanPacket) -> str:
    lines = [f"Planning recall packet for {packet.manifest_path}", ""]
    for section_index, section in enumerate(packet.sections):
        if section_index:
            lines.append("")
        lines.append(f"{section.title}:")
        if section.entries:
            lines.extend(f"- {entry}" for entry in section.entries)
        else:
            lines.append("- none")
        if section.omitted_count:
            lines.append(f"... {section.omitted_count} more omitted")
    return "\n".join(lines)


def recall_outcomes(
    index: OutcomeIndex,
    query: OutcomeRecallQuery,
    limit: int = 10,
) -> list[OutcomeRecallMatch]:
    normalized = _NormalizedQuery.from_query(query)
    if normalized.is_empty:
        raise ValueError("Outcome recall query cannot be empty")

    matches: list[OutcomeRecallMatch] = []
    for record in index.records:
        match = _score_record(record, normalized)
        if match is not None:
            matches.append(match)

    matches.sort(
        key=lambda match: (
            -match.score,
            match.record.manifest_slug,
            match.record.manifest_path,
        )
    )
    return matches[: max(0, limit)]


@dataclass(frozen=True)
class _NormalizedQuery:
    text_tokens: tuple[str, ...]
    tags: tuple[str, ...]
    paths: tuple[str, ...]
    artifacts: tuple[str, ...]
    validation_commands: tuple[str, ...]
    review_tokens: tuple[str, ...]
    manifest_slugs: tuple[str, ...]
    project_root: str | None

    @classmethod
    def from_query(cls, query: OutcomeRecallQuery) -> "_NormalizedQuery":
        return cls(
            text_tokens=_tokens(query.text),
            tags=_unique(str(tag).lower() for tag in query.tags if str(tag).strip()),
            paths=_unique(
                _normalize_path(path, query.project_root) for path in query.paths
            ),
            artifacts=_unique(str(artifact) for artifact in query.artifacts),
            validation_commands=_unique(
                str(command)
                for command in query.validation_commands
                if str(command).strip()
            ),
            review_tokens=_tokens(query.review_text),
            manifest_slugs=_unique(
                str(slug) for slug in query.manifest_slugs if str(slug).strip()
            ),
            project_root=query.project_root,
        )

    @property
    def is_empty(self) -> bool:
        return not any(
            (
                self.text_tokens,
                self.tags,
                self.paths,
                self.artifacts,
                self.validation_commands,
                self.review_tokens,
                self.manifest_slugs,
            )
        )


def _score_record(
    record: OutcomeIndexRecord,
    query: _NormalizedQuery,
) -> OutcomeRecallMatch | None:
    reasons: list[str] = []
    score = 0

    slug_score = _score_exact(
        query.manifest_slugs,
        {record.manifest_slug},
        weight=100,
        reason_prefix="manifest_slug",
    )
    if slug_score is None:
        return None
    score += slug_score[0]
    reasons.extend(slug_score[1])

    path_score = _score_paths(
        query.paths,
        {_normalize_path(path, query.project_root) for path in record.declared_paths},
    )
    if path_score is None:
        return None
    score += path_score[0]
    reasons.extend(path_score[1])

    artifact_score = _score_exact(
        query.artifacts,
        set(record.artifacts),
        weight=60,
        reason_prefix="artifact",
    )
    if artifact_score is None:
        return None
    score += artifact_score[0]
    reasons.extend(artifact_score[1])

    tag_score = _score_tags(
        query.tags,
        {tag.lower() for tag in record.tags if str(tag).strip()},
    )
    if tag_score is None:
        return None
    score += tag_score[0]
    reasons.extend(tag_score[1])

    command_score = _score_exact(
        query.validation_commands,
        {token for command in record.validation_commands for token in command},
        weight=30,
        reason_prefix="validation_command",
    )
    if command_score is None:
        return None
    score += command_score[0]
    reasons.extend(command_score[1])

    review_score = _score_text(
        query.review_tokens,
        _review_note_tokens(record),
        weight=20,
        reason_prefix="review_text",
    )
    if review_score is None:
        return None
    score += review_score[0]
    reasons.extend(review_score[1])

    text_score = _score_text(
        query.text_tokens,
        _full_text_tokens(record),
        weight=10,
        reason_prefix="text",
    )
    if text_score is None:
        return None
    score += text_score[0]
    reasons.extend(text_score[1])

    return OutcomeRecallMatch(record=record, score=score, reasons=tuple(reasons))


def _score_exact(
    query_values: tuple[str, ...],
    record_values: set[str],
    *,
    weight: int,
    reason_prefix: str,
) -> tuple[int, list[str]] | None:
    if not query_values:
        return 0, []

    matched = [value for value in query_values if value in record_values]
    if not matched:
        return None
    return (
        len(matched) * weight,
        [f"{reason_prefix}:{value} (+{weight})" for value in matched],
    )


def _score_paths(
    query_values: tuple[str, ...],
    record_values: set[str],
) -> tuple[int, list[str]] | None:
    if not query_values:
        return 0, []

    score = 0
    reasons: list[str] = []

    for value in query_values:
        if value in record_values:
            score += 80
            reasons.append(f"path:{value} (+80)")
    if reasons:
        return score, reasons

    for value in query_values:
        parent = Path(value).parent.as_posix()
        has_same_parent = any(
            record_value != value and Path(record_value).parent.as_posix() == parent
            for record_value in record_values
        )
        if has_same_parent:
            return (
                _PARTIAL_PATH_SHARED_PARENT_WEIGHT,
                [
                    f"path~dir:{parent} (+{_PARTIAL_PATH_SHARED_PARENT_WEIGHT})",
                ],
            )

    return None


def _score_tags(
    query_values: tuple[str, ...],
    record_values: set[str],
) -> tuple[int, list[str]] | None:
    if not query_values:
        return 0, []

    exact_matched = [value for value in query_values if value in record_values]
    if exact_matched:
        return (
            len(exact_matched) * 40,
            [f"tag:{value} (+40)" for value in exact_matched],
        )

    for value in query_values:
        if _has_related_tag(value, record_values):
            return (
                _PARTIAL_TAG_CONTAINMENT_WEIGHT,
                [f"tag~related:{value} (+{_PARTIAL_TAG_CONTAINMENT_WEIGHT})"],
            )
    return None


def _has_related_tag(query_value: str, record_values: set[str]) -> bool:
    return any(
        query_value != record_value
        and (query_value in record_value or record_value in query_value)
        for record_value in record_values
    )


def _score_text(
    query_tokens: tuple[str, ...],
    record_tokens: set[str],
    *,
    weight: int,
    reason_prefix: str,
) -> tuple[int, list[str]] | None:
    if not query_tokens:
        return 0, []

    matched = [token for token in query_tokens if token in record_tokens]
    if not matched:
        return None
    return (
        len(matched) * weight,
        [f"{reason_prefix}:{token} (+{weight})" for token in matched],
    )


def _review_note_tokens(record: OutcomeIndexRecord) -> set[str]:
    return {
        token
        for note in record.review_notes
        for token in _tokens(" ".join((note.source, note.severity, note.summary)))
    }


def _full_text_tokens(record: OutcomeIndexRecord) -> set[str]:
    chunks: list[str] = [
        record.manifest_slug,
        *record.declared_paths,
        *record.artifacts,
    ]
    chunks.extend(summary.summary for summary in record.validation_evidence)
    for lesson in record.lessons:
        chunks.append(lesson.summary)
        chunks.extend(lesson.tags)
    for note in record.review_notes:
        chunks.extend((note.source, note.severity, note.summary))

    return {token for chunk in chunks for token in _tokens(chunk)}


def _tokens(text: str | None) -> tuple[str, ...]:
    if not text:
        return ()
    return _unique(token.lower() for token in re.split(r"[^A-Za-z0-9]+", text) if token)


def _values_for_dimension(
    signals: list[ManifestQuerySignal],
    dimension: str,
) -> tuple[str, ...]:
    return _unique(signal.value for signal in signals if signal.dimension == dimension)


def _plan_packet_section(
    title: str,
    entries: list[str],
    limit_per_section: int,
) -> PlanPacketSection:
    limit = max(0, limit_per_section)
    return PlanPacketSection(
        title=title,
        entries=tuple(entries[:limit]),
        omitted_count=max(0, len(entries) - limit),
    )


def _validate_command_tokens(command) -> tuple[str, ...]:
    if isinstance(command, str):
        return tuple(shlex.split(command))
    if isinstance(command, list):
        return tuple(str(token) for token in command)
    return ()


def _non_empty_string(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_path(path: str, project_root: str | None = None) -> str:
    raw_path = Path(str(path).replace("\\", "/"))
    if raw_path.is_absolute() and project_root is not None:
        try:
            raw_path = raw_path.resolve().relative_to(Path(project_root).resolve())
        except ValueError:
            return raw_path.resolve().as_posix()
    normalized = raw_path.as_posix()
    parts: list[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == ".." and parts:
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _unique(values) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)
