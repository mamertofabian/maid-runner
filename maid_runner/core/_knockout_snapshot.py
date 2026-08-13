"""Isolated current-byte project snapshots for destructive verification."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path


_EXCLUDED_TREE_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
)
_GIT_CONTROL_FILES = ("HEAD", "index", "ORIG_HEAD", "config.worktree")
_LOCATION_ENVIRONMENT_NAMES = frozenset(
    {
        "NODE_PATH",
        "PWD",
        "PYTHONPATH",
        "PYTHONPYCACHEPREFIX",
        "UV_PROJECT_ENVIRONMENT",
        "VIRTUAL_ENV",
    }
)


@dataclass(frozen=True)
class KnockoutProjectSnapshot:
    """One materialized project root with independent writable state."""

    root: Path
    input_digest: str
    source_digests: Mapping[str, str]
    git_dir: Path | None
    git_common_dir: Path | None
    source_repository_identity: str | None
    environment_overrides: Mapping[str, str]
    environment_removals: tuple[str, ...]


class ProjectSnapshotBackend(ABC):
    """Owned context-managed boundary for project snapshot implementations."""

    @abstractmethod
    def create(
        self,
        project_root: Path,
        required_paths: Sequence[str],
        worker_id: str,
    ) -> AbstractContextManager[KnockoutProjectSnapshot]:
        raise NotImplementedError


class MaterializedProjectSnapshotBackend(ProjectSnapshotBackend):
    """Create isolated copies of current inputs and local Git metadata."""

    @contextmanager
    def create(
        self,
        project_root: Path,
        required_paths: Sequence[str],
        worker_id: str,
    ) -> AbstractContextManager[KnockoutProjectSnapshot]:
        source_root = Path(project_root).resolve()
        normalized_required = tuple(
            _validated_relative_path(source_root, path) for path in required_paths
        )
        source_repository_identity = _repository_identity(source_root)
        temp_root = Path(
            tempfile.mkdtemp(prefix=f"maid-knockout-{_safe_worker_id(worker_id)}-")
        )
        snapshot: KnockoutProjectSnapshot | None = None
        body_error: BaseException | None = None
        input_paths: tuple[str, ...] = ()
        before_state: str | None = None
        dependency_sources: Mapping[str, Path] = {}
        dependency_identity: Mapping[str, str] = {}
        try:
            input_paths = _project_input_paths(source_root, normalized_required)
            before_state = _input_stat_identity(source_root, input_paths)
            dependency_sources = _dependency_sources(source_root)
            dependency_identity = _source_dependency_identity(dependency_sources)
            copy_file = _copy_strategy(source_root, temp_root, normalized_required)
            _copy_project_inputs(source_root, temp_root, input_paths, copy_file)
            _copy_dependency_environments(
                source_root,
                temp_root,
                dependency_sources,
            )
            git_dir, git_common_dir = _copy_git_metadata(
                source_root,
                temp_root,
                copy_file,
            )
            after_state = _input_stat_identity(source_root, input_paths)
            if after_state != before_state:
                raise RuntimeError(
                    "Project inputs changed while the knockout snapshot was created"
                )
            _verify_dependency_identity(dependency_sources, dependency_identity)
            source_digests = _required_source_digests(
                source_root,
                temp_root,
                normalized_required,
            )
            snapshot = KnockoutProjectSnapshot(
                root=temp_root,
                input_digest=_snapshot_input_digest(
                    temp_root,
                    input_paths,
                    dependency_identity,
                ),
                source_digests=source_digests,
                git_dir=git_dir,
                git_common_dir=git_common_dir,
                source_repository_identity=source_repository_identity,
                environment_overrides=_snapshot_environment(source_root, temp_root),
                environment_removals=tuple(
                    sorted(
                        _LOCATION_ENVIRONMENT_NAMES
                        | {name for name in os.environ if name.startswith("GIT_")}
                    )
                ),
            )
            try:
                yield snapshot
            except BaseException as exc:
                body_error = exc
                raise
        finally:
            cleanup_error = _cleanup_snapshot(temp_root)
            input_error = _input_identity_error(
                source_root,
                input_paths,
                before_state,
            )
            identity_error = _verify_repository_identity(
                source_root,
                source_repository_identity,
            )
            dependency_error = _dependency_identity_error(
                dependency_sources,
                dependency_identity,
            )
            final_error = (
                input_error or identity_error or dependency_error or cleanup_error
            )
            if final_error is not None:
                raise RuntimeError(final_error) from body_error


def _safe_worker_id(worker_id: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", worker_id).strip("-.")
    return value[:48] or "worker"


def _validated_relative_path(root: Path, raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        candidate = path
    else:
        candidate = root / path
    try:
        relative = candidate.resolve(strict=False).relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(
            f"Snapshot required path escapes the project root: {raw_path}"
        ) from exc
    return relative.as_posix()


def _project_input_paths(root: Path, required_paths: Sequence[str]) -> tuple[str, ...]:
    git_paths = _git_project_paths(root)
    paths = set(git_paths if git_paths is not None else _bounded_tree_paths(root))
    paths.update(required_paths)
    normalized: list[str] = []
    for relative in sorted(paths):
        source = root / relative
        if source.is_symlink():
            _validate_materializable_symlink(root, source, relative)
        if source.is_file() or source.is_symlink():
            normalized.append(relative)
        elif relative in required_paths:
            raise RuntimeError(f"Snapshot required path is not a file: {relative}")
    return tuple(normalized)


def _git_project_paths(root: Path) -> tuple[str, ...] | None:
    _reject_gitlinks(root)
    result = _run_git(
        root,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        check=False,
    )
    if result is None or result.returncode != 0:
        return None
    return tuple(
        part.decode("utf-8", errors="surrogateescape")
        for part in result.stdout.split(b"\0")
        if part
    )


def _reject_gitlinks(root: Path) -> None:
    result = _run_git(root, "ls-files", "--stage", "-z", check=False)
    if result is None or result.returncode != 0:
        return
    for record in result.stdout.split(b"\0"):
        if record.startswith(b"160000 "):
            path = record.partition(b"\t")[2].decode("utf-8", errors="surrogateescape")
            raise RuntimeError(
                "Snapshot cannot safely materialize Git gitlink/submodule: " + path
            )


def _bounded_tree_paths(root: Path) -> tuple[str, ...]:
    paths: list[str] = []
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(directory)
        retained_directories: list[str] = []
        for name in directory_names:
            candidate = current / name
            if name in _EXCLUDED_TREE_NAMES:
                continue
            if candidate.is_symlink():
                _validate_materializable_symlink(
                    root,
                    candidate,
                    candidate.relative_to(root).as_posix(),
                )
                raise RuntimeError(
                    "Snapshot cannot safely materialize a directory symlink: "
                    f"{candidate.relative_to(root).as_posix()}"
                )
            retained_directories.append(name)
        directory_names[:] = retained_directories
        for name in file_names:
            candidate = current / name
            relative = candidate.relative_to(root).as_posix()
            if candidate.is_symlink():
                _validate_materializable_symlink(root, candidate, relative)
            paths.append(relative)
    return tuple(paths)


def _validate_materializable_symlink(root: Path, path: Path, relative: str) -> None:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(
            f"Snapshot symlink escapes or cannot be resolved inside project: {relative}"
        ) from exc
    if resolved.is_dir():
        raise RuntimeError(
            f"Snapshot cannot safely materialize directory symlink: {relative}"
        )


def _input_stat_identity(root: Path, paths: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        path = root / relative
        try:
            metadata = path.stat()
        except OSError as exc:
            raise RuntimeError(
                f"Snapshot could not stat project input {relative}: {exc}"
            )
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(
            f"{metadata.st_size}:{metadata.st_mtime_ns}:{metadata.st_ctime_ns}".encode()
        )
        digest.update(b"\0")
    return digest.hexdigest()


def _input_identity_error(
    root: Path,
    paths: Sequence[str],
    expected: str | None,
) -> str | None:
    if expected is None:
        return None
    try:
        actual = _input_stat_identity(root, paths)
    except Exception as exc:
        return f"Knockout could not verify source project inputs: {exc}"
    if actual != expected:
        return "Knockout snapshot command changed source project inputs"
    return None


def _copy_strategy(root: Path, destination: Path, required: Sequence[str]):
    probe_source = next(
        (
            root / relative
            for relative in required
            if (root / relative).is_file() and not (root / relative).is_symlink()
        ),
        None,
    )
    if probe_source is None or not _reflink_probe(probe_source, destination):
        return shutil.copy2

    def copy_reflink(source: str | os.PathLike[str], target: str | os.PathLike[str]):
        result = subprocess.run(
            (
                "cp",
                "--reflink=always",
                "--preserve=mode,timestamps",
                "--",
                os.fspath(source),
                os.fspath(target),
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return shutil.copy2(source, target)
        if os.stat(source).st_ino == os.stat(target).st_ino:
            Path(target).unlink(missing_ok=True)
            return shutil.copy2(source, target)
        return os.fspath(target)

    return copy_reflink


def _reflink_probe(source: Path, destination: Path) -> bool:
    probe = destination / ".maid-reflink-probe"
    before = _file_digest(source)
    try:
        result = subprocess.run(
            (
                "cp",
                "--reflink=always",
                "--preserve=mode,timestamps",
                "--",
                str(source),
                str(probe),
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or source.stat().st_ino == probe.stat().st_ino:
            return False
        with probe.open("ab") as handle:
            handle.write(b"\0")
        return _file_digest(source) == before
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        probe.unlink(missing_ok=True)


def _copy_project_inputs(
    root: Path,
    destination: Path,
    paths: Sequence[str],
    copy_file,
) -> None:
    for relative in paths:
        source = root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_file(source.resolve(strict=True), target)
        if source.is_symlink() or source.stat().st_ino == target.stat().st_ino:
            if source.stat().st_ino == target.stat().st_ino:
                raise RuntimeError(
                    f"Snapshot input shares a writable inode with source: {relative}"
                )


def _copy_dependency_environments(
    root: Path,
    destination: Path,
    sources: Mapping[str, Path],
) -> None:
    for name, source in sources.items():
        target = destination / name
        result = subprocess.run(
            (
                "cp",
                "--archive",
                "--reflink=auto",
                "--",
                str(source),
                str(target),
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target, symlinks=True, copy_function=shutil.copy2)
        _verify_dependency_copy_isolated(root, source, target)
        if name == ".venv":
            _rewrite_dependency_paths(
                target,
                {
                    os.fspath(source): os.fspath(target),
                    os.fspath(root): os.fspath(destination),
                },
            )


def _verify_dependency_copy_isolated(root: Path, source: Path, target: Path) -> None:
    source_text = os.fspath(source)
    target_text = os.fspath(target)
    for directory, directory_names, file_names in os.walk(
        target_text, followlinks=False
    ):
        for name in (*directory_names, *file_names):
            copied_text = os.path.join(directory, name)
            relative_text = os.path.relpath(copied_text, target_text)
            original_text = os.path.join(source_text, relative_text)
            copied_metadata = os.lstat(copied_text)
            if stat.S_ISLNK(copied_metadata.st_mode):
                copied = Path(copied_text)
                relative = Path(relative_text)
                try:
                    resolved = copied.resolve(strict=True)
                except (OSError, RuntimeError) as exc:
                    raise RuntimeError(
                        f"Snapshot dependency contains unresolved symlink: {copied}"
                    ) from exc
                if _is_relative_to(resolved, root):
                    raise RuntimeError(
                        "Snapshot dependency symlink points into source project: "
                        f"{copied.relative_to(target)}"
                    )
                if not _is_relative_to(resolved, target) and not (
                    source.name == ".venv"
                    and relative.parts
                    and relative.parts[0] in {"bin", "Scripts"}
                    and relative.name.startswith("python")
                ):
                    raise RuntimeError(
                        "Snapshot dependency symlink reaches shared external state: "
                        f"{copied.relative_to(target)}"
                    )
            elif stat.S_ISREG(copied_metadata.st_mode) and os.path.isfile(
                original_text
            ):
                if copied_metadata.st_ino == os.stat(original_text).st_ino:
                    raise RuntimeError(
                        "Snapshot dependency shares a writable inode with source: "
                        f"{source.name}/{relative_text.replace(os.sep, '/')}"
                    )


def _rewrite_dependency_paths(venv: Path, replacements: Mapping[str, str]) -> None:
    metadata_suffixes = frozenset({".cfg", ".egg-link", ".json", ".pth", ".py"})
    encoded_replacements = tuple(
        (source.encode(), target.encode())
        for source, target in replacements.items()
        if source != target
    )
    for directory, _directory_names, file_names in os.walk(venv):
        current = Path(directory)
        is_launcher_directory = current.parent == venv and current.name in {
            "bin",
            "Scripts",
        }
        for name in file_names:
            path = current / name
            if path.is_symlink() or not path.is_file():
                continue
            if not is_launcher_directory and path.suffix not in metadata_suffixes:
                continue
            try:
                content = path.read_bytes()
            except OSError as exc:
                raise RuntimeError(
                    f"Snapshot could not inspect dependency path metadata: {path}"
                ) from exc
            rewritten = content
            for source, target in encoded_replacements:
                rewritten = rewritten.replace(source, target)
            if rewritten != content:
                path.write_bytes(rewritten)


def _dependency_sources(root: Path) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    project_venv = root / ".venv"
    if project_venv.is_dir():
        sources[".venv"] = project_venv
    else:
        for variable in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
            value = os.environ.get(variable)
            if value and (candidate := Path(value).resolve()).is_dir():
                sources[".venv"] = candidate
                break
    node_modules = root / "node_modules"
    if node_modules.is_dir():
        sources["node_modules"] = node_modules
    return sources


def _source_dependency_identity(sources: Mapping[str, Path]) -> dict[str, str]:
    return {name: _directory_stat_identity(path) for name, path in sources.items()}


def _directory_stat_identity(root: Path) -> str:
    digest = hashlib.sha256()
    root_text = os.fspath(root)
    root_metadata = os.lstat(root_text)
    digest.update(
        f".:{root_metadata.st_mode}:{root_metadata.st_size}:"
        f"{root_metadata.st_mtime_ns}:{root_metadata.st_ctime_ns}\0".encode()
    )
    for directory, directory_names, file_names in os.walk(root_text, followlinks=False):
        for name in sorted((*directory_names, *file_names)):
            path = os.path.join(directory, name)
            metadata = os.lstat(path)
            relative = os.path.relpath(path, root_text).replace(os.sep, "/")
            digest.update(relative.encode())
            digest.update(
                f":{metadata.st_mode}:{metadata.st_size}:{metadata.st_mtime_ns}:"
                f"{metadata.st_ctime_ns}".encode()
            )
            if stat.S_ISLNK(metadata.st_mode):
                digest.update(os.readlink(path).encode(errors="surrogateescape"))
            digest.update(b"\0")
    return digest.hexdigest()


def _verify_dependency_identity(
    sources: Mapping[str, Path], expected: Mapping[str, str]
) -> None:
    error = _dependency_identity_error(sources, expected)
    if error is not None:
        raise RuntimeError(error)


def _dependency_identity_error(
    sources: Mapping[str, Path],
    expected: Mapping[str, str],
) -> str | None:
    try:
        actual = _source_dependency_identity(sources)
    except Exception as exc:
        return f"Knockout could not verify source dependency identity: {exc}"
    if actual != dict(expected):
        return "Knockout snapshot command changed a source dependency environment"
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _copy_git_metadata(root: Path, destination: Path, copy_file):
    git_dir_output = _git_stdout(root, "rev-parse", "--absolute-git-dir")
    common_output = _git_stdout(root, "rev-parse", "--git-common-dir")
    if git_dir_output is None or common_output is None:
        return None, None
    source_git_dir = Path(git_dir_output.decode().strip()).resolve()
    source_common = Path(common_output.decode().strip())
    if not source_common.is_absolute():
        source_common = (root / source_common).resolve()
    else:
        source_common = source_common.resolve()
    target_git = destination / ".git"
    _reject_git_symlinks(source_common)
    shutil.copytree(
        source_common,
        target_git,
        symlinks=False,
        copy_function=copy_file,
    )
    if source_git_dir != source_common:
        for name in _GIT_CONTROL_FILES:
            source = source_git_dir / name
            if not source.is_file():
                continue
            target = target_git / name
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_file(source, target)
        source_head_log = source_git_dir / "logs/HEAD"
        if source_head_log.is_file():
            (target_git / "logs").mkdir(exist_ok=True)
            copy_file(source_head_log, target_git / "logs/HEAD")
    shutil.rmtree(target_git / "worktrees", ignore_errors=True)
    (target_git / "objects/info/alternates").unlink(missing_ok=True)
    _disable_unsafe_git_hooks(target_git)
    _sanitize_snapshot_git_config(target_git)
    return target_git, target_git


def _reject_git_symlinks(git_dir: Path) -> None:
    for directory, directory_names, file_names in os.walk(git_dir, followlinks=False):
        current = Path(directory)
        for name in (*directory_names, *file_names):
            path = current / name
            if path.is_symlink():
                raise RuntimeError(
                    "Snapshot cannot prove isolation for Git metadata symlink: "
                    f"{path.relative_to(git_dir).as_posix()}"
                )


def _disable_unsafe_git_hooks(git_dir: Path) -> None:
    hooks = git_dir / "hooks"
    if hooks.is_dir():
        for hook in hooks.iterdir():
            if hook.name.endswith(".sample") or not hook.is_file():
                continue
            if hook.stat().st_mode & stat.S_IXUSR:
                raise RuntimeError(
                    f"Snapshot cannot safely isolate executable Git hook: {hook.name}"
                )


def _sanitize_snapshot_git_config(git_dir: Path) -> None:
    for config in (git_dir / "config", git_dir / "config.worktree"):
        if not config.is_file():
            continue
        names = subprocess.run(
            ("git", "config", "--file", str(config), "--name-only", "--list"),
            capture_output=True,
            text=True,
            check=False,
        )
        if names.returncode != 0:
            raise RuntimeError(
                f"Snapshot could not inspect Git config {config.name}: "
                f"{names.stderr.strip()}"
            )
        unsafe_includes = [
            name
            for name in names.stdout.splitlines()
            if name.lower() == "include.path"
            or (
                name.lower().startswith("includeif.") and name.lower().endswith(".path")
            )
        ]
        if unsafe_includes:
            raise RuntimeError(
                "Snapshot cannot safely isolate Git config include: "
                + ", ".join(unsafe_includes)
            )
        unsafe_commands = [
            name
            for name in names.stdout.splitlines()
            if name.lower().startswith("alias.")
            or (
                name.lower().startswith("filter.")
                and name.lower().rsplit(".", 1)[-1] in {"clean", "process", "smudge"}
            )
            or (name.lower().startswith("merge.") and name.lower().endswith(".driver"))
        ]
        if unsafe_commands:
            raise RuntimeError(
                "Snapshot cannot safely isolate process-bearing Git config: "
                + ", ".join(unsafe_commands)
            )
        for key in (
            "core.editor",
            "core.fsmonitor",
            "core.hookspath",
            "core.sshcommand",
            "core.worktree",
            "diff.external",
            "gpg.program",
            "sequence.editor",
        ):
            result = subprocess.run(
                ("git", "config", "--file", str(config), "--unset-all", key),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode not in (0, 5):
                raise RuntimeError(
                    f"Snapshot could not remove source {key} binding: "
                    f"{result.stderr.strip()}"
                )
    result = subprocess.run(
        (
            "git",
            "config",
            "--file",
            str(git_dir / "config"),
            "core.hooksPath",
            str(git_dir / "hooks"),
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Snapshot could not bind Git hooks to isolated metadata: "
            f"{result.stderr.strip()}"
        )


def _required_source_digests(
    root: Path,
    destination: Path,
    required: Sequence[str],
) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative in required:
        source = root / relative
        copied = destination / relative
        source_digest = _file_digest(source)
        if not copied.is_file() or _file_digest(copied) != source_digest:
            raise RuntimeError(
                f"Snapshot required path does not match current source bytes: {relative}"
            )
        digests[relative] = source_digest
    return digests


def _tree_digest(root: Path, paths: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative in paths:
        path = root / relative
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _snapshot_input_digest(
    root: Path,
    paths: Sequence[str],
    dependency_identity: Mapping[str, str],
) -> str:
    digest = hashlib.sha256(_tree_digest(root, paths).encode())
    for name, identity in sorted(dependency_identity.items()):
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(identity.encode())
        digest.update(b"\0")
    return digest.hexdigest()


def _snapshot_environment(source_root: Path, snapshot_root: Path) -> dict[str, str]:
    git_author_config = _snapshot_git_author_config(source_root, snapshot_root)
    overrides = {
        "GIT_CONFIG_GLOBAL": str(git_author_config),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "PWD": str(snapshot_root),
        "PYTHONPATH": _prepend_path(
            snapshot_root,
            _paths_outside_root(os.environ.get("PYTHONPATH"), source_root),
        ),
        "PYTHONPYCACHEPREFIX": str(snapshot_root / ".maid-pycache"),
    }
    executable_paths: list[Path] = []
    virtual_environment = snapshot_root / ".venv"
    if virtual_environment.is_dir():
        overrides["VIRTUAL_ENV"] = str(virtual_environment)
        overrides["UV_PROJECT_ENVIRONMENT"] = str(virtual_environment)
        overrides["UV_NO_SYNC"] = "1"
        executable_paths.append(
            virtual_environment / ("Scripts" if os.name == "nt" else "bin")
        )
    node_modules = snapshot_root / "node_modules"
    if node_modules.is_dir():
        overrides["NODE_PATH"] = _prepend_path(
            node_modules,
            None,
        )
        executable_paths.append(node_modules / ".bin")
    if executable_paths:
        current_path = _paths_outside_root(os.environ.get("PATH"), source_root) or ""
        overrides["PATH"] = os.pathsep.join(
            [*(str(path) for path in executable_paths), current_path]
        )
    return overrides


def _snapshot_git_author_config(source_root: Path, snapshot_root: Path) -> Path:
    config_root = snapshot_root / ".git"
    if not config_root.is_dir():
        return Path(os.devnull)
    config_path = config_root / "maid-global-config"
    name = _resolved_git_config_value(source_root, "user.name")
    email = _resolved_git_config_value(source_root, "user.email")
    config_path.write_text("", encoding="utf-8")
    if name is None or email is None:
        return config_path
    for key, value in (("user.name", name), ("user.email", email)):
        result = subprocess.run(
            ("git", "config", "--file", str(config_path), key, value),
            cwd=snapshot_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Snapshot could not materialize Git author {key}: "
                f"{result.stderr.strip()}"
            )
    return config_path


def _resolved_git_config_value(root: Path, key: str) -> str | None:
    result = subprocess.run(
        ("git", "config", "--get", key),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 1:
        return None
    if result.returncode != 0:
        raise RuntimeError(
            f"Snapshot could not resolve Git author {key}: {result.stderr.strip()}"
        )
    value = result.stdout.rstrip("\r\n")
    return value or None


def _prepend_path(path: Path, current: str | None) -> str:
    return str(path) if not current else f"{path}{os.pathsep}{current}"


def _paths_outside_root(value: str | None, root: Path) -> str | None:
    if not value:
        return None
    retained: list[str] = []
    for item in value.split(os.pathsep):
        if not item:
            continue
        try:
            resolved = Path(item).resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if not _is_relative_to(resolved, root):
            retained.append(item)
    return os.pathsep.join(retained) or None


def _repository_identity(root: Path) -> str | None:
    git_dir_output = _git_stdout(root, "rev-parse", "--absolute-git-dir")
    common_output = _git_stdout(root, "rev-parse", "--git-common-dir")
    if git_dir_output is None or common_output is None:
        return None
    git_dir = Path(git_dir_output.decode().strip()).resolve()
    common = Path(common_output.decode().strip())
    if not common.is_absolute():
        common = (root / common).resolve()
    digest = hashlib.sha256()
    for args in (
        ("rev-parse", "HEAD"),
        ("for-each-ref", "--format=%(refname)%00%(objectname)"),
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
        ("config", "--local", "--null", "--list"),
        ("worktree", "list", "--porcelain"),
    ):
        output = _git_stdout(root, *args)
        if output is None:
            raise RuntimeError(
                "Snapshot could not capture source repository identity: "
                + " ".join(args)
            )
        digest.update(output)
        digest.update(b"\0")
    for control in (
        git_dir / "index",
        git_dir / "HEAD",
        git_dir / "config.worktree",
        common / "config",
    ):
        digest.update(str(control).encode())
        digest.update(b"\0")
        if control.is_file():
            digest.update(control.read_bytes())
        digest.update(b"\0")
    objects = common / "objects"
    if objects.is_dir():
        for path in sorted(item for item in objects.rglob("*") if item.is_file()):
            metadata = path.stat()
            digest.update(path.relative_to(objects).as_posix().encode())
            digest.update(
                f":{metadata.st_size}:{metadata.st_mtime_ns}:{metadata.st_ctime_ns}".encode()
            )
            digest.update(b"\0")
    return digest.hexdigest()


def _verify_repository_identity(root: Path, expected: str | None) -> str | None:
    try:
        actual = _repository_identity(root)
    except Exception as exc:
        return f"Knockout could not verify source repository identity: {exc}"
    if actual != expected:
        return "Knockout snapshot command changed source repository metadata"
    return None


def _cleanup_snapshot(root: Path) -> str | None:
    try:
        shutil.rmtree(root)
    except Exception as exc:
        return f"Knockout could not clean snapshot {root}: {exc}"
    if root.exists():
        return f"Knockout snapshot cleanup left materialized state at {root}"
    return None


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_stdout(root: Path, *args: str) -> bytes | None:
    result = _run_git(root, *args, check=False)
    if result is None or result.returncode != 0:
        return None
    return result.stdout


def _run_git(
    root: Path,
    *args: str,
    check: bool,
) -> subprocess.CompletedProcess[bytes] | None:
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        return subprocess.run(
            (
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                f"core.hooksPath={os.devnull}",
                *args,
            ),
            cwd=root,
            env=environment,
            capture_output=True,
            check=check,
        )
    except (OSError, subprocess.SubprocessError):
        return None
