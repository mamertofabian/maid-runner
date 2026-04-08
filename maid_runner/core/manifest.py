"""Manifest loading, saving, and schema validation for MAID Runner v2."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
from typing import Union

import jsonschema
import yaml

from maid_runner.core.types import (
    AcceptanceConfig,
    ArgSpec,
    ArtifactKind,
    ArtifactSpec,
    DeleteSpec,
    FileMode,
    FileSpec,
    Manifest,
    TaskType,
)

_SCHEMA_DIR = Path(__file__).parent.parent / "schemas"


class ManifestLoadError(Exception):
    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to load manifest {path}: {reason}")


class ManifestSchemaError(Exception):
    def __init__(self, path: str, errors: list[str]):
        self.path = path
        self.errors = errors
        super().__init__(f"Schema validation failed for {path}: {'; '.join(errors)}")


def slug_from_path(path: Union[str, Path]) -> str:
    name = Path(path).name
    for suffix in (".manifest.json", ".manifest.yaml", ".manifest.yml"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def validate_manifest_schema(data: dict, schema_version: str = "2") -> list[str]:
    schema_file = _SCHEMA_DIR / f"manifest.v{schema_version}.schema.json"
    if not schema_file.exists():
        return [f"Schema file not found: {schema_file}"]
    schema = json.loads(schema_file.read_text())
    validator = jsonschema.Draft7Validator(schema)
    return [e.message for e in validator.iter_errors(data)]


def load_manifest_raw(path: Union[str, Path]) -> dict:
    path = Path(path)
    if not path.exists():
        raise ManifestLoadError(str(path), "File not found")
    text = path.read_text()
    if path.suffix == ".json":
        return json.loads(text)
    elif path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    else:
        raise ManifestLoadError(str(path), f"Unknown extension: {path.suffix}")


def load_manifest(path: Union[str, Path]) -> Manifest:
    path = Path(path)
    try:
        data = load_manifest_raw(path)
    except ManifestLoadError:
        raise
    except Exception as exc:
        raise ManifestLoadError(str(path), str(exc)) from exc

    # Detect v1 and convert
    from maid_runner.compat.v1_loader import is_v1_manifest, convert_v1_to_v2

    if is_v1_manifest(data):
        data = convert_v1_to_v2(data)

    errors = validate_manifest_schema(data)
    if errors:
        raise ManifestSchemaError(str(path), errors)

    return _parse_manifest(data, path)


def save_manifest(manifest: Manifest, path: Union[str, Path]) -> None:
    path = Path(path)
    data = _manifest_to_dict(manifest)
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def _parse_manifest(data: dict, path: Path) -> Manifest:
    slug = slug_from_path(path)
    files = data.get("files", {})

    files_create = tuple(
        _parse_file_spec(f, FileMode.CREATE) for f in files.get("create", [])
    )
    files_edit = tuple(
        _parse_file_spec(f, FileMode.EDIT) for f in files.get("edit", [])
    )
    files_read = tuple(files.get("read", []))
    files_delete = tuple(
        DeleteSpec(path=d["path"], reason=d.get("reason"))
        for d in files.get("delete", [])
    )
    files_snapshot = tuple(
        _parse_file_spec(f, FileMode.SNAPSHOT) for f in files.get("snapshot", [])
    )

    validate_commands = _parse_validate(data.get("validate", []))

    task_type = TaskType(data["type"]) if "type" in data else None

    acceptance = None
    if "acceptance" in data:
        acc_data = data["acceptance"]
        acceptance = AcceptanceConfig(
            tests=_parse_validate(acc_data.get("tests", [])),
            immutable=acc_data.get("immutable", True),
        )

    return Manifest(
        slug=slug,
        source_path=str(path.resolve()),
        goal=data["goal"],
        validate_commands=validate_commands,
        files_create=files_create,
        files_edit=files_edit,
        files_read=files_read,
        files_delete=files_delete,
        files_snapshot=files_snapshot,
        schema_version=data.get("schema", "2"),
        task_type=task_type,
        description=data.get("description"),
        supersedes=tuple(data.get("supersedes", [])),
        created=data.get("created"),
        metadata=data.get("metadata"),
        acceptance=acceptance,
    )


def _parse_file_spec(data: dict, mode: FileMode) -> FileSpec:
    artifacts = tuple(_parse_artifact(a) for a in data.get("artifacts", []))
    return FileSpec(
        path=data["path"],
        artifacts=artifacts,
        status=data.get("status", "present"),
        mode=mode,
        imports=tuple(data.get("imports", [])),
    )


def _parse_artifact(data: dict) -> ArtifactSpec:
    args = tuple(
        ArgSpec(
            name=a["name"],
            type=a.get("type"),
            default=a.get("default"),
        )
        for a in data.get("args", [])
    )

    returns = data.get("returns")
    if isinstance(returns, dict):
        returns = returns.get("type")

    kind = ArtifactKind(data["kind"])

    return ArtifactSpec(
        kind=kind,
        name=data["name"],
        description=data.get("description"),
        args=args,
        returns=returns,
        raises=tuple(data.get("raises", [])),
        is_async=data.get("async", False),
        bases=tuple(data.get("bases", [])),
        of=data.get("of"),
        type_annotation=data.get("type"),
    )


def _parse_validate(data: list) -> tuple[tuple[str, ...], ...]:
    if not data:
        return ()
    commands = []
    for item in data:
        if isinstance(item, str):
            commands.append(tuple(shlex.split(item)))
        else:
            commands.append(tuple(item))
    return tuple(commands)


def _manifest_to_dict(manifest: Manifest) -> dict:
    data: dict = {
        "schema": manifest.schema_version,
        "goal": manifest.goal,
    }
    if manifest.task_type:
        data["type"] = manifest.task_type.value
    if manifest.description:
        data["description"] = manifest.description

    files: dict = {}
    if manifest.files_create:
        files["create"] = [_file_spec_to_dict(fs) for fs in manifest.files_create]
    if manifest.files_edit:
        files["edit"] = [_file_spec_to_dict(fs) for fs in manifest.files_edit]
    if manifest.files_read:
        files["read"] = list(manifest.files_read)
    if manifest.files_delete:
        files["delete"] = [
            {"path": ds.path, **({"reason": ds.reason} if ds.reason else {})}
            for ds in manifest.files_delete
        ]
    if manifest.files_snapshot:
        files["snapshot"] = [_file_spec_to_dict(fs) for fs in manifest.files_snapshot]
    if files:
        data["files"] = files

    # Preserve argv structure losslessly on write.
    data["validate"] = [list(cmd) for cmd in manifest.validate_commands]

    if manifest.acceptance is not None:
        acc: dict = {
            "tests": [list(cmd) for cmd in manifest.acceptance.tests],
        }
        if not manifest.acceptance.immutable:
            acc["immutable"] = False
        data["acceptance"] = acc

    if manifest.supersedes:
        data["supersedes"] = list(manifest.supersedes)
    if manifest.created:
        data["created"] = manifest.created
    if manifest.metadata:
        data["metadata"] = manifest.metadata

    return data


def _file_spec_to_dict(fs: FileSpec) -> dict:
    d: dict = {"path": fs.path}
    if fs.status != "present":
        d["status"] = fs.status
    d["artifacts"] = [_artifact_to_dict(a) for a in fs.artifacts]
    if fs.imports:
        d["imports"] = list(fs.imports)
    return d


def _artifact_to_dict(spec: ArtifactSpec) -> dict:
    d: dict = {"kind": spec.kind.value, "name": spec.name}
    if spec.description:
        d["description"] = spec.description
    if spec.of:
        d["of"] = spec.of
    if spec.args:
        d["args"] = [
            {
                "name": a.name,
                **({"type": a.type} if a.type else {}),
                **({"default": a.default} if a.default else {}),
            }
            for a in spec.args
        ]
    if spec.returns:
        d["returns"] = spec.returns
    if spec.raises:
        d["raises"] = list(spec.raises)
    if spec.is_async:
        d["async"] = True
    if spec.bases:
        d["bases"] = list(spec.bases)
    if spec.type_annotation:
        d["type"] = spec.type_annotation
    return d
