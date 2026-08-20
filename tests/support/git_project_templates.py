"""Reusable immutable real-Git projects for subprocess-heavy policy tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

from maid_runner.cli.commands.plan import cmd_plan_lock


@dataclass(frozen=True)
class GitProjectTemplate:
    """An immutable committed project used as the source for local clones."""

    source_root: Path
    revision: str
    shape: str


class GitProjectTemplateFactory:
    """Build and retain one immutable real-Git repository per project shape."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.build_count = 0
        self._templates: dict[str, GitProjectTemplate] = {}

    def get(self, shape: str) -> GitProjectTemplate:
        """Return the cached template for ``shape``, building it once."""
        cached = self._templates.get(shape)
        if cached is not None:
            return cached

        template = build_git_project_template(self.root / shape, shape)
        self._templates[shape] = template
        self.build_count += 1
        return template


def build_git_project_template(root: Path, shape: str) -> GitProjectTemplate:
    """Create one canonical committed real-Git repository for ``shape``."""
    builders = {
        "legacy-baseline": _write_legacy_baseline_project,
        "stash-red-contract": _write_stash_red_contract_project,
        "stash-import-obstruction": _write_stash_import_obstruction_project,
    }
    try:
        builder = builders[shape]
    except KeyError as exc:
        raise ValueError(f"Unsupported Git project template shape: {shape}") from exc

    project_root = Path(root)
    if project_root.exists():
        raise FileExistsError(
            f"Git template destination already exists: {project_root}"
        )
    project_root.mkdir(parents=True)
    builder(project_root)
    revision = _git(project_root, "rev-parse", "HEAD").stdout.strip()
    if _git(project_root, "status", "--porcelain").stdout:
        raise RuntimeError(f"Git template {shape!r} was not built cleanly")
    return GitProjectTemplate(
        source_root=project_root,
        revision=revision,
        shape=shape,
    )


def clone_git_project_template(template: GitProjectTemplate, destination: Path) -> Path:
    """Clone ``template`` with an independent index, worktree, and objects."""
    target = Path(destination)
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise FileExistsError(f"Git template clone destination exists: {target}")
        target.rmdir()
    target.parent.mkdir(parents=True, exist_ok=True)

    source_status = _git(template.source_root, "status", "--porcelain").stdout
    if source_status:
        raise RuntimeError(f"Git template {template.shape!r} is dirty before clone")
    _run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-hardlinks",
            str(template.source_root),
            str(target),
        ],
        cwd=target.parent,
    )
    _git(target, "remote", "remove", "origin")

    actual_revision = _git(target, "rev-parse", "HEAD").stdout.strip()
    if actual_revision != template.revision:
        raise RuntimeError(
            f"Git template clone revision mismatch: {actual_revision} != "
            f"{template.revision}"
        )
    if _git(target, "status", "--porcelain").stdout:
        raise RuntimeError(f"Git template clone {target} did not start cleanly")
    if _git(template.source_root, "status", "--porcelain").stdout:
        raise RuntimeError(f"Git template {template.shape!r} changed during clone")
    if (target / ".git" / "objects" / "info" / "alternates").exists():
        raise RuntimeError("Git template clone unexpectedly shares an object store")
    return target


def _run(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "git",
            "-c",
            "user.name=MAID Test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=project_root,
    )


def _commit_all(project_root: Path, message: str) -> None:
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-qm", message)


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        json=False,
    )


def _init_and_commit(project_root: Path, message: str) -> None:
    _git(project_root, "init", "-q")
    _git(project_root, "config", "user.email", "maid-test@example.com")
    _git(project_root, "config", "user.name", "MAID Test")
    _commit_all(project_root, message)


def _remove_python_caches(project_root: Path) -> None:
    for cache_path in project_root.rglob("__pycache__"):
        shutil.rmtree(cache_path)


def _write_legacy_baseline_project(project_root: Path) -> None:
    for relative in ("manifests", "src", "tests", "scripts"):
        (project_root / relative).mkdir()
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n", encoding="utf-8"
    )
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo() -> None:\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    (project_root / "tests" / "test_other.py").write_text(
        "from src.demo import demo\n\n\ndef test_other() -> None:\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    (project_root / "scripts" / "validate.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8"
    )
    (project_root / "manifests" / "legacy-task.manifest.yaml").write_text(
        """schema: "2"
goal: "Completed legacy task"
type: fix
created: "2026-05-01T00:00:00Z"
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
  - python scripts/validate.py
""",
        encoding="utf-8",
    )
    _init_and_commit(project_root, "legacy completed task")


def _write_stash_red_contract_project(project_root: Path) -> None:
    for relative in ("manifests", "src", "tests"):
        (project_root / relative).mkdir()
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
    _init_and_commit(project_root, "red contract")
    if cmd_plan_lock(_lock_args(manifest_path, project_root)) != 0:
        raise RuntimeError("Failed to lock stash red-contract template")
    _remove_python_caches(project_root)
    _commit_all(project_root, "plan lock")


def _write_stash_import_obstruction_project(project_root: Path) -> None:
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
    _init_and_commit(project_root, "red baseline")
    if cmd_plan_lock(_lock_args(manifest_path, project_root)) != 0:
        raise RuntimeError("Failed to lock stash import-obstruction template")
    _remove_python_caches(project_root)
    _commit_all(project_root, "lock baseline")
