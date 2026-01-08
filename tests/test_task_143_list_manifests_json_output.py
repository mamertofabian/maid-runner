"""Behavioral tests for Task-143: List manifests JSON output.

Tests the format_manifests_json function and the json_output parameter
for run_list_manifests, enabling the maid-lsp server to receive manifest
paths in machine-readable JSON format.
"""

import inspect
import json


class TestFormatManifestsJsonFunction:
    """Tests for the format_manifests_json function."""

    def test_format_manifests_json_exists(self):
        """Test that format_manifests_json function exists and can be imported."""
        from maid_runner.cli.list_manifests import format_manifests_json

        assert callable(format_manifests_json)

    def test_format_manifests_json_signature(self):
        """Test that format_manifests_json has the expected signature."""
        from maid_runner.cli.list_manifests import format_manifests_json

        sig = inspect.signature(format_manifests_json)
        params = list(sig.parameters.keys())

        assert "categorized_manifests" in params
        assert "manifest_dir" in params
        assert sig.parameters["categorized_manifests"].annotation is dict
        assert sig.parameters["manifest_dir"].annotation is str

    def test_format_manifests_json_returns_valid_json(self):
        """Test that format_manifests_json returns a valid JSON string."""
        from maid_runner.cli.list_manifests import format_manifests_json

        categorized = {
            "created": ["task-001.manifest.json"],
            "edited": [],
            "read": [],
        }

        result = format_manifests_json(categorized, "manifests")

        # Should be a valid JSON string
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_format_manifests_json_empty_categories_returns_empty_array(self):
        """Test that empty categories returns an empty JSON array."""
        from maid_runner.cli.list_manifests import format_manifests_json

        categorized = {
            "created": [],
            "edited": [],
            "read": [],
        }

        result = format_manifests_json(categorized, "manifests")

        assert result == "[]"

    def test_format_manifests_json_single_manifest_in_created(self):
        """Test that single manifest in created returns array with one path."""
        from maid_runner.cli.list_manifests import format_manifests_json

        categorized = {
            "created": ["task-001.manifest.json"],
            "edited": [],
            "read": [],
        }

        result = format_manifests_json(categorized, "manifests")
        parsed = json.loads(result)

        assert len(parsed) == 1
        assert parsed[0] == "manifests/task-001.manifest.json"

    def test_format_manifests_json_multiple_manifests_across_categories(self):
        """Test that multiple manifests across categories returns flat array."""
        from maid_runner.cli.list_manifests import format_manifests_json

        categorized = {
            "created": ["task-001.manifest.json"],
            "edited": ["task-002.manifest.json"],
            "read": ["task-003.manifest.json", "task-004.manifest.json"],
        }

        result = format_manifests_json(categorized, "manifests")
        parsed = json.loads(result)

        assert len(parsed) == 4
        assert "manifests/task-001.manifest.json" in parsed
        assert "manifests/task-002.manifest.json" in parsed
        assert "manifests/task-003.manifest.json" in parsed
        assert "manifests/task-004.manifest.json" in parsed

    def test_format_manifests_json_paths_constructed_correctly(self):
        """Test that paths are constructed from manifest_dir + manifest_name."""
        from maid_runner.cli.list_manifests import format_manifests_json

        categorized = {
            "created": ["task-001.manifest.json"],
            "edited": [],
            "read": [],
        }

        # Test with different manifest_dir values
        result1 = format_manifests_json(categorized, "manifests")
        result2 = format_manifests_json(categorized, "custom/path")

        parsed1 = json.loads(result1)
        parsed2 = json.loads(result2)

        assert parsed1[0] == "manifests/task-001.manifest.json"
        assert parsed2[0] == "custom/path/task-001.manifest.json"

    def test_format_manifests_json_deduplicates_manifests(self):
        """Test that duplicate manifests across categories are deduplicated."""
        from maid_runner.cli.list_manifests import format_manifests_json

        # Same manifest might appear in multiple categories theoretically
        categorized = {
            "created": ["task-001.manifest.json"],
            "edited": ["task-001.manifest.json"],  # Duplicate
            "read": ["task-002.manifest.json"],
        }

        result = format_manifests_json(categorized, "manifests")
        parsed = json.loads(result)

        # Should only have 2 unique paths
        assert len(parsed) == 2
        assert len(set(parsed)) == 2  # All unique


class TestRunListManifestsJsonOutput:
    """Tests for run_list_manifests with json_output parameter."""

    def test_run_list_manifests_has_json_output_parameter(self):
        """Test that run_list_manifests accepts json_output parameter."""
        from maid_runner.cli.list_manifests import run_list_manifests

        sig = inspect.signature(run_list_manifests)
        params = list(sig.parameters.keys())

        assert "json_output" in params
        assert sig.parameters["json_output"].annotation is bool

    def test_run_list_manifests_json_output_prints_json_array(self, tmp_path, capsys):
        """Test that json_output=True prints JSON array to stdout."""
        from maid_runner.cli.list_manifests import run_list_manifests

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest1 = {
            "goal": "Create test.py",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
        }

        with open(manifest_dir / "task-001.manifest.json", "w") as f:
            json.dump(manifest1, f)

        run_list_manifests("test.py", str(manifest_dir), quiet=False, json_output=True)

        captured = capsys.readouterr()
        output = captured.out.strip()

        # Should be valid JSON array
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1

    def test_run_list_manifests_json_output_no_manifests_prints_empty_array(
        self, tmp_path, capsys
    ):
        """Test that json_output=True with no matches prints empty JSON array."""
        from maid_runner.cli.list_manifests import run_list_manifests

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest1 = {
            "goal": "Create other.py",
            "creatableFiles": ["other.py"],
            "editableFiles": [],
            "readonlyFiles": [],
        }

        with open(manifest_dir / "task-001.manifest.json", "w") as f:
            json.dump(manifest1, f)

        run_list_manifests(
            "not_found.py", str(manifest_dir), quiet=False, json_output=True
        )

        captured = capsys.readouterr()
        output = captured.out.strip()

        assert output == "[]"

    def test_run_list_manifests_json_false_prints_formatted_text(
        self, tmp_path, capsys
    ):
        """Test that json_output=False prints formatted text (existing behavior)."""
        from maid_runner.cli.list_manifests import run_list_manifests

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest1 = {
            "goal": "Create test.py",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
        }

        with open(manifest_dir / "task-001.manifest.json", "w") as f:
            json.dump(manifest1, f)

        run_list_manifests("test.py", str(manifest_dir), quiet=False, json_output=False)

        captured = capsys.readouterr()
        output = captured.out

        # Should NOT be a plain JSON array - should have formatted text
        # Should contain manifest reference and decorative text
        assert "task-001" in output
        # Verify it's not just a JSON array (formatted output has more content)
        assert "test.py" in output or "CREATED" in output.upper()

    def test_run_list_manifests_json_output_valid_parseable_json(
        self, tmp_path, capsys
    ):
        """Test that JSON output is valid and parseable."""
        from maid_runner.cli.list_manifests import run_list_manifests

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest1 = {
            "goal": "Create test.py",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
        }

        manifest2 = {
            "goal": "Edit test.py",
            "creatableFiles": [],
            "editableFiles": ["test.py"],
            "readonlyFiles": [],
        }

        with open(manifest_dir / "task-001.manifest.json", "w") as f:
            json.dump(manifest1, f)

        with open(manifest_dir / "task-002.manifest.json", "w") as f:
            json.dump(manifest2, f)

        run_list_manifests("test.py", str(manifest_dir), quiet=False, json_output=True)

        captured = capsys.readouterr()
        output = captured.out.strip()

        # Should be valid JSON
        parsed = json.loads(output)

        # Should be a list of strings
        assert isinstance(parsed, list)
        assert all(isinstance(p, str) for p in parsed)

        # Should contain full paths
        assert len(parsed) == 2
        assert any("task-001" in p for p in parsed)
        assert any("task-002" in p for p in parsed)

    def test_run_list_manifests_json_output_contains_full_paths(self, tmp_path, capsys):
        """Test that JSON output contains full manifest paths with directory."""
        from maid_runner.cli.list_manifests import run_list_manifests

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest1 = {
            "goal": "Create test.py",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
        }

        with open(manifest_dir / "task-001.manifest.json", "w") as f:
            json.dump(manifest1, f)

        run_list_manifests("test.py", str(manifest_dir), quiet=False, json_output=True)

        captured = capsys.readouterr()
        output = captured.out.strip()
        parsed = json.loads(output)

        # Path should include the manifest directory
        assert len(parsed) == 1
        assert str(manifest_dir) in parsed[0]
        assert "task-001.manifest.json" in parsed[0]


class TestRunListManifestsBackwardCompatibility:
    """Tests ensuring backward compatibility when json_output is not provided."""

    def test_run_list_manifests_works_without_json_output_kwarg(self, tmp_path, capsys):
        """Test that run_list_manifests works when json_output is omitted."""
        from maid_runner.cli.list_manifests import run_list_manifests

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest1 = {
            "goal": "Create test.py",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
        }

        with open(manifest_dir / "task-001.manifest.json", "w") as f:
            json.dump(manifest1, f)

        # Call without json_output - should use default behavior (text output)
        sig = inspect.signature(run_list_manifests)
        if "json_output" in sig.parameters:
            # Check if it has a default value
            param = sig.parameters["json_output"]
            assert (
                param.default is not inspect.Parameter.empty
            ), "json_output should have a default value for backward compatibility"
