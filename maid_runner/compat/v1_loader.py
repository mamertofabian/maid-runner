"""V1 manifest compatibility layer for MAID Runner v2."""

from __future__ import annotations

from pathlib import Path
from typing import Union


def is_v1_manifest(data: dict) -> bool:
    if data.get("schema") == "2":
        return False
    if "expectedArtifacts" in data or "systemArtifacts" in data:
        return True
    if "creatableFiles" in data or "editableFiles" in data:
        return True
    if "validationCommand" in data and "validate" not in data:
        return True
    if data.get("version") == "1":
        return True
    return False


def convert_v1_to_v2(data: dict) -> dict:
    v2: dict = {
        "schema": "2",
        "goal": data.get("goal", ""),
    }

    # Task type mapping
    task_type = data.get("taskType", "feature")
    type_map = {"create": "feature", "edit": "feature"}
    v2["type"] = type_map.get(task_type, task_type)

    if data.get("description"):
        v2["description"] = data["description"]

    # Files
    files: dict = {}
    creatable = data.get("creatableFiles", [])
    editable = data.get("editableFiles", [])
    readonly = data.get("readonlyFiles", [])

    # Expected artifacts
    ea = data.get("expectedArtifacts")
    ea_file = ea.get("file") if ea else None
    ea_contains = ea.get("contains", []) if ea else []
    ea_status = ea.get("status", "present") if ea else "present"

    converted_artifacts = [
        a for a in (_convert_artifact(raw) for raw in ea_contains) if a is not None
    ]

    # System artifacts for snapshots
    system_artifacts = data.get("systemArtifacts", [])
    if system_artifacts and task_type in ("snapshot", "system-snapshot"):
        snapshot_files = []
        for sa in system_artifacts:
            sa_artifacts = [
                a
                for a in (_convert_artifact(raw) for raw in sa.get("contains", []))
                if a is not None
            ]
            snapshot_files.append({"path": sa["file"], "artifacts": sa_artifacts})
        if snapshot_files:
            files["snapshot"] = snapshot_files

    # Place expected artifacts in create or edit
    if ea_file:
        if ea_status == "absent":
            files.setdefault("delete", []).append({"path": ea_file})
        elif ea_file in creatable:
            files.setdefault("create", []).append(
                {"path": ea_file, "artifacts": converted_artifacts}
            )
        else:
            files.setdefault("edit", []).append(
                {"path": ea_file, "artifacts": converted_artifacts}
            )

    # Add remaining creatable/editable files without artifacts
    for f in creatable:
        if f != ea_file:
            # Files without artifacts get a placeholder (schema requires at least 1)
            # We skip them since they can't satisfy schema validation
            pass
    for f in editable:
        if f != ea_file:
            pass

    # Snapshot with expected artifacts (non-system)
    if task_type == "snapshot" and ea_file and "snapshot" not in files:
        # Move from create/edit to snapshot
        for section in ("create", "edit"):
            section_files = files.get(section, [])
            for i, sf in enumerate(section_files):
                if sf.get("path") == ea_file:
                    files.setdefault("snapshot", []).append(section_files.pop(i))
                    if not section_files:
                        del files[section]
                    break

    if readonly:
        files["read"] = readonly

    if files:
        v2["files"] = files

    # Validation commands
    if "validationCommands" in data:
        v2["validate"] = data["validationCommands"]
    elif "validationCommand" in data:
        v2["validate"] = [data["validationCommand"]]
    else:
        v2["validate"] = ["echo no validation"]

    # Supersedes: convert paths to slugs
    supersedes = data.get("supersedes", [])
    if supersedes:
        v2["supersedes"] = [_path_to_slug(s) for s in supersedes]

    # Metadata / created
    metadata = data.get("metadata")
    if metadata:
        v2["metadata"] = metadata
        if "created" in metadata and "created" not in data:
            v2["created"] = metadata["created"]
    if "created" in data:
        v2["created"] = data["created"]

    return v2


def convert_v1_file(
    input_path: Union[str, Path], output_path: Union[str, Path, None] = None
) -> Path:
    import json
    import yaml

    input_path = Path(input_path)
    data = json.loads(input_path.read_text())
    v2_data = convert_v1_to_v2(data)

    if output_path is None:
        slug = _path_to_slug(str(input_path))
        output_path = input_path.parent / f"{slug}.manifest.yaml"
    output_path = Path(output_path)
    output_path.write_text(
        yaml.dump(v2_data, default_flow_style=False, sort_keys=False)
    )
    return output_path


def _convert_artifact(v1: dict) -> dict | None:
    art_type = v1.get("type", "")
    # Skip parameter artifacts (redundant with args)
    if art_type == "parameter":
        return None

    name = v1.get("name", "")
    parent_class = v1.get("class")

    # Determine kind
    if art_type == "function" and parent_class:
        kind = "method"
    elif art_type == "function":
        kind = "function"
    elif art_type == "attribute":
        kind = "attribute"
    elif art_type == "class":
        kind = "class"
    else:
        kind = art_type  # interface, type, enum, namespace

    result: dict = {"kind": kind, "name": name}

    if parent_class:
        result["of"] = parent_class

    # Args: prefer "args" over "parameters"
    args = v1.get("args") or v1.get("parameters")
    if args:
        result["args"] = [
            {
                "name": a["name"],
                **({"type": a["type"]} if "type" in a else {}),
                **({"default": a["default"]} if "default" in a else {}),
            }
            for a in args
        ]

    # Returns
    returns = v1.get("returns")
    if isinstance(returns, dict):
        returns = returns.get("type")
    if returns:
        result["returns"] = returns

    if v1.get("raises"):
        result["raises"] = v1["raises"]

    if v1.get("bases"):
        result["bases"] = v1["bases"]

    if v1.get("description"):
        result["description"] = v1["description"]

    return result


def _path_to_slug(path: str) -> str:
    name = Path(path).name
    for suffix in (".manifest.json", ".manifest.yaml", ".manifest.yml"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name
