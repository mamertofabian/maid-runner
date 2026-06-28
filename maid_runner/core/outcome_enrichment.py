"""Deterministic Outcome enrichment policy and digest serialization."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Union

from maid_runner.core.outcome_insights import (
    OutcomeInsightGroup,
    active_unique_records,
)
from maid_runner.core.outcomes import OutcomeIndex


@dataclass(frozen=True)
class LessonRef:
    manifest_slug: str
    lesson_type: str


@dataclass(frozen=True)
class EnrichmentTheme:
    canonical_name: str
    member_lesson_types: tuple[str, ...]
    summary: str
    source_manifests: tuple[str, ...]


@dataclass(frozen=True)
class DigestEntry:
    theme: str
    summary: str
    source_lessons: tuple[LessonRef, ...]


@dataclass(frozen=True)
class EnrichmentRequest:
    system_prompt: str
    user_prompt: str
    known_lesson_types: tuple[str, ...]
    known_manifest_slugs: tuple[str, ...]


@dataclass(frozen=True)
class EnrichmentDigest:
    schema_version: str
    source_generated_from: str
    advisory: bool
    themes: tuple[EnrichmentTheme, ...]
    digest_entries: tuple[DigestEntry, ...]


def build_enrichment_request(index: OutcomeIndex) -> EnrichmentRequest:
    records = active_unique_records(index)
    lesson_types = sorted(
        {
            lesson.lesson_type
            for record in records
            for lesson in record.lessons
            if lesson.lesson_type.strip()
        }
    )
    manifest_slugs = tuple(sorted({record.manifest_slug for record in records}))
    corpus = []
    for record in records:
        lesson_payload = [
            {
                "lesson_type": lesson.lesson_type,
                "summary": lesson.summary,
                "tags": list(lesson.tags),
                "paths": list(lesson.paths),
            }
            for lesson in record.lessons
        ]
        corpus.append(
            {
                "manifest_slug": record.manifest_slug,
                "manifest_path": record.manifest_path,
                "tags": list(record.tags),
                "lessons": lesson_payload,
            }
        )

    return EnrichmentRequest(
        system_prompt=(
            "cluster and summarize only the provided MAID Outcome lessons. "
            "Do not invent manifests, lesson_types, themes, source lessons, "
            "private context, or validation evidence."
        ),
        user_prompt=json.dumps(
            {
                "generated_from": index.generated_from,
                "known_lesson_types": lesson_types,
                "known_manifest_slugs": list(manifest_slugs),
                "records": corpus,
            },
            indent=2,
            sort_keys=True,
        ),
        known_lesson_types=tuple(lesson_types),
        known_manifest_slugs=manifest_slugs,
    )


def validate_enrichment_digest(
    digest: EnrichmentDigest,
    index: OutcomeIndex,
) -> None:
    if digest.schema_version != _DIGEST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported enrichment schema_version {digest.schema_version!r}"
        )
    if digest.advisory is not True:
        raise ValueError("enrichment digest advisory must be true")

    lesson_pairs = _lesson_pairs(index)
    lesson_types = {lesson_type for _manifest_slug, lesson_type in lesson_pairs}
    manifest_slugs = {manifest_slug for manifest_slug, _lesson_type in lesson_pairs}

    declared_themes = {theme.canonical_name for theme in digest.themes}
    if len(declared_themes) != len(digest.themes):
        raise ValueError("theme canonical_name values must be unique")

    mapped_lesson_types: dict[str, str] = {}
    for theme in digest.themes:
        if not theme.canonical_name.strip():
            raise ValueError("theme canonical_name must not be empty")
        for lesson_type in theme.member_lesson_types:
            if lesson_type not in lesson_types:
                raise ValueError(f"unknown lesson_type {lesson_type!r}")
            existing_theme = mapped_lesson_types.get(lesson_type)
            if existing_theme is not None:
                raise ValueError(
                    f"lesson_type {lesson_type!r} is mapped into both "
                    f"{existing_theme!r} and {theme.canonical_name!r}"
                )
            mapped_lesson_types[lesson_type] = theme.canonical_name
        for manifest_slug in theme.source_manifests:
            if manifest_slug not in manifest_slugs:
                raise ValueError(f"unknown manifest_slug {manifest_slug!r}")
            if not any(
                (manifest_slug, lesson_type) in lesson_pairs
                for lesson_type in theme.member_lesson_types
            ):
                joined_types = ", ".join(theme.member_lesson_types)
                raise ValueError(
                    f"manifest_slug {manifest_slug!r} does not co-occur with "
                    f"theme lesson_type(s): {joined_types}"
                )

    for entry in digest.digest_entries:
        if entry.theme not in declared_themes:
            raise ValueError(f"undeclared digest entry theme {entry.theme!r}")
        for source in entry.source_lessons:
            if (source.manifest_slug, source.lesson_type) not in lesson_pairs:
                raise ValueError(
                    f"source lesson {source.manifest_slug!r}:"
                    f"{source.lesson_type!r} does not co-occur in the index"
                )
            expected_theme = mapped_lesson_types.get(
                source.lesson_type, source.lesson_type
            )
            if expected_theme != entry.theme:
                raise ValueError(
                    f"source lesson {source.manifest_slug!r}:"
                    f"{source.lesson_type!r} belongs to theme "
                    f"{expected_theme!r}, not {entry.theme!r}"
                )


def apply_theme_map(
    index: OutcomeIndex,
    digest: EnrichmentDigest,
) -> "tuple[OutcomeInsightGroup, ...]":
    validate_enrichment_digest(digest, index)
    theme_by_lesson_type = {
        lesson_type: theme.canonical_name
        for theme in digest.themes
        for lesson_type in theme.member_lesson_types
    }
    grouped: dict[str, dict[str, set[str]]] = {}
    for record in active_unique_records(index):
        record_lesson_types = {lesson.lesson_type for lesson in record.lessons}
        record_review_severities = {note.severity for note in record.review_notes}
        for lesson_type in record_lesson_types:
            key = theme_by_lesson_type.get(lesson_type, lesson_type)
            bucket = grouped.setdefault(
                key,
                {
                    "source_manifests": set(),
                    "lesson_types": set(),
                    "review_severities": set(),
                },
            )
            bucket["source_manifests"].add(record.manifest_slug)
            bucket["lesson_types"].update(record_lesson_types)
            bucket["review_severities"].update(record_review_severities)

    groups = [
        OutcomeInsightGroup(
            key=key,
            count=len(values["source_manifests"]),
            source_manifests=tuple(sorted(values["source_manifests"])),
            lesson_types=tuple(sorted(values["lesson_types"])),
            review_severities=tuple(sorted(values["review_severities"])),
        )
        for key, values in grouped.items()
    ]
    groups.sort(key=lambda group: (-group.count, group.key))
    return tuple(groups)


def render_digest_markdown(digest: EnrichmentDigest) -> str:
    lines = [
        "# Outcome Enrichment Digest",
        "",
        f"- schema_version: {digest.schema_version}",
        f"- source_generated_from: {digest.source_generated_from}",
        f"- advisory: {str(digest.advisory).lower()}",
        "",
        "## Themes",
    ]
    if not digest.themes:
        lines.append("- None")
    for theme in digest.themes:
        lines.extend(
            [
                f"- {theme.canonical_name}: {theme.summary}",
                f"  - lesson_types: {', '.join(theme.member_lesson_types)}",
                f"  - source_manifests: {', '.join(theme.source_manifests)}",
            ]
        )

    lines.extend(["", "## Recurring Lessons"])
    if not digest.digest_entries:
        lines.append("- None")
    for entry in digest.digest_entries:
        sources = ", ".join(
            f"{source.manifest_slug}:{source.lesson_type}"
            for source in entry.source_lessons
        )
        lines.append(f"- {entry.theme}: {entry.summary} ({sources})")
    return "\n".join(lines) + "\n"


def digest_is_stale(digest: EnrichmentDigest, index: OutcomeIndex) -> bool:
    return digest.source_generated_from != index.generated_from


def enrichment_digest_to_dict(digest: EnrichmentDigest) -> dict:
    return {
        "advisory": digest.advisory,
        "digest_entries": [
            {
                "source_lessons": [
                    {
                        "lesson_type": source.lesson_type,
                        "manifest_slug": source.manifest_slug,
                    }
                    for source in entry.source_lessons
                ],
                "summary": entry.summary,
                "theme": entry.theme,
            }
            for entry in digest.digest_entries
        ],
        "schema_version": digest.schema_version,
        "source_generated_from": digest.source_generated_from,
        "themes": [
            {
                "canonical_name": theme.canonical_name,
                "member_lesson_types": list(theme.member_lesson_types),
                "source_manifests": list(theme.source_manifests),
                "summary": theme.summary,
            }
            for theme in digest.themes
        ],
    }


def enrichment_digest_from_dict(data: dict) -> EnrichmentDigest:
    if not isinstance(data, dict):
        raise ValueError("digest root must be an object")
    return EnrichmentDigest(
        schema_version=_expect_str(data, "schema_version"),
        source_generated_from=_expect_str(data, "source_generated_from"),
        advisory=_expect_bool(data, "advisory"),
        themes=tuple(
            EnrichmentTheme(
                canonical_name=_expect_str(theme, "canonical_name"),
                member_lesson_types=_expect_str_tuple(theme, "member_lesson_types"),
                summary=_expect_str(theme, "summary"),
                source_manifests=_expect_str_tuple(theme, "source_manifests"),
            )
            for theme in _expect_object_list(data, "themes")
        ),
        digest_entries=tuple(
            DigestEntry(
                theme=_expect_str(entry, "theme"),
                summary=_expect_str(entry, "summary"),
                source_lessons=tuple(
                    LessonRef(
                        manifest_slug=_expect_str(source, "manifest_slug"),
                        lesson_type=_expect_str(source, "lesson_type"),
                    )
                    for source in _expect_nested_object_list(entry, "source_lessons")
                ),
            )
            for entry in _expect_object_list(data, "digest_entries")
        ),
    )


def read_enrichment_digest(digest_path: Union[str, Path]) -> EnrichmentDigest:
    path = Path(digest_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return enrichment_digest_from_dict(data)
    except Exception as exc:
        raise ValueError(f"Malformed enrichment digest at {path}: {exc}") from exc


def write_enrichment_digest(
    digest: EnrichmentDigest,
    output_path: Union[str, Path],
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(enrichment_digest_to_dict(digest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


_DIGEST_SCHEMA_VERSION = "1"


def _lesson_pairs(index: OutcomeIndex) -> set[tuple[str, str]]:
    return {
        (record.manifest_slug, lesson.lesson_type)
        for record in active_unique_records(index)
        for lesson in record.lessons
    }


def _expect_str(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _expect_bool(data: dict, key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
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


def _expect_nested_object_list(data: dict, key: str) -> list[dict]:
    return _expect_object_list(data, key)


def _expect_str_tuple(data: dict, key: str) -> tuple[str, ...]:
    values = _expect_list(data, key)
    if not all(isinstance(item, str) for item in values):
        raise ValueError(f"{key} must be a list of strings")
    return tuple(values)
