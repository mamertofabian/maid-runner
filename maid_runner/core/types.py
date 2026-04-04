"""Core data types for MAID Runner v2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ArtifactKind(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    ATTRIBUTE = "attribute"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    NAMESPACE = "namespace"


class TaskType(str, Enum):
    FEATURE = "feature"
    FIX = "fix"
    REFACTOR = "refactor"
    SNAPSHOT = "snapshot"
    SYSTEM_SNAPSHOT = "system-snapshot"


class ValidationMode(str, Enum):
    BEHAVIORAL = "behavioral"
    IMPLEMENTATION = "implementation"


class FileMode(str, Enum):
    CREATE = "create"
    EDIT = "edit"
    READ = "read"
    DELETE = "delete"
    SNAPSHOT = "snapshot"


class TestStream(str, Enum):
    ACCEPTANCE = "acceptance"
    IMPLEMENTATION = "implementation"


@dataclass(frozen=True)
class AcceptanceConfig:
    tests: tuple[tuple[str, ...], ...] = ()
    immutable: bool = True


@dataclass(frozen=True)
class ArgSpec:
    name: str
    type: Optional[str] = None
    default: Optional[str] = None


@dataclass(frozen=True)
class ArtifactSpec:
    kind: ArtifactKind
    name: str
    description: Optional[str] = None
    args: tuple[ArgSpec, ...] = ()
    returns: Optional[str] = None
    raises: tuple[str, ...] = ()
    is_async: bool = False
    bases: tuple[str, ...] = ()
    of: Optional[str] = None
    type_annotation: Optional[str] = None

    @property
    def qualified_name(self) -> str:
        if self.of:
            return f"{self.of}.{self.name}"
        return self.name

    @property
    def is_private(self) -> bool:
        if self.name.startswith("_"):
            return True
        if self.of and self.of.startswith("_"):
            return True
        return False

    def merge_key(self) -> str:
        if self.kind == ArtifactKind.METHOD and self.of:
            return f"{self.of}.{self.name}"
        if self.kind == ArtifactKind.ATTRIBUTE and self.of:
            return f"{self.of}.{self.name}"
        return self.name


@dataclass(frozen=True)
class FileSpec:
    path: str
    artifacts: tuple[ArtifactSpec, ...]
    status: str = "present"
    mode: FileMode = FileMode.CREATE
    imports: tuple[str, ...] = ()

    @property
    def is_strict(self) -> bool:
        return self.mode in (FileMode.CREATE, FileMode.SNAPSHOT)

    @property
    def is_absent(self) -> bool:
        return self.status == "absent" or self.mode == FileMode.DELETE


@dataclass(frozen=True)
class DeleteSpec:
    path: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class Manifest:
    slug: str
    source_path: str
    goal: str
    validate_commands: tuple[tuple[str, ...], ...]
    files_create: tuple[FileSpec, ...] = ()
    files_edit: tuple[FileSpec, ...] = ()
    files_read: tuple[str, ...] = ()
    files_delete: tuple[DeleteSpec, ...] = ()
    files_snapshot: tuple[FileSpec, ...] = ()
    schema_version: str = "2"
    task_type: Optional[TaskType] = None
    description: Optional[str] = None
    supersedes: tuple[str, ...] = ()
    created: Optional[str] = None
    metadata: Optional[dict] = None
    acceptance: Optional[AcceptanceConfig] = None

    @property
    def all_file_specs(self) -> list[FileSpec]:
        return (
            list(self.files_create) + list(self.files_edit) + list(self.files_snapshot)
        )

    @property
    def all_writable_paths(self) -> set[str]:
        paths = {fs.path for fs in self.files_create}
        paths |= {fs.path for fs in self.files_edit}
        paths |= {ds.path for ds in self.files_delete}
        paths |= {fs.path for fs in self.files_snapshot}
        return paths

    @property
    def all_referenced_paths(self) -> set[str]:
        return self.all_writable_paths | set(self.files_read)

    @property
    def is_superseded_by(self) -> bool:
        raise NotImplementedError("Use ManifestChain.is_superseded()")

    def file_spec_for(self, path: str) -> Optional[FileSpec]:
        for fs in self.all_file_specs:
            if fs.path == path:
                return fs
        return None

    def artifacts_for(self, path: str) -> tuple[ArtifactSpec, ...]:
        fs = self.file_spec_for(path)
        return fs.artifacts if fs else ()
