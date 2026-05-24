"""Tests for maid_runner.core.validate - ValidationEngine.

Golden test cases from 15-golden-tests.md sections 6 and 7.
"""

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import (
    ValidationEngine,
    validate,
    validate_all,
)

# Historical active manifests still read this legacy file for these method
# references. Executable assertions live in tests/core/validation/test_validate_api.py.
_VALIDATION_ENGINE_PUBLIC_METHODS = (
    ValidationEngine.validate,
    ValidationEngine.validate_behavioral,
    ValidationEngine.validate_acceptance,
    ValidationEngine.validate_implementation,
)
_LEGACY_MANIFEST_REFERENCE_ANCHORS = (
    ManifestChain,
    ValidationEngine.run_file_tracking,
    validate,
    validate_all,
    ErrorCode.STUB_FUNCTION_DETECTED,
    ErrorCode.MISSING_REQUIRED_IMPORT,
    ErrorCode.VALIDATOR_NOT_AVAILABLE,
)


@pytest.fixture()
def project(tmp_path):
    """Create a temporary project directory."""
    src = tmp_path / "src"
    src.mkdir()
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    return tmp_path


def _write_manifest(manifests_dir, name, content):
    path = manifests_dir / name
    path.write_text(content)
    return path


def _write_source(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _commit_all(project_dir):
    import subprocess

    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", "."], cwd=project_dir, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            "baseline",
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )


def _add_test_file(project_dir, test_rel_path, source_module, artifact_names):
    """Write a minimal test file that references the given artifacts.

    Returns the test_rel_path for inclusion in manifest YAML.
    """
    public_names = [n for n in artifact_names if not n.startswith("_")]
    if not public_names:
        public_names = artifact_names
    imports = ", ".join(public_names)
    tests = "\n".join(
        f"def test_{n}():\n    assert {n} is not None\n" for n in public_names
    )
    content = f"from {source_module} import {imports}\n\n{tests}\n"
    _write_source(project_dir, test_rel_path, content)
    return test_rel_path


class TestStubDetection:
    """Tests for check_stubs=True detecting hollow implementations."""


class TestImplementationTestCoverage:
    """Test that implementation mode enforces test coverage.

    Manifests with public artifacts MUST have test files.
    Artifacts not referenced in tests produce warnings.
    """

    def test_implementation_fails_when_public_artifact_not_referenced_in_tests(
        self, project
    ):
        """Public artifact not referenced in any test -> E200 error."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(
            project,
            "src/widget.py",
            "def render():\n    pass\n\ndef update():\n    pass\n",
        )
        # Test only references 'render', not 'update'
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import render\n\ndef test_render():\n    render()\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        assert result.success is False
        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert len(untested) == 1
        assert "update" in untested[0].message
        assert untested[0].severity.value == "error"

    def test_python_import_only_reference_does_not_satisfy_coverage(self, project):
        """Import declarations alone are not behavioral coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def test_widget_placeholder():\n"
            "    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_shadowed_import_reference_does_not_satisfy_coverage(self, project):
        """A local test helper with the same name as an import is not coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def test_widget_shadow():\n"
            "    def update():\n"
            "        return 'local'\n"
            "    assert update() == 'local'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_shadowed_import_before_later_import_does_not_cover_artifact(
        self, project
    ):
        """Shadow detection is not dependent on source order of imports."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "def test_widget_shadow():\n"
            "    def update():\n"
            "        return 'local'\n"
            "    assert update() == 'local'\n\n"
            "from src.widget import update\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_module_rebinding_after_import_does_not_cover_artifact(
        self, project
    ):
        """A module-level local rebinding after import is not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_alias_placeholder_import_does_not_cover_local_artifact(
        self, project
    ):
        """Importing the artifact under an alias does not cover a local namesake."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update as real_update\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_module_placeholder_import_does_not_cover_local_artifact(
        self, project
    ):
        """Importing the artifact module under an alias is not local coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "import src.widget as widget_module\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_shadow():\n"
            "    assert update() == 'local'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_function_local_import_still_covers_after_module_shadow(
        self, project
    ):
        """A real function-local import keeps identity despite module rebinding."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def update():\n"
            "    return 'local'\n\n"
            "def test_widget_imports_real_update():\n"
            "    from src.widget import update\n"
            "    assert update() == 'updated'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True
        assert untested == []

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n\n"
                "def test_widget_lambda_shadow():\n"
                "    assert (lambda update: update())(lambda: 'local') == 'local'\n",
                "lambda parameter",
            ),
            (
                "from src.widget import update\n\n"
                "def test_widget_comprehension_shadow():\n"
                "    values = [update() for update in [lambda: 'local']]\n"
                "    assert values == ['local']\n",
                "comprehension target",
            ),
        ],
    )
    def test_python_expression_scope_shadowed_import_does_not_cover_artifact(
        self, project, source, scenario
    ):
        """Lambda and comprehension-local names are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n\n"
                "def test_widget_walrus_shadow():\n"
                "    assert (update := (lambda: 'local'))() == 'local'\n",
                "walrus binding",
            ),
            (
                "from src.widget import update\n\n"
                "def test_widget_match_shadow():\n"
                "    match (lambda: 'local'):\n"
                "        case update:\n"
                "            assert update() == 'local'\n",
                "match capture",
            ),
        ],
    )
    def test_python_binding_expression_shadowed_import_does_not_cover_artifact(
        self, project, source, scenario
    ):
        """Walrus and match bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_annotation_only_reference_does_not_cover_artifact(self, project):
        """Python type annotations are not behavioral runtime coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def test_widget_annotation_only(value: update = None) -> update:\n"
            "    assert value is None\n"
            "    return None\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_keyword_argument_does_not_cover_same_module_artifact(self, project):
        """A keyword name passed to one function does not cover another artifact."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: render
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(
            project,
            "src/widget.py",
            "def render(**kwargs):\n    return kwargs\n\n"
            "def update():\n    return 'updated'\n",
        )
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import render\n\n"
            "def test_widget_render_flag():\n"
            "    assert render(update=True) == {'update': True}\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n\n"
                "def test_widget_starred_assignment_shadow():\n"
                "    *update, = [lambda: 'local']\n"
                "    assert update[0]() == 'local'\n",
                "starred assignment",
            ),
            (
                "from src.widget import update\n\n"
                "def test_widget_starred_for_shadow():\n"
                "    for *update, in [[lambda: 'local']]:\n"
                "        assert update[0]() == 'local'\n",
                "starred for target",
            ),
        ],
    )
    def test_python_starred_shadowed_import_does_not_cover_artifact(
        self, project, source, scenario
    ):
        """Starred Python target bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_late_function_local_import_does_not_cover_artifact(self, project):
        """A later local import shadows earlier same-name calls in a function."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "src/other.py", "def update():\n    return 'other'\n")
        _write_source(
            project,
            "tests/test_widget.py",
            "from src.widget import update\n\n"
            "def test_widget_late_local_import_shadow():\n"
            "    update()\n"
            "    from src.other import update\n"
            "    assert update() == 'other'\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n\n"
                "class TestWidget:\n"
                "    update = staticmethod(lambda: 'local')\n\n"
                "    def test_local_class_attribute(self):\n"
                "        assert self.update() == 'local'\n",
                "class attribute assignment",
            ),
            (
                "from src.widget import update\n\n"
                "del update\n\n"
                "def test_delete_placeholder():\n"
                "    assert True\n",
                "delete target",
            ),
        ],
    )
    def test_python_store_and_delete_references_do_not_cover_artifact(
        self, project, source, scenario
    ):
        """Store and delete targets are not behavioral access coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_python_shadowed_constructor_keyword_does_not_cover_attribute(
        self, project
    ):
        """A keyword on a shadowed local callable does not cover an attribute."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-settings.manifest.yaml",
            """schema: "2"
goal: "Add settings"
files:
  edit:
    - path: src/settings.py
      artifacts:
        - kind: class
          name: Settings
        - kind: attribute
          name: timeout
          of: Settings
  read:
    - tests/test_settings.py
validate:
  - pytest tests/test_settings.py -v
""",
        )
        _write_source(
            project,
            "src/settings.py",
            "class Settings:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n",
        )
        _write_source(
            project,
            "tests/test_settings.py",
            "from src.settings import Settings as RealSettings\n\n"
            "def test_settings_shadowed_keyword():\n"
            "    assert RealSettings is not None\n"
            "    def Settings(**kwargs):\n"
            "        return kwargs\n"
            "    assert Settings(timeout=5) == {'timeout': 5}\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "timeout" in untested[0].message

    def test_python_constructor_keyword_covers_owned_attribute(self, project):
        """A keyword on an imported constructor covers that class's attribute."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-settings.manifest.yaml",
            """schema: "2"
goal: "Add settings"
files:
  edit:
    - path: src/settings.py
      artifacts:
        - kind: class
          name: Settings
        - kind: attribute
          name: timeout
          of: Settings
  read:
    - tests/test_settings.py
validate:
  - pytest tests/test_settings.py -v
""",
        )
        _write_source(
            project,
            "src/settings.py",
            "class Settings:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n",
        )
        _write_source(
            project,
            "tests/test_settings.py",
            "from src.settings import Settings\n\n"
            "def test_settings_timeout_keyword():\n"
            "    settings = Settings(timeout=5)\n"
            "    assert settings.timeout == 5\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True
        assert untested == []

    def test_python_unrelated_imported_callable_keyword_does_not_cover_attribute(
        self, project
    ):
        """A keyword on an unrelated imported callable does not cover an attribute."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-settings.manifest.yaml",
            """schema: "2"
goal: "Add settings"
files:
  edit:
    - path: src/settings.py
      artifacts:
        - kind: class
          name: Settings
        - kind: attribute
          name: timeout
          of: Settings
  read:
    - tests/test_settings.py
validate:
  - pytest tests/test_settings.py -v
""",
        )
        _write_source(
            project,
            "src/settings.py",
            "class Settings:\n"
            "    def __init__(self, timeout):\n"
            "        self.timeout = timeout\n\n"
            "def render(**kwargs):\n"
            "    return kwargs\n",
        )
        _write_source(
            project,
            "tests/test_settings.py",
            "from src.settings import Settings, render\n\n"
            "def test_settings_unrelated_keyword():\n"
            "    assert Settings is not None\n"
            "    assert render(timeout=5) == {'timeout': 5}\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "timeout" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "from src.widget import update\n"
                "import pytest\n\n"
                "@pytest.mark.parametrize('value', [update()])\n"
                "def test_widget_decorator(value):\n"
                "    assert value == 'updated'\n",
                "decorator",
            ),
            (
                "from src.widget import update\n\n"
                "def test_widget_default(value=update()):\n"
                "    assert value == 'updated'\n",
                "default value",
            ),
        ],
    )
    def test_python_runtime_definition_references_cover_artifact(
        self, project, source, scenario
    ):
        """Runtime decorators and default values are behavioral coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.py
      artifacts:
        - kind: function
          name: update
  read:
    - tests/test_widget.py
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(project, "src/widget.py", "def update():\n    return 'updated'\n")
        _write_source(project, "tests/test_widget.py", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True, scenario
        assert untested == []

    def test_typescript_import_only_reference_does_not_satisfy_coverage(self, project):
        """TypeScript import declarations alone are not behavioral coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update } from '../src/widget';\n\n"
            "it('placeholder', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_shadowed_import_reference_does_not_satisfy_coverage(
        self, project
    ):
        """A local TypeScript binding with the same name as an import is not coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update } from '../src/widget';\n\n"
            "it('shadows update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update in a for loop', () => {\n"
                "  for (const update of [() => 'local']) {\n"
                "    expect(update()).toBe('local');\n"
                "  }\n"
                "});\n",
                "for loop binding",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update in a catch clause', () => {\n"
                "  try {\n"
                "    throw () => 'local';\n"
                "  } catch (update) {\n"
                "    expect(update()).toBe('local');\n"
                "  }\n"
                "});\n",
                "catch clause binding",
            ),
        ],
    )
    def test_typescript_control_flow_shadowed_import_does_not_satisfy_coverage(
        self, project, source, scenario
    ):
        """Control-flow scoped TypeScript bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update as an arrow parameter', update => {\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "single arrow parameter",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update with nested var', () => {\n"
                "  { var update = () => 'local'; }\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "nested var binding",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update with for-var', () => {\n"
                "  for (var update of [() => 'local']) {}\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "for-var binding",
            ),
        ],
    )
    def test_typescript_function_scope_shadowed_import_does_not_satisfy_coverage(
        self, project, source, scenario
    ):
        """Function-scoped TypeScript bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_switch_case_shadowed_import_does_not_satisfy_coverage(
        self, project
    ):
        """Switch-case lexical bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update } from '../src/widget';\n\n"
            "it('shadows update in a switch case', () => {\n"
            "  switch ('local') {\n"
            "    case 'local':\n"
            "      const update = () => 'local';\n"
            "      expect(update()).toBe('local');\n"
            "      break;\n"
            "  }\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update through destructuring', () => {\n"
                "  const helper = { update: () => 'local' };\n"
                "  const { update } = helper;\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "variable destructuring",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update through a parameter', ({ update }) => {\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "parameter destructuring",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update through a for header', () => {\n"
                "  for (const { update } of [{ update: () => 'local' }]) {\n"
                "    expect(update()).toBe('local');\n"
                "  }\n"
                "});\n",
                "for destructuring",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "it('shadows update through a catch binding', () => {\n"
                "  try {\n"
                "    throw { update: () => 'local' };\n"
                "  } catch ({ update }) {\n"
                "    expect(update()).toBe('local');\n"
                "  }\n"
                "});\n",
                "catch destructuring",
            ),
        ],
    )
    def test_typescript_destructuring_shadowed_import_does_not_satisfy_coverage(
        self, project, source, scenario
    ):
        """Destructured TypeScript bindings are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_type_only_reference_does_not_satisfy_coverage(self, project):
        """Type-only TypeScript references are not runtime coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import type { update } from '../src/widget';\n\n"
            "type UpdateType = typeof update;\n\n"
            "it('placeholder', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "interface User { id: string }\n\n"
                "it('uses a local interface only', () => {\n"
                "  expect(true).toBe(true);\n"
                "});\n",
                "local interface",
            ),
            (
                "function identity<User>(value: User): User {\n"
                "  return value;\n"
                "}\n\n"
                "it('uses a local type parameter only', () => {\n"
                "  expect(identity({ id: 'local' })).toEqual({ id: 'local' });\n"
                "});\n",
                "type parameter",
            ),
        ],
    )
    def test_typescript_local_type_bindings_do_not_cover_imported_interface(
        self, project, source, scenario
    ):
        """Local type declarations and parameters are not production coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-user.manifest.yaml",
            """schema: "2"
goal: "Add user"
files:
  edit:
    - path: src/user.ts
      artifacts:
        - kind: interface
          name: User
  read:
    - tests/user.test.ts
validate:
  - pytest tests/user.test.ts -v
""",
        )
        _write_source(
            project,
            "src/user.ts",
            "export interface User {\n  id: string;\n}\n",
        )
        _write_source(project, "tests/user.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False, scenario
        assert len(untested) == 1
        assert "User" in untested[0].message

    @pytest.mark.parametrize(
        ("source", "scenario"),
        [
            (
                "import { update } from '../src/widget';\n\n"
                "type update = () => string;\n\n"
                "it('calls the runtime update', () => {\n"
                "  expect(update()).toBe('updated');\n"
                "});\n",
                "type alias",
            ),
            (
                "import { update } from '../src/widget';\n\n"
                "interface update { value: string }\n\n"
                "it('calls the runtime update', () => {\n"
                "  expect(update()).toBe('updated');\n"
                "});\n",
                "interface",
            ),
        ],
    )
    def test_typescript_type_declarations_do_not_shadow_runtime_import_coverage(
        self, project, source, scenario
    ):
        """Type-only declarations do not shadow same-named runtime imports."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(project, "tests/widget.test.ts", source)

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is True, scenario
        assert untested == []

    def test_typescript_alias_placeholder_import_does_not_cover_local_artifact(
        self, project
    ):
        """Importing a TypeScript artifact under an alias is not local coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update as realUpdate } from '../src/widget';\n\n"
            "it('uses a local update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_namespace_placeholder_import_does_not_cover_local_artifact(
        self, project
    ):
        """Importing the artifact namespace is not local binding coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import * as widget from '../src/widget';\n\n"
            "it('uses a local update', () => {\n"
            "  const update = () => 'local';\n"
            "  expect(update()).toBe('local');\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_typescript_test_label_does_not_satisfy_artifact_coverage(self, project):
        """A test label matching an artifact name is not behavioral coverage."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-widget.manifest.yaml",
            """schema: "2"
goal: "Add widget"
files:
  edit:
    - path: src/widget.ts
      artifacts:
        - kind: function
          name: update
  read:
    - tests/widget.test.ts
validate:
  - pytest tests/widget.test.ts -v
""",
        )
        _write_source(
            project,
            "src/widget.ts",
            "export function update() {\n  return 'updated';\n}\n",
        )
        _write_source(
            project,
            "tests/widget.test.ts",
            "import { update } from '../src/widget';\n\n"
            "it('update', () => {\n"
            "  expect(true).toBe(true);\n"
            "});\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        untested = [
            e for e in result.errors if e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        ]
        assert result.success is False
        assert len(untested) == 1
        assert "update" in untested[0].message

    def test_snapshot_manifest_still_exempt_from_behavioral_coverage_error(
        self, project
    ):
        """Snapshot manifests do not emit E200 for unreferenced public artifacts."""
        manifest_path = _write_manifest(
            project / "manifests",
            "snapshot-utils.manifest.yaml",
            """schema: "2"
goal: "Snapshot utils"
type: snapshot
files:
  create:
    - path: src/utils.py
      artifacts:
        - kind: function
          name: helper
  read:
    - tests/test_utils.py
validate:
  - pytest tests/test_utils.py -v
""",
        )
        _write_source(project, "src/utils.py", "def helper():\n    pass\n")
        _write_source(
            project, "tests/test_utils.py", "def test_smoke():\n    assert True\n"
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)
        behavioral_result = engine.validate(
            manifest_path, mode=ValidationMode.BEHAVIORAL
        )

        assert result.success is True
        assert not any(
            e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
            for e in result.errors + result.warnings
        )
        assert behavioral_result.success is True
        assert not any(
            e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
            for e in behavioral_result.errors + behavioral_result.warnings
        )

    def test_test_file_artifacts_do_not_require_meta_test_coverage(self, project):
        """test_function artifacts do not need another test file."""
        manifest_path = _write_manifest(
            project / "manifests",
            "add-test-coverage.manifest.yaml",
            """schema: "2"
goal: "Add tests"
type: fix
files:
  edit:
    - path: tests/test_widget.py
      artifacts:
        - kind: test_function
          name: test_widget
validate:
  - pytest tests/test_widget.py -v
""",
        )
        _write_source(
            project,
            "tests/test_widget.py",
            "def test_widget():\n    assert True\n",
        )

        engine = ValidationEngine(project_root=project)
        result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

        assert result.success is True
        assert not any(
            e.code
            in {
                ErrorCode.NO_TEST_FILES,
                ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
            }
            for e in result.errors + result.warnings
        )

        workflow_manifest_path = _write_manifest(
            project / "manifests",
            "workflow-test-behavior.manifest.yaml",
            """schema: "2"
goal: "Describe workflow behavior"
type: fix
files:
  edit:
    - path: .github/workflows/publish.yml
      artifacts:
        - kind: test_function
          name: publish_workflow_test_job_installs_npm_dependencies
validate:
  - make check
""",
        )
        _write_source(project, ".github/workflows/publish.yml", "name: publish\n")

        workflow_result = engine.validate(
            workflow_manifest_path, mode=ValidationMode.IMPLEMENTATION
        )

        assert workflow_result.success is True
        assert not any(
            e.code
            in {
                ErrorCode.NO_TEST_FILES,
                ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
            }
            for e in workflow_result.errors + workflow_result.warnings
        )
