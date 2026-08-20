"""Behavioral contract for exact-command knockout control sharing."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.runtime_evidence import collect_runtime_evidence
from maid_runner.core.types import TestStream


MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def test_exact_command_group_runs_one_baseline_and_resets_generated_state(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import (
        build_knockout_mutation_specs,
        run_knockout_batch,
    )

    manifest = _manifest(tmp_path, "shared", ("alpha", "beta", "gamma"), git=True)
    specs = build_knockout_mutation_specs((manifest,), tmp_path)
    assert [spec.identity.artifact_name for spec in specs] == [
        "alpha",
        "beta",
        "gamma",
    ]
    executor = _StatefulExecutor()

    report = run_knockout_batch(
        (manifest,), tmp_path, executor=executor, no_cache=True
    )[manifest.source_path]

    assert report.success is True
    assert [result.artifact_name for result in report.results] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert [phase for _slug, phase, _command, _root in executor.calls].count(
        "baseline"
    ) == 1
    assert [phase for _slug, phase, _command, _root in executor.calls].count(
        "mutant"
    ) == 3
    assert [phase for _slug, phase, _command, _root in executor.calls].count(
        "restored"
    ) == 3
    assert len(executor.calls) == 7
    assert len({root for _slug, _phase, _command, root in executor.calls}) == 1


def test_focused_groups_share_only_equal_selected_commands(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    shared_root = tmp_path / "shared-focus"
    shared = _focus_manifest(shared_root, shared_node=True)
    shared_evidence = collect_runtime_evidence((shared,), shared_root).evidence
    shared_executor = _StatefulExecutor()

    shared_report = run_knockout_batch(
        (shared,),
        shared_root,
        evidence=shared_evidence,
        executor=shared_executor,
        no_cache=True,
    )[shared.source_path]

    assert shared_report.success is True
    assert len(shared_executor.calls) == 5
    assert all(
        result.proof is not None and result.proof.used_exact_fallback is False
        for result in shared_report.results
    )
    assert len({result.proof.command for result in shared_report.results}) == 1

    split_root = tmp_path / "split-focus"
    split = _focus_manifest(split_root, shared_node=False)
    split_evidence = collect_runtime_evidence((split,), split_root).evidence
    split_executor = _StatefulExecutor()

    split_report = run_knockout_batch(
        (split,),
        split_root,
        evidence=split_evidence,
        executor=split_executor,
        no_cache=True,
    )[split.source_path]

    assert split_report.success is True
    assert len(split_executor.calls) == 6
    assert len({result.proof.command for result in split_report.results}) == 2
    assert len({root for _slug, _phase, _command, root in split_executor.calls}) == 2


def test_grouped_focused_green_member_keeps_exact_fallback(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _focus_manifest(tmp_path, shared_node=True)
    evidence = collect_runtime_evidence((manifest,), tmp_path).evidence
    executor = _FocusedFallbackExecutor()

    report = run_knockout_batch(
        (manifest,),
        tmp_path,
        evidence=evidence,
        executor=executor,
        no_cache=True,
    )[manifest.source_path]

    assert report.success is True
    alpha, beta = report.results
    assert alpha.proof is not None
    assert alpha.proof.used_exact_fallback is False
    assert beta.proof is not None
    assert beta.proof.used_exact_fallback is True
    assert beta.proof.command == tuple(manifest.validate_commands[0])
    assert len(executor.calls) == 7
    assert sum("::test_both" in " ".join(command) for command in executor.calls) == 4
    assert (
        sum("::test_both" not in " ".join(command) for command in executor.calls) == 3
    )


def test_command_groups_do_not_cross_manifest_slug_identity(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    first = _manifest(tmp_path, "first", ("alpha", "beta"))
    second = _manifest(tmp_path, "second", ("gamma", "delta"))
    executor = _StatefulExecutor()

    reports = run_knockout_batch(
        (first, second), tmp_path, executor=executor, no_cache=True
    )

    assert reports[first.source_path].success is True
    assert reports[second.source_path].success is True
    baselines = [
        (slug, root)
        for slug, phase, _command, root in executor.calls
        if phase == "baseline"
    ]
    assert [slug for slug, _root in baselines] == ["first", "second"]
    assert len({root for _slug, root in baselines}) == 2
    assert len(executor.calls) == 10


def test_shared_baseline_failure_is_projected_fail_closed_once(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _manifest(tmp_path, "failing", ("alpha", "beta"))
    executor = _FailingBaselineExecutor()

    report = run_knockout_batch(
        (manifest,), tmp_path, executor=executor, no_cache=True
    )[manifest.source_path]

    assert [result.artifact_name for result in report.results] == ["alpha", "beta"]
    assert all(result.detected is False for result in report.results)
    assert [error.code.value for error in report.errors] == ["E712", "E712"]
    assert len(executor.calls) == 1


def test_grouped_exact_verdicts_keep_e711_e712_and_later_group_order(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    verdicts = _manifest(tmp_path, "verdicts", ("alpha", "beta", "gamma"))
    later = _manifest(tmp_path, "later", ("delta", "epsilon"))
    executor = _VerdictExecutor()

    reports = run_knockout_batch(
        (verdicts, later), tmp_path, executor=executor, no_cache=True
    )

    verdict_report = reports[verdicts.source_path]
    assert [result.artifact_name for result in verdict_report.results] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert [result.detected for result in verdict_report.results] == [
        True,
        False,
        False,
    ]
    assert [error.code.value for error in verdict_report.errors] == ["E711", "E712"]
    assert reports[later.source_path].success is True
    assert [result.artifact_name for result in reports[later.source_path].results] == [
        "delta",
        "epsilon",
    ]
    assert [
        slug for slug, phase, _artifact in executor.calls if phase == "baseline"
    ] == [
        "verdicts",
        "later",
    ]


def test_multi_command_declarations_keep_independent_transitions(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _manifest(
        tmp_path,
        "multiple",
        ("alpha", "beta"),
        commands=("non-detecting", "detecting"),
    )
    executor = _MultiCommandExecutor()

    report = run_knockout_batch(
        (manifest,), tmp_path, executor=executor, no_cache=True
    )[manifest.source_path]

    assert report.success is True
    assert [result.artifact_name for result in report.results] == ["alpha", "beta"]
    assert len(executor.calls) == 10
    assert [result.proof.command for result in report.results] == [
        ("detecting",),
        ("detecting",),
    ]


def test_custom_snapshot_backend_keeps_independent_transitions(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        MaterializedProjectSnapshotBackend,
    )
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _manifest(tmp_path, "custom", ("alpha", "beta"))
    executor = _StatefulExecutor()

    report = run_knockout_batch(
        (manifest,),
        tmp_path,
        executor=executor,
        snapshot_backend=MaterializedProjectSnapshotBackend(),
        no_cache=True,
    )[manifest.source_path]

    assert report.success is True
    assert len(executor.calls) == 6
    assert len({root for _slug, _phase, _command, root in executor.calls}) == 2


def test_dependency_drift_between_group_mutations_fails_closed(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _manifest(tmp_path, "dependency", ("alpha", "beta"))
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv/seed").write_text("stable\n", encoding="utf-8")
    executor = _DependencyDriftExecutor()

    report = run_knockout_batch(
        (manifest,), tmp_path, executor=executor, no_cache=True
    )[manifest.source_path]

    assert report.success is False
    assert report.errors
    assert all(error.code.value == "E712" for error in report.errors)
    assert executor.mutated_artifacts == ["alpha"]


@pytest.mark.parametrize("drift", ("source", "repository"))
def test_live_input_drift_during_group_returns_e712_reports(
    tmp_path: Path,
    drift: str,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _manifest(tmp_path, "live-drift", ("alpha", "beta", "gamma"), git=True)
    executor = _LiveDriftExecutor(tmp_path, drift)

    report = run_knockout_batch(
        (manifest,), tmp_path, executor=executor, no_cache=True
    )[manifest.source_path]

    assert report.success is False
    assert len(report.errors) == 3
    assert all(error.code.value == "E712" for error in report.errors)
    assert executor.mutated_artifacts == ["alpha"]


def test_mixed_cache_hits_group_only_remaining_exact_commands(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _manifest(tmp_path, "cached", ("alpha", "beta", "gamma"))
    warm_executor = _StatefulExecutor()
    warm = run_knockout_batch((manifest,), tmp_path, executor=warm_executor, limit=1)[
        manifest.source_path
    ]
    assert warm.success is True
    assert len(warm_executor.calls) == 3

    executor = _StatefulExecutor()
    report = run_knockout_batch((manifest,), tmp_path, executor=executor)[
        manifest.source_path
    ]

    assert report.success is True
    assert [result.cache_hit for result in report.results] == [True, False, False]
    assert len(executor.calls) == 5
    assert len({root for _slug, _phase, _command, root in executor.calls}) == 1


def test_group_checkpoints_completed_artifact_before_later_failure(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _manifest(tmp_path, "interrupted", ("alpha", "beta", "gamma"))
    interrupted = run_knockout_batch(
        (manifest,), tmp_path, executor=_InterruptingExecutor()
    )[manifest.source_path]
    assert interrupted.success is False

    executor = _StatefulExecutor()
    resumed = run_knockout_batch((manifest,), tmp_path, executor=executor)[
        manifest.source_path
    ]

    assert [result.cache_hit for result in resumed.results] == [True, False, False]
    assert resumed.success is True
    assert len(executor.calls) == 5


class _StatefulExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[str, ...], Path]] = []

    def execute(
        self,
        command: tuple[str, ...],
        project_root: Path,
        manifest_slug: str,
        *_environment,
    ) -> TestRunResult:
        root = Path(project_root)
        source = (root / "src/target.py").read_text(encoding="utf-8")
        state = root / "baseline-state"
        leak = root / "mutant-leak"
        generated = root / "generated/absolute-root.txt"
        support = root / "src/support.py"
        deleted = root / "baseline-delete-me.txt"
        git_config = root / ".git/config"
        mutated = MUTANT_MARKER in source
        if mutated:
            assert state.read_text(encoding="utf-8") == manifest_slug
            assert not leak.exists()
            assert generated.read_text(encoding="utf-8") == str(root)
            assert support.read_text(encoding="utf-8") == "baseline-ready\n"
            assert not deleted.exists()
            if git_config.exists():
                assert "mutation-leak" not in git_config.read_text(encoding="utf-8")
            leak.write_text("mutation-local\n", encoding="utf-8")
            generated.write_text("corrupt\n", encoding="utf-8")
            support.write_text("corrupt\n", encoding="utf-8")
            deleted.write_text("recreated\n", encoding="utf-8")
            if git_config.exists():
                with git_config.open("a", encoding="utf-8") as stream:
                    stream.write("\n[maid]\n\tmutation-leak = true\n")
            phase = "mutant"
            exit_code = 1
        elif not state.exists():
            assert not leak.exists()
            state.write_text(manifest_slug, encoding="utf-8")
            generated.parent.mkdir()
            generated.write_text(str(root), encoding="utf-8")
            support.write_text("baseline-ready\n", encoding="utf-8")
            deleted.unlink()
            phase = "baseline"
            exit_code = 0
        else:
            assert state.read_text(encoding="utf-8") == manifest_slug
            assert leak.read_text(encoding="utf-8") == "mutation-local\n"
            assert generated.read_text(encoding="utf-8") == "corrupt\n"
            assert support.read_text(encoding="utf-8") == "corrupt\n"
            assert deleted.read_text(encoding="utf-8") == "recreated\n"
            phase = "restored"
            exit_code = 0
        self.calls.append((manifest_slug, phase, tuple(command), root))
        return _result(command, exit_code)


class _FailingBaselineExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def execute(self, command, project_root, manifest_slug, *_environment):
        self.calls.append(tuple(command))
        return _result(command, 1)


class _VerdictExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.last_mutant_by_root: dict[Path, str] = {}

    def execute(self, command, project_root, manifest_slug, *_environment):
        root = Path(project_root)
        source = (root / "src/target.py").read_text(encoding="utf-8")
        artifact = _mutated_artifact(source)
        if artifact is not None:
            self.last_mutant_by_root[root] = artifact
            self.calls.append((manifest_slug, "mutant", artifact))
            return _result(command, 0 if artifact == "beta" else 1)
        prior = self.last_mutant_by_root.get(root)
        if prior is None:
            self.calls.append((manifest_slug, "baseline", None))
            return _result(command, 0)
        self.calls.append((manifest_slug, "restored", prior))
        return _result(command, 1 if prior == "gamma" else 0)


class _MultiCommandExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def execute(self, command, project_root, manifest_slug, *_environment):
        source = (Path(project_root) / "src/target.py").read_text(encoding="utf-8")
        mutated = MUTANT_MARKER in source
        self.calls.append(tuple(command))
        return _result(command, int(mutated and tuple(command) == ("detecting",)))


class _FocusedFallbackExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def execute(self, command, project_root, manifest_slug, *_environment):
        command = tuple(command)
        source = (Path(project_root) / "src/target.py").read_text(encoding="utf-8")
        artifact = _mutated_artifact(source)
        focused = "::test_both" in " ".join(command)
        self.calls.append(command)
        if artifact == "alpha":
            return _result(command, 1)
        if artifact == "beta":
            return _result(command, 0 if focused else 1)
        return _result(command, 0)


class _DependencyDriftExecutor(_StatefulExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.mutated_artifacts: list[str] = []

    def execute(self, command, project_root, manifest_slug, *_environment):
        root = Path(project_root)
        source = (root / "src/target.py").read_text(encoding="utf-8")
        mutated = _mutated_artifact(source)
        result = super().execute(command, root, manifest_slug, *_environment)
        if mutated is not None:
            self.mutated_artifacts.append(mutated)
            if mutated == "alpha":
                (root / ".venv/seed").write_text("changed\n", encoding="utf-8")
        return result


class _LiveDriftExecutor(_StatefulExecutor):
    def __init__(self, live_root: Path, drift: str) -> None:
        super().__init__()
        self.live_root = live_root
        self.drift = drift
        self.mutated_artifacts: list[str] = []

    def execute(self, command, project_root, manifest_slug, *_environment):
        root = Path(project_root)
        source = (root / "src/target.py").read_text(encoding="utf-8")
        artifact = _mutated_artifact(source)
        result = super().execute(command, root, manifest_slug, *_environment)
        if artifact is not None:
            self.mutated_artifacts.append(artifact)
            if artifact == "alpha":
                if self.drift == "source":
                    (self.live_root / "src/support.py").write_text(
                        "live drift\n", encoding="utf-8"
                    )
                else:
                    _git(self.live_root, "config", "maid.live-drift", "changed")
        return result


class _InterruptingExecutor(_StatefulExecutor):
    def execute(self, command, project_root, manifest_slug, *_environment):
        root = Path(project_root)
        source = (root / "src/target.py").read_text(encoding="utf-8")
        if _mutated_artifact(source) == "beta":
            raise RuntimeError("interrupt later grouped mutation")
        return super().execute(command, root, manifest_slug, *_environment)


def _manifest(
    root: Path,
    slug: str,
    artifacts: tuple[str, ...],
    *,
    commands: tuple[str, ...] = ("shared-check",),
    git: bool = False,
):
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(exist_ok=True)
    (root / "manifests").mkdir(exist_ok=True)
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    (root / "src/target.py").write_text(
        "\n\n".join(
            f"def {name}() -> str:\n    return {name!r}"
            for name in ("alpha", "beta", "gamma", "delta", "epsilon")
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "tests/test_target.py").write_text(
        "def test_placeholder():\n    assert True\n", encoding="utf-8"
    )
    (root / "src/support.py").write_text("original\n", encoding="utf-8")
    (root / "baseline-delete-me.txt").write_text("delete me\n", encoding="utf-8")
    path = root / f"manifests/{slug}.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": slug,
                "type": "refactor",
                "created": "2026-08-18T00:40:00+08:00",
                "files": {
                    "edit": [
                        {
                            "path": "src/target.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": name,
                                    "args": [],
                                    "returns": "str",
                                }
                                for name in artifacts
                            ],
                        }
                    ]
                },
                "validate": list(commands),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    if git:
        _git(root, "init")
        _git(root, "add", ".")
        _git(
            root,
            "-c",
            "user.name=MAID Test",
            "-c",
            "user.email=maid-test@example.invalid",
            "commit",
            "-m",
            "fixture",
        )
    return load_manifest(path)


def _focus_manifest(root: Path, *, shared_node: bool):
    _manifest(root, "focus", ("alpha", "beta"))
    test_path = root / "tests/test_target.py"
    if shared_node:
        test_path.write_text(
            "from src.target import alpha, beta\n\n"
            "def test_both():\n"
            "    assert alpha() == 'alpha'\n"
            "    assert beta() == 'beta'\n",
            encoding="utf-8",
        )
    else:
        test_path.write_text(
            "from src.target import alpha, beta\n\n"
            "def test_alpha():\n    assert alpha() == 'alpha'\n\n"
            "def test_beta():\n    assert beta() == 'beta'\n",
            encoding="utf-8",
        )
    path = root / "manifests/focus.manifest.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["files"]["read"] = ["tests/test_target.py"]
    payload["validate"] = ["python -m pytest -q tests/test_target.py"]
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return load_manifest(path)


def _mutated_artifact(source: str) -> str | None:
    if MUTANT_MARKER not in source:
        return None
    prefix = source[: source.index(MUTANT_MARKER)]
    return max(
        ("alpha", "beta", "gamma", "delta", "epsilon"),
        key=lambda name: prefix.rfind(f"def {name}"),
    )


def _git(root: Path, *args: str) -> None:
    subprocess.run(("git", *args), cwd=root, check=True, capture_output=True)


def _result(command, exit_code: int) -> TestRunResult:
    return TestRunResult(
        manifest_slug="shared-controls",
        command=tuple(command),
        exit_code=exit_code,
        stdout="",
        stderr="",
        duration_ms=1.0,
        stream=TestStream.IMPLEMENTATION,
    )
