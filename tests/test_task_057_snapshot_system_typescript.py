"""Integration tests for Task-057: Verify snapshot-system TypeScript support.

This test suite verifies that snapshot-system correctly handles TypeScript manifests
and mixed Python/TypeScript projects. Since snapshot-system is language-agnostic
(it aggregates existing manifests rather than parsing source code), these tests
focus on integration scenarios.

Test Organization:
- TypeScript manifest aggregation
- Mixed Python/TypeScript projects
- TypeScript validation command aggregation
- System manifest generation with TypeScript
- End-to-end integration tests
"""

import json


# =============================================================================
# SECTION 1: TypeScript Manifest Aggregation
# =============================================================================


class TestTypeScriptManifestAggregation:
    """Test that snapshot-system aggregates TypeScript manifests correctly."""

    def test_aggregate_typescript_artifacts(self, tmp_path):
        """snapshot-system must aggregate TypeScript artifacts from manifests."""
        from maid_runner.cli.snapshot_system import aggregate_system_artifacts

        # Create TypeScript manifests
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Manifest 1: TypeScript interface and class
        manifest1 = manifest_dir / "task-001.manifest.json"
        manifest1.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "TypeScript types",
                    "taskType": "create",
                    "creatableFiles": ["types.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "types.ts",
                        "contains": [
                            {"type": "interface", "name": "User"},
                            {"type": "class", "name": "UserService"},
                        ],
                    },
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Manifest 2: TypeScript type aliases and enums
        manifest2 = manifest_dir / "task-002.manifest.json"
        manifest2.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "More TypeScript types",
                    "taskType": "create",
                    "creatableFiles": ["enums.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "enums.ts",
                        "contains": [
                            {"type": "type", "name": "UserID"},
                            {"type": "enum", "name": "Role"},
                        ],
                    },
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Aggregate artifacts
        manifest_paths = [manifest1, manifest2]
        artifact_blocks = aggregate_system_artifacts(manifest_paths)

        # Verify aggregation
        assert len(artifact_blocks) == 2

        # Verify first file
        types_block = next(b for b in artifact_blocks if b["file"] == "types.ts")
        assert len(types_block["contains"]) == 2
        artifact_types = {a["type"] for a in types_block["contains"]}
        assert "interface" in artifact_types
        assert "class" in artifact_types

        # Verify second file
        enums_block = next(b for b in artifact_blocks if b["file"] == "enums.ts")
        assert len(enums_block["contains"]) == 2
        artifact_types = {a["type"] for a in enums_block["contains"]}
        assert "type" in artifact_types
        assert "enum" in artifact_types

    def test_aggregate_typescript_namespaces(self, tmp_path):
        """snapshot-system must handle TypeScript namespace artifacts."""
        from maid_runner.cli.snapshot_system import aggregate_system_artifacts

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest = manifest_dir / "task-001.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "Namespaces",
                    "taskType": "create",
                    "creatableFiles": ["utils.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "utils.ts",
                        "contains": [{"type": "namespace", "name": "Utils"}],
                    },
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        artifact_blocks = aggregate_system_artifacts([manifest])

        assert len(artifact_blocks) == 1
        assert artifact_blocks[0]["contains"][0]["type"] == "namespace"
        assert artifact_blocks[0]["contains"][0]["name"] == "Utils"


# =============================================================================
# SECTION 2: Mixed Python/TypeScript Projects
# =============================================================================


class TestMixedLanguageProjects:
    """Test snapshot-system with mixed Python and TypeScript manifests."""

    def test_aggregate_mixed_python_typescript(self, tmp_path):
        """snapshot-system must handle mixed Python/TypeScript projects."""
        from maid_runner.cli.snapshot_system import aggregate_system_artifacts

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Python manifest
        python_manifest = manifest_dir / "task-001.manifest.json"
        python_manifest.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "Python module",
                    "taskType": "create",
                    "creatableFiles": ["backend.py"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "backend.py",
                        "contains": [
                            {"type": "class", "name": "ApiHandler"},
                            {"type": "function", "name": "process_request"},
                        ],
                    },
                    "validationCommand": ["pytest", "tests/"],
                }
            )
        )

        # TypeScript manifest
        ts_manifest = manifest_dir / "task-002.manifest.json"
        ts_manifest.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "TypeScript frontend",
                    "taskType": "create",
                    "creatableFiles": ["frontend.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "frontend.ts",
                        "contains": [
                            {"type": "interface", "name": "ApiResponse"},
                            {"type": "class", "name": "ApiClient"},
                        ],
                    },
                    "validationCommand": ["npm", "test"],
                }
            )
        )

        # Aggregate
        artifact_blocks = aggregate_system_artifacts([python_manifest, ts_manifest])

        # Verify both languages present
        assert len(artifact_blocks) == 2

        # Python file
        py_block = next(b for b in artifact_blocks if b["file"] == "backend.py")
        assert len(py_block["contains"]) == 2

        # TypeScript file
        ts_block = next(b for b in artifact_blocks if b["file"] == "frontend.ts")
        assert len(ts_block["contains"]) == 2
        ts_types = {a["type"] for a in ts_block["contains"]}
        assert "interface" in ts_types
        assert "class" in ts_types

    def test_validation_commands_for_mixed_languages(self, tmp_path):
        """snapshot-system must aggregate validation commands from both languages."""
        from maid_runner.cli.snapshot_system import aggregate_validation_commands

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Python manifest with pytest
        python_manifest = manifest_dir / "task-001.manifest.json"
        python_manifest.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "Python",
                    "taskType": "create",
                    "creatableFiles": ["test.py"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["pytest", "tests/"],
                }
            )
        )

        # TypeScript manifest with npm test
        ts_manifest = manifest_dir / "task-002.manifest.json"
        ts_manifest.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "TypeScript",
                    "taskType": "create",
                    "creatableFiles": ["test.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.ts", "contains": []},
                    "validationCommand": ["npm", "test"],
                }
            )
        )

        # Aggregate commands
        commands = aggregate_validation_commands([python_manifest, ts_manifest])

        # Verify both commands present
        assert len(commands) == 2
        assert ["pytest", "tests/"] in commands
        assert ["npm", "test"] in commands


# =============================================================================
# SECTION 3: System Manifest Generation with TypeScript
# =============================================================================


class TestSystemManifestGeneration:
    """Test complete system manifest generation with TypeScript."""

    def test_create_system_manifest_with_typescript(self, tmp_path):
        """System manifest must include TypeScript artifacts correctly."""
        from maid_runner.cli.snapshot_system import create_system_manifest

        # System artifacts with TypeScript
        system_artifacts = [
            {
                "file": "types.ts",
                "contains": [
                    {"type": "interface", "name": "User"},
                    {"type": "type", "name": "UserID"},
                ],
            },
            {
                "file": "utils.py",
                "contains": [{"type": "function", "name": "helper"}],
            },
        ]

        validation_commands = [["pytest", "tests/"], ["npm", "test"]]

        manifest = create_system_manifest(system_artifacts, validation_commands)

        # Verify structure
        assert manifest["taskType"] == "system-snapshot"
        assert "systemArtifacts" in manifest
        assert len(manifest["systemArtifacts"]) == 2

        # Verify TypeScript artifacts
        ts_block = next(
            b for b in manifest["systemArtifacts"] if b["file"] == "types.ts"
        )
        assert len(ts_block["contains"]) == 2
        types = {a["type"] for a in ts_block["contains"]}
        assert "interface" in types
        assert "type" in types

    def test_system_snapshot_only_typescript(self, tmp_path):
        """System snapshot must work with TypeScript-only projects."""
        from maid_runner.cli.snapshot_system import create_system_manifest

        system_artifacts = [
            {
                "file": "app.ts",
                "contains": [
                    {"type": "class", "name": "App"},
                    {"type": "interface", "name": "Config"},
                    {"type": "enum", "name": "Environment"},
                ],
            }
        ]

        validation_commands = [["npm", "test"]]

        manifest = create_system_manifest(system_artifacts, validation_commands)

        assert len(manifest["systemArtifacts"]) == 1
        assert manifest["validationCommands"] == validation_commands


# =============================================================================
# SECTION 4: End-to-End Integration
# =============================================================================


class TestEndToEndIntegration:
    """Test complete end-to-end snapshot-system workflow with TypeScript."""

    def test_full_workflow_mixed_project(self, tmp_path):
        """Complete workflow: discover → aggregate → generate system manifest."""
        from maid_runner.cli.snapshot_system import (
            discover_active_manifests,
            aggregate_system_artifacts,
            aggregate_validation_commands,
            create_system_manifest,
        )

        # Set up manifest directory
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create mixed manifests
        manifests_data = [
            {
                "name": "task-001-python.manifest.json",
                "content": {
                    "version": "1",
                    "goal": "Python backend",
                    "taskType": "create",
                    "creatableFiles": ["api.py"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "api.py",
                        "contains": [{"type": "class", "name": "API"}],
                    },
                    "validationCommand": ["pytest", "tests/test_api.py"],
                },
            },
            {
                "name": "task-002-typescript.manifest.json",
                "content": {
                    "version": "1",
                    "goal": "TypeScript frontend",
                    "taskType": "create",
                    "creatableFiles": ["client.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "client.ts",
                        "contains": [
                            {"type": "interface", "name": "Response"},
                            {"type": "class", "name": "Client"},
                        ],
                    },
                    "validationCommand": ["npm", "test"],
                },
            },
        ]

        for manifest_info in manifests_data:
            manifest_path = manifest_dir / manifest_info["name"]
            manifest_path.write_text(json.dumps(manifest_info["content"]))

        # Execute workflow
        active_manifests = discover_active_manifests(manifest_dir)
        assert len(active_manifests) == 2

        system_artifacts = aggregate_system_artifacts(active_manifests)
        assert len(system_artifacts) == 2

        validation_commands = aggregate_validation_commands(active_manifests)
        assert len(validation_commands) == 2

        system_manifest = create_system_manifest(system_artifacts, validation_commands)

        # Verify system manifest
        assert system_manifest["taskType"] == "system-snapshot"
        assert len(system_manifest["systemArtifacts"]) == 2
        assert len(system_manifest["validationCommands"]) == 2

        # Verify TypeScript artifacts included
        ts_artifacts = next(
            b for b in system_manifest["systemArtifacts"] if b["file"] == "client.ts"
        )
        assert len(ts_artifacts["contains"]) == 2
        types = {a["type"] for a in ts_artifacts["contains"]}
        assert "interface" in types
        assert "class" in types

    def test_run_snapshot_system_with_typescript(self, tmp_path):
        """Test run_snapshot_system orchestration with TypeScript manifests."""
        from maid_runner.cli.snapshot_system import run_snapshot_system

        # Set up manifests
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest = manifest_dir / "task-001.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "TypeScript app",
                    "taskType": "create",
                    "creatableFiles": ["app.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "app.ts",
                        "contains": [
                            {"type": "interface", "name": "Config"},
                            {"type": "class", "name": "Application"},
                        ],
                    },
                    "validationCommand": ["npm", "test"],
                }
            )
        )

        output_path = tmp_path / "system.manifest.json"

        # Run snapshot-system
        run_snapshot_system(str(output_path), str(manifest_dir), quiet=True)

        # Verify output
        assert output_path.exists()

        with open(output_path) as f:
            system_manifest = json.load(f)

        assert system_manifest["taskType"] == "system-snapshot"
        assert len(system_manifest["systemArtifacts"]) == 1

        # Verify TypeScript artifacts
        ts_block = system_manifest["systemArtifacts"][0]
        assert ts_block["file"] == "app.ts"
        types = {a["type"] for a in ts_block["contains"]}
        assert "interface" in types
        assert "class" in types


# =============================================================================
# SECTION 5: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases for TypeScript support in snapshot-system."""

    def test_all_typescript_artifact_types(self, tmp_path):
        """System snapshot must handle all TypeScript artifact types."""
        from maid_runner.cli.snapshot_system import aggregate_system_artifacts

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest = manifest_dir / "task-001.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "All TS types",
                    "taskType": "create",
                    "creatableFiles": ["complete.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "complete.ts",
                        "contains": [
                            {"type": "class", "name": "MyClass"},
                            {"type": "interface", "name": "MyInterface"},
                            {"type": "type", "name": "MyType"},
                            {"type": "enum", "name": "MyEnum"},
                            {"type": "namespace", "name": "MyNamespace"},
                            {"type": "function", "name": "myFunction"},
                        ],
                    },
                    "validationCommand": ["npm", "test"],
                }
            )
        )

        artifact_blocks = aggregate_system_artifacts([manifest])

        assert len(artifact_blocks) == 1
        artifacts = artifact_blocks[0]["contains"]
        assert len(artifacts) == 6

        types = {a["type"] for a in artifacts}
        assert types == {"class", "interface", "type", "enum", "namespace", "function"}

    def test_empty_typescript_manifest(self, tmp_path):
        """System snapshot must handle TypeScript manifest with no artifacts."""
        from maid_runner.cli.snapshot_system import aggregate_system_artifacts

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest = manifest_dir / "task-001.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": "1",
                    "goal": "Empty TS file",
                    "taskType": "create",
                    "creatableFiles": ["empty.ts"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "empty.ts", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        artifact_blocks = aggregate_system_artifacts([manifest])

        # Should still create an entry for the file
        assert len(artifact_blocks) == 1
        assert artifact_blocks[0]["file"] == "empty.ts"
        assert artifact_blocks[0]["contains"] == []
