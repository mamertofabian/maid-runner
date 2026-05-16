"""Manifest loading, saving, and schema validation for MAID Runner v2."""

from __future__ import annotations

import json
from pathlib import Path
from pathlib import PureWindowsPath
import shlex
from typing import Union

import jsonschema
import yaml

from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.types import (
    AcceptanceConfig,
    ArgSpec,
    ArtifactKind,
    ArtifactSpec,
    DeleteSpec,
    FileMode,
    FileSpec,
    Manifest,
    RemovedArtifactSpec,
    TaskType,
    TemptationSpec,
    TestFunctionDetails,
    TestFunctionSetup,
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


def validate_manifest_paths(
    manifest: Manifest,
    project_root: Union[str, Path],
) -> list[ValidationError]:
    """Reject manifest-declared paths that resolve outside project_root."""
    root = Path(project_root)
    errors: list[ValidationError] = []

    for section, path in _iter_manifest_declared_paths(manifest, root):
        if _path_is_within_project(root, path):
            continue
        errors.append(
            ValidationError(
                code=ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT,
                message=(
                    f"Manifest path in {section} escapes the project root: " f"'{path}'"
                ),
                location=Location(file=path),
                suggestion=(
                    "Use a project-relative path inside the repository; "
                    "absolute and parent-relative paths are not allowed."
                ),
            )
        )

    return errors


def _iter_manifest_declared_paths(
    manifest: Manifest,
    project_root: Path,
) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []

    for fs in manifest.files_create:
        paths.append(("files.create", fs.path))
    for fs in manifest.files_edit:
        paths.append(("files.edit", fs.path))
    for fs in manifest.files_snapshot:
        paths.append(("files.snapshot", fs.path))
    for path in manifest.files_read:
        paths.append(("files.read", path))
    for ds in manifest.files_delete:
        paths.append(("files.delete", ds.path))
    for spec in manifest.removed_artifacts:
        paths.append(("removed_artifacts", spec.file))

    for cmd in manifest.validate_commands:
        for path in _test_paths_from_command(cmd, project_root):
            paths.append(("validate command", path))

    if manifest.acceptance is not None:
        for cmd in manifest.acceptance.tests:
            for path in _test_paths_from_command(cmd, project_root):
                paths.append(("acceptance.tests", path))

    return paths


def _path_is_within_project(project_root: Path, file_path: str) -> bool:
    candidate = Path(file_path)
    windows_candidate = PureWindowsPath(file_path)
    if candidate.is_absolute() or windows_candidate.is_absolute():
        return False
    if windows_candidate.drive:
        return False
    try:
        project_abs = project_root.resolve()
        full = (project_root / candidate).resolve()
        full.relative_to(project_abs)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _test_paths_from_command(
    command: tuple[str, ...],
    project_root: Path,
) -> list[str]:
    paths: list[str] = []
    cwd = Path(".")

    for segment in _command_segments(command):
        if not segment:
            continue
        if segment[0] == "cd":
            if len(segment) > 1:
                cwd = cwd / segment[1]
            continue

        allow_explicit_directories = _runs_known_test_runner(segment)
        index = 0
        while index < len(segment):
            part = segment[index]
            if part in {"-C", "--cwd", "--dir", "--prefix"} and index + 1 < len(
                segment
            ):
                cwd = cwd / segment[index + 1]
                index += 2
                continue
            if part.startswith("-"):
                option_path = _path_value_from_option_assignment(part)
                if option_path is not None:
                    candidate = _display_path(cwd / option_path)
                    if _looks_like_test_path(
                        candidate,
                        project_root,
                        allow_explicit_directories=allow_explicit_directories,
                    ):
                        paths.append(candidate)
                index += 1
                continue

            candidate = _display_path(cwd / part)
            if _looks_like_test_path(
                candidate,
                project_root,
                allow_explicit_directories=allow_explicit_directories,
            ):
                paths.append(candidate)
            index += 1

    return paths


def _command_segments(command: tuple[str, ...]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for part in command:
        if part in {"&&", "||", ";"}:
            segments.append([])
        else:
            segments[-1].append(part)
    return segments


def _runs_known_test_runner(segment: list[str]) -> bool:
    test_runners = {
        "pytest",
        "py.test",
        "vitest",
        "jest",
        "playwright",
    }
    return any(Path(part).name in test_runners for part in segment)


def _path_value_from_option_assignment(part: str) -> str | None:
    if "=" not in part:
        return None

    option, value = part.split("=", 1)
    if not value:
        return None

    path_options = {
        "-C",
        "-c",
        "--basetemp",
        "--config",
        "--confcutdir",
        "--cov",
        "--cov-config",
        "--cwd",
        "--dir",
        "--prefix",
        "--project",
        "--rootdir",
    }
    if option not in path_options:
        return None

    return value


def _looks_like_test_path(
    path: str,
    project_root: Path,
    *,
    allow_explicit_directories: bool,
) -> bool:
    if _is_test_file(path):
        return True

    path_obj = Path(path)
    test_dir_names = {"test", "tests", "__tests__", "spec", "specs"}
    if path_obj.name.lower() in test_dir_names:
        return True

    if not allow_explicit_directories:
        return False
    if any(part.lower() in test_dir_names for part in path_obj.parts):
        return True
    if "/" in path or "\\" in path:
        return True

    full_path = project_root / path
    return full_path.is_dir()


def _is_test_file(path: str) -> bool:
    name = Path(path).name
    lower = name.lower()
    if lower == "conftest.py":
        return True
    if lower.startswith("test_") and lower.endswith(".py"):
        return True
    if lower.endswith("_test.py"):
        return True
    return lower.endswith(
        (
            ".test.ts",
            ".test.tsx",
            ".test.js",
            ".test.jsx",
            ".spec.ts",
            ".spec.tsx",
            ".spec.js",
            ".spec.jsx",
        )
    )


def _display_path(path: Path) -> str:
    text = str(path)
    if text.startswith("./"):
        return text[2:]
    return text


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
        sequence_number=data.get("sequence_number"),
        version_tag=data.get("version_tag"),
        created=data.get("created"),
        metadata=data.get("metadata"),
        acceptance=acceptance,
        temptations=_parse_temptations(data.get("temptations", [])),
        removed_artifacts=_parse_removed_artifacts(data.get("removed_artifacts", [])),
    )


def _parse_removed_artifacts(data: list) -> tuple[RemovedArtifactSpec, ...]:
    return tuple(
        RemovedArtifactSpec(
            kind=ArtifactKind(item["kind"]),
            name=item["name"],
            file=item["file"],
            of=item.get("of"),
            reason=item.get("reason", ""),
        )
        for item in data
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

    test_details = None
    if kind == ArtifactKind.TEST_FUNCTION:
        # Test function details may be at artifact level or nested in test_function_details
        # The enriched manifests have source_scenario, tags, setup, actions, expected,
        # dependencies directly on the artifact object.
        # Also check test_function_details for backwards compat with the nested format.
        nest = data.get("test_function_details", {})
        # Merge: artifact-level fields take precedence over nested
        source = data.get("source_scenario", nest.get("source_scenario", ""))
        tags = data.get("tags", nest.get("tags", []))
        nested_setup = nest.get("setup", {})
        setup_data = data.get("setup", {})
        # Merge setup: artifact-level wins
        merged_setup = {**nested_setup, **setup_data}
        test_details = TestFunctionDetails(
            source_scenario=source,
            tags=tuple(tags),
            setup=TestFunctionSetup(
                auth_required=merged_setup.get("auth_required", False),
                test_data=merged_setup.get("test_data", {}),
                setup_actions=tuple(merged_setup.get("setup_actions", [])),
            ),
            actions=tuple(data.get("actions", nest.get("actions", []))),
            expected=data.get("expected", nest.get("expected", {})),
            dependencies=data.get("dependencies", nest.get("dependencies", {})),
        )

    return ArtifactSpec(
        kind=kind,
        name=data["name"],
        description=data.get("description"),
        args=args,
        returns=returns,
        raises=tuple(data.get("raises", [])),
        is_async=data.get("async", False),
        bases=tuple(data.get("bases", [])),
        type_parameters=tuple(data.get("type_parameters", [])),
        of=data.get("of"),
        type_annotation=data.get("type"),
        test_details=test_details,
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


def _parse_temptations(data: list) -> tuple[TemptationSpec, ...]:
    return tuple(
        TemptationSpec(risk=item["risk"], instead=item["instead"]) for item in data
    )


def _manifest_to_dict(manifest: Manifest) -> dict:
    data: dict = {
        "schema": manifest.schema_version,
        "goal": manifest.goal,
    }
    if manifest.task_type:
        data["type"] = manifest.task_type.value
    if manifest.description:
        data["description"] = manifest.description
    if manifest.temptations:
        data["temptations"] = [
            {"risk": t.risk, "instead": t.instead} for t in manifest.temptations
        ]

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

    if manifest.removed_artifacts:
        data["removed_artifacts"] = [
            {
                "kind": ra.kind.value,
                "name": ra.name,
                "file": ra.file,
                **({"of": ra.of} if ra.of else {}),
                **({"reason": ra.reason} if ra.reason else {}),
            }
            for ra in manifest.removed_artifacts
        ]
    if manifest.supersedes:
        data["supersedes"] = list(manifest.supersedes)
    if manifest.sequence_number is not None:
        data["sequence_number"] = manifest.sequence_number
    if manifest.version_tag is not None:
        data["version_tag"] = manifest.version_tag
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
    if spec.type_parameters:
        d["type_parameters"] = list(spec.type_parameters)
    if spec.type_annotation:
        d["type"] = spec.type_annotation
    if spec.test_details is not None:
        td = spec.test_details
        # Serialize test function fields at artifact level
        if td.source_scenario:
            d["source_scenario"] = td.source_scenario
        if td.tags:
            d["tags"] = list(td.tags)
        setup: dict = {}
        if td.setup.auth_required:
            setup["auth_required"] = td.setup.auth_required
        if td.setup.test_data:
            setup["test_data"] = td.setup.test_data
        if td.setup.setup_actions:
            setup["setup_actions"] = list(td.setup.setup_actions)
        if setup:
            d["setup"] = setup
        if td.actions:
            d["actions"] = list(td.actions)
        if td.expected:
            d["expected"] = td.expected
        if td.dependencies:
            d["dependencies"] = td.dependencies
    return d
