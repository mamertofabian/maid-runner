"""Behavioral tests for stash-backed plan-lock revision."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.plan_lock import default_plan_lock_path


def _git(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=project_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def _commit_all(project_root: Path, message: str) -> None:
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-q", "-m", message)


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        json=False,
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    reason: str,
    *,
    no_run: bool = False,
    preserve_red_evidence: bool = False,
    stash_implementation: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=no_run,
        preserve_red_evidence=preserve_red_evidence,
        stash_implementation=stash_implementation,
        json=False,
    )


def _lock_record(project_root: Path, slug: str = "demo-task") -> dict:
    return json.loads(default_plan_lock_path(project_root, slug).read_text())


def _write_tracked_project(project_root: Path) -> Path:
    (project_root / "manifests").mkdir()
    (project_root / "src").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "src" / "__init__.py").write_text("")
    (project_root / "src" / "demo.py").write_text("def demo() -> int:\n    return 0\n")
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\n"
        "def test_demo_contract():\n"
        "    assert demo() == 1\n"
    )
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-26T00:00:00Z"
files:
  edit:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          args: []
          returns: int
  read:
    - tests/test_demo.py
validate:
  - python -m pytest -q tests/test_demo.py
"""
    )
    _git(project_root, "init", "-q")
    _commit_all(project_root, "red contract")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    _commit_all(project_root, "plan lock")
    return manifest_path


def _write_untracked_create_project(project_root: Path) -> Path:
    (project_root / "manifests").mkdir()
    (project_root / "scripts").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "scripts" / "validate_generated.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "sys.exit(0 if Path('src/generated.py').exists() else 1)\n"
    )
    (project_root / "tests" / "test_generated_contract.py").write_text(
        "from pathlib import Path\n\n\n"
        "def test_generated_contract_path_is_declared():\n"
        "    assert Path('src/generated.py').as_posix() == 'src/generated.py'\n"
    )
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Demo generated task"
type: feature
created: "2026-06-26T00:00:00Z"
files:
  create:
    - path: src/generated.py
      artifacts:
        - kind: attribute
          name: VALUE
          of: module
          type: int
  read:
    - tests/test_generated_contract.py
validate:
  - python scripts/validate_generated.py
"""
    )
    _git(project_root, "init", "-q")
    _commit_all(project_root, "red generated contract")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    _commit_all(project_root, "plan lock")
    return manifest_path


def test_revise_parser_exposes_stash_implementation() -> None:
    args = build_parser().parse_args(
        [
            "plan",
            "revise",
            "manifests/demo-task.manifest.yaml",
            "--reason",
            "review added missing behavior",
            "--stash-implementation",
        ]
    )

    assert args.stash_implementation is True


def test_stash_implementation_recaptures_red_evidence_and_restores_tracked_change(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    implementation_path = tmp_path / "src" / "demo.py"
    implementation_path.write_text("def demo() -> int:\n    return 1\n")
    test_path = tmp_path / "tests" / "test_demo.py"
    test_path.write_text(
        "from src.demo import demo\n\n\n"
        "def test_demo_contract():\n"
        "    assert demo() == 1\n"
        "    assert demo() != 2\n"
    )
    manifest_path.write_text(
        manifest_path.read_text().replace("Demo task", "Demo task with review gap")
    )

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added the missing not-two assertion",
        )
    )

    assert exit_code == 0
    assert implementation_path.read_text() == "def demo() -> int:\n    return 1\n"
    assert _git(tmp_path, "stash", "list") == ""
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"]["red"] is True
    assert record["red_evidence"]["commands"][0]["classification"] == "red"
    assert record["test_hashes"]["tests/test_demo.py"].startswith("sha256:")


def test_stash_implementation_restores_untracked_declared_create_file(
    tmp_path: Path,
) -> None:
    manifest_path = _write_untracked_create_project(tmp_path)
    generated_path = tmp_path / "src" / "generated.py"
    generated_path.parent.mkdir()
    generated_path.write_text("VALUE = 1\n")
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "Demo generated task", "Demo generated task with reviewed contract"
        )
    )

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added generated contract metadata",
        )
    )

    assert exit_code == 0
    assert generated_path.read_text() == "VALUE = 1\n"
    assert _git(tmp_path, "stash", "list") == ""
    assert _lock_record(tmp_path)["red_evidence"]["red"] is True


def test_stash_implementation_rejects_green_stashed_state_without_revising_lock(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    implementation_path = tmp_path / "src" / "demo.py"
    implementation_path.write_text("def demo() -> int:\n    return 1\n")
    test_path = tmp_path / "tests" / "test_demo.py"
    test_path.write_text(
        "from src.demo import demo\n\n\n"
        "def test_demo_contract():\n"
        "    assert demo() in {0, 1}\n"
    )
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    original_lock = lock_path.read_bytes()

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, "weak test stayed green")
    )

    assert exit_code == 1
    assert lock_path.read_bytes() == original_lock
    assert implementation_path.read_text() == "def demo() -> int:\n    return 1\n"
    assert _git(tmp_path, "stash", "list") == ""


def test_stash_implementation_rejects_unrelated_dirty_paths_before_stashing(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    implementation_path = tmp_path / "src" / "demo.py"
    implementation_path.write_text("def demo() -> int:\n    return 1\n")
    (tmp_path / "README.md").write_text("unrelated user work\n")
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    original_lock = lock_path.read_bytes()

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, "review added missing behavior")
    )

    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock
    assert implementation_path.read_text() == "def demo() -> int:\n    return 1\n"
    assert _git(tmp_path, "stash", "list") == ""


def test_stash_implementation_allows_current_lock_dirty(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    implementation_path = tmp_path / "src" / "demo.py"
    implementation_path.write_text("def demo() -> int:\n    return 1\n")
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    lock_path.write_text(lock_path.read_text() + "\n")

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added missing behavior while lock was uncommitted",
        )
    )

    assert exit_code == 0
    assert implementation_path.read_text() == "def demo() -> int:\n    return 1\n"
    assert _git(tmp_path, "stash", "list") == ""
    assert _lock_record(tmp_path)["red_evidence"]["red"] is True


def test_stash_implementation_ignores_clean_missing_create_targets(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "  read:\n",
            "  create:\n"
            "    - path: src/extra.py\n"
            "      artifacts:\n"
            "        - kind: attribute\n"
            "          name: EXTRA\n"
            "          of: module\n"
            "          type: int\n"
            "  read:\n",
        )
    )
    assert not (tmp_path / "src" / "extra.py").exists()
    implementation_path = tmp_path / "src" / "demo.py"
    implementation_path.write_text("def demo() -> int:\n    return 1\n")

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added missing behavior while create target stayed absent",
        )
    )

    assert exit_code == 0
    assert implementation_path.read_text() == "def demo() -> int:\n    return 1\n"
    assert not (tmp_path / "src" / "extra.py").exists()
    assert _git(tmp_path, "stash", "list") == ""


def test_stash_implementation_restores_original_when_validate_creates_new_stash(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_creates_stash.py").write_text(
        "from pathlib import Path\n"
        "import subprocess\n"
        "import sys\n"
        "Path('validate-created.txt').write_text('validate stash\\n')\n"
        "subprocess.run([\n"
        "    'git', 'stash', 'push', '--include-untracked',\n"
        "    '--message', 'validate-created-stash', '--',\n"
        "    'validate-created.txt',\n"
        "], check=True)\n"
        "sys.exit(1)\n"
    )
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "  - python -m pytest -q tests/test_demo.py",
            "  - python scripts/validate_creates_stash.py",
        )
    )
    _commit_all(tmp_path, "validate command creates a stash")
    implementation_path = tmp_path / "src" / "demo.py"
    implementation_path.write_text("def demo() -> int:\n    return 1\n")

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added missing behavior while validate created a stash",
        )
    )

    stash_list = _git(tmp_path, "stash", "list")
    assert exit_code == 0
    assert implementation_path.read_text() == "def demo() -> int:\n    return 1\n"
    assert "validate-created-stash" in stash_list
    assert "maid plan revise --stash-implementation" not in stash_list
    assert _lock_record(tmp_path)["red_evidence"]["red"] is True


def test_stash_implementation_preserves_stash_when_validate_dirties_target(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_dirties_target.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path('src/demo.py').write_text('def demo() -> int:\\n    return 99\\n')\n"
        "sys.exit(1)\n"
    )
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "  - python -m pytest -q tests/test_demo.py",
            "  - python scripts/validate_dirties_target.py",
        )
    )
    _commit_all(tmp_path, "validate command dirties target")
    implementation_path = tmp_path / "src" / "demo.py"
    implementation_path.write_text("def demo() -> int:\n    return 1\n")
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    original_lock = lock_path.read_bytes()

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added missing behavior while validate dirtied target",
        )
    )

    stash_list = _git(tmp_path, "stash", "list")
    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock
    assert implementation_path.read_text() == "def demo() -> int:\n    return 99\n"
    assert "maid plan revise --stash-implementation" in stash_list


def test_stash_implementation_rejects_validate_mutated_behavioral_test(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate_mutates_test.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path('tests/test_demo.py').write_text(\n"
        "    'from src.demo import demo\\n\\n\\n'\n"
        "    'def test_demo_contract():\\n'\n"
        "    '    assert demo() == 0\\n'\n"
        ")\n"
        "sys.exit(1)\n"
    )
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "  - python -m pytest -q tests/test_demo.py",
            "  - python scripts/validate_mutates_test.py",
        )
    )
    _commit_all(tmp_path, "validate command mutates behavioral test")
    implementation_path = tmp_path / "src" / "demo.py"
    implementation_path.write_text("def demo() -> int:\n    return 1\n")
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    original_lock = lock_path.read_bytes()

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added missing behavior while validate mutated the test",
        )
    )

    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock
    assert implementation_path.read_text() == "def demo() -> int:\n    return 1\n"
    assert "assert demo() == 0" in (tmp_path / "tests" / "test_demo.py").read_text()
    assert _git(tmp_path, "stash", "list") == ""


def test_stash_implementation_rejects_conflicting_revise_modes(
    tmp_path: Path,
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    original_lock = default_plan_lock_path(tmp_path, "demo-task").read_bytes()

    no_run_exit = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "conflicting no-run mode",
            no_run=True,
        )
    )
    preserve_exit = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "conflicting preserve mode",
            preserve_red_evidence=True,
        )
    )

    assert no_run_exit == 2
    assert preserve_exit == 2
    assert default_plan_lock_path(tmp_path, "demo-task").read_bytes() == original_lock


def test_docs_describe_stash_implementation_revise_workflow() -> None:
    packaged_workflow = Path("maid_runner/docs/draft-manifest-workflow.md").read_text()
    docs = (
        Path("docs/maid_specs.md").read_text()
        + Path("docs/draft-manifest-workflow.md").read_text()
        + Path("README.md").read_text()
    )

    assert "--stash-implementation" in docs
    assert "--stash-implementation" in packaged_workflow
    assert "--preserve-red-evidence" in docs
    assert "behavioral test" in docs
    assert "implementation" in docs
