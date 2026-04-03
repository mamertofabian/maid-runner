"""Snapshot generation for MAID Runner v2.

Generates manifest files from existing source code, enabling MAID adoption
on existing projects.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from maid_runner.core.manifest import save_manifest as _save_manifest_core
from maid_runner.core.types import (
    ArtifactSpec,
    FileMode,
    FileSpec,
    Manifest,
    TaskType,
)
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry, auto_register


class SnapshotError(Exception):
    """Raised when snapshot generation fails due to source file errors."""

    def __init__(self, message: str, path: Union[str, Path]):
        super().__init__(message)
        self.path = path


def generate_snapshot(
    file_path: Union[str, Path],
    *,
    project_root: Union[str, Path] = ".",
    include_private: bool = False,
) -> Manifest:
    """Generate a snapshot manifest from an existing source file."""
    file_path = Path(file_path).resolve()
    project_root = Path(project_root).resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Ensure validators are registered
    auto_register()

    validator = ValidatorRegistry.get(file_path)
    source = file_path.read_text()
    result = validator.collect_implementation_artifacts(source, file_path)

    if result.errors:
        raise SnapshotError(
            f"Failed to parse {file_path}: {'; '.join(result.errors)}",
            path=file_path,
        )

    # Filter artifacts
    artifacts = result.artifacts
    if not include_private:
        artifacts = [a for a in artifacts if not a.is_private]

    # Convert FoundArtifact -> ArtifactSpec
    specs = tuple(_found_to_spec(a) for a in artifacts)

    # Compute relative path
    try:
        rel_path = str(file_path.relative_to(project_root))
    except ValueError:
        rel_path = str(file_path)

    slug = _snapshot_slug(rel_path)

    file_spec = FileSpec(path=rel_path, artifacts=specs, mode=FileMode.SNAPSHOT)

    return Manifest(
        slug=slug,
        source_path="",
        goal=f"Snapshot of {rel_path}",
        validate_commands=_infer_validation_command(rel_path),
        files_snapshot=(file_spec,),
        task_type=TaskType.SNAPSHOT,
        created=datetime.now(timezone.utc).isoformat(),
    )


def generate_system_snapshot(
    manifest_dir: Union[str, Path] = "manifests/",
    *,
    project_root: Union[str, Path] = ".",
    include_private: bool = False,
) -> Manifest:
    """Generate a system-wide snapshot aggregating all tracked files."""
    from maid_runner.core.chain import ManifestChain

    project_root = Path(project_root).resolve()

    try:
        chain = ManifestChain(manifest_dir, project_root=str(project_root))
    except FileNotFoundError:
        return _empty_system_snapshot()

    tracked = chain.all_tracked_paths()
    if not tracked:
        return _empty_system_snapshot()

    auto_register()

    file_specs = []
    for rel_path in sorted(tracked):
        abs_path = project_root / rel_path
        if not abs_path.exists():
            continue
        if not ValidatorRegistry.has_validator(abs_path):
            continue

        try:
            validator = ValidatorRegistry.get(abs_path)
            source = abs_path.read_text()
            result = validator.collect_implementation_artifacts(source, abs_path)
        except Exception:
            continue

        artifacts = result.artifacts
        if not include_private:
            artifacts = [a for a in artifacts if not a.is_private]

        specs = tuple(_found_to_spec(a) for a in artifacts)
        file_specs.append(
            FileSpec(path=rel_path, artifacts=specs, mode=FileMode.SNAPSHOT)
        )

    return Manifest(
        slug="system-snapshot",
        source_path="",
        goal="System-wide snapshot of all tracked files",
        validate_commands=(("pytest", "tests/", "-v"),),
        files_snapshot=tuple(file_specs),
        task_type=TaskType.SYSTEM_SNAPSHOT,
        created=datetime.now(timezone.utc).isoformat(),
    )


def save_snapshot(
    manifest: Manifest,
    *,
    output_dir: Union[str, Path] = "manifests/",
    output: Union[str, Path, None] = None,
    format: str = "yaml",
) -> Path:
    """Save a snapshot manifest to disk."""
    if output is not None:
        out_path = Path(output)
    else:
        ext = ".json" if format == "json" else ".yaml"
        out_path = Path(output_dir) / f"{manifest.slug}.manifest{ext}"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if format == "json":
        import json
        from maid_runner.core.manifest import _manifest_to_dict

        data = _manifest_to_dict(manifest)
        out_path.write_text(json.dumps(data, indent=2))
    else:
        _save_manifest_core(manifest, out_path)

    return out_path


def generate_test_stub(
    manifest: Manifest,
    *,
    output_dir: Union[str, Path] = "tests/",
) -> dict[str, str]:
    """Generate test stub files for a manifest."""
    auto_register()

    stubs: dict[str, str] = {}
    for file_spec in manifest.all_file_specs:
        if not file_spec.artifacts:
            continue
        if not ValidatorRegistry.has_validator(file_spec.path):
            continue

        validator = ValidatorRegistry.get(file_spec.path)
        found_artifacts = [_spec_to_found(a) for a in file_spec.artifacts]
        content = validator.generate_test_stub(found_artifacts, file_spec.path)
        if content:
            test_path = _infer_test_path(file_spec.path, str(output_dir))
            stubs[test_path] = content

    return stubs


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _snapshot_slug(file_path: str) -> str:
    """Generate slug for a snapshot manifest.

    Examples:
        "src/auth/service.py" -> "snapshot-auth-service"
        "maid_runner/validators/python.py" -> "snapshot-validators-python"
        "main.py" -> "snapshot-main"
    """
    p = Path(file_path)
    stem = p.stem
    # Convert PascalCase/camelCase to kebab-case
    stem = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", stem).lower()
    # Replace underscores
    stem = stem.replace("_", "-")

    parts = list(p.parent.parts)
    if not parts or (len(parts) == 1 and parts[0] == "."):
        return f"snapshot-{stem}"

    # Drop the first (top-level) directory - it's usually the project/src root
    meaningful = [part.replace("_", "-") for part in parts]
    if len(meaningful) > 1:
        meaningful = meaningful[1:]

    # Use last 2 or fewer directory components
    if len(meaningful) > 2:
        meaningful = meaningful[-2:]

    return f"snapshot-{'-'.join(meaningful)}-{stem}"


def _infer_validation_command(rel_path: str) -> tuple[tuple[str, ...], ...]:
    """Infer the test command for a snapshot."""
    p = Path(rel_path)
    if p.suffix == ".py":
        return (("pytest", "tests/", "-v"),)
    elif p.suffix in (".ts", ".tsx"):
        return (("vitest", "run"),)
    return (("pytest", "tests/", "-v"),)


def _infer_test_path(source_path: str, test_dir: str) -> str:
    """Infer test file path from source path."""
    p = Path(source_path)
    if p.suffix == ".py":
        return str(Path(test_dir) / f"test_{p.stem}.py")
    elif p.suffix in (".ts", ".tsx"):
        return str(Path(test_dir) / p.parent / f"{p.stem}.test{p.suffix}")
    return str(Path(test_dir) / f"test_{p.stem}{p.suffix}")


def _found_to_spec(artifact: FoundArtifact) -> ArtifactSpec:
    """Convert FoundArtifact to ArtifactSpec."""
    return ArtifactSpec(
        kind=artifact.kind,
        name=artifact.name,
        of=artifact.of,
        args=artifact.args,
        returns=artifact.returns,
        is_async=artifact.is_async,
        bases=artifact.bases,
        type_annotation=artifact.type_annotation,
    )


def _spec_to_found(spec: ArtifactSpec) -> FoundArtifact:
    """Convert ArtifactSpec to FoundArtifact (for test stub generation)."""
    return FoundArtifact(
        kind=spec.kind,
        name=spec.name,
        of=spec.of,
        args=spec.args,
        returns=spec.returns,
        is_async=spec.is_async,
        bases=spec.bases,
        type_annotation=spec.type_annotation,
    )


def _empty_system_snapshot() -> Manifest:
    return Manifest(
        slug="system-snapshot",
        source_path="",
        goal="System-wide snapshot of all tracked files",
        validate_commands=(("pytest", "tests/", "-v"),),
        files_snapshot=(),
        task_type=TaskType.SYSTEM_SNAPSHOT,
        created=datetime.now(timezone.utc).isoformat(),
    )
