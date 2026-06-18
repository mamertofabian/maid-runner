"""Behavioral tests for daemon-resident validation cache scope."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from maid_runner.__version__ import __version__


def _write_manifest(project: Path, body: str, name: str = "demo.manifest.yaml") -> Path:
    manifest = project / name
    manifest.write_text(body)
    return manifest


def _write_python_project(project: Path, *, function_body: str = "return 'ok'") -> Path:
    source = project / "src" / "demo.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(f"def _demo() -> str:\n    {function_body}\n")
    return source


def _write_typescript_project(project: Path) -> tuple[Path, Path]:
    source = project / "src" / "App.ts"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        'import { Budget } from "@models/Budget";\n\nexport class _App {}\n'
    )

    model = project / "src" / "models" / "Budget.ts"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_text("export class Budget {}\n")

    tsconfig = project / "tsconfig.json"
    tsconfig.write_text(
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@models/*": ["src/models/*"]}}}'
    )
    return source, tsconfig


def _strip_duration_fields(value):
    if isinstance(value, dict):
        return {
            key: _strip_duration_fields(item)
            for key, item in value.items()
            if key not in {"duration_ms", "duration_s", "uptime_s"}
        }
    if isinstance(value, list):
        return [_strip_duration_fields(item) for item in value]
    return value


def test_content_cache_key_includes_content_and_version():
    from maid_runner.daemon.cache import content_cache_key

    key = content_cache_key(b"same", __version__)

    assert key == content_cache_key(b"same", __version__)
    assert key != content_cache_key(b"different", __version__)
    assert key != content_cache_key(b"same", "next-version")


def test_scope_records_hit_for_repeated_identical_validate_request(tmp_path):
    from maid_runner.daemon.cache import DaemonValidationCacheScope

    _write_manifest(
        tmp_path,
        """schema: "2"
goal: cache demo
type: feature
files:
  create: []
validate:
  - python -c 'pass'
""",
    )
    cache = DaemonValidationCacheScope(project_root=tmp_path)

    first = cache.validate("demo.manifest.yaml", mode="schema", use_chain=False)
    second = cache.validate("demo.manifest.yaml", mode="schema", use_chain=False)

    assert _strip_duration_fields(second) == _strip_duration_fields(first)
    assert cache.stats() == {"entries": 1, "hits": 1, "misses": 1}


def test_scope_observes_manifest_edit_as_new_request_identity(tmp_path):
    from maid_runner.daemon.cache import DaemonValidationCacheScope

    manifest = _write_manifest(
        tmp_path,
        """schema: "2"
goal: cache demo
type: feature
files:
  create: []
validate:
  - python -c 'pass'
""",
    )
    cache = DaemonValidationCacheScope(project_root=tmp_path)

    first = cache.validate("demo.manifest.yaml", mode="schema", use_chain=False)
    manifest.write_text(
        """schema: "2"
goal: cache demo changed
type: feature
files:
  create: []
validate:
  - python -c 'pass'
"""
    )
    second = cache.validate("demo.manifest.yaml", mode="schema", use_chain=False)

    assert first["success"] is True
    assert second["success"] is True
    assert cache.stats() == {"entries": 2, "hits": 0, "misses": 2}


def test_scope_observes_source_edit_and_revalidates_result(tmp_path):
    from maid_runner.daemon.cache import DaemonValidationCacheScope

    _write_python_project(tmp_path)
    _write_manifest(
        tmp_path,
        """schema: "2"
goal: cache demo
type: feature
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: _demo
          returns: str
validate:
  - python -c 'pass'
""",
    )
    cache = DaemonValidationCacheScope(project_root=tmp_path)

    first = cache.validate("demo.manifest.yaml", mode="implementation", use_chain=False)
    (tmp_path / "src" / "demo.py").write_text("# demo removed\n")
    second = cache.validate(
        "demo.manifest.yaml", mode="implementation", use_chain=False
    )

    assert first["success"] is True
    assert second["success"] is False
    assert cache.stats() == {"entries": 2, "hits": 0, "misses": 2}


def test_scope_observes_tsconfig_edit_as_new_request_identity(tmp_path):
    from maid_runner.daemon.cache import DaemonValidationCacheScope

    _write_typescript_project(tmp_path)
    _write_manifest(
        tmp_path,
        """schema: "2"
goal: cache demo
type: feature
files:
  create:
    - path: src/App.ts
      artifacts:
        - kind: class
          name: _App
      imports:
        - src/models/Budget
validate:
  - python -c 'pass'
""",
    )
    cache = DaemonValidationCacheScope(project_root=tmp_path)

    first = cache.validate("demo.manifest.yaml", mode="implementation", use_chain=False)
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@models/*": ["src/lib/*"]}}}'
    )
    second = cache.validate(
        "demo.manifest.yaml", mode="implementation", use_chain=False
    )

    assert first["success"] is True
    assert second["success"] is False
    assert cache.stats() == {"entries": 2, "hits": 0, "misses": 2}


def test_clear_resets_scope_entries_and_counters(tmp_path):
    from maid_runner.daemon.cache import DaemonValidationCacheScope

    _write_manifest(
        tmp_path,
        """schema: "2"
goal: cache demo
type: feature
files:
  create: []
validate:
  - python -c 'pass'
""",
    )
    cache = DaemonValidationCacheScope(project_root=tmp_path)
    cache.validate("demo.manifest.yaml", mode="schema", use_chain=False)

    cache.clear()

    assert cache.stats() == {"entries": 0, "hits": 0, "misses": 0}


def test_handlers_share_cache_scope_and_ping_reports_stats(tmp_path):
    from maid_runner.daemon.handlers import (
        configure_context,
        handle_ping,
        handle_validate,
    )

    _write_manifest(
        tmp_path,
        """schema: "2"
goal: cache demo
type: feature
files:
  create: []
validate:
  - python -c 'pass'
""",
    )
    configure_context(tmp_path)

    before = handle_ping({})
    first = handle_validate({"manifest_path": "demo.manifest.yaml", "mode": "schema"})
    second = handle_validate({"manifest_path": "demo.manifest.yaml", "mode": "schema"})
    after = handle_ping({})

    assert before["cache_stats"] == {"entries": 0, "hits": 0, "misses": 0}
    assert _strip_duration_fields(second) == _strip_duration_fields(first)
    assert after["cache_stats"] == {"entries": 1, "hits": 1, "misses": 1}


def test_configure_context_resets_cache_like_daemon_restart(tmp_path):
    from maid_runner.daemon.handlers import (
        configure_context,
        handle_ping,
        handle_validate,
    )

    project_a = tmp_path / "a"
    project_a.mkdir()
    _write_manifest(
        project_a,
        """schema: "2"
goal: cache demo
type: feature
files:
  create: []
validate:
  - python -c 'pass'
""",
    )
    configure_context(project_a)
    handle_validate({"manifest_path": "demo.manifest.yaml", "mode": "schema"})
    populated = deepcopy(handle_ping({})["cache_stats"])

    project_b = tmp_path / "b"
    project_b.mkdir()
    _write_manifest(
        project_b,
        """schema: "2"
goal: cache demo
type: feature
files:
  create: []
validate:
  - python -c 'pass'
""",
    )
    configure_context(project_b)

    assert populated == {"entries": 1, "hits": 0, "misses": 1}
    assert handle_ping({})["cache_stats"] == {"entries": 0, "hits": 0, "misses": 0}
