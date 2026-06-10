"""Tests for ranked bootstrap adoption planning."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import yaml

from maid_runner.core.bootstrap import (
    BootstrapCandidate,
    BootstrapRankReport,
    rank_bootstrap_candidates,
)


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


def _commit_all(project_dir: Path, message: str) -> None:
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-m", message)


def _write(project_dir: Path, rel_path: str, content: str) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


def _tracked_manifest(project_dir: Path, rel_path: str) -> None:
    manifest_dir = project_dir / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    manifest = {
        "schema": "2",
        "goal": f"Snapshot of {rel_path}",
        "type": "snapshot",
        "files": {
            "snapshot": [
                {
                    "path": rel_path,
                    "artifacts": [{"kind": "function", "name": "tracked"}],
                }
            ]
        },
        "validate": ["pytest tests/ -v"],
        "created": "2026-01-01T00:00:00+00:00",
    }
    (manifest_dir / "snapshot-tracked.manifest.yaml").write_text(
        yaml.safe_dump(manifest)
    )


def test_rank_orders_by_churn_inbound_artifacts_then_path(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/churn.py", "def churn() -> None:\n    pass\n")
    _write(tmp_path, "src/inbound.py", "def inbound() -> None:\n    pass\n")
    _write(tmp_path, "src/artifacts.py", "def one() -> None:\n    pass\n")
    _write(tmp_path, "src/path_a.py", "def same() -> None:\n    pass\n")
    _write(tmp_path, "src/path_b.py", "def same() -> None:\n    pass\n")
    _write(
        tmp_path,
        "src/importer.py",
        "from src.inbound import inbound\n\n\ndef use() -> None:\n    inbound()\n",
    )
    _commit_all(tmp_path, "initial")

    _write(
        tmp_path,
        "src/artifacts.py",
        """
        def one() -> None:
            pass

        def two() -> None:
            pass
        """,
    )
    _write(tmp_path, "src/inbound.py", "def inbound() -> str:\n    return 'two'\n")
    _write(tmp_path, "src/churn.py", "def churn() -> str:\n    return 'two'\n")
    _commit_all(tmp_path, "second")

    _write(tmp_path, "src/churn.py", "def churn() -> str:\n    return 'three'\n")
    _commit_all(tmp_path, "third")

    report = rank_bootstrap_candidates(tmp_path)

    assert isinstance(report, BootstrapRankReport)
    assert all(
        isinstance(candidate, BootstrapCandidate) for candidate in report.candidates
    )
    paths = [candidate.path for candidate in report.candidates]
    assert paths.index("src/churn.py") < paths.index("src/inbound.py")
    assert paths.index("src/inbound.py") < paths.index("src/artifacts.py")
    assert paths.index("src/artifacts.py") < paths.index("src/importer.py")
    assert paths.index("src/path_a.py") < paths.index("src/path_b.py")

    by_path = {candidate.path: candidate for candidate in report.candidates}
    assert by_path["src/churn.py"].churn == 3
    assert by_path["src/inbound.py"].inbound_refs == 1
    assert by_path["src/artifacts.py"].public_artifacts == 2


def test_rank_excludes_tracked_and_test_files(tmp_path):
    _write(tmp_path, "src/tracked.py", "def tracked() -> None:\n    pass\n")
    _write(tmp_path, "src/new.py", "def new() -> None:\n    pass\n")
    _write(tmp_path, "tests/test_new.py", "def test_new():\n    pass\n")
    _tracked_manifest(tmp_path, "src/tracked.py")

    report = rank_bootstrap_candidates(tmp_path)

    paths = {candidate.path for candidate in report.candidates}
    assert paths == {"src/new.py"}
    assert report.total_candidates == 1


def test_rank_limit_truncates_after_ordering_and_reports_total(tmp_path):
    _init_repo(tmp_path)
    for name in ("a", "b", "c"):
        _write(tmp_path, f"src/{name}.py", f"def {name}() -> None:\n    pass\n")
    _commit_all(tmp_path, "initial")
    _write(tmp_path, "src/c.py", "def c() -> str:\n    return 'changed'\n")
    _commit_all(tmp_path, "change c")

    report = rank_bootstrap_candidates(tmp_path, limit=2)

    assert report.limit == 2
    assert report.total_candidates == 3
    assert [candidate.path for candidate in report.candidates] == [
        "src/c.py",
        "src/a.py",
    ]


def test_rank_untracked_files_have_zero_churn_and_are_deterministic(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/committed.py", "def committed() -> None:\n    pass\n")
    _commit_all(tmp_path, "initial")
    _write(tmp_path, "src/untracked.py", "def untracked() -> None:\n    pass\n")

    first = rank_bootstrap_candidates(tmp_path)
    second = rank_bootstrap_candidates(tmp_path)

    assert first == second
    by_path = {candidate.path: candidate for candidate in first.candidates}
    assert by_path["src/untracked.py"].churn == 0


def test_rank_degrades_when_registered_validator_cannot_construct(
    tmp_path, monkeypatch
):
    _write(tmp_path, "src/client.ts", "export function client() { return 1; }\n")
    _write(
        tmp_path,
        "src/importer.ts",
        "import { client } from './client';\nexport const value = client();\n",
    )

    class BrokenRegistry:
        def has_validator(self, file_path):
            return str(file_path).endswith(".ts")

        def get(self, file_path):
            raise ImportError("optional TypeScript parser unavailable")

    monkeypatch.setattr(
        "maid_runner.core.bootstrap.ValidatorRegistry.with_builtin_validators",
        lambda: BrokenRegistry(),
    )

    report = rank_bootstrap_candidates(tmp_path)

    assert report.total_candidates == 2
    assert report.candidates[0] == BootstrapCandidate(
        path="src/client.ts",
        churn=0,
        inbound_refs=1,
        public_artifacts=0,
    )
