"""Behavioral contract: a red exact command escalates only itself.

Contract: manifests/drafts/121-20-escalate-only-affected-coverage-identities.manifest.yaml

The isolated fallback worker used to set one whole-batch ``unsafe`` flag: any
single command that returned non-zero forced every command to replay serially
in place. On a real repository even a handful of genuinely failing coverage
commands then discarded the entire parallel batch, so the isolated path did the
work twice and ran slower than the legacy serial loop.

A command that exits non-zero without writing material project state leaves its
lane snapshot clean for the next command, so it does not need to contaminate
the batch. It escalates only its own identity to in-place replay while every
clean command keeps its isolated result. Material writes and harness/worker
errors remain whole-batch fail-closed, because those genuinely threaten later
readers and are proven separately.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from maid_runner.core._runtime_command_executor import (
    RuntimeCommandRecord,
    RuntimeFileExecution,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.runtime_evidence import RuntimeCommandIdentity


def test_single_red_command_escalates_only_itself_and_keeps_clean_isolated(
    tmp_path: Path,
) -> None:
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )

    root = tmp_path / "project"
    identities = _identities(_write_project(root, ("alpha", "beta", "gamma")))
    red_identity = identities[1]

    run = run_isolated_artifact_coverage_fallbacks(
        identities,
        root,
        _targets(root, identities),
        _CopySnapshotBackend(tmp_path / "snapshots"),
        _RedForExecutor(root, red_command_stem="beta"),
        jobs=3,
        max_processes=6,
    )

    assert run.serial_fallback_identities == (red_identity,)
    clean = [r for r in run.results if r.identity != red_identity]
    assert clean and all(r.command_run.returncode == 0 for r in clean)
    assert all(not r.material_project_writes for r in run.results)


def test_all_red_commands_still_escalate_every_identity(tmp_path: Path) -> None:
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )

    root = tmp_path / "project"
    identities = _identities(_write_project(root, ("alpha", "beta")))

    run = run_isolated_artifact_coverage_fallbacks(
        identities,
        root,
        _targets(root, identities),
        _CopySnapshotBackend(tmp_path / "snapshots"),
        _RedForExecutor(root, red_command_stem=None),
        jobs=2,
        max_processes=4,
    )

    assert run.serial_fallback_identities == identities


def _identities(manifests):
    return tuple(
        RuntimeCommandIdentity(manifest.source_path, 0, manifest.validate_commands[0])
        for manifest in manifests
    )


def _targets(root: Path, identities):
    return {
        identity: {
            str(
                (
                    root
                    / "src"
                    / f"{Path(identity.manifest_path).stem.split('.')[0]}.py"
                ).resolve()
            )
        }
        for identity in identities
    }


def _write_project(root: Path, names):
    for directory in ("src", "tests", "manifests"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text("")
    manifests = []
    for name in names:
        (root / "src" / f"{name}.py").write_text(
            f"def {name}() -> str:\n    return '{name}'\n"
        )
        (root / "tests" / f"test_{name}.py").write_text(
            f"from src.{name} import {name}\n\n"
            f"def test_{name}():\n    assert {name}() == '{name}'\n"
        )
        path = root / "manifests" / f"{name}.manifest.yaml"
        path.write_text(
            f"""schema: "2"
goal: "Cover {name}"
type: feature
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/{name}.py
      artifacts:
        - kind: function
          name: {name}
          args: []
          returns: str
  read:
    - tests/test_{name}.py
validate:
  - python -m pytest -q tests/test_{name}.py
"""
        )
        manifests.append(load_manifest(path))
    return tuple(manifests)


class _CopySnapshotBackend:
    def __init__(self, destination: Path):
        self.destination = destination

    @contextmanager
    def create(self, project_root, required_paths, worker_id):
        import shutil

        snapshot_root = self.destination / worker_id
        shutil.copytree(project_root, snapshot_root)
        try:
            yield SimpleNamespace(
                root=snapshot_root,
                environment_overrides={},
                environment_removals=(),
            )
        finally:
            shutil.rmtree(snapshot_root)


class _RedForExecutor:
    """Return non-zero for the command selecting ``red_command_stem`` tests.

    A red result never writes material state, so the worker can escalate it
    alone. ``red_command_stem=None`` makes every command red.
    """

    def __init__(self, source_root: Path, *, red_command_stem: str | None):
        self.source_root = source_root
        self.red_command_stem = red_command_stem

    def execute(
        self,
        command,
        target_files,
        project_root,
        timeout_seconds,
        environment_overrides=None,
        environment_removals=(),
    ):
        joined = " ".join(str(part) for part in command)
        red = self.red_command_stem is None or (
            f"test_{self.red_command_stem}.py" in joined
        )
        target = next(iter(target_files))
        return RuntimeCommandRecord(
            command=tuple(command),
            returncode=1 if red else 0,
            stdout="",
            stderr="",
            execution_data={
                target: RuntimeFileExecution(
                    executed_lines=frozenset({2}),
                    called_qualnames=frozenset({Path(target).stem}),
                )
            },
            report_errors=(),
        )
