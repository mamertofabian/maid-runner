"""Focused characterization tests for validate-command test targets."""

from pathlib import Path

from maid_runner.core import _test_command_targets as targets


def test_validate_command_targets_respect_cd_and_package_runner(tmp_path):
    test_path = tmp_path / "apps" / "frontend" / "src" / "current.test.ts"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("test('current', () => {})\n")

    paths = targets.test_paths_from_validate_command(
        ("cd", "apps/frontend", "&&", "pnpm", "vitest", "run", "src/current.test.ts"),
        tmp_path,
    )

    assert paths == ["apps/frontend/src/current.test.ts"]


def test_executing_targets_reject_pytest_node_selector_by_default(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_gate.py").write_text("def test_gate():\n    pass\n")

    default_paths = targets.test_paths_from_executing_validate_command(
        ("pytest", "tests/test_gate.py::test_gate", "-q"),
        tmp_path,
    )
    allowed_paths = targets.test_paths_from_executing_validate_command(
        ("pytest", "tests/test_gate.py::test_gate", "-q"),
        tmp_path,
        allow_selectors=True,
    )

    assert default_paths == []
    assert allowed_paths == ["tests/test_gate.py"]


def test_executing_targets_accept_uv_run_project_pytest_file(tmp_path):
    test_file = tmp_path / "backend" / "tests" / "test_gate.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_gate():\n    assert True\n")

    paths = targets.test_paths_from_executing_validate_command(
        (
            "uv",
            "run",
            "--project",
            "backend",
            "pytest",
            "backend/tests/test_gate.py",
            "-q",
        ),
        tmp_path,
    )

    assert paths == ["backend/tests/test_gate.py"]


def test_executing_targets_reject_uv_run_directory_without_cwd_modeling(tmp_path):
    test_file = tmp_path / "tests" / "test_gate.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_gate():\n    assert True\n")

    paths = targets.test_paths_from_executing_validate_command(
        (
            "uv",
            "run",
            "--directory",
            "backend",
            "pytest",
            "tests/test_gate.py",
            "-q",
        ),
        tmp_path,
    )

    assert paths == []


def test_command_target_coverage_maps_directory_target_to_file(tmp_path):
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_gate.py").write_text(
        "def test_gate():\n    pass\n"
    )

    covered = targets.test_files_covered_by_validate_command(
        ("pytest", "tests/unit", "-q"),
        ["tests/unit/test_gate.py", "tests/other/test_other.py"],
        tmp_path,
    )

    assert covered == {"tests/unit/test_gate.py"}


def test_validate_command_targets_use_django_resolver_callback(tmp_path):
    def django_resolver(segment: list[str], project_root: Path, cwd: Path) -> list[str]:
        assert segment == [
            "python",
            "manage.py",
            "test",
            "app.tests.test_gate",
        ]
        assert project_root == tmp_path
        assert cwd == Path(".")
        return ["src/app/tests/test_gate.py"]

    paths = targets.test_paths_from_validate_command(
        ("python", "manage.py", "test", "app.tests.test_gate"),
        tmp_path,
        django_test_paths_from_validate_segment=django_resolver,
    )

    assert paths == ["src/app/tests/test_gate.py"]


def test_command_segments_split_shell_separators():
    assert targets.command_segments(
        ("cd", "ui", "&&", "pytest", "tests", ";", "echo", "ok")
    ) == [
        ["cd", "ui"],
        ["pytest", "tests"],
        ["echo", "ok"],
    ]
