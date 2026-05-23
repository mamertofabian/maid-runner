"""Per-process artifact collection cache for validation runs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union

from maid_runner.validators.base import BaseValidator, CollectionResult

_CacheKey = tuple[str, str, str, str, str]

_IMPLEMENTATION_CACHE: dict[_CacheKey, CollectionResult] = {}
_BEHAVIORAL_CACHE: dict[_CacheKey, CollectionResult] = {}
_TEST_BODY_CACHE: dict[_CacheKey, dict[str, str]] = {}


def collect_cached_implementation_artifacts(
    validator: BaseValidator,
    source: str,
    file_path: Union[str, Path],
) -> CollectionResult:
    key = _cache_key("implementation", validator, source, file_path)
    cached = _IMPLEMENTATION_CACHE.get(key)
    if cached is not None:
        return cached
    result = validator.collect_implementation_artifacts(source, file_path)
    _IMPLEMENTATION_CACHE[key] = result
    return result


def collect_cached_behavioral_artifacts(
    validator: BaseValidator,
    source: str,
    file_path: Union[str, Path],
) -> CollectionResult:
    key = _cache_key("behavioral", validator, source, file_path)
    cached = _BEHAVIORAL_CACHE.get(key)
    if cached is not None:
        return cached
    result = validator.collect_behavioral_artifacts(source, file_path)
    _BEHAVIORAL_CACHE[key] = result
    return result


def get_cached_test_function_bodies(
    validator: BaseValidator,
    source: str,
    file_path: Union[str, Path],
) -> dict[str, str]:
    key = _cache_key("test-bodies", validator, source, file_path)
    cached = _TEST_BODY_CACHE.get(key)
    if cached is not None:
        return cached
    result = validator.get_test_function_bodies(source, file_path)
    _TEST_BODY_CACHE[key] = result
    return result


def clear_artifact_collection_cache() -> None:
    _IMPLEMENTATION_CACHE.clear()
    _BEHAVIORAL_CACHE.clear()
    _TEST_BODY_CACHE.clear()


def _cache_key(
    kind: str,
    validator: BaseValidator,
    source: str,
    file_path: Union[str, Path],
) -> _CacheKey:
    validator_type = type(validator)
    return (
        kind,
        validator_type.__module__,
        validator_type.__qualname__,
        _normalize_path(file_path),
        _source_fingerprint(source),
    )


def _normalize_path(file_path: Union[str, Path]) -> str:
    return str(file_path).replace("\\", "/")


def _source_fingerprint(source: str) -> str:
    data = source.encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(data).hexdigest()
