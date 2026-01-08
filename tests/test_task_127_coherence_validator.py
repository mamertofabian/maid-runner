"""Behavioral tests for Task 127: CoherenceValidator class.

Tests the main orchestration class for architectural coherence validation.
The CoherenceValidator loads system context (system snapshot and knowledge graph),
runs coherence checks, and returns a CoherenceResult with any issues found.

Artifacts tested:
- CoherenceValidator: Main class for coherence validation orchestration
- __init__(self, manifest_dir: Path): Initialize with manifest directory
- validate(self, manifest_path: Path) -> CoherenceResult: Main validation entry point
- _load_system_context(self): Build system snapshot and knowledge graph
- _run_checks(self, manifest_data: dict) -> List[CoherenceIssue]: Execute all validation checks
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List

from maid_runner.coherence.validator import CoherenceValidator
from maid_runner.coherence.result import (
    CoherenceResult,
    CoherenceIssue,
)


@pytest.fixture
def manifest_dir(tmp_path: Path) -> Path:
    """Create a temporary manifest directory with sample manifests."""
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    return manifests


@pytest.fixture
def sample_manifest_data() -> Dict[str, Any]:
    """Create a sample manifest data dictionary."""
    return {
        "version": "1",
        "goal": "Create utility module",
        "taskType": "create",
        "creatableFiles": ["src/utils.py"],
        "editableFiles": [],
        "readonlyFiles": ["src/config.py"],
        "expectedArtifacts": {
            "file": "src/utils.py",
            "contains": [
                {"type": "function", "name": "helper_function"},
                {"type": "class", "name": "HelperClass"},
            ],
        },
        "validationCommand": ["pytest", "tests/test_utils.py", "-v"],
    }


@pytest.fixture
def manifest_file(manifest_dir: Path, sample_manifest_data: Dict[str, Any]) -> Path:
    """Create a manifest file in the test directory."""
    manifest_path = manifest_dir / "task-001.manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(sample_manifest_data, f)
    return manifest_path


@pytest.fixture
def multiple_manifests(manifest_dir: Path) -> List[Path]:
    """Create multiple manifest files in the test directory."""
    manifests = []

    manifest_1 = {
        "version": "1",
        "goal": "Create module A",
        "taskType": "create",
        "creatableFiles": ["src/module_a.py"],
        "expectedArtifacts": {
            "file": "src/module_a.py",
            "contains": [{"type": "function", "name": "func_a"}],
        },
    }
    path_1 = manifest_dir / "task-001.manifest.json"
    with open(path_1, "w") as f:
        json.dump(manifest_1, f)
    manifests.append(path_1)

    manifest_2 = {
        "version": "1",
        "goal": "Create module B",
        "taskType": "create",
        "creatableFiles": ["src/module_b.py"],
        "expectedArtifacts": {
            "file": "src/module_b.py",
            "contains": [{"type": "class", "name": "ClassB"}],
        },
    }
    path_2 = manifest_dir / "task-002.manifest.json"
    with open(path_2, "w") as f:
        json.dump(manifest_2, f)
    manifests.append(path_2)

    return manifests


def create_manifest_file(
    manifest_dir: Path, filename: str, data: Dict[str, Any]
) -> Path:
    """Helper to create a manifest file in the test directory."""
    manifest_path = manifest_dir / filename
    with open(manifest_path, "w") as f:
        json.dump(data, f)
    return manifest_path


class TestCoherenceValidatorClass:
    """Tests for CoherenceValidator class instantiation."""

    def test_class_can_be_instantiated(self, manifest_dir: Path) -> None:
        """CoherenceValidator can be instantiated with a manifest_dir Path."""
        validator = CoherenceValidator(manifest_dir)

        assert validator is not None
        assert isinstance(validator, CoherenceValidator)

    def test_accepts_path_object(self, manifest_dir: Path) -> None:
        """Constructor accepts Path object for manifest_dir."""
        validator = CoherenceValidator(manifest_dir)

        assert hasattr(validator, "manifest_dir")

    def test_stores_manifest_dir_attribute(self, manifest_dir: Path) -> None:
        """Constructor stores manifest_dir as an attribute."""
        validator = CoherenceValidator(manifest_dir)

        assert validator.manifest_dir == manifest_dir


class TestCoherenceValidatorInit:
    """Tests for CoherenceValidator.__init__ method."""

    def test_init_with_valid_path(self, manifest_dir: Path) -> None:
        """__init__ accepts a valid Path to manifests directory."""
        validator = CoherenceValidator(manifest_dir=manifest_dir)

        assert validator.manifest_dir == manifest_dir

    def test_init_stores_path_as_attribute(self, tmp_path: Path) -> None:
        """__init__ stores the provided path as manifest_dir attribute."""
        custom_dir = tmp_path / "custom_manifests"
        custom_dir.mkdir()

        validator = CoherenceValidator(manifest_dir=custom_dir)

        assert validator.manifest_dir == custom_dir

    def test_init_explicitly_called(self, manifest_dir: Path) -> None:
        """__init__ can be called explicitly on an existing instance."""
        validator = CoherenceValidator(manifest_dir)
        original_dir = validator.manifest_dir

        validator.__init__(manifest_dir=manifest_dir)

        assert validator.manifest_dir == original_dir

    def test_init_with_different_path(self, tmp_path: Path) -> None:
        """__init__ can reinitialize with a different manifest_dir."""
        dir1 = tmp_path / "manifests1"
        dir1.mkdir()
        dir2 = tmp_path / "manifests2"
        dir2.mkdir()

        validator = CoherenceValidator(manifest_dir=dir1)
        assert validator.manifest_dir == dir1

        validator.__init__(manifest_dir=dir2)

        assert validator.manifest_dir == dir2


class TestCoherenceValidatorValidate:
    """Tests for CoherenceValidator.validate method."""

    def test_validate_returns_coherence_result(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """validate() returns a CoherenceResult instance."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_file)

        assert isinstance(result, CoherenceResult)

    def test_validate_accepts_path_parameter(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """validate() accepts a manifest_path Path parameter."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_path=manifest_file)

        assert isinstance(result, CoherenceResult)

    def test_validate_with_valid_manifest_returns_result(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """validate() with valid manifest returns a CoherenceResult with valid field."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_file)

        assert hasattr(result, "valid")
        assert isinstance(result.valid, bool)

    def test_validate_result_has_issues_list(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """validate() result has an issues list."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_file)

        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)

    def test_validate_with_empty_manifest_dir_still_works(self, tmp_path: Path) -> None:
        """validate() works even with empty manifest directory."""
        empty_dir = tmp_path / "empty_manifests"
        empty_dir.mkdir()
        manifest_data = {
            "version": "1",
            "goal": "Test manifest",
            "taskType": "create",
            "creatableFiles": ["test.py"],
        }
        manifest_path = empty_dir / "task-001.manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        validator = CoherenceValidator(empty_dir)
        result = validator.validate(manifest_path)

        assert isinstance(result, CoherenceResult)

    def test_validate_loads_manifest_data(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """validate() loads and processes the manifest data."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_file)

        # The result should exist - specific checks will run once implemented
        assert result is not None
        assert isinstance(result, CoherenceResult)

    def test_validate_with_multiple_manifests_in_dir(
        self, manifest_dir: Path, multiple_manifests: List[Path]
    ) -> None:
        """validate() works when manifest_dir contains multiple manifests."""
        validator = CoherenceValidator(manifest_dir)

        # Validate the first manifest
        result = validator.validate(multiple_manifests[0])

        assert isinstance(result, CoherenceResult)

    def test_validate_result_issues_are_coherence_issues(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """validate() result issues are CoherenceIssue instances (when present)."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_file)

        # All items in issues list should be CoherenceIssue instances
        for issue in result.issues:
            assert isinstance(issue, CoherenceIssue)


class TestCoherenceValidatorLoadSystemContext:
    """Tests for CoherenceValidator._load_system_context method."""

    def test_load_system_context_exists(self, manifest_dir: Path) -> None:
        """_load_system_context method exists on CoherenceValidator."""
        validator = CoherenceValidator(manifest_dir)

        assert hasattr(validator, "_load_system_context")
        assert callable(validator._load_system_context)

    def test_load_system_context_can_be_called(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """_load_system_context can be called without error."""
        validator = CoherenceValidator(manifest_dir)

        # Should not raise an exception
        validator._load_system_context()

    def test_load_system_context_with_empty_dir(self, tmp_path: Path) -> None:
        """_load_system_context works with empty manifest directory."""
        empty_dir = tmp_path / "empty_manifests"
        empty_dir.mkdir()

        validator = CoherenceValidator(empty_dir)

        # Should not raise an exception
        validator._load_system_context()

    def test_load_system_context_with_manifests(
        self, manifest_dir: Path, multiple_manifests: List[Path]
    ) -> None:
        """_load_system_context loads context when manifests exist."""
        validator = CoherenceValidator(manifest_dir)

        # Should not raise an exception
        validator._load_system_context()


class TestCoherenceValidatorRunChecks:
    """Tests for CoherenceValidator._run_checks method."""

    def test_run_checks_exists(self, manifest_dir: Path) -> None:
        """_run_checks method exists on CoherenceValidator."""
        validator = CoherenceValidator(manifest_dir)

        assert hasattr(validator, "_run_checks")
        assert callable(validator._run_checks)

    def test_run_checks_returns_list(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_run_checks returns a list."""
        validator = CoherenceValidator(manifest_dir)
        # Load system context first (required before running checks)
        validator._load_system_context()

        result = validator._run_checks(manifest_data=sample_manifest_data)

        assert isinstance(result, list)

    def test_run_checks_accepts_manifest_data_dict(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_run_checks accepts a manifest_data dict parameter."""
        validator = CoherenceValidator(manifest_dir)
        validator._load_system_context()

        result = validator._run_checks(manifest_data=sample_manifest_data)

        assert isinstance(result, list)

    def test_run_checks_returns_list_of_coherence_issues(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_run_checks returns a list of CoherenceIssue instances (when issues exist)."""
        validator = CoherenceValidator(manifest_dir)
        validator._load_system_context()

        result = validator._run_checks(manifest_data=sample_manifest_data)

        # All items in the list should be CoherenceIssue instances
        for item in result:
            assert isinstance(item, CoherenceIssue)

    def test_run_checks_with_empty_manifest(self, manifest_dir: Path) -> None:
        """_run_checks handles minimal manifest data."""
        validator = CoherenceValidator(manifest_dir)
        validator._load_system_context()
        minimal_manifest = {
            "version": "1",
            "goal": "Minimal manifest",
            "taskType": "create",
        }

        result = validator._run_checks(manifest_data=minimal_manifest)

        assert isinstance(result, list)

    def test_run_checks_with_full_manifest(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_run_checks handles full manifest data with all fields."""
        validator = CoherenceValidator(manifest_dir)
        validator._load_system_context()

        result = validator._run_checks(manifest_data=sample_manifest_data)

        assert isinstance(result, list)


class TestCoherenceValidatorIntegration:
    """Integration tests for CoherenceValidator."""

    def test_full_workflow_single_manifest(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """Test complete validation workflow with single manifest."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_file)

        assert isinstance(result, CoherenceResult)
        assert hasattr(result, "valid")
        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)

    def test_full_workflow_multiple_manifests(
        self, manifest_dir: Path, multiple_manifests: List[Path]
    ) -> None:
        """Test validation with multiple manifests in directory."""
        validator = CoherenceValidator(manifest_dir)

        # Validate each manifest
        for manifest_path in multiple_manifests:
            result = validator.validate(manifest_path)

            assert isinstance(result, CoherenceResult)
            assert isinstance(result.issues, list)

    def test_validate_calls_load_system_context(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """validate() invokes _load_system_context as part of its workflow."""
        validator = CoherenceValidator(manifest_dir)

        # This should work without manually calling _load_system_context
        result = validator.validate(manifest_file)

        assert isinstance(result, CoherenceResult)

    def test_validate_calls_run_checks(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """validate() invokes _run_checks as part of its workflow."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_file)

        # Result should contain issues list from _run_checks
        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)

    def test_coherence_result_properties_work(
        self, manifest_dir: Path, manifest_file: Path
    ) -> None:
        """CoherenceResult errors and warnings properties work correctly."""
        validator = CoherenceValidator(manifest_dir)

        result = validator.validate(manifest_file)

        # These properties should be accessible
        assert isinstance(result.errors, int)
        assert isinstance(result.warnings, int)
        assert result.errors >= 0
        assert result.warnings >= 0

    def test_validator_reusable_for_multiple_validations(
        self, manifest_dir: Path, multiple_manifests: List[Path]
    ) -> None:
        """Same validator instance can be used for multiple validations."""
        validator = CoherenceValidator(manifest_dir)

        results = []
        for manifest_path in multiple_manifests:
            result = validator.validate(manifest_path)
            results.append(result)

        assert len(results) == len(multiple_manifests)
        for result in results:
            assert isinstance(result, CoherenceResult)
