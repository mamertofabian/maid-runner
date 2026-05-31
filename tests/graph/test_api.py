"""Behavioral tests for the runner-owned graph API surface."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml


def test_build_graph_from_manifest_dir_uses_active_manifest_chain(
    tmp_path: Path,
) -> None:
    from maid_runner.graph.api import build_graph_from_manifest_dir
    from maid_runner.graph import build_graph_from_manifest_dir as exported_build

    manifest_dir = _write_manifest_chain(tmp_path)

    graph = build_graph_from_manifest_dir(manifest_dir, project_root=tmp_path)

    assert exported_build is build_graph_from_manifest_dir
    assert graph.get_node("manifest:replacement") is not None
    assert graph.get_node("manifest:original") is None
    assert graph.get_node("artifact:src/service.py:class:ServiceV2") is not None


def test_build_graph_from_manifest_dir_resolves_relative_dir_against_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.graph.api import build_graph_from_manifest_dir

    project_root = tmp_path / "project"
    project_root.mkdir()
    _write_manifest_chain(project_root)
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    graph = build_graph_from_manifest_dir("manifests", project_root=project_root)

    assert Path.cwd() == other_cwd
    assert graph.get_node("manifest:replacement") is not None


def test_build_graph_from_manifest_dir_rejects_manifest_load_errors(
    tmp_path: Path,
) -> None:
    from maid_runner.graph.api import build_graph_from_manifest_dir

    manifest_dir = _write_manifest_chain(tmp_path)
    (manifest_dir / "bad.manifest.yaml").write_text("schema: [", encoding="utf-8")

    with pytest.raises(ValueError, match="bad.manifest.yaml"):
        build_graph_from_manifest_dir(manifest_dir, project_root=tmp_path)


def test_query_graph_returns_json_serializable_definition_result(
    tmp_path: Path,
) -> None:
    from maid_runner.graph.api import (
        build_graph_from_manifest_dir,
        graph_stats,
        query_graph,
    )
    from maid_runner.graph import graph_stats as exported_stats
    from maid_runner.graph import query_graph as exported_query

    manifest_dir = _write_manifest_chain(tmp_path)
    graph = build_graph_from_manifest_dir(manifest_dir, project_root=tmp_path)

    result = query_graph(graph, "what defines ServiceV2")
    stats = graph_stats(graph)

    assert exported_query is query_graph
    assert exported_stats is graph_stats
    json.dumps(result)
    assert result["success"] is True
    assert result["query_type"] == "find_definition"
    assert result["results"]["node"]["id"] == "artifact:src/service.py:class:ServiceV2"
    assert stats["nodes"] >= 3
    assert result["stats"]["node_types"]["artifact"] >= 1


def test_serialize_graph_returns_deterministic_json_without_uuid_edge_ids(
    tmp_path: Path,
) -> None:
    from maid_runner.graph.api import build_graph_from_manifest_dir, serialize_graph
    from maid_runner.graph import serialize_graph as exported_serialize

    manifest_dir = _write_manifest_chain(tmp_path)

    first_graph = build_graph_from_manifest_dir(manifest_dir, project_root=tmp_path)
    second_graph = build_graph_from_manifest_dir(manifest_dir, project_root=tmp_path)

    first = serialize_graph(first_graph, "json")
    second = serialize_graph(second_graph, "json")

    assert exported_serialize is serialize_graph
    assert first == second
    payload = json.loads(first)
    assert payload["stats"]["nodes"] == len(payload["nodes"])
    assert all(edge["id"].startswith("edge:") for edge in payload["edges"])


def test_analyze_file_dependencies_includes_stats_manifest_and_artifacts(
    tmp_path: Path,
) -> None:
    from maid_runner.graph.api import (
        analyze_file_dependencies,
        build_graph_from_manifest_dir,
    )
    from maid_runner.graph import analyze_file_dependencies as exported_analyze

    manifest_dir = _write_manifest_chain(tmp_path)
    graph = build_graph_from_manifest_dir(manifest_dir, project_root=tmp_path)

    result = analyze_file_dependencies(graph, "src/service.py")

    assert exported_analyze is analyze_file_dependencies
    assert result["file"] == "src/service.py"
    assert result["manifests"] == ["manifest:replacement"]
    assert result["artifacts"] == ["ServiceV2", "run"]
    assert result["stats"]["edge_types"]["edits"] == 1


def test_export_graph_writes_supported_dot_format(tmp_path: Path) -> None:
    from maid_runner.graph.api import build_graph_from_manifest_dir, export_graph
    from maid_runner.graph import export_graph as exported_export

    manifest_dir = _write_manifest_chain(tmp_path)
    graph = build_graph_from_manifest_dir(manifest_dir, project_root=tmp_path)
    output_path = tmp_path / "graph.dot"

    content = export_graph(graph, "dot", output_path=output_path)

    assert exported_export is export_graph
    assert content.startswith("digraph G")
    assert output_path.read_text(encoding="utf-8") == content


def _write_manifest_chain(tmp_path: Path) -> Path:
    os.makedirs(tmp_path, exist_ok=True)
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir,
        "original",
        goal="Original service",
        files_create=[
            {
                "path": "src/service.py",
                "artifacts": [
                    {"kind": "class", "name": "Service"},
                ],
            }
        ],
    )
    _write_manifest(
        manifest_dir,
        "replacement",
        goal="Replacement service",
        supersedes=["original"],
        files_edit=[
            {
                "path": "src/service.py",
                "artifacts": [
                    {"kind": "class", "name": "ServiceV2"},
                    {
                        "kind": "method",
                        "name": "run",
                        "of": "ServiceV2",
                        "args": [],
                        "returns": "None",
                    },
                ],
            }
        ],
        files_read=["README.md"],
    )
    return manifest_dir


def _write_manifest(
    manifest_dir: Path,
    slug: str,
    *,
    goal: str,
    supersedes: list[str] | None = None,
    files_create: list[dict] | None = None,
    files_edit: list[dict] | None = None,
    files_read: list[str] | None = None,
) -> None:
    data = {
        "schema": "2",
        "goal": goal,
        "type": "feature",
        "created": "2026-05-31T00:00:00+00:00",
        "files": {},
        "validate": ["uv run python -m pytest -q tests/graph/test_api.py"],
    }
    if supersedes:
        data["supersedes"] = supersedes
    if files_create:
        data["files"]["create"] = files_create
    if files_edit:
        data["files"]["edit"] = files_edit
    if files_read:
        data["files"]["read"] = files_read
    (manifest_dir / f"{slug}.manifest.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False),
        encoding="utf-8",
    )
