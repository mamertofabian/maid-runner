"""Focused characterization tests for command-integrity test discovery."""

from maid_runner.core import _command_integrity_test_discovery as discovery
from maid_runner.core.manifest import load_manifest


def write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_command_integrity_discovery_includes_manifest_and_validate_targets(tmp_path):
    manifest_path = write(
        tmp_path / "manifests" / "discover-command-tests.manifest.yaml",
        """schema: "2"
goal: "Discover command-integrity tests"
files:
  edit:
    - path: src/example.py
      artifacts:
        - kind: function
          name: example
  read:
    - tests/test_from_read.py
    - tests/unit
validate:
  - pytest tests/test_from_validate.py tests/feature -q
""",
    )
    write(tmp_path / "tests" / "test_from_read.py", "def test_from_read():\n    pass\n")
    write(
        tmp_path / "tests" / "unit" / "test_nested.py", "def test_nested():\n    pass\n"
    )
    write(tmp_path / "tests" / "unit" / "helper.py", "def helper():\n    pass\n")
    write(tmp_path / "tests" / "unit" / "conftest.py", "VALUE = object()\n")
    write(
        tmp_path / "tests" / "test_from_validate.py",
        "def test_from_validate():\n    pass\n",
    )
    write(
        tmp_path / "tests" / "feature" / "test_feature.py",
        "def test_feature():\n    pass\n",
    )

    manifest = load_manifest(manifest_path)

    assert discovery.find_command_integrity_test_files(manifest, tmp_path) == [
        "tests/test_from_read.py",
        "tests/unit/test_nested.py",
        "tests/test_from_validate.py",
        "tests/feature/test_feature.py",
    ]


def test_command_integrity_test_file_excludes_conftest(tmp_path):
    write(tmp_path / "tests" / "conftest.py", "def pytest_configure():\n    pass\n")

    assert (
        discovery.is_command_integrity_test_file("tests/conftest.py", tmp_path) is False
    )


def test_python_behavioral_test_file_accepts_test_class_method(tmp_path):
    write(
        tmp_path / "tests" / "test_class.py",
        "class TestThing:\n" "    def test_thing(self):\n" "        pass\n",
    )

    assert (
        discovery.is_python_behavioral_test_file("tests/test_class.py", tmp_path)
        is True
    )


def test_python_behavioral_test_file_rejects_helper_only_file(tmp_path):
    write(tmp_path / "tests" / "test_helpers.py", "def helper():\n    pass\n")

    assert (
        discovery.is_python_behavioral_test_file("tests/test_helpers.py", tmp_path)
        is False
    )


def test_python_behavioral_test_file_fails_open_on_syntax_error(tmp_path):
    write(tmp_path / "tests" / "test_broken.py", "def test_broken(:\n    pass\n")

    assert (
        discovery.is_python_behavioral_test_file("tests/test_broken.py", tmp_path)
        is True
    )
