"""Behavioral tests for rendering draft manifests from diff scope."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

from maid_runner.core.diff_scope import (
    DiffScopeBaseline,
    DiffScopeResult,
    FileArtifactDelta,
)
from maid_runner.core.manifest import validate_manifest_schema
from maid_runner.core.manifest_from_diff import (
    FromDiffRenderError,
    build_from_diff_manifest,
    default_from_diff_slug,
    write_from_diff_manifest,
)
from maid_runner.core.types import ArgSpec, ArtifactKind, ArtifactSpec


def _git(project_dir: Path, *argv: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            *argv,
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(project_dir: Path) -> None:
    _git(project_dir, "init")


def _commit_all(project_dir: Path, message: str = "commit") -> str:
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-m", message)
    return _git(project_dir, "rev-parse", "HEAD")


def _write(project_dir: Path, rel_path: str, content: str) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _artifact(
    name: str,
    *,
    kind: ArtifactKind = ArtifactKind.FUNCTION,
    args: tuple[ArgSpec, ...] = (),
    returns: str | None = None,
    of: str | None = None,
) -> ArtifactSpec:
    return ArtifactSpec(kind=kind, name=name, args=args, returns=returns, of=of)


def test_build_from_diff_manifest_renders_schema_valid_review_marked_draft(tmp_path):
    diff = DiffScopeResult(
        created=("README.md", "src/new.py"),
        edited=("src/edited.py",),
        deleted=("src/old.py",),
        deltas=(
            FileArtifactDelta(
                path="src/new.py",
                added=(
                    _artifact(
                        "create_user",
                        args=(
                            ArgSpec(name="email", type="str"),
                            ArgSpec(name="nickname", type="str", default=""),
                        ),
                        returns="User",
                    ),
                ),
            ),
            FileArtifactDelta(
                path="src/edited.py",
                added=(_artifact("fresh"),),
                signature_changed=(_artifact("changed", returns="str"),),
            ),
        ),
    )

    data = build_from_diff_manifest(diff, tmp_path, "from-diff-demo")

    assert data["goal"] == "TODO: describe this change"
    assert data["metadata"]["generated_by"] == "maid-manifest-from-diff"
    assert data["metadata"]["needs_review"] is True
    assert data["validate"] == [
        "maid validate manifests/drafts/from-diff-demo.manifest.yaml --mode schema --quiet"
    ]
    assert [entry["path"] for entry in data["files"]["create"]] == [
        "README.md",
        "src/new.py",
    ]
    readme_artifact = data["files"]["create"][0]["artifacts"][0]
    assert readme_artifact["kind"] == "attribute"
    assert readme_artifact["name"].startswith("_")
    created_artifact = data["files"]["create"][1]["artifacts"][0]
    assert created_artifact == {
        "kind": "function",
        "name": "create_user",
        "args": [
            {"name": "email", "type": "str"},
            {"name": "nickname", "type": "str", "default": ""},
        ],
        "returns": "User",
    }
    assert [artifact["name"] for artifact in data["files"]["edit"][0]["artifacts"]] == [
        "changed",
        "fresh",
    ]
    assert data["files"]["delete"] == [
        {"path": "src/old.py", "reason": "File was removed in the diff."}
    ]
    assert validate_manifest_schema(data) == []


def test_build_from_diff_manifest_quotes_slug_path_in_validate_command(tmp_path):
    diff = DiffScopeResult(created=("src/new.py",), edited=(), deleted=(), deltas=())

    data = build_from_diff_manifest(diff, tmp_path, "my demo")

    assert shlex.split(data["validate"][0]) == [
        "maid",
        "validate",
        "manifests/drafts/my demo.manifest.yaml",
        "--mode",
        "schema",
        "--quiet",
    ]


def test_build_from_diff_manifest_rejects_empty_diff(tmp_path):
    diff = DiffScopeResult(created=(), edited=(), deleted=(), deltas=())

    with pytest.raises(FromDiffRenderError, match="No changed files"):
        build_from_diff_manifest(diff, tmp_path, "empty")


def test_build_from_diff_manifest_is_deterministic(tmp_path):
    diff = DiffScopeResult(
        created=("z.py", "a.py"),
        edited=("b.py",),
        deleted=(),
        deltas=(
            FileArtifactDelta(path="z.py", added=(_artifact("zed"),)),
            FileArtifactDelta(path="a.py", added=(_artifact("alpha"),)),
            FileArtifactDelta(
                path="b.py",
                added=(_artifact("beta"), _artifact("alpha")),
            ),
        ),
    )

    first = yaml.safe_dump(
        build_from_diff_manifest(diff, tmp_path, "same-slug"),
        default_flow_style=False,
        sort_keys=False,
    )
    second = yaml.safe_dump(
        build_from_diff_manifest(diff, tmp_path, "same-slug"),
        default_flow_style=False,
        sort_keys=False,
    )

    assert first == second
    assert first.index("a.py") < first.index("z.py")


def test_default_from_diff_slug_uses_resolved_since_commit_hash(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/base.py", "def base() -> None:\n    return None\n")
    sha = _commit_all(tmp_path, "baseline")

    slug = default_from_diff_slug(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=sha),
    )

    assert re.fullmatch(r"from-diff-\d{4}-\d{2}-\d{2}-[0-9a-f]{7,}", slug)
    assert slug.endswith(sha[:7])


def test_write_from_diff_manifest_refuses_existing_output_without_force(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "manifests" / "drafts" / "demo.manifest.yaml"
    output.parent.mkdir(parents=True)
    output.write_text("existing\n")
    data = build_from_diff_manifest(
        DiffScopeResult(created=("src/new.py",), edited=(), deleted=(), deltas=()),
        tmp_path,
        "demo",
    )

    with pytest.raises(FromDiffRenderError, match="already exists"):
        write_from_diff_manifest(data, output)

    assert output.read_text() == "existing\n"


def test_write_from_diff_manifest_force_overwrites_with_stable_yaml(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "manifests" / "drafts" / "demo.manifest.yaml"
    output.parent.mkdir(parents=True)
    output.write_text("existing\n")
    data = build_from_diff_manifest(
        DiffScopeResult(created=("src/new.py",), edited=(), deleted=(), deltas=()),
        tmp_path,
        "demo",
    )

    path = write_from_diff_manifest(data, output, force=True)
    first = output.read_text()
    path_again = write_from_diff_manifest(data, output, force=True)

    assert path == output
    assert path_again == output
    assert output.read_text() == first
    assert yaml.safe_load(first)["metadata"]["needs_review"] is True


def test_write_from_diff_manifest_writes_nothing_when_schema_invalid(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "manifests" / "drafts" / "bad.manifest.yaml"
    data = {
        "schema": "2",
        "goal": "TODO: describe this change",
        "files": {"create": []},
    }

    with pytest.raises(FromDiffRenderError, match="schema"):
        write_from_diff_manifest(data, output)

    assert not output.exists()


def test_write_from_diff_manifest_rejects_non_draft_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "manifests" / "active.manifest.yaml"
    data = build_from_diff_manifest(
        DiffScopeResult(created=("src/new.py",), edited=(), deleted=(), deltas=()),
        tmp_path,
        "demo",
    )

    with pytest.raises(FromDiffRenderError, match="manifests/drafts"):
        write_from_diff_manifest(data, output, force=True)

    assert not output.exists()


def test_write_from_diff_manifest_rejects_draft_path_outside_project(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    output = (
        tmp_path.parent / "other" / "manifests" / "drafts" / "outside.manifest.yaml"
    )
    data = build_from_diff_manifest(
        DiffScopeResult(created=("src/new.py",), edited=(), deleted=(), deltas=()),
        tmp_path,
        "demo",
    )

    with pytest.raises(FromDiffRenderError, match="manifests/drafts"):
        write_from_diff_manifest(data, output, force=True)

    assert not output.exists()
