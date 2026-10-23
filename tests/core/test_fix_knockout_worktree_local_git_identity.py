"""Snapshot identity follows this worktree while independent sibling Git work proceeds."""

import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from maid_runner.core._knockout_snapshot import SharedEnvironmentProjectSnapshotBackend
from maid_runner.core.knockout import KnockoutCommandExecutor, run_knockout_batch
from maid_runner.core.manifest import load_manifest

_SOURCE = "def target() -> int:\n    return 42\n\ndef other() -> int:\n    return 7\n"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _project(base: Path, linked: bool = True) -> tuple[Path, Path, Path]:
    repository = base / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "MAID fixture")
    _git(repository, "config", "user.email", "fixture@example.invalid")
    _git(repository, "config", "extensions.worktreeConfig", "true")
    (repository / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n.maid/\n")
    (repository / "target.py").write_text(_SOURCE)
    (repository / "tests").mkdir()
    (repository / "tests/test_target.py").write_text(
        "from target import target, other\ndef test_target() -> None:\n    assert target() == 42\n    assert other() == 7\n"
    )
    (repository / "manifests").mkdir()
    (repository / "manifests/target.manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Observe target knockout",
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
                                },
                                {
                                    "kind": "function",
                                    "name": "other",
                                    "args": [],
                                    "returns": "int",
                                },
                            ],
                        }
                    ],
                    "read": ["tests/test_target.py"],
                },
                "validate": [["python", "-m", "pytest", "tests/test_target.py", "-q"]],
            }
        )
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "Fixture baseline")
    task = base / "task" if linked else repository
    if linked:
        _git(repository, "worktree", "add", "-b", "task", str(task))
    sibling = base / "sibling"
    _git(repository, "worktree", "add", "-b", "sibling", str(sibling))
    return repository, task, sibling


def _sibling_operation(repository: Path, sibling: Path, operation: str) -> None:
    if operation == "commit":
        (sibling / "sibling.txt").write_text("independent change\n")
        _git(sibling, "add", "sibling.txt")
        _git(sibling, "commit", "-m", "Sibling commit")
    elif operation == "object":
        blob = repository.parent / "unrelated-object.txt"
        blob.write_text("unreferenced sibling object\n")
        _git(sibling, "hash-object", "-w", str(blob))
    elif operation == "ref":
        _git(
            sibling,
            "update-ref",
            "refs/heads/unrelated",
            _git(sibling, "rev-parse", "HEAD"),
        )
    elif operation == "pack-refs":
        _git(sibling, "pack-refs", "--all")
    elif operation == "worktree":
        _git(
            repository,
            "worktree",
            "add",
            "-b",
            "another",
            str(repository.parent / "another"),
        )
    else:
        raise AssertionError(operation)


@pytest.mark.parametrize("linked", [False, True])
@pytest.mark.parametrize(
    "operation", ["commit", "object", "ref", "pack-refs", "worktree"]
)
def test_sibling_git_changes_do_not_invalidate_public_snapshot(
    tmp_path: Path, linked: bool, operation: str
) -> None:
    repository, task, sibling = _project(tmp_path, linked)
    head = _git(task, "rev-parse", "HEAD")
    index = Path(_git(task, "rev-parse", "--absolute-git-dir")) / "index"
    before = index.read_bytes()
    opened = threading.Event()

    def independent_work() -> None:
        assert opened.wait(20), "snapshot did not open"
        _sibling_operation(repository, sibling, operation)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(independent_work)
        with SharedEnvironmentProjectSnapshotBackend().create(
            task, ("target.py",), "sibling-proof"
        ) as snapshot:
            opened.set()
            future.result(timeout=30)
            executed = KnockoutCommandExecutor().execute(
                ("python", "-c", "from target import target; assert target() == 42"),
                snapshot.root,
                "sibling-proof",
                snapshot.environment_overrides,
                snapshot.environment_removals,
            )
            assert executed.exit_code == 0, executed.stderr
            assert _git(task, "rev-parse", "HEAD") == head
            assert index.read_bytes() == before
    assert (task / "target.py").read_text() == _SOURCE


@pytest.mark.parametrize(
    "change", ["branch", "index", "shared-config", "worktree-config", "input"]
)
def test_own_worktree_changes_remain_blocking(tmp_path: Path, change: str) -> None:
    _, task, _ = _project(tmp_path)
    with pytest.raises(RuntimeError, match="changed|identity"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            task, ("target.py",), "own-proof"
        ):
            if change == "branch":
                git_dir = Path(_git(task, "rev-parse", "--absolute-git-dir"))
                before = (git_dir / "HEAD").read_bytes()
                new = _git(
                    task,
                    "commit-tree",
                    _git(task, "rev-parse", "HEAD^{tree}"),
                    "-p",
                    _git(task, "rev-parse", "HEAD"),
                    "-m",
                    "Advance current branch without input change",
                )
                _git(task, "update-ref", _git(task, "symbolic-ref", "HEAD"), new)
                assert (git_dir / "HEAD").read_bytes() == before
            elif change == "index":
                _git(task, "update-index", "--force-remove", "tests/test_target.py")
            elif change == "shared-config":
                _git(task, "config", "maid.identity-probe", "changed")
            elif change == "worktree-config":
                _git(task, "config", "--worktree", "maid.identity-probe", "changed")
            elif change == "input":
                (task / "target.py").write_text("def target() -> int:\n    return 99\n")


def test_snapshot_command_writing_source_is_still_detected(tmp_path: Path) -> None:
    _, task, _ = _project(tmp_path)
    with pytest.raises(RuntimeError, match="changed|identity"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            task, ("target.py",), "source-write"
        ) as snapshot:
            script = f"from pathlib import Path; Path({str(task / 'target.py')!r}).write_text('changed by snapshot command\\n')"
            result = KnockoutCommandExecutor().execute(
                ("python", "-c", script),
                snapshot.root,
                "source-write",
                snapshot.environment_overrides,
                snapshot.environment_removals,
            )
            assert result.exit_code == 0, result.stderr


class _SiblingGitExecutor(KnockoutCommandExecutor):
    def __init__(self, repository: Path, sibling: Path, operation: str) -> None:
        self._repository = repository
        self._sibling = sibling
        self._operation = operation
        self._committed = False

    def execute(self, command, project_root, manifest_slug, *environment):
        result = super().execute(command, project_root, manifest_slug, *environment)
        if not self._committed:
            assert result.exit_code == 0, result.stderr
            _sibling_operation(self._repository, self._sibling, self._operation)
            self._committed = True
        return result


@pytest.mark.parametrize(
    "operation", ["commit", "object", "ref", "pack-refs", "worktree"]
)
def test_real_knockout_batch_accepts_sibling_changes_during_command_group(
    tmp_path: Path, operation: str
) -> None:
    repository, task, sibling = _project(tmp_path)
    manifest = load_manifest(task / "manifests/target.manifest.yaml")
    reports = run_knockout_batch(
        (manifest,),
        task,
        executor=_SiblingGitExecutor(repository, sibling, operation),
        no_cache=True,
    )
    report = reports[manifest.source_path]
    assert report.success, report
    assert {result.artifact_name for result in report.results} == {"target", "other"}
    assert all(result.detected for result in report.results), report
