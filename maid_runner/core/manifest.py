"""Manifest loading, saving, and schema validation for MAID Runner v2."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
from typing import Iterable, Union

import jsonschema
import yaml

from maid_runner.core._file_discovery import is_test_file
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
_TEST_RUNNERS = {
    "ava",
    "cypress",
    "jest",
    "mocha",
    "playwright",
    "py.test",
    "pytest",
    "vitest",
}
_TEST_RUNNER_NON_PATH_VALUE_OPTIONS = {"-k", "-m", "-o", "-p"}
_TEST_RUNNER_PATH_VALUE_OPTIONS = {
    "--basetemp",
    "--confcutdir",
    "--cov",
    "--deselect",
    "--ignore",
    "--ignore-glob",
    "--junitxml",
    "--rootdir",
}


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
    """Validate every project-relative manifest path stays in project_root."""
    root = Path(project_root)
    errors: list[ValidationError] = []

    for fs in manifest.files_create:
        errors.extend(_validate_project_path(root, fs.path, "files.create path"))
    for fs in manifest.files_edit:
        errors.extend(_validate_project_path(root, fs.path, "files.edit path"))
    for fs in manifest.files_snapshot:
        errors.extend(_validate_project_path(root, fs.path, "files.snapshot path"))
    for path in manifest.files_read:
        errors.extend(_validate_project_path(root, path, "files.read path"))
    for spec in manifest.files_delete:
        errors.extend(_validate_project_path(root, spec.path, "files.delete path"))
    for spec in manifest.removed_artifacts:
        errors.extend(_validate_project_path(root, spec.file, "removed_artifacts file"))
    for path, source in _test_paths_from_commands(
        manifest.validate_commands,
        source="validate command test path",
    ):
        errors.extend(_validate_project_path(root, path, source))
    if manifest.acceptance is not None:
        for path, source in _test_paths_from_commands(
            manifest.acceptance.tests,
            source="acceptance test path",
        ):
            errors.extend(_validate_project_path(root, path, source))

    return errors


def _validate_project_path(
    project_root: Path,
    path: str,
    source: str,
) -> list[ValidationError]:
    candidate = Path(path)
    if _path_is_within_project(project_root, candidate):
        return []
    return [
        ValidationError(
            code=ErrorCode.MANIFEST_PATH_OUTSIDE_PROJECT,
            message=(f"Manifest {source} '{path}' resolves outside the project root"),
            location=Location(file=path),
            suggestion=(
                "Use a project-relative path inside the repository; absolute "
                "and parent-relative paths are not allowed."
            ),
        )
    ]


def _path_is_within_project(project_root: Path, path: Path) -> bool:
    if path.is_absolute():
        return False
    try:
        root = project_root.resolve()
        full_path = (project_root / path).resolve()
        full_path.relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _test_paths_from_commands(
    commands: Iterable[tuple[str, ...]],
    *,
    source: str,
) -> Iterable[tuple[str, str]]:
    for command in commands:
        cwd = Path(".")
        for segment in _command_segments(command):
            if not segment:
                continue
            in_test_runner = False
            skip_next_non_path_value = False
            next_value_is_path = False
            if segment[0] == "cd":
                if len(segment) > 1:
                    cwd = cwd / segment[1]
                    yield str(cwd), f"{source} working directory"
                continue
            index = 0
            while index < len(segment):
                part = segment[index]
                if part in {"-C", "--cwd", "--dir", "--prefix"} and index + 1 < len(
                    segment
                ):
                    cwd = cwd / segment[index + 1]
                    yield str(cwd), f"{source} working directory"
                    index += 2
                    continue
                if skip_next_non_path_value:
                    skip_next_non_path_value = False
                    index += 1
                    continue
                if next_value_is_path:
                    next_value_is_path = False
                    yield str(cwd / part), source
                    index += 1
                    continue
                option_name, option_value = _split_command_option(part)
                if in_test_runner and option_name in _TEST_RUNNER_PATH_VALUE_OPTIONS:
                    if option_value is not None:
                        yield str(cwd / option_value), source
                    else:
                        next_value_is_path = True
                    index += 1
                    continue
                if (
                    in_test_runner
                    and option_name in _TEST_RUNNER_NON_PATH_VALUE_OPTIONS
                ):
                    if option_value is None:
                        skip_next_non_path_value = True
                    index += 1
                    continue
                if part.startswith("-"):
                    index += 1
                    continue
                if _is_test_runner(part):
                    in_test_runner = True
                    index += 1
                    continue
                candidate = cwd / part
                if _looks_like_manifest_test_path(part) or (
                    in_test_runner and _looks_like_path_argument(part)
                ):
                    yield str(candidate), source
                index += 1


def _command_segments(command: tuple[str, ...]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for part in command:
        if part in {"&&", "||", ";"}:
            segments.append([])
        else:
            segments[-1].append(part)
    return segments


def _looks_like_manifest_test_path(path: str) -> bool:
    candidate = Path(path)
    if is_test_file(path):
        return True
    test_dir_names = {"test", "tests", "__tests__", "spec", "specs"}
    if any(part.lower() in test_dir_names for part in candidate.parts):
        return True
    return candidate.suffix in {".py", ".ts", ".tsx", ".js", ".jsx", ".svelte"}


def _is_test_runner(part: str) -> bool:
    name = Path(part).name
    if name.endswith(".exe"):
        name = name.removesuffix(".exe")
    return name in _TEST_RUNNERS


def _split_command_option(part: str) -> tuple[str, str | None]:
    if not part.startswith("-"):
        return part, None
    option, separator, value = part.partition("=")
    return option, value if separator else None


def _looks_like_path_argument(part: str) -> bool:
    if Path(part).is_absolute():
        return True
    return (
        part.startswith(".")
        or os.sep in part
        or (os.altsep is not None and os.altsep in part)
    )


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
