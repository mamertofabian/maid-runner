"""Subproject Node dependencies keep their own identity in public snapshots."""

import json
import os
import shutil
from contextlib import nullcontext
from pathlib import Path

import pytest
import yaml

from maid_runner.core._knockout_snapshot import (
    MaterializedProjectSnapshotBackend,
    SharedEnvironmentProjectSnapshotBackend,
    WorkerRetainedProjectSnapshotBackend,
)
from maid_runner.core.knockout import KnockoutCommandExecutor, run_knockout_batch
from maid_runner.core.manifest import load_manifest


def _package(directory: Path, value: str, commonjs: bool = False) -> None:
    directory.mkdir(parents=True)
    extension = "cjs" if commonjs else "js"
    (directory / "package.json").write_text(
        json.dumps(
            {
                "name": directory.name,
                "version": "1.0.0",
                "type": "commonjs" if commonjs else "module",
                "exports": f"./index.{extension}",
            }
        )
    )
    (directory / f"index.{extension}").write_text(
        f"exports.value = {value!r};\n"
        if commonjs
        else f"export const value = {value!r};\n"
    )


def _project(root: Path, cross_store: bool = False) -> Path:
    root.mkdir()
    (root / "package.json").write_text('{"name":"snapshot-root","private":true}')
    (root / "ui").mkdir()
    (root / "ui/package.json").write_text(
        '{"name":"snapshot-ui","private":true,"type":"module"}'
    )
    _package(root / "node_modules/versioned", "ROOT", commonjs=True)
    _package(root / "node_modules/hoisted", "HOISTED")
    store = root / (
        "node_modules/.pnpm/versioned@1/node_modules/versioned"
        if cross_store
        else "ui/node_modules/.pnpm/versioned@1/node_modules/versioned"
    )
    _package(store, "UI")
    (root / "ui/node_modules").mkdir(parents=True, exist_ok=True)
    (root / "ui/node_modules/versioned").symlink_to(
        os.path.relpath(store, root / "ui/node_modules"), target_is_directory=True
    )
    tool = root / "ui/node_modules/fixture-tool"
    tool.mkdir()
    (tool / "package.json").write_text(
        '{"name":"fixture-tool","version":"1.0.0","type":"module","bin":{"fixture-probe":"cli.mjs"}}'
    )
    (tool / "cli.mjs").write_text(
        "#!/usr/bin/env node\nimport {pathToFileURL} from 'node:url';\nawait import(pathToFileURL(process.cwd() + '/probe.mjs'));\n"
    )
    (tool / "cli.mjs").chmod(0o755)
    binary = root / "ui/node_modules/.bin"
    binary.mkdir()
    (binary / "fixture-probe").symlink_to("../fixture-tool/cli.mjs")
    (tool / "only.mjs").write_text(
        "#!/usr/bin/env node\nconsole.log('UI-only tool');\n"
    )
    (tool / "only.mjs").chmod(0o755)
    (binary / "maid-ui-only-tool").symlink_to("../fixture-tool/only.mjs")
    (root / "ui/probe.mjs").write_text(
        "import assert from 'node:assert/strict';\nimport {value} from 'versioned';\nimport {value as hoisted} from 'hoisted';\nassert.equal(value, 'UI'); assert.equal(hoisted, 'HOISTED');\nconsole.log(JSON.stringify({version:value,hoisted,cwd:process.cwd()}));\n"
    )
    (root / "root-probe.cjs").write_text(
        "const assert = require('node:assert/strict');\nassert.equal(require('versioned').value, 'ROOT');\n"
    )
    (root / "target.py").write_text("def target() -> int:\n    return 42\n")
    (root / "tests").mkdir()
    (root / "tests/test_target.py").write_text(
        "from target import target\ndef test_target() -> None:\n    assert target() == 42\n"
    )
    return root


def _backend(kind: str):
    return {
        "shared": SharedEnvironmentProjectSnapshotBackend,
        "materialized": MaterializedProjectSnapshotBackend,
        "retained": WorkerRetainedProjectSnapshotBackend,
    }[kind]()


def _execute(root: Path, command: tuple[str, ...], snapshot=None):
    return KnockoutCommandExecutor().execute(
        command,
        root,
        "nested-node",
        snapshot.environment_overrides if snapshot else None,
        snapshot.environment_removals if snapshot else (),
    )


@pytest.mark.parametrize("kind", ["shared", "materialized", "retained"])
@pytest.mark.parametrize(
    "command_kind",
    [
        "node",
        pytest.param(
            "pnpm",
            marks=pytest.mark.skipif(
                shutil.which("pnpm") is None,
                reason="pnpm integration requires the optional pnpm executable",
            ),
        ),
    ],
)
@pytest.mark.parametrize("cross_store", [False, True])
def test_nested_node_resolution_and_local_executable_survive_snapshot(
    tmp_path: Path, kind: str, command_kind: str, cross_store: bool
) -> None:
    root = _project(tmp_path / "project", cross_store)
    command = (
        ("node", "ui/probe.mjs")
        if command_kind == "node"
        else ("pnpm", "--dir", "ui", "exec", "fixture-probe")
    )
    original = _execute(root, command)
    assert original.exit_code == 0, original.stderr
    backend = _backend(kind)
    lifetime = backend.retain() if kind == "retained" else nullcontext()
    with lifetime:
        with backend.create(
            root, ("target.py", "ui/package.json"), "nested-node"
        ) as snapshot:
            captured = snapshot.root
            result = _execute(snapshot.root, command, snapshot)
            assert result.exit_code == 0, result.stderr
            assert '"version":"UI"' in result.stdout
            assert '"hoisted":"HOISTED"' in result.stdout
            assert str(root) not in result.stdout
            assert (
                _execute(snapshot.root, ("node", "root-probe.cjs"), snapshot).exit_code
                == 0
            )
    assert not captured.exists()
    assert (
        root / "ui/node_modules/versioned/index.js"
    ).read_text() == "export const value = 'UI';\n"


@pytest.mark.parametrize("kind", ["shared", "materialized", "retained"])
@pytest.mark.parametrize("escape_style", ["entry", "entry-source", "root"])
def test_nested_dependency_symlink_escape_is_rejected(
    tmp_path: Path, kind: str, escape_style: str
) -> None:
    root = _project(tmp_path / "project")
    outside = (
        root / "source-package"
        if escape_style == "entry-source"
        else tmp_path / "outside"
    )
    outside.mkdir()
    (outside / "private.txt").write_text("must remain outside snapshot\n")
    if escape_style in {"entry", "entry-source"}:
        (root / "ui/node_modules/escape").symlink_to(outside, target_is_directory=True)
    else:
        shutil.rmtree(root / "ui/node_modules")
        (root / "ui/node_modules").symlink_to(outside, target_is_directory=True)
    backend = _backend(kind)
    with pytest.raises(RuntimeError, match="dependency|symlink"):
        with backend.retain() if kind == "retained" else nullcontext():
            with backend.create(root, ("target.py", "ui/package.json"), "escape"):
                pass
    assert (outside / "private.txt").read_text() == "must remain outside snapshot\n"


def test_shared_nested_dependency_changes_are_detected(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    with pytest.raises(RuntimeError, match="dependenc.*changed|changed.*dependenc"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            root, ("target.py", "ui/package.json"), "dependency-change"
        ):
            (root / "ui/node_modules/versioned/index.js").write_text(
                "export const value = 'CHANGED';\n"
            )


def test_nested_node_directory_without_package_input_stays_excluded(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "project")
    _package(root / "unregistered/node_modules/private", "EXCLUDED")
    with SharedEnvironmentProjectSnapshotBackend().create(
        root, ("target.py", "ui/package.json"), "bounded-roots"
    ) as snapshot:
        assert not (snapshot.root / "unregistered/node_modules").exists()


def test_retained_workers_keep_nested_dependency_paths_across_fresh_roots(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path / "project")
    backend = WorkerRetainedProjectSnapshotBackend()
    captured = []
    dependency_paths = []
    with backend.retain():
        for worker in ("first", "second"):
            with backend.create(
                root, ("target.py", "ui/package.json"), worker
            ) as snapshot:
                captured.append(snapshot.root)
                dependency_paths.append((snapshot.root / "ui/node_modules").resolve())
                result = _execute(snapshot.root, ("node", "ui/probe.mjs"), snapshot)
                assert result.exit_code == 0, result.stderr
    assert captured[0] != captured[1]
    assert dependency_paths[0] == dependency_paths[1]
    assert not dependency_paths[0].exists()
    assert all(not path.exists() for path in captured)
    assert (
        root / "ui/node_modules/versioned/index.js"
    ).read_text() == "export const value = 'UI';\n"


@pytest.mark.skipif(
    shutil.which("pnpm") is None,
    reason="pnpm integration requires the optional pnpm executable",
)
def test_real_python_knockout_runs_after_nested_node_baseline(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    (root / "manifests").mkdir()
    path = root / "manifests/target.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Node baseline then Python mutation",
                "type": "fix",
                "created": "2026-10-21T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": "target.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "target",
                                    "args": [],
                                    "returns": "int",
                                }
                            ],
                        }
                    ],
                    "read": ["tests/test_target.py", "ui/package.json", "ui/probe.mjs"],
                },
                "validate": [
                    ["pnpm", "--dir", "ui", "exec", "fixture-probe"],
                    ["python", "-m", "pytest", "tests/test_target.py", "-q"],
                ],
            }
        )
    )
    manifest = load_manifest(path)
    report = run_knockout_batch((manifest,), root, no_cache=True)[manifest.source_path]
    assert report.success, report
    assert len(report.results) == 1 and report.results[0].detected, report


@pytest.mark.parametrize("kind", ["shared", "materialized", "retained"])
def test_root_cannot_resolve_subproject_only_module(tmp_path: Path, kind: str) -> None:
    root = _project(tmp_path / "project")
    _package(root / "ui/node_modules/maid-ui-only-fixture", "UI-ONLY", commonjs=True)
    command = ("node", "-e", "require('maid-ui-only-fixture')")
    assert _execute(root, command).exit_code != 0
    backend = _backend(kind)
    with backend.retain() if kind == "retained" else nullcontext():
        with backend.create(
            root, ("target.py", "ui/package.json"), "module-boundary"
        ) as snapshot:
            result = _execute(snapshot.root, command, snapshot)
            assert result.exit_code != 0, result.stdout


@pytest.mark.parametrize("kind", ["shared", "materialized", "retained"])
def test_root_cannot_execute_subproject_only_tool(tmp_path: Path, kind: str) -> None:
    root = _project(tmp_path / "project")
    command = ("maid-ui-only-tool",)
    assert _execute(root, command).exit_code != 0
    backend = _backend(kind)
    with backend.retain() if kind == "retained" else nullcontext():
        with backend.create(
            root, ("target.py", "ui/package.json"), "executable-boundary"
        ) as snapshot:
            result = _execute(snapshot.root, command, snapshot)
            assert result.exit_code != 0, result.stdout


@pytest.mark.parametrize("kind", ["shared", "materialized", "retained"])
@pytest.mark.parametrize("slot", ["node_modules", "ui/node_modules"])
def test_dependency_root_alias_cannot_reclassify_project_source(
    tmp_path: Path, kind: str, slot: str
) -> None:
    root = _project(tmp_path / "project")
    source = root / "source-package"
    source.mkdir()
    (source / "private.js").write_text("module.exports = 'project source';\n")
    shutil.rmtree(root / slot)
    (root / slot).symlink_to(source, target_is_directory=True)
    backend = _backend(kind)
    with pytest.raises(RuntimeError, match="dependency|symlink"):
        with backend.retain() if kind == "retained" else nullcontext():
            with backend.create(
                root, ("target.py", "ui/package.json"), "source-root-alias"
            ):
                pass
    assert (source / "private.js").read_text() == "module.exports = 'project source';\n"
