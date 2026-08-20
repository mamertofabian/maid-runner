"""Behavioral coverage for stash-induced import obstruction during plan revise."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.plan_lock import default_plan_lock_path

if TYPE_CHECKING:
    from tests.support.git_project_templates import GitProjectTemplateFactory


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
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        json=False,
    )


def _revise_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason="review added backend artifact and frontend regression",
        no_run=False,
        preserve_red_evidence=False,
        stash_implementation=True,
        allow_sibling_dirty=False,
        test_only_green=False,
        json=False,
    )


def _write_locked_full_stack_project(
    project_root: Path,
    template_factory: GitProjectTemplateFactory | None = None,
) -> Path:
    if template_factory is not None:
        from tests.support.git_project_templates import clone_git_project_template

        template = template_factory.get("stash-import-obstruction")
        clone_git_project_template(template, project_root)
        return project_root / "manifests" / "full-stack.manifest.yaml"

    for relative in ("manifests", "app", "tests"):
        (project_root / relative).mkdir()
    (project_root / "app" / "__init__.py").write_text("")
    (project_root / "app" / "models.py").write_text(
        "def legacy() -> int:\n    return 0\n"
    )
    (project_root / "tests" / "test_backend.py").write_text(
        "from app.models import legacy\n\n\n"
        "def test_legacy():\n"
        "    assert legacy() == 1\n"
    )
    (project_root / "tests" / "test_frontend.py").write_text(
        "def test_frontend():\n    assert True\n"
    )
    (project_root / "tests" / "always_invalid.py").write_text("raise SystemExit(2)\n")
    (project_root / "tests" / "restoration_runner.py").write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path.cwd()))\n\n"
        "try:\n"
        "    from app.models import NewItem\n"
        "except ImportError:\n"
        "    raise SystemExit(2)\n\n"
        "path = Path('app/models.py')\n"
        "if os.environ['STASH_MUTATION'] == 'content':\n"
        "    path.write_text(path.read_text() + '# validation mutation\\n')\n"
        "else:\n"
        "    path.chmod(path.stat().st_mode ^ 0o100)\n"
        "assert NewItem().value == 1\n"
        "sys.exit(0)\n"
    )
    manifest_path = project_root / "manifests" / "full-stack.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Full-stack revision"
type: fix
created: "2026-08-10T00:00:00Z"
files:
  edit:
    - path: app/models.py
      artifacts:
        - kind: function
          name: legacy
          args: []
          returns: int
  read:
    - tests/test_backend.py
    - tests/test_frontend.py
validate:
  - python -m pytest -q tests/test_backend.py
  - python -m pytest -q tests/test_frontend.py
"""
    )
    _git(project_root, "init", "-q")
    _commit_all(project_root, "red baseline")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    from tests.support.git_project_templates import _remove_python_caches

    _remove_python_caches(project_root)
    _commit_all(project_root, "lock baseline")
    return manifest_path


def _add_review_revision(project_root: Path, manifest_path: Path) -> Path:
    implementation_path = project_root / "app" / "models.py"
    implementation_path.write_text(
        "def legacy() -> int:\n"
        "    return 1\n\n\n"
        "class NewItem:\n"
        "    value: int = 1\n"
    )
    (project_root / "tests" / "test_backend.py").write_text(
        "from app.models import NewItem, legacy\n\n\n"
        "def test_backend_contract():\n"
        "    assert legacy() == 1\n"
        "    assert NewItem().value == 1\n"
    )
    (project_root / "tests" / "test_frontend.py").write_text(
        "def test_frontend_review_regression():\n"
        '    assert False, "review-found frontend gap"\n'
    )
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "          returns: int\n",
            "          returns: int\n"
            "        - kind: class\n"
            "          name: NewItem\n",
        )
    )
    return implementation_path


def test_stash_revision_accepts_red_when_restoration_resolves_import_obstruction(
    tmp_path: Path,
    git_project_template_factory: GitProjectTemplateFactory,
) -> None:
    manifest_path = _write_locked_full_stack_project(
        tmp_path, git_project_template_factory
    )
    implementation_path = _add_review_revision(tmp_path, manifest_path)

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    lock = json.loads(default_plan_lock_path(tmp_path, "full-stack").read_text())
    evidence = lock["red_evidence"]
    assert exit_code == 0
    assert lock["revision"] == 2
    assert evidence["red"] is True
    assert evidence["mode"] == "stash_restoration"
    assert [command["classification"] for command in evidence["commands"]] == [
        "invalid",
        "red",
    ]
    assert [command["classification"] for command in evidence["restored_commands"]] == [
        "not_red",
        "red",
    ]
    assert "class NewItem" in implementation_path.read_text()
    assert _git(tmp_path, "stash", "list") == ""


def test_stash_revision_rejects_invalid_command_that_restoration_does_not_resolve(
    tmp_path: Path,
    git_project_template_factory: GitProjectTemplateFactory,
) -> None:
    manifest_path = _write_locked_full_stack_project(
        tmp_path, git_project_template_factory
    )
    implementation_path = _add_review_revision(tmp_path, manifest_path)
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "  - python -m pytest -q tests/test_backend.py\n",
            "  - python tests/always_invalid.py\n",
        )
    )
    original_lock = default_plan_lock_path(tmp_path, "full-stack").read_bytes()

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 1
    assert default_plan_lock_path(tmp_path, "full-stack").read_bytes() == original_lock
    assert "class NewItem" in implementation_path.read_text()
    assert _git(tmp_path, "stash", "list") == ""


@pytest.mark.parametrize("mutation", ["content", "mode"])
def test_stash_revision_recovers_exact_implementation_when_restored_validation_mutates_it(
    tmp_path: Path,
    mutation: str,
    git_project_template_factory: GitProjectTemplateFactory,
) -> None:
    manifest_path = _write_locked_full_stack_project(
        tmp_path, git_project_template_factory
    )
    implementation_path = _add_review_revision(tmp_path, manifest_path)
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "python -m pytest -q tests/test_backend.py",
            f"env STASH_MUTATION={mutation} python tests/restoration_runner.py",
        )
    )
    lock_path = default_plan_lock_path(tmp_path, "full-stack")
    if mutation == "mode":
        implementation_path.chmod(0o600)
    original_lock = lock_path.read_bytes()
    original_content = implementation_path.read_bytes()
    original_mode = implementation_path.stat().st_mode

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock
    assert implementation_path.read_bytes() == original_content
    assert implementation_path.stat().st_mode == original_mode
    assert _git(tmp_path, "stash", "list") == ""
