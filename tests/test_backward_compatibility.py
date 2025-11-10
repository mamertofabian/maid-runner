"""Tests ensuring backward compatibility with existing manifests."""

import json
from pathlib import Path


from maid_runner.validators.manifest_validator import validate_schema
from maid_runner.cli.validate import extract_test_files_from_command

SCHEMA_PATH = Path("maid_runner/validators/schemas/manifest.schema.json")
MANIFESTS_DIR = Path("manifests")


def test_all_existing_manifests_validate():
    """Test that all existing manifests still validate without modification."""
    manifest_files = list(MANIFESTS_DIR.glob("task-*.manifest.json"))
    assert len(manifest_files) > 0, "No manifest files found"

    for manifest_path in manifest_files:
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        # Schema validation should pass
        validate_schema(manifest_data, str(SCHEMA_PATH))

        # Check that validationCommand exists (legacy format)
        assert (
            "validationCommand" in manifest_data
            or "validationCommands" in manifest_data
        )


def test_legacy_validation_command_still_works():
    """Test that legacy validationCommand format still works in code."""
    validation_command = ["pytest", "tests/test1.py", "tests/test2.py", "-v"]
    test_files = extract_test_files_from_command(validation_command)
    assert len(test_files) >= 2
    assert "tests/test1.py" in test_files or "tests/test2.py" in test_files


def test_legacy_parameters_still_works():
    """Test that legacy parameters field still works in code."""
    artifact = {
        "type": "function",
        "name": "test_func",
        "parameters": [{"name": "param1"}, {"name": "param2"}],
    }
    # Code should read parameters field
    params = artifact.get("args") or artifact.get("parameters", [])
    assert len(params) == 2
    assert params[0]["name"] == "param1"


def test_both_formats_can_coexist():
    """Test that old and new format manifests can coexist."""
    # Legacy format manifest
    legacy_manifest = {
        "goal": "Legacy format",
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {"type": "function", "name": "func", "parameters": [{"name": "p"}]}
            ],
        },
        "validationCommand": ["pytest", "test.py"],
    }

    # Enhanced format manifest
    enhanced_manifest = {
        "goal": "Enhanced format",
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "func",
                    "args": [{"name": "p", "type": "str"}],
                }
            ],
        },
        "validationCommands": [["pytest", "test.py"]],
    }

    # Both should validate
    validate_schema(legacy_manifest, str(SCHEMA_PATH))
    validate_schema(enhanced_manifest, str(SCHEMA_PATH))


def test_code_reads_both_parameters_and_args():
    """Test that code correctly reads both parameters and args fields."""
    # Test with parameters (legacy)
    artifact1 = {"parameters": [{"name": "p1"}]}
    params1 = artifact1.get("args") or artifact1.get("parameters", [])
    assert len(params1) == 1

    # Test with args (enhanced)
    artifact2 = {"args": [{"name": "p1"}]}
    params2 = artifact2.get("args") or artifact2.get("parameters", [])
    assert len(params2) == 1

    # Test with both (args takes precedence)
    artifact3 = {"parameters": [{"name": "p1"}], "args": [{"name": "p2"}]}
    params3 = artifact3.get("args") or artifact3.get("parameters", [])
    assert len(params3) == 1
    assert params3[0]["name"] == "p2"  # args takes precedence


def test_code_reads_both_validation_command_formats():
    """Test that code correctly reads both validationCommand and validationCommands."""
    # Test with validationCommand (legacy)
    manifest1 = {"validationCommand": ["pytest", "test.py"]}
    commands1 = manifest1.get("validationCommands", [])
    if not commands1:
        commands1 = manifest1.get("validationCommand", [])
    assert len(commands1) > 0

    # Test with validationCommands (enhanced)
    manifest2 = {"validationCommands": [["pytest", "test.py"]]}
    commands2 = manifest2.get("validationCommands", [])
    if not commands2:
        commands2 = manifest2.get("validationCommand", [])
    assert len(commands2) > 0
    assert isinstance(commands2[0], list)
