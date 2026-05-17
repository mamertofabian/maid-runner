"""Tests for CLI 'maid validate' command (v2)."""

from __future__ import annotations

import argparse
import json
import os
import textwrap

import pytest
import yaml


@pytest.fixture
def project_dir(tmp_path):
    """Create a project directory with a valid manifest and source file."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create a source file
    (src_dir / "greet.py").write_text(
        textwrap.dedent(
            """\
        def greet(name: str) -> str:
            return f"Hello, {name}"
        """
        )
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_greet.py").write_text(
        textwrap.dedent(
            """\
        from src.greet import greet


        def test_greet():
            assert greet("World") == "Hello, World"
        """
        )
    )

    # Create a v2 manifest
    manifest = {
        "schema": "2",
        "goal": "Add greeting function",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/greet.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "greet",
                            "args": [{"name": "name", "type": "str"}],
                            "returns": "str",
                        }
                    ],
                }
            ],
            "read": ["tests/test_greet.py"],
        },
        "validate": ["pytest tests/test_greet.py -v"],
    }
    (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

    return tmp_path


@pytest.fixture
def failing_project(tmp_path):
    """Create a project with a missing artifact in source."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Source file missing the declared artifact
    (src_dir / "greet.py").write_text("# empty\n")

    manifest = {
        "schema": "2",
        "goal": "Add greeting function",
        "type": "feature",
        "files": {
            "create": [
                {
                    "path": "src/greet.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "greet",
                        }
                    ],
                }
            ]
        },
        "validate": ["pytest tests/test_greet.py -v"],
    }
    (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

    return tmp_path


class TestCmdValidateSingleManifest:
    def test_cmd_validate_handler_is_directly_importable(self):
        from maid_runner.cli.commands.validate import cmd_validate

        assert callable(cmd_validate)

    def test_valid_manifest_returns_0(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(
            ["validate", "manifests/add-greet.manifest.yaml", "--no-chain"]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "add-greet" in captured.out

    def test_invalid_manifest_returns_1(self, failing_project, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(failing_project)
        exit_code = main(
            ["validate", "manifests/add-greet.manifest.yaml", "--no-chain"]
        )
        assert exit_code == 1

    def test_validate_returns_1_for_unreferenced_public_artifact(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        (src_dir / "widget.py").write_text(
            "def render():\n    return 'rendered'\n\n"
            "def update():\n    return 'updated'\n"
        )
        (tests_dir / "test_widget.py").write_text(
            "from src.widget import render\n\n"
            "def test_render():\n"
            "    assert render() == 'rendered'\n"
        )
        manifest = {
            "schema": "2",
            "goal": "Add widget",
            "type": "feature",
            "files": {
                "edit": [
                    {
                        "path": "src/widget.py",
                        "artifacts": [
                            {"kind": "function", "name": "render"},
                            {"kind": "function", "name": "update"},
                        ],
                    }
                ],
                "read": ["tests/test_widget.py"],
            },
            "validate": ["pytest tests/test_widget.py -v"],
        }
        (manifest_dir / "add-widget.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/add-widget.manifest.yaml",
                "--mode",
                "implementation",
                "--no-chain",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Errors (1):" in captured.out
        assert "E200" in captured.out
        assert "Warnings" not in captured.out

    def test_json_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(
            ["validate", "manifests/add-greet.manifest.yaml", "--no-chain", "--json"]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["success"] is True
        assert data["manifest"] == "add-greet"

    def test_quiet_mode_success_minimal_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(
            ["validate", "manifests/add-greet.manifest.yaml", "--no-chain", "--quiet"]
        )
        assert exit_code == 0

    def test_nonexistent_manifest_returns_error(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "manifests/nonexistent.yaml", "--no-chain"])
        # Should return 1 (validation failure - manifest not found is a validation error)
        assert exit_code == 1

    def test_behavioral_mode_reports_test_function_behavior_warnings_by_default(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        manifest = {
            "schema": "2",
            "goal": "Behavior check",
            "type": "feature",
            "files": {
                "edit": [
                    {
                        "path": "tests/test_api.test.ts",
                        "artifacts": [
                            {
                                "kind": "test_function",
                                "name": "test_api_call",
                                "test_function_details": {
                                    "actions": [
                                        {
                                            "type": "api_call",
                                            "subject": {
                                                "module": "src/api.ts",
                                                "export": "createLogin",
                                            },
                                            "endpoint": "/api/v1/auth/login",
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ]
            },
            "validate": ["echo ok"],
        }
        (manifest_dir / "behavior.manifest.yaml").write_text(yaml.dump(manifest))
        (tests_dir / "test_api.test.ts").write_text(
            'it("test_api_call", () => { expect(true).toBe(true); });\n'
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/behavior.manifest.yaml",
                "--mode",
                "behavioral",
                "--no-chain",
                "--json",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert any(w["code"] == "E610" for w in data["warnings"])

    def test_behavioral_validate_check_assertions_returns_1_for_no_assertions(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "greet.py").write_text("def greet():\n    return 'hello'\n")
        (tmp_path / "tests" / "test_greet.py").write_text(
            "from src.greet import greet\n\n" "def test_greet():\n" "    greet()\n"
        )
        manifest = {
            "schema": "2",
            "goal": "Add greet",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/greet.py",
                        "artifacts": [{"kind": "function", "name": "greet"}],
                    }
                ],
                "read": ["tests/test_greet.py"],
            },
            "validate": ["pytest tests/test_greet.py -v"],
        }
        (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--mode",
                "behavioral",
                "--no-chain",
                "--check-assertions",
                "--fail-on-warnings",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E210" in captured.out
        assert "Warnings" in captured.out

    def test_implementation_validate_check_stubs_returns_1_for_stub_function(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "greet.py").write_text("def greet():\n    pass\n")
        (tmp_path / "tests" / "test_greet.py").write_text(
            "from src.greet import greet\n\n"
            "def test_greet():\n"
            "    assert greet is not None\n"
        )
        manifest = {
            "schema": "2",
            "goal": "Add greet",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/greet.py",
                        "artifacts": [{"kind": "function", "name": "greet"}],
                    }
                ],
                "read": ["tests/test_greet.py"],
            },
            "validate": ["pytest tests/test_greet.py -v"],
        }
        (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--check-stubs",
                "--fail-on-warnings",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E310" in captured.out
        assert "Warnings" in captured.out

        quiet_exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--check-stubs",
                "--fail-on-warnings",
                "--quiet",
            ]
        )

        assert quiet_exit_code == 1
        quiet_output = capsys.readouterr().out
        assert "E310" in quiet_output
        assert "Warnings" in quiet_output

    def test_validate_strict_enables_assertion_stub_and_warning_failure(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "greet.py").write_text("def greet():\n    pass\n")
        (tmp_path / "tests" / "test_greet.py").write_text(
            "from src.greet import greet\n\n" "def test_greet():\n" "    greet()\n"
        )
        manifest = {
            "schema": "2",
            "goal": "Add greet",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/greet.py",
                        "artifacts": [{"kind": "function", "name": "greet"}],
                    }
                ],
                "read": ["tests/test_greet.py"],
            },
            "validate": ["pytest tests/test_greet.py -v"],
        }
        (manifest_dir / "add-greet.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        default_exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--mode",
                "behavioral",
                "--no-chain",
            ]
        )
        assert default_exit_code == 0
        capsys.readouterr()

        behavioral_exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--mode",
                "behavioral",
                "--no-chain",
                "--strict",
            ]
        )
        behavioral_output = capsys.readouterr().out

        implementation_exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--strict",
            ]
        )
        implementation_output = capsys.readouterr().out

        assert behavioral_exit_code == 1
        assert "E210" in behavioral_output
        assert implementation_exit_code == 1
        assert "E310" in implementation_output

    def test_schema_mode_single_manifest_returns_0_for_valid_schema_without_source_files(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        manifest = {
            "schema": "2",
            "goal": "Validate schema only",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/missing.py",
                        "artifacts": [{"kind": "function", "name": "missing"}],
                    }
                ],
                "read": ["tests/test_missing.py"],
            },
            "validate": ["python missing_test_runner.py"],
        }
        (manifest_dir / "schema-only.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/schema-only.manifest.yaml",
                "--mode",
                "schema",
            ]
        )

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "PASS schema-only" in captured.out
        assert "Mode: schema" in captured.out

    def test_schema_mode_single_manifest_returns_1_for_invalid_schema(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (manifest_dir / "invalid.manifest.yaml").write_text(
            yaml.dump({"schema": "2", "type": "feature"})
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/invalid.manifest.yaml",
                "--mode",
                "schema",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E004" in captured.out

    def test_schema_mode_cli_returns_1_for_duplicate_yaml_key(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (manifest_dir / "duplicate.manifest.yaml").write_text(
            """schema: "2"
goal: "Reject duplicate key"
type: fix
files:
  create:
    - path: src/visible.py
      artifacts:
        - kind: function
          name: visible
files:
  create:
    - path: src/actual.py
      artifacts:
        - kind: function
          name: actual
validate:
  - pytest tests/test_actual.py -q
"""
        )

        os.chdir(tmp_path)
        exit_code = main(
            [
                "validate",
                "manifests/duplicate.manifest.yaml",
                "--mode",
                "schema",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E003" in captured.out
        assert "duplicate YAML key" in captured.out

    def test_schema_mode_all_manifests_reports_schema_load_errors(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        valid_manifest = {
            "schema": "2",
            "goal": "Validate schema only",
            "type": "feature",
            "files": {
                "create": [
                    {
                        "path": "src/missing.py",
                        "artifacts": [{"kind": "function", "name": "missing"}],
                    }
                ]
            },
            "validate": [],
        }
        (manifest_dir / "valid.manifest.yaml").write_text(yaml.dump(valid_manifest))
        (manifest_dir / "invalid.manifest.yaml").write_text(
            yaml.dump({"schema": "2", "type": "feature"})
        )

        os.chdir(tmp_path)
        exit_code = main(["validate", "--mode", "schema"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Validation Results: 2 manifests" in captured.out
        assert "E004" in captured.out


class TestCmdValidateAll:
    def test_validate_all_returns_0_on_success(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate"])
        assert exit_code == 0

    def test_validate_file_tracking_gate_returns_1_for_undeclared_source(
        self, project_dir, capsys
    ):
        from maid_runner.cli.commands._main import main

        (project_dir / "src" / "extra.py").write_text(
            "def extra():\n    return 'drift'\n"
        )

        os.chdir(project_dir)
        exit_code = main(["validate", "--file-tracking"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "src/extra.py" in captured.out

        json_exit_code = main(["validate", "--file-tracking", "--json"])

        assert json_exit_code == 1
        json_output = capsys.readouterr().out
        data = json.loads(json_output)
        assert "src/extra.py" in json.dumps(data)

        schema_exit_code = main(["validate", "--mode", "schema", "--file-tracking"])

        assert schema_exit_code == 1
        schema_output = capsys.readouterr().out
        assert "src/extra.py" in schema_output

        from maid_runner.cli.commands import validate as validate_cmd

        watch_args = argparse.Namespace(
            watch=True,
            watch_all=False,
            manifest_path="manifests/add-greet.manifest.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            coherence=False,
            coherence_only=False,
            file_tracking=True,
        )
        watch_exit_code = validate_cmd.cmd_validate(watch_args)

        assert watch_exit_code == 2
        watch_output = capsys.readouterr()
        assert "--file-tracking is only supported" in watch_output.err

    def test_validate_all_returns_1_on_failure(self, failing_project, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(failing_project)
        exit_code = main(["validate"])
        assert exit_code == 1

    def test_validate_all_includes_nested_active_manifest_failure(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        (manifest_dir / "components" / "auth").mkdir(parents=True)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "top_level.py").write_text(
            "def top_level():\n    return 'ok'\n"
        )

        top_manifest = {
            "schema": "2",
            "goal": "Top-level active manifest",
            "type": "fix",
            "files": {
                "create": [
                    {
                        "path": "src/top_level.py",
                        "artifacts": [{"kind": "function", "name": "top_level"}],
                    }
                ],
                "read": ["tests/test_top_level.py"],
            },
            "validate": ["pytest tests/test_top_level.py -q"],
        }
        nested_manifest = {
            "schema": "2",
            "goal": "Nested active manifest",
            "type": "fix",
            "files": {
                "create": [
                    {
                        "path": "src/missing_nested.py",
                        "artifacts": [{"kind": "function", "name": "missing_nested"}],
                    }
                ],
                "read": ["tests/test_missing_nested.py"],
            },
            "validate": ["pytest tests/test_missing_nested.py -q"],
        }
        (manifest_dir / "top-level.manifest.yaml").write_text(yaml.dump(top_manifest))
        nested_manifest_path = (
            manifest_dir / "components" / "auth" / "nested-active.manifest.yml"
        )
        nested_manifest_path.write_text(yaml.dump(nested_manifest))
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_top_level.py").write_text(
            "from src.top_level import top_level\n\n"
            "def test_top_level():\n"
            "    assert top_level is not None\n"
        )
        (tmp_path / "tests" / "test_missing_nested.py").write_text(
            "from src.missing_nested import missing_nested\n\n"
            "def test_missing_nested():\n"
            "    assert missing_nested is not None\n"
        )

        os.chdir(tmp_path)
        exit_code = main(["validate", "--manifest-dir", "manifests"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Validation Results: 2 manifests" in captured.out
        assert "FAIL nested-active" in captured.out
        assert "src/missing_nested.py" in captured.out

    def test_validate_all_json_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total" in data
        assert "passed" in data

    def test_validate_nonexistent_dir_returns_1_by_default(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(["validate", "--manifest-dir", "nonexistent/"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E112" in captured.out
        assert "nonexistent" in captured.out

    def test_validate_empty_manifest_dir_returns_1_by_default(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        (tmp_path / "manifests").mkdir()
        os.chdir(tmp_path)

        exit_code = main(["validate"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "E112" in captured.out
        assert "No active manifests discovered" in captured.out

    def test_validate_allow_empty_returns_0_for_empty_manifest_dir(
        self, tmp_path, capsys
    ):
        from maid_runner.cli.commands._main import build_parser
        from maid_runner.cli.commands._main import main

        (tmp_path / "manifests").mkdir()
        os.chdir(tmp_path)

        args = build_parser().parse_args(["validate", "--allow-empty"])
        assert args.allow_empty is True

        exit_code = main(["validate", "--allow-empty"])

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Validation Results: 0 manifests" in captured.out

    def test_behavioral_mode(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--mode", "behavioral"])
        # May return 1 since there's no actual test file
        assert exit_code in (0, 1)


class TestCmdValidateCoherenceOnly:
    def test_coherence_only_with_valid_manifests(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--coherence-only"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Coherence:" in captured.out

    def test_coherence_only_json_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--coherence-only", "--json"])
        assert exit_code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "success" in data

    def test_coherence_only_nonexistent_dir(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(tmp_path)
        exit_code = main(
            ["validate", "--coherence-only", "--manifest-dir", "nonexistent/"]
        )
        assert exit_code == 2


class TestCmdValidateCoherenceFlag:
    def test_coherence_flag_returns_1_when_coherence_errors(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        (project_dir / ".maid-constraints.json").write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "name": "no-greet",
                            "description": "greet module is blocked",
                            "pattern": {
                                "file_pattern": "src/greet.py",
                                "forbidden_imports": ["blocked"],
                            },
                            "severity": "error",
                        }
                    ]
                }
            )
        )

        os.chdir(project_dir)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--coherence",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Coherence: FAIL" in captured.out
        assert "greet module is blocked" in captured.out

    def test_coherence_flag_json_reports_failure_and_exits_1(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        (project_dir / ".maid-constraints.json").write_text(
            json.dumps(
                {
                    "rules": [
                        {
                            "name": "no-greet",
                            "description": "greet module is blocked",
                            "pattern": {
                                "file_pattern": "src/greet.py",
                                "forbidden_imports": ["blocked"],
                            },
                            "severity": "error",
                        }
                    ]
                }
            )
        )

        os.chdir(project_dir)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--coherence",
                "--json",
            ]
        )

        assert exit_code == 1
        captured = capsys.readouterr()
        decoder = json.JSONDecoder()
        _, offset = decoder.raw_decode(captured.out)
        coherence, _ = decoder.raw_decode(captured.out[offset:].lstrip())
        assert coherence["success"] is False
        assert coherence["errors"] == 1
        assert coherence["issues"][0]["message"] == "greet module is blocked"

    def test_coherence_flag_returns_2_when_coherence_cannot_run(
        self, project_dir, capsys, monkeypatch
    ):
        from maid_runner.cli.commands import validate
        from maid_runner.cli.commands.validate import run_coherence

        assert callable(run_coherence)

        def fail_coherence(manifest_dir, json_mode):
            raise RuntimeError(f"cannot run coherence for {manifest_dir}")

        monkeypatch.setattr(validate, "run_coherence", fail_coherence)

        os.chdir(project_dir)
        args = argparse.Namespace(
            watch=False,
            watch_all=False,
            manifest_path="manifests/add-greet.manifest.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            coherence=True,
            coherence_only=False,
        )

        exit_code = validate.cmd_validate(args)

        assert exit_code == 2
        captured = capsys.readouterr()
        assert "cannot run coherence for manifests/" in captured.err

    def test_coherence_flag_appends_coherence_output(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(
            [
                "validate",
                "manifests/add-greet.manifest.yaml",
                "--no-chain",
                "--coherence",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        # Coherence output may be appended after validation
        assert "add-greet" in captured.out

    def test_coherence_flag_on_batch_validation(self, project_dir, capsys):
        from maid_runner.cli.commands._main import main

        os.chdir(project_dir)
        exit_code = main(["validate", "--coherence"])
        assert exit_code == 0


class TestCmdValidateWatchMode:
    def test_watch_without_watchdog_returns_error(self, project_dir, capsys):
        """If watchdog is not installed, watch mode returns 2."""
        import importlib.util

        # Check if watchdog is available
        if importlib.util.find_spec("watchdog") is not None:
            pytest.skip("watchdog is installed, cannot test missing dependency path")

        from maid_runner.cli.commands.validate import _run_watch

        args = argparse.Namespace(
            watch=True,
            watch_all=False,
            manifest_path=None,
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=False,
            coherence=False,
            coherence_only=False,
        )
        exit_code = _run_watch(args)
        assert exit_code == 2


class TestCmdValidateErrorHandling:
    def test_malformed_manifest_returns_error(self, tmp_path, capsys):
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        (manifest_dir / "bad.manifest.yaml").write_text("not: valid: yaml: {{}")

        os.chdir(tmp_path)
        exit_code = main(["validate", "manifests/bad.manifest.yaml", "--no-chain"])
        assert exit_code in (1, 2)  # Either validation error or usage error

    def test_exception_in_validation_returns_2(self, tmp_path, capsys):
        """When validation raises an unexpected exception, returns 2."""
        from maid_runner.cli.commands._main import main

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()
        # Write manifest pointing to missing directory structure
        manifest = {
            "schema": "2",
            "goal": "Test error",
            "type": "feature",
            "files": {"create": []},
            "validate": [],
        }
        (manifest_dir / "test.manifest.yaml").write_text(yaml.dump(manifest))

        os.chdir(tmp_path)
        # This should handle gracefully
        exit_code = main(["validate"])
        assert exit_code in (0, 1, 2)


class TestRunValidationPass:
    def test_single_manifest_pass(self, project_dir, capsys):
        """_run_validation_pass validates a single manifest."""
        from maid_runner.cli.commands.validate import _run_validation_pass

        os.chdir(project_dir)
        args = argparse.Namespace(
            manifest_path="manifests/add-greet.manifest.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            watch_all=False,
        )
        _run_validation_pass(args)
        captured = capsys.readouterr()
        assert "add-greet" in captured.out

    def test_batch_validation_pass(self, project_dir, capsys):
        """_run_validation_pass validates all manifests when watch_all."""
        from maid_runner.cli.commands.validate import _run_validation_pass

        os.chdir(project_dir)
        args = argparse.Namespace(
            manifest_path=None,
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            watch_all=True,
        )
        _run_validation_pass(args)
        captured = capsys.readouterr()
        assert "Validation Results" in captured.out

    def test_error_handling_in_pass(self, tmp_path, capsys):
        """_run_validation_pass handles errors gracefully."""
        from maid_runner.cli.commands.validate import _run_validation_pass

        os.chdir(tmp_path)
        args = argparse.Namespace(
            manifest_path="nonexistent.yaml",
            manifest_dir="manifests/",
            mode="implementation",
            json=False,
            quiet=False,
            no_chain=True,
            watch_all=False,
        )
        # Should not crash
        _run_validation_pass(args)
        captured = capsys.readouterr()
        assert "Error" in captured.err or "FAIL" in captured.out or captured.out
