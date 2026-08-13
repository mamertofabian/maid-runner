from __future__ import annotations

import ast
import hashlib
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest


def test_snapshot_source_and_ast_reader_observes_mutated_bytes(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import (
        KnockoutProjectSnapshot,
        MaterializedProjectSnapshotBackend,
    )

    root = _project(tmp_path)
    original = (root / "src/target.py").read_bytes()

    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "source-reader"
    ) as snapshot:
        assert isinstance(snapshot, KnockoutProjectSnapshot)
        assert snapshot.input_digest
        target = snapshot.root / "src/target.py"
        target.write_text(
            'def target():\n    raise NotImplementedError("maid-knockout")\n'
        )
        tree = ast.parse(target.read_text())
        assert isinstance(tree.body[0], ast.FunctionDef)
        assert "maid-knockout" in target.read_text()

    assert (root / "src/target.py").read_bytes() == original
    assert not snapshot.root.exists()


def test_snapshot_path_loader_and_editable_import_observe_mutation(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend
    from maid_runner.core.knockout import KnockoutCommandExecutor

    root = _project(tmp_path)
    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "path-loader"
    ) as snapshot:
        (snapshot.root / "src/target.py").write_text("VALUE = 'snapshot'\n")
        result = KnockoutCommandExecutor().execute(
            (
                sys.executable,
                "-c",
                "import importlib.util, pathlib; "
                "p=pathlib.Path('src/target.py'); "
                "s=importlib.util.spec_from_file_location('loaded', p); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "assert m.VALUE == 'snapshot'",
            ),
            snapshot.root,
            "snapshot",
            snapshot.environment_overrides,
            snapshot.environment_removals,
        )

    assert result.exit_code == 0, result.stderr


def test_snapshot_subprocess_and_nonpytest_command_observe_mutation(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend
    from maid_runner.core.knockout import KnockoutCommandExecutor

    root = _project(tmp_path)
    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "subprocess"
    ) as snapshot:
        (snapshot.root / "src/target.py").write_text("VALUE = 'mutated'\n")
        result = KnockoutCommandExecutor().execute(
            (
                sys.executable,
                "-c",
                "import subprocess,sys; "
                "p=subprocess.run([sys.executable,'-c',"
                "\"from pathlib import Path; assert 'mutated' in "
                "Path('src/target.py').read_text()\"]); raise SystemExit(p.returncode)",
            ),
            snapshot.root,
            "snapshot",
            snapshot.environment_overrides,
            snapshot.environment_removals,
        )

    assert result.exit_code == 0, result.stderr


def test_snapshot_generated_and_cache_writes_are_worker_local(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project(tmp_path)
    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "generated"
    ) as snapshot:
        (snapshot.root / ".pytest_cache").mkdir()
        (snapshot.root / ".pytest_cache/worker").write_text("local")
        (snapshot.root / "generated.txt").write_text("local")
        assert not (root / ".pytest_cache/worker").exists()
        assert not (root / "generated.txt").exists()

    assert not snapshot.root.exists()


def test_duplicate_declarations_receive_fresh_snapshot_state(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project(tmp_path)
    backend = MaterializedProjectSnapshotBackend()
    with backend.create(root, ("src/target.py",), "first") as first:
        (first.root / "state.txt").write_text("first declaration")
    with backend.create(root, ("src/target.py",), "second") as second:
        assert not (second.root / "state.txt").exists()


def test_stateful_cross_declaration_dependency_is_visible_hardening_not_silent_success(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch
    from maid_runner.core.manifest import load_manifest

    root = _project(tmp_path)
    first = _manifest(
        root,
        "first",
        "target",
        "python first_check.py",
    )
    second = _manifest(
        root,
        "second",
        "target",
        "python second_check.py",
    )
    (root / "first_check.py").write_text(
        "from pathlib import Path\n"
        "source = Path('src/target.py').read_text()\n"
        "Path('state.txt').write_text('created')\n"
        "raise SystemExit(1 if 'maid-knockout' in source else 0)\n"
    )
    (root / "second_check.py").write_text(
        "from pathlib import Path\n"
        "source = Path('src/target.py').read_text()\n"
        "raise SystemExit(0 if Path('state.txt').exists() else 2)\n"
    )

    reports = run_knockout_batch(
        (load_manifest(first), load_manifest(second)), root, allow_dirty=True
    )

    assert reports[str(first)].success is True
    assert reports[str(second)].success is False
    assert reports[str(second)].errors[0].code.value == "E712"
    assert not (root / "state.txt").exists()


def test_snapshot_uses_current_dirty_and_relevant_untracked_inputs(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project(tmp_path, git=True)
    (root / "src/target.py").write_text("VALUE = 'dirty'\n")
    (root / "input.txt").write_text("untracked")

    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py", "input.txt"), "dirty"
    ) as snapshot:
        first_input_digest = snapshot.input_digest
        assert (snapshot.root / "src/target.py").read_text() == "VALUE = 'dirty'\n"
        assert (snapshot.root / "input.txt").read_text() == "untracked"
        assert (
            snapshot.source_digests["src/target.py"]
            == hashlib.sha256(b"VALUE = 'dirty'\n").hexdigest()
        )
    (root / "input.txt").write_text("changed untracked input")
    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py", "input.txt"), "dirty-changed"
    ) as changed:
        assert changed.input_digest != first_input_digest


def test_snapshot_never_changes_original_bytes_or_git_status(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project(tmp_path, git=True)
    before = _git(root, "status", "--porcelain=v1", "-z")
    original = (root / "src/target.py").read_bytes()

    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "unchanged"
    ) as snapshot:
        assert (snapshot.root / "src/target.py").stat().st_ino != (
            root / "src/target.py"
        ).stat().st_ino
        (snapshot.root / "src/target.py").write_text("changed\n")
        _git(snapshot.root, "add", "src/target.py")

    assert (root / "src/target.py").read_bytes() == original
    assert _git(root, "status", "--porcelain=v1", "-z") == before

    nongit = _project(tmp_path / "nongit")
    with pytest.raises(RuntimeError, match="input|source|changed"):
        with MaterializedProjectSnapshotBackend().create(
            nongit, ("src/target.py",), "source-input-guard"
        ):
            (nongit / "src/target.py").write_text("external mutation\n")

    (root / "untracked.txt").write_text("before\n")
    with pytest.raises(RuntimeError, match="input|source|changed"):
        with MaterializedProjectSnapshotBackend().create(
            root, ("src/target.py", "untracked.txt"), "untracked-input-guard"
        ):
            (root / "untracked.txt").write_text("same status, different bytes\n")


def test_ordinary_git_directory_is_independently_writable(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project(tmp_path, git=True)
    source_head = _git(root, "rev-parse", "HEAD")
    _git(root, "config", "core.worktree", str(root))
    fsmonitor = root / "fsmonitor.py"
    fsmonitor.write_text(
        "#!/usr/bin/env python3\n"
        "from pathlib import Path\n"
        f"Path({str(root / 'source-fsmonitor-ran')!r}).write_text('unsafe')\n"
    )
    fsmonitor.chmod(0o755)
    _git(root, "config", "core.fsmonitor", str(fsmonitor))

    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "ordinary-git"
    ) as snapshot:
        assert snapshot.git_dir is not None
        assert snapshot.git_dir.is_relative_to(snapshot.root)
        assert Path(_git(snapshot.root, "rev-parse", "--show-toplevel")).resolve() == (
            snapshot.root.resolve()
        )
        _git(snapshot.root, "status", "--porcelain")
        assert not (root / "source-fsmonitor-ran").exists()
        (snapshot.root / "snapshot.txt").write_text("snapshot")
        _git(snapshot.root, "add", "snapshot.txt")
        _git(snapshot.root, "commit", "-m", "snapshot commit")
        assert _git(snapshot.root, "rev-parse", "HEAD") != source_head

    assert _git(root, "rev-parse", "HEAD") == source_head


def test_linked_worktree_git_pointer_and_common_dir_are_not_shared(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project(tmp_path / "main", git=True)
    linked = tmp_path / "linked"
    _git(root, "worktree", "add", "-b", "linked-test", str(linked))
    _git(root, "config", "extensions.worktreeConfig", "true")
    _git(linked, "config", "--worktree", "core.worktree", str(linked))
    source_git_dir = Path(_git(linked, "rev-parse", "--absolute-git-dir"))
    source_common = Path(_git(linked, "rev-parse", "--git-common-dir"))
    source_head = _git(linked, "rev-parse", "HEAD")
    source_worktrees = _git(root, "worktree", "list", "--porcelain")

    with MaterializedProjectSnapshotBackend().create(
        linked, ("src/target.py",), "linked-git"
    ) as snapshot:
        assert (snapshot.root / ".git").is_dir()
        assert snapshot.git_dir is not None and snapshot.git_common_dir is not None
        assert snapshot.git_dir.is_relative_to(snapshot.root)
        assert snapshot.git_common_dir.is_relative_to(snapshot.root)
        assert snapshot.git_dir.resolve() not in {
            source_git_dir.resolve(),
            source_common.resolve(),
        }
        assert Path(_git(snapshot.root, "rev-parse", "--show-toplevel")).resolve() == (
            snapshot.root.resolve()
        )
        (snapshot.root / "linked-snapshot.txt").write_text("snapshot")
        _git(snapshot.root, "add", "linked-snapshot.txt")
        _git(snapshot.root, "commit", "-m", "linked snapshot commit")
        assert _git(snapshot.root, "rev-parse", "HEAD") != source_head

    assert _git(linked, "rev-parse", "HEAD") == source_head
    assert _git(root, "worktree", "list", "--porcelain") == source_worktrees


def test_snapshot_git_commands_cannot_change_original_head_refs_stash_config_index_objects_or_registrations(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project(tmp_path, git=True)
    backend = MaterializedProjectSnapshotBackend()
    with backend.create(root, ("src/target.py",), "git-identity") as snapshot:
        before = snapshot.source_repository_identity
        _git(snapshot.root, "config", "snapshot.changed", "true")
        (snapshot.root / "src/target.py").write_text("snapshot change\n")
        _git(snapshot.root, "add", "src/target.py")
        _git(snapshot.root, "commit", "-m", "snapshot change")
        (snapshot.root / "stash.txt").write_text("stash")
        _git(snapshot.root, "add", "stash.txt")
        _git(snapshot.root, "stash", "push", "-m", "snapshot stash")
        _git(snapshot.root, "gc")

    with backend.create(root, ("src/target.py",), "identity-check") as check:
        assert check.source_repository_identity == before

    _git(root, "config", "extensions.worktreeConfig", "true")
    with pytest.raises(RuntimeError, match="metadata|repository"):
        with backend.create(root, ("src/target.py",), "worktree-config-guard"):
            _git(root, "config", "--worktree", "snapshot.external", "changed")


def test_inherited_git_repository_pointer_environment_is_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend
    from maid_runner.core.knockout import KnockoutCommandExecutor

    root = _project(tmp_path, git=True)
    monkeypatch.setenv("GIT_DIR", str(root / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(root))

    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "git-environment"
    ) as snapshot:
        result = KnockoutCommandExecutor().execute(
            ("git", "rev-parse", "--show-toplevel"),
            snapshot.root,
            "snapshot",
            snapshot.environment_overrides,
            snapshot.environment_removals,
        )

    assert result.exit_code == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == snapshot.root.resolve()


def test_snapshot_preserves_only_resolved_git_author_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend
    from maid_runner.core.knockout import KnockoutCommandExecutor

    root = _project(tmp_path)
    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "non-git-author"
    ) as non_git_snapshot:
        assert non_git_snapshot.git_dir is None
        assert non_git_snapshot.environment_overrides["GIT_CONFIG_GLOBAL"] == os.devnull
        assert not (non_git_snapshot.root / "maid-global-config").exists()

    global_config = tmp_path / "source-global.gitconfig"
    global_config.write_text(
        "[user]\n"
        "\tname = Snapshot Global Author\n"
        "\temail = global-author@example.test\n"
        "[alias]\n"
        "\tdangerous = !touch should-not-run\n"
        "[credential]\n"
        "\thelper = should-not-copy\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    subprocess.run(("git", "init", "-q"), cwd=root, check=True)
    subprocess.run(("git", "add", "."), cwd=root, check=True)
    subprocess.run(("git", "commit", "-qm", "fixture"), cwd=root, check=True)

    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "git-author"
    ) as snapshot:
        isolated_config = Path(snapshot.environment_overrides["GIT_CONFIG_GLOBAL"])
        config_text = isolated_config.read_text()
        config_keys = subprocess.run(
            ("git", "config", "--file", str(isolated_config), "--name-only", "--list"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        result = KnockoutCommandExecutor().execute(
            ("git", "var", "GIT_AUTHOR_IDENT"),
            snapshot.root,
            "snapshot",
            snapshot.environment_overrides,
            snapshot.environment_removals,
        )

        assert isolated_config != global_config
        assert isolated_config.is_relative_to(snapshot.root / ".git")
        assert "Snapshot Global Author" in config_text
        assert "global-author@example.test" in config_text
        assert "dangerous" not in config_text
        assert "credential" not in config_text
        assert set(config_keys) == {"user.name", "user.email"}

    assert result.exit_code == 0, result.stderr
    assert "Snapshot Global Author <global-author@example.test>" in result.stdout

    global_config.write_text(
        "[user]\n"
        "\tname = Changed Snapshot Author\n"
        "\temail = changed-author@example.test\n"
    )
    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "changed-git-author"
    ) as changed_snapshot:
        changed_result = KnockoutCommandExecutor().execute(
            ("git", "var", "GIT_AUTHOR_IDENT"),
            changed_snapshot.root,
            "changed-snapshot",
            changed_snapshot.environment_overrides,
            changed_snapshot.environment_removals,
        )

    assert changed_result.exit_code == 0, changed_result.stderr
    assert (
        "Changed Snapshot Author <changed-author@example.test>" in changed_result.stdout
    )

    global_config.write_text("[user]\n\tname = Incomplete Author\n")
    with MaterializedProjectSnapshotBackend().create(
        root, ("src/target.py",), "incomplete-git-author"
    ) as incomplete_snapshot:
        incomplete_config = Path(
            incomplete_snapshot.environment_overrides["GIT_CONFIG_GLOBAL"]
        )
        incomplete_result = KnockoutCommandExecutor().execute(
            ("git", "var", "GIT_AUTHOR_IDENT"),
            incomplete_snapshot.root,
            "incomplete-snapshot",
            incomplete_snapshot.environment_overrides,
            incomplete_snapshot.environment_removals,
        )

        assert incomplete_config.read_text() == ""

    assert incomplete_result.exit_code != 0
    assert "Author identity unknown" in incomplete_result.stderr


def test_snapshot_dependency_environment_loads_snapshot_project_bytes(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend
    from maid_runner.core.knockout import KnockoutCommandExecutor

    root = _project(tmp_path)
    subprocess.run(
        ("uv", "venv", ".venv", "--python", sys.executable),
        cwd=root,
        check=True,
        capture_output=True,
    )
    site_packages = next((root / ".venv/lib").glob("python*/site-packages"))
    package = root / "src/editable_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 'source'\n")
    (site_packages / "editable_fixture.pth").write_text("import editable_finder\n")
    (site_packages / "editable_finder.py").write_text(
        "import importlib.abc, importlib.util, pathlib, sys\n"
        f"SOURCE = pathlib.Path({str(package / '__init__.py')!r})\n"
        "class Finder(importlib.abc.MetaPathFinder):\n"
        "    @classmethod\n"
        "    def find_spec(cls, fullname, path=None, target=None):\n"
        "        if fullname == 'editable_pkg':\n"
        "            return importlib.util.spec_from_file_location(fullname, SOURCE)\n"
        "sys.meta_path.insert(0, Finder)\n"
    )
    launcher = root / ".venv/bin/snapshot-tool"
    launcher.write_text(
        f"#!{root / '.venv/bin/python'}\n"
        "import editable_pkg, pathlib, sys\n"
        "assert editable_pkg.VALUE == 'snapshot'\n"
        "assert pathlib.Path(sys.prefix).resolve().is_relative_to(pathlib.Path.cwd())\n"
    )
    launcher.chmod(0o755)
    (root / "node_modules/package").mkdir(parents=True)
    (root / "node_modules/package/index.js").write_text("source dependency\n")
    venv_before = _directory_stat_identity(root / ".venv")
    node_before = _directory_stat_identity(root / "node_modules")
    inherited = tmp_path / "inherited"
    inherited.mkdir()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("PWD", str(root))
        monkeypatch.setenv("VIRTUAL_ENV", str(inherited))
        monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(inherited))
        monkeypatch.setenv("NODE_PATH", str(inherited))
        with MaterializedProjectSnapshotBackend().create(
            root, ("src/target.py",), "dependency-environment"
        ) as snapshot:
            (snapshot.root / "src/target.py").write_text("VALUE = 'snapshot-env'\n")
            (snapshot.root / "src/editable_pkg/__init__.py").write_text(
                "VALUE = 'snapshot'\n"
            )
            assert snapshot.environment_overrides["UV_NO_SYNC"] == "1"
            result = KnockoutCommandExecutor().execute(
                (
                    sys.executable,
                    "-c",
                    "import os,pathlib; from src.target import VALUE; "
                    "root=pathlib.Path.cwd(); "
                    "assert pathlib.Path(os.environ['PWD']).resolve() == root; "
                    "assert VALUE == 'snapshot-env'; "
                    "venv=pathlib.Path(os.environ['VIRTUAL_ENV']); "
                    "node=pathlib.Path(os.environ['NODE_PATH']); "
                    "assert venv.resolve().is_relative_to(root); "
                    "assert node.resolve().is_relative_to(root); "
                    "(venv/'command-write').write_text('local'); "
                    "(node/'command-write').write_text('local')",
                ),
                snapshot.root,
                "snapshot",
                snapshot.environment_overrides,
                snapshot.environment_removals,
            )
            launcher_result = KnockoutCommandExecutor().execute(
                ("snapshot-tool",),
                snapshot.root,
                "snapshot-launcher",
                snapshot.environment_overrides,
                snapshot.environment_removals,
            )

            assert (snapshot.root / ".venv/command-write").read_text() == "local"
            assert (snapshot.root / "node_modules/command-write").read_text() == "local"

    assert result.exit_code == 0, result.stderr
    assert launcher_result.exit_code == 0, launcher_result.stderr
    assert not (root / ".venv/command-write").exists()
    assert not (root / "node_modules/command-write").exists()
    assert _directory_stat_identity(root / ".venv") == venv_before
    assert _directory_stat_identity(root / "node_modules") == node_before


def test_escaping_source_symlink_fails_closed_without_external_write(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend

    root = _project(tmp_path / "project")
    external = tmp_path / "external.py"
    external.write_text("external\n")
    (root / "src/target.py").unlink()
    (root / "src/target.py").symlink_to(external)

    with pytest.raises(RuntimeError, match="symlink|project"):
        with MaterializedProjectSnapshotBackend().create(
            root, ("src/target.py",), "escaping-symlink"
        ):
            pass

    assert external.read_text() == "external\n"

    gitlink_root = _project(tmp_path / "gitlink", git=True)
    head = _git(gitlink_root, "rev-parse", "HEAD")
    _git(
        gitlink_root,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{head},vendor/submodule",
    )
    with pytest.raises(RuntimeError, match="gitlink|submodule"):
        with MaterializedProjectSnapshotBackend().create(
            gitlink_root, ("src/target.py",), "gitlink"
        ):
            pass


def test_unverified_copy_on_write_or_cleanup_failure_is_e712(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        KnockoutProjectSnapshot,
        ProjectSnapshotBackend,
    )
    from maid_runner.core.knockout import run_knockout
    from maid_runner.core.manifest import load_manifest

    root = _project(tmp_path)
    manifest_path = _manifest(root, "target", "target", "python check.py")
    (root / "check.py").write_text("raise SystemExit(0)\n")

    class FailingBackend(ProjectSnapshotBackend):
        def create(self, project_root, required_paths, worker_id):
            raise RuntimeError("snapshot isolation probe failed")

    create_report = run_knockout(
        load_manifest(manifest_path),
        root,
        allow_dirty=True,
        snapshot_backend=FailingBackend(),
    )

    class CleanupFailingBackend(ProjectSnapshotBackend):
        @contextmanager
        def create(self, project_root, required_paths, worker_id):
            yield KnockoutProjectSnapshot(
                root=Path(project_root),
                input_digest="fixture",
                source_digests={
                    "src/target.py": hashlib.sha256(
                        (Path(project_root) / "src/target.py").read_bytes()
                    ).hexdigest()
                },
                git_dir=None,
                git_common_dir=None,
                source_repository_identity=None,
                environment_overrides={},
                environment_removals=(),
            )
            raise RuntimeError("snapshot cleanup failed")

    cleanup_report = run_knockout(
        load_manifest(manifest_path),
        root,
        allow_dirty=True,
        snapshot_backend=CleanupFailingBackend(),
    )

    assert create_report.success is False
    assert create_report.errors[0].code.value == "E712"
    assert "snapshot isolation probe failed" in create_report.errors[0].message
    assert cleanup_report.success is False
    assert cleanup_report.errors[0].code.value == "E712"
    assert "snapshot cleanup failed" in cleanup_report.errors[0].message


def test_allow_dirty_flag_remains_accepted_but_is_not_required(tmp_path: Path) -> None:
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()
    default = parser.parse_args(["verify", "--knockout"])
    compatibility = parser.parse_args(
        ["verify", "--knockout", "--knockout-allow-dirty"]
    )

    assert default.knockout_allow_dirty is False
    assert compatibility.knockout_allow_dirty is True


def _project(base: Path, *, git: bool = False) -> Path:
    root = base / "project" if base.name != "project" else base
    (root / "src").mkdir(parents=True)
    (root / "src/__init__.py").write_text("")
    (root / "src/target.py").write_text("def target():\n    return 'original'\n")
    (root / "pyproject.toml").write_text(
        "[project]\nname='snapshot-fixture'\nversion='0.0.0'\n"
    )
    if git:
        _git(root, "init")
        _git(root, "config", "user.email", "snapshot@example.test")
        _git(root, "config", "user.name", "Snapshot Test")
        _git(root, "add", ".")
        _git(root, "commit", "-m", "fixture")
    return root


def _manifest(
    root: Path,
    slug: str,
    artifact: str,
    command: str,
) -> Path:
    manifests = root / "manifests"
    manifests.mkdir(exist_ok=True)
    path = manifests / f"{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Snapshot fixture {slug}"
type: refactor
created: "2026-08-12T00:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
        - kind: function
          name: {artifact}
  read:
    - {Path(command.split()[-1]).as_posix()}
validate:
  - {command}
"""
    )
    return path


def _git(root: Path, *args: str) -> str:
    env = dict(os.environ)
    for name in tuple(env):
        if name.startswith("GIT_"):
            env.pop(name)
    result = subprocess.run(
        ("git", *args),
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _directory_stat_identity(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        metadata = path.stat()
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(
            f":{metadata.st_size}:{metadata.st_mtime_ns}:{metadata.st_ctime_ns}".encode()
        )
        digest.update(b"\0")
    return digest.hexdigest()
