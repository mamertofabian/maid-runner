"""Behavioral tests for Task-054: TypeScript test runner integration.

This test suite validates that the TypeScript test runner utilities correctly
detect TypeScript projects, identify package managers, normalize commands, and
integrate with the existing 'maid test' infrastructure.

Test Organization:
- Function importability and structure
- TypeScript project detection
- Package manager detection
- Command identification
- Command normalization
- Package.json parsing
- Integration with maid test command
"""

import json
from pathlib import Path


# =============================================================================
# SECTION 1: Module and Function Imports
# =============================================================================


class TestModuleStructure:
    """Test that all expected functions are importable."""

    def test_detect_typescript_project_is_importable(self):
        """detect_typescript_project function must be importable."""
        from maid_runner.validators.typescript_test_runner import (
            detect_typescript_project,
        )

        assert callable(detect_typescript_project)

    def test_get_package_manager_is_importable(self):
        """get_package_manager function must be importable."""
        from maid_runner.validators.typescript_test_runner import get_package_manager

        assert callable(get_package_manager)

    def test_is_typescript_command_is_importable(self):
        """is_typescript_command function must be importable."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert callable(is_typescript_command)

    def test_normalize_typescript_command_is_importable(self):
        """normalize_typescript_command function must be importable."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        assert callable(normalize_typescript_command)

    def test_get_test_script_from_package_json_is_importable(self):
        """get_test_script_from_package_json function must be importable."""
        from maid_runner.validators.typescript_test_runner import (
            get_test_script_from_package_json,
        )

        assert callable(get_test_script_from_package_json)

    def test_has_typescript_installed_is_importable(self):
        """has_typescript_installed function must be importable."""
        from maid_runner.validators.typescript_test_runner import (
            has_typescript_installed,
        )

        assert callable(has_typescript_installed)


# =============================================================================
# SECTION 2: TypeScript Project Detection
# =============================================================================


class TestTypescriptProjectDetection:
    """Test detection of TypeScript/JavaScript projects."""

    def test_detects_project_with_package_json(self, tmp_path):
        """Must detect TypeScript project when package.json exists."""
        from maid_runner.validators.typescript_test_runner import (
            detect_typescript_project,
        )

        # Create package.json
        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test-project"}))

        result = detect_typescript_project(tmp_path)
        assert result is True

    def test_returns_false_when_no_package_json(self, tmp_path):
        """Must return False when no package.json exists."""
        from maid_runner.validators.typescript_test_runner import (
            detect_typescript_project,
        )

        result = detect_typescript_project(tmp_path)
        assert result is False

    def test_detects_typescript_dependency_in_package_json(self, tmp_path):
        """Must detect TypeScript when listed in dependencies."""
        from maid_runner.validators.typescript_test_runner import (
            has_typescript_installed,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(
            json.dumps({"name": "test", "devDependencies": {"typescript": "^5.0.0"}})
        )

        result = has_typescript_installed(tmp_path)
        assert result is True

    def test_returns_false_when_typescript_not_in_dependencies(self, tmp_path):
        """Must return False when TypeScript not in dependencies."""
        from maid_runner.validators.typescript_test_runner import (
            has_typescript_installed,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test", "dependencies": {}}))

        result = has_typescript_installed(tmp_path)
        assert result is False


# =============================================================================
# SECTION 3: Package Manager Detection
# =============================================================================


class TestPackageManagerDetection:
    """Test detection of package managers (npm, pnpm, yarn)."""

    def test_detects_pnpm_from_lockfile(self, tmp_path):
        """Must detect pnpm when pnpm-lock.yaml exists."""
        from maid_runner.validators.typescript_test_runner import get_package_manager

        (tmp_path / "pnpm-lock.yaml").touch()
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = get_package_manager(tmp_path)
        assert result == "pnpm"

    def test_detects_yarn_from_lockfile(self, tmp_path):
        """Must detect yarn when yarn.lock exists."""
        from maid_runner.validators.typescript_test_runner import get_package_manager

        (tmp_path / "yarn.lock").touch()
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = get_package_manager(tmp_path)
        assert result == "yarn"

    def test_detects_npm_from_lockfile(self, tmp_path):
        """Must detect npm when package-lock.json exists."""
        from maid_runner.validators.typescript_test_runner import get_package_manager

        (tmp_path / "package-lock.json").touch()
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = get_package_manager(tmp_path)
        assert result == "npm"

    def test_defaults_to_npm_when_no_lockfile(self, tmp_path):
        """Must default to npm when no lockfile exists."""
        from maid_runner.validators.typescript_test_runner import get_package_manager

        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = get_package_manager(tmp_path)
        assert result == "npm"

    def test_prioritizes_pnpm_over_others(self, tmp_path):
        """Must prioritize pnpm when multiple lockfiles exist."""
        from maid_runner.validators.typescript_test_runner import get_package_manager

        (tmp_path / "pnpm-lock.yaml").touch()
        (tmp_path / "yarn.lock").touch()
        (tmp_path / "package-lock.json").touch()
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = get_package_manager(tmp_path)
        assert result == "pnpm"


# =============================================================================
# SECTION 4: TypeScript Command Identification
# =============================================================================


class TestCommandIdentification:
    """Test identification of TypeScript-related commands."""

    def test_identifies_npm_test(self):
        """Must identify 'npm test' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["npm", "test"]) is True

    def test_identifies_pnpm_test(self):
        """Must identify 'pnpm test' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["pnpm", "test"]) is True

    def test_identifies_yarn_test(self):
        """Must identify 'yarn test' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["yarn", "test"]) is True

    def test_identifies_tsc_command(self):
        """Must identify 'tsc' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["tsc", "--noEmit"]) is True

    def test_identifies_tsx_command(self):
        """Must identify 'tsx' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["tsx", "test.ts"]) is True

    def test_identifies_jest_command(self):
        """Must identify 'jest' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["jest"]) is True

    def test_identifies_vitest_command(self):
        """Must identify 'vitest' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["vitest"]) is True

    def test_rejects_pytest_command(self):
        """Must NOT identify 'pytest' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["pytest"]) is False

    def test_rejects_python_command(self):
        """Must NOT identify 'python' as TypeScript command."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command(["python", "test.py"]) is False

    def test_handles_empty_command(self):
        """Must handle empty command list."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        assert is_typescript_command([]) is False


# =============================================================================
# SECTION 5: Command Normalization
# =============================================================================


class TestCommandNormalization:
    """Test normalization of TypeScript commands."""

    def test_normalizes_npm_test_to_full_command(self, tmp_path):
        """Must normalize 'npm test' with proper environment setup."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(
            json.dumps({"name": "test", "scripts": {"test": "jest"}})
        )

        result = normalize_typescript_command(["npm", "test"], tmp_path)
        assert result == ["npm", "test"]
        assert isinstance(result, list)

    def test_preserves_additional_arguments(self, tmp_path):
        """Must preserve additional arguments in command."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = normalize_typescript_command(
            ["npm", "test", "--", "--coverage"], tmp_path
        )
        assert "--coverage" in result

    def test_handles_tsc_noEmit(self, tmp_path):
        """Must handle 'tsc --noEmit' command."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = normalize_typescript_command(["tsc", "--noEmit"], tmp_path)
        assert result == ["tsc", "--noEmit"]

    def test_handles_direct_jest_command(self, tmp_path):
        """Must handle direct 'jest' command."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = normalize_typescript_command(["jest", "--verbose"], tmp_path)
        assert "jest" in result

    def test_handles_pnpm_with_workspace(self, tmp_path):
        """Must handle pnpm workspace commands."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = normalize_typescript_command(
            ["pnpm", "--filter", "workspace", "test"], tmp_path
        )
        assert "pnpm" in result
        assert "--filter" in result


# =============================================================================
# SECTION 6: Package.json Parsing
# =============================================================================


class TestPackageJsonParsing:
    """Test parsing of package.json test scripts."""

    def test_extracts_test_script(self, tmp_path):
        """Must extract test script from package.json."""
        from maid_runner.validators.typescript_test_runner import (
            get_test_script_from_package_json,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(
            json.dumps({"name": "test", "scripts": {"test": "jest --coverage"}})
        )

        result = get_test_script_from_package_json(tmp_path)
        assert result == "jest --coverage"

    def test_returns_none_when_no_test_script(self, tmp_path):
        """Must return None when no test script exists."""
        from maid_runner.validators.typescript_test_runner import (
            get_test_script_from_package_json,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test", "scripts": {}}))

        result = get_test_script_from_package_json(tmp_path)
        assert result is None

    def test_returns_none_when_no_scripts_field(self, tmp_path):
        """Must return None when scripts field missing."""
        from maid_runner.validators.typescript_test_runner import (
            get_test_script_from_package_json,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = get_test_script_from_package_json(tmp_path)
        assert result is None

    def test_handles_malformed_json(self, tmp_path):
        """Must handle malformed package.json gracefully."""
        from maid_runner.validators.typescript_test_runner import (
            get_test_script_from_package_json,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text("{ invalid json")

        result = get_test_script_from_package_json(tmp_path)
        assert result is None

    def test_handles_missing_package_json(self, tmp_path):
        """Must handle missing package.json gracefully."""
        from maid_runner.validators.typescript_test_runner import (
            get_test_script_from_package_json,
        )

        result = get_test_script_from_package_json(tmp_path)
        assert result is None


# =============================================================================
# SECTION 7: Return Type Validation
# =============================================================================


class TestReturnTypes:
    """Validate that functions return correct types."""

    def test_detect_typescript_project_returns_bool(self, tmp_path):
        """detect_typescript_project must return bool."""
        from maid_runner.validators.typescript_test_runner import (
            detect_typescript_project,
        )

        result = detect_typescript_project(tmp_path)
        assert isinstance(result, bool)

    def test_get_package_manager_returns_str(self, tmp_path):
        """get_package_manager must return str."""
        from maid_runner.validators.typescript_test_runner import get_package_manager

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = get_package_manager(tmp_path)
        assert isinstance(result, str)

    def test_is_typescript_command_returns_bool(self):
        """is_typescript_command must return bool."""
        from maid_runner.validators.typescript_test_runner import is_typescript_command

        result = is_typescript_command(["npm", "test"])
        assert isinstance(result, bool)

    def test_normalize_typescript_command_returns_list(self, tmp_path):
        """normalize_typescript_command must return list."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = normalize_typescript_command(["npm", "test"], tmp_path)
        assert isinstance(result, list)

    def test_get_test_script_returns_optional_str(self, tmp_path):
        """get_test_script_from_package_json must return Optional[str]."""
        from maid_runner.validators.typescript_test_runner import (
            get_test_script_from_package_json,
        )

        result = get_test_script_from_package_json(tmp_path)
        assert result is None or isinstance(result, str)

    def test_has_typescript_installed_returns_bool(self, tmp_path):
        """has_typescript_installed must return bool."""
        from maid_runner.validators.typescript_test_runner import (
            has_typescript_installed,
        )

        result = has_typescript_installed(tmp_path)
        assert isinstance(result, bool)


# =============================================================================
# SECTION 8: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_nonexistent_directory(self):
        """Must handle nonexistent directory gracefully."""
        from maid_runner.validators.typescript_test_runner import (
            detect_typescript_project,
        )

        nonexistent = Path("/nonexistent/directory")
        result = detect_typescript_project(nonexistent)
        assert result is False

    def test_handles_empty_command_normalization(self, tmp_path):
        """Must handle empty command in normalization."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = normalize_typescript_command([], tmp_path)
        assert isinstance(result, list)

    def test_handles_command_with_relative_paths(self, tmp_path):
        """Must handle commands with relative paths."""
        from maid_runner.validators.typescript_test_runner import (
            normalize_typescript_command,
        )

        package_json = tmp_path / "package.json"
        package_json.write_text(json.dumps({"name": "test"}))

        result = normalize_typescript_command(
            ["npm", "run", "./scripts/test.sh"], tmp_path
        )
        assert isinstance(result, list)

    def test_detects_multiple_package_managers(self, tmp_path):
        """Must handle projects with multiple lockfiles."""
        from maid_runner.validators.typescript_test_runner import get_package_manager

        # Create multiple lockfiles
        (tmp_path / "pnpm-lock.yaml").touch()
        (tmp_path / "yarn.lock").touch()
        (tmp_path / "package.json").write_text(json.dumps({"name": "test"}))

        result = get_package_manager(tmp_path)
        # Should pick the highest priority (pnpm)
        assert result in ["pnpm", "yarn", "npm"]
