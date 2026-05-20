"""Focused characterization tests for Django validate-command targets."""

from pathlib import Path

from maid_runner.core._django_test_targets import (
    django_test_paths_from_args,
    django_test_paths_from_validate_segment,
    resolve_django_test_label_paths,
)


def test_django_segment_resolves_src_layout_dotted_module(tmp_path):
    test_path = tmp_path / "src" / "app" / "tests" / "test_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_gate():\n    pass\n")

    paths = django_test_paths_from_validate_segment(
        ["python", "manage.py", "test", "app.tests.test_gate"],
        tmp_path,
        Path("."),
    )

    assert paths == ["src/app/tests/test_gate.py"]


def test_django_args_skip_value_and_standalone_flags(tmp_path):
    test_path = tmp_path / "src" / "app" / "tests" / "test_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_gate():\n    pass\n")

    paths = django_test_paths_from_args(
        [
            "app.tests.test_gate",
            "--settings",
            "project.settings",
            "--keepdb",
            "-v",
            "2",
        ],
        tmp_path,
        Path("."),
    )

    assert paths == ["src/app/tests/test_gate.py"]


def test_django_label_resolution_uses_cwd_and_src_candidates(tmp_path):
    test_path = tmp_path / "services" / "src" / "app" / "tests" / "test_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_gate():\n    pass\n")

    paths = resolve_django_test_label_paths(
        "app.tests.test_gate",
        tmp_path,
        Path("services"),
    )

    assert paths == ["services/src/app/tests/test_gate.py"]


def test_django_segment_rejects_pythonpath_shadowing(tmp_path):
    test_path = tmp_path / "src" / "app" / "tests" / "test_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_gate():\n    pass\n")

    paths = django_test_paths_from_validate_segment(
        [
            "python",
            "manage.py",
            "test",
            "app.tests.test_gate",
            "--pythonpath",
            "../outside",
        ],
        tmp_path,
        Path("."),
    )

    assert paths == []


def test_django_label_resolution_rejects_class_selector(tmp_path):
    test_path = tmp_path / "src" / "app" / "tests" / "test_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("class TestGate:\n    pass\n")

    paths = resolve_django_test_label_paths(
        "app.tests.test_gate.TestGate",
        tmp_path,
        Path("."),
    )

    assert paths == []
