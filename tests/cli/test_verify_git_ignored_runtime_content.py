"""Behavioral contract for Git-aware runtime-evidence content identity."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest
import yaml

from maid_runner.cli.commands._main import main


@pytest.mark.parametrize(
    ("ignore_source", "generated_path"),
    [
        ("gitignore", "build/advisory/report.txt"),
        ("info-exclude", ".local/session/output.json"),
    ],
)
def test_verify_accepts_generated_runtime_content_excluded_by_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ignore_source: str,
    generated_path: str,
) -> None:
    _write_runtime_mutating_project(tmp_path, generated_path)
    _git(tmp_path, "init")
    if ignore_source == "gitignore":
        (tmp_path / ".gitignore").write_text(f"/{generated_path}\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    if ignore_source == "info-exclude":
        exclude = tmp_path / ".git" / "info" / "exclude"
        exclude.write_text(exclude.read_text() + f"\n/{generated_path}\n")
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--artifact-coverage",
            "--no-changed-scope",
            "--advisory",
            "--no-cache",
            "--summary",
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 0, output.out + output.err
    assert "VERIFY: PASS" in output.out
    assert (tmp_path / generated_path).is_file()


def test_verify_rejects_generated_runtime_content_not_excluded_by_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_mutating_project(tmp_path, "generated/unignored.txt")
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--artifact-coverage",
            "--no-changed-scope",
            "--advisory",
            "--no-cache",
            "--summary",
        ]
    )
    output = capsys.readouterr()

    assert exit_code == 1
    assert "BLOCKING (1):" in output.out
    assert "FAIL artifact_coverage" in output.out
    assert "Artifact coverage evidence command changed project content" in output.out


def test_verify_rejects_mutation_of_tracked_file_that_later_matches_ignore_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generated_path = "generated/tracked.txt"
    _write_runtime_mutating_project(tmp_path, generated_path)
    tracked = tmp_path / generated_path
    tracked.parent.mkdir(parents=True)
    tracked.write_text("baseline tracked content\n")
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    (tmp_path / ".gitignore").write_text(f"/{generated_path}\n")
    _git(tmp_path, "add", ".gitignore")
    _git(tmp_path, "commit", "-m", "ignore tracked path")
    monkeypatch.chdir(tmp_path)

    exit_code = _run_artifact_coverage_verify()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL artifact_coverage" in output.out
    assert "Artifact coverage evidence command changed project content" in output.out


def test_verify_non_git_fallback_rejects_unignored_generated_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_mutating_project(tmp_path, "generated/non-git.txt")
    monkeypatch.chdir(tmp_path)

    exit_code = _run_artifact_coverage_verify()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL artifact_coverage" in output.out
    assert "Artifact coverage evidence command changed project content" in output.out


@pytest.mark.parametrize(
    "excluded_path",
    [".pytest_cache/generated.txt", ".maid/cache/evidence.json"],
)
def test_verify_non_git_fallback_accepts_canonical_excluded_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    excluded_path: str,
) -> None:
    _write_runtime_mutating_project(tmp_path, excluded_path)
    monkeypatch.chdir(tmp_path)

    exit_code = _run_artifact_coverage_verify()
    output = capsys.readouterr()

    assert exit_code == 0, output.out + output.err
    assert "VERIFY: PASS" in output.out
    assert (tmp_path / excluded_path).is_file()


def test_verify_ignores_ambient_git_repository_pointers_when_hashing_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "project"
    ambient = tmp_path / "ambient"
    project.mkdir()
    ambient.mkdir()
    _write_runtime_mutating_project(project, "generated/unignored.txt")
    _git(project, "init")
    _git(project, "add", ".")
    _git(project, "commit", "-m", "project baseline")
    _git(ambient, "init")
    (ambient / "elsewhere.txt").write_text("ambient repository\n")
    _git(ambient, "add", ".")
    _git(ambient, "commit", "-m", "ambient baseline")
    monkeypatch.setenv("GIT_DIR", str(ambient / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(ambient))
    monkeypatch.setenv("GIT_INDEX_FILE", str(ambient / ".git" / "index"))
    monkeypatch.chdir(project)

    exit_code = _run_artifact_coverage_verify(keep_going=True)
    output = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL artifact_coverage" in output.out
    assert "Artifact coverage evidence command changed project content" in output.out


def test_verify_rejects_runtime_mutation_of_local_git_exclude_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_mutating_project(
        tmp_path,
        "generated/newly-hidden.txt",
        mutate_local_exclude=True,
    )
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)

    exit_code = _run_artifact_coverage_verify()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL artifact_coverage" in output.out
    assert "Artifact coverage evidence command changed project content" in output.out


def test_verify_rejects_runtime_mutation_of_core_excludes_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_mutating_project(
        tmp_path,
        "generated/core-hidden.txt",
        mutate_core_excludes=True,
    )
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)

    exit_code = _run_artifact_coverage_verify()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL artifact_coverage" in output.out
    assert "Artifact coverage evidence command changed project content" in output.out


def test_verify_rejects_runtime_self_ignored_gitignore_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_mutating_project(
        tmp_path,
        "generated/gitignore-hidden.txt",
        mutate_self_ignored_gitignore=True,
    )
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)

    exit_code = _run_artifact_coverage_verify()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL artifact_coverage" in output.out
    assert "Artifact coverage evidence command changed project content" in output.out


def test_verify_rejects_runtime_ignore_case_configuration_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_runtime_mutating_project(
        tmp_path,
        "generated/case-hidden.txt",
        mutate_ignore_case=True,
    )
    (tmp_path / ".gitignore").write_text("/generated/CASE-HIDDEN.txt\n")
    _git(tmp_path, "init")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "baseline")
    monkeypatch.chdir(tmp_path)

    exit_code = _run_artifact_coverage_verify()
    output = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL artifact_coverage" in output.out
    assert "Artifact coverage evidence command changed project content" in output.out


def _run_artifact_coverage_verify(*, keep_going: bool = False) -> int:
    fail_fast_option = "--keep-going" if keep_going else "--fail-fast"
    return main(
        [
            "verify",
            "--artifact-coverage",
            "--no-changed-scope",
            "--advisory",
            "--no-cache",
            "--summary",
            fail_fast_option,
        ]
    )


def _write_runtime_mutating_project(
    root: Path,
    generated_path: str,
    *,
    mutate_local_exclude: bool = False,
    mutate_core_excludes: bool = False,
    mutate_self_ignored_gitignore: bool = False,
    mutate_ignore_case: bool = False,
) -> None:
    (root / "manifests").mkdir()
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "src" / "target.py").write_text(
        "def transform(value: str) -> str:\n" "    return value.upper()\n"
    )
    local_exclude_mutation = ""
    if mutate_local_exclude:
        local_exclude_mutation = (
            "    exclude = Path('.git/info/exclude')\n"
            f"    exclude.write_text(exclude.read_text() + '\\n/{generated_path}\\n')\n"
        )
    core_excludes_mutation = ""
    if mutate_core_excludes:
        core_excludes_mutation = (
            "    import subprocess\n"
            "    exclude = Path('.git/runtime-excludes')\n"
            f"    exclude.write_text('/{generated_path}\\n')\n"
            "    subprocess.run(\n"
            "        ['git', 'config', '--local', 'core.excludesFile', "
            "str(exclude.resolve())], check=True\n"
            "    )\n"
        )
    gitignore_mutation = ""
    if mutate_self_ignored_gitignore:
        gitignore_mutation = (
            "    Path('.gitignore').write_text(\n"
            f"        '/.gitignore\\n/{generated_path}\\n'\n"
            "    )\n"
        )
    ignore_case_mutation = ""
    if mutate_ignore_case:
        ignore_case_mutation = (
            "    import subprocess\n"
            "    subprocess.run(\n"
            "        ['git', 'config', '--local', 'core.ignoreCase', 'true'], "
            "check=True\n"
            "    )\n"
        )
    (root / "tests" / "test_target.py").write_text(
        "from pathlib import Path\n"
        "from src.target import transform\n\n"
        "def test_target():\n"
        f"{local_exclude_mutation}"
        f"{core_excludes_mutation}"
        f"{gitignore_mutation}"
        f"{ignore_case_mutation}"
        f"    generated = Path({generated_path!r})\n"
        "    generated.parent.mkdir(parents=True, exist_ok=True)\n"
        "    generated.write_text('generated advisory insight\\n')\n"
        "    assert transform('evidence') == 'EVIDENCE'\n"
    )
    manifest = {
        "schema": "2",
        "goal": "Exercise Git-aware runtime content identity",
        "type": "fix",
        "created": "2026-08-18T21:53:00Z",
        "files": {
            "edit": [
                {
                    "path": "src/target.py",
                    "artifacts": [
                        {
                            "kind": "function",
                            "name": "transform",
                            "args": [{"name": "value", "type": "str"}],
                            "returns": "str",
                        }
                    ],
                }
            ],
            "read": ["tests/test_target.py"],
        },
        "validate": ["python -m pytest -q tests/test_target.py"],
    }
    (root / "manifests" / "runtime-content.manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False)
    )


def _git(root: Path, *args: str) -> None:
    command = ["git", "-C", str(root)]
    if args and args[0] == "commit":
        command.extend(
            [
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "user.email=test@example.com",
                "-c",
                "user.name=Test User",
            ]
        )
    command.extend(args)
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
