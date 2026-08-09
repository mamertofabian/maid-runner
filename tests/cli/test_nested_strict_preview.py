from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence


def test_strict_preview_propagates_strict_defaults_to_nested_validation(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands.validate import cmd_validate

    assert callable(cmd_validate)
    outer_manifest = _write_nested_validation_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    relative_manifest = str(outer_manifest.relative_to(tmp_path))

    default_exit = main(
        [
            "validate",
            relative_manifest,
            "--mode",
            "schema",
            "--no-chain",
            "--artifact-coverage",
            "--json",
        ]
    )
    default_payload = json.loads(capsys.readouterr().out)

    preview_exit = main(
        [
            "validate",
            relative_manifest,
            "--mode",
            "schema",
            "--no-chain",
            "--strict-preview",
            "--json",
        ]
    )
    preview_payload = json.loads(capsys.readouterr().out)

    restored_default_exit = main(
        [
            "validate",
            relative_manifest,
            "--mode",
            "schema",
            "--no-chain",
            "--artifact-coverage",
            "--json",
        ]
    )
    restored_default_payload = json.loads(capsys.readouterr().out)

    assert default_exit == 0
    assert default_payload["artifact_coverage"]["success"] is True
    assert "strict_preview" not in default_payload
    assert preview_exit == 1
    assert preview_payload["strict_preview"] is True
    assert preview_payload["artifact_coverage"]["success"] is False
    assert [
        error["code"] for error in preview_payload["artifact_coverage"]["errors"]
    ] == ["E900"]
    assert (
        "appears to be a stub"
        in preview_payload["artifact_coverage"]["errors"][0]["suggestion"]
    )
    assert restored_default_exit == 0
    assert restored_default_payload["artifact_coverage"]["success"] is True
    assert "strict_preview" not in restored_default_payload


def test_strict_delta_reports_nested_default_gate_regression_without_failing_default_side(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    outer_manifest = _write_nested_validation_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "validate",
            str(outer_manifest.relative_to(tmp_path)),
            "--mode",
            "schema",
            "--no-chain",
            "--artifact-coverage",
            "--strict-delta",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["artifact_coverage"]["success"] is True
    assert [
        (entry["manifest_path"], entry["code"]) for entry in payload["strict_delta"]
    ] == [("manifests/outer.manifest.yaml", "E900")]


def test_inherited_strict_boundary_blocks_explicit_nested_coverage_modes(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    modes = {
        "artifact-coverage": ("--artifact-coverage",),
        "strict-preview": ("--strict-preview",),
        "strict-delta": ("--strict-delta",),
    }
    for label, nested_options in modes.items():
        project_root = tmp_path / label
        project_root.mkdir()
        outer_manifest = _write_nested_validation_project(
            project_root,
            inner_source=(
                'def inner() -> str:\n    parts = ("in", "ner")\n'
                '    return "".join(parts)\n'
            ),
            nested_options=nested_options,
            guard_reentry=True,
        )
        monkeypatch.chdir(project_root)

        exit_code = main(
            [
                "validate",
                str(outer_manifest.relative_to(project_root)),
                "--mode",
                "schema",
                "--no-chain",
                "--strict-preview",
                "--json",
            ]
        )

        payload = json.loads(capsys.readouterr().out)
        assert exit_code == 0, label
        assert payload["strict_preview"] is True
        assert payload["artifact_coverage"]["success"] is True
        assert (project_root / ".nested-execution-count").read_text() == "1"


def test_forged_internal_environment_cannot_suppress_top_level_artifact_coverage(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    outer_manifest = _write_nested_validation_project(tmp_path)
    (tmp_path / "tests" / "test_outer.py").write_text(
        "from src.outer import outer\n\n"
        "def test_only_mentions_outer():\n"
        "    assert outer is not None\n"
    )
    forged_capability = tmp_path / "forged-capability"
    forged_capability.write_text("chosen-token")
    monkeypatch.setenv(
        "MAID_INTERNAL_STRICT_VALIDATION",
        str(forged_capability),
    )
    monkeypatch.setenv(
        "MAID_INTERNAL_STRICT_VALIDATION_TOKEN",
        "chosen-token",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "validate",
            str(outer_manifest.relative_to(tmp_path)),
            "--mode",
            "schema",
            "--no-chain",
            "--artifact-coverage",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["artifact_coverage"]["success"] is False
    assert [error["code"] for error in payload["artifact_coverage"]["errors"]] == [
        "E710"
    ]


def test_inherited_strict_boundary_reaches_nested_validation_in_worker_thread(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    from maid_runner.cli.commands._main import main

    outer_manifest = _write_nested_validation_project(
        tmp_path,
        inner_source=(
            'def inner() -> str:\n    parts = ("in", "ner")\n'
            '    return "".join(parts)\n'
        ),
        nested_options=("--artifact-coverage",),
        guard_reentry=True,
        nested_in_thread=True,
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "validate",
            str(outer_manifest.relative_to(tmp_path)),
            "--mode",
            "schema",
            "--no-chain",
            "--strict-preview",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["strict_preview"] is True
    assert payload["artifact_coverage"]["success"] is True
    assert (tmp_path / ".nested-execution-count").read_text() == "1"


def _write_nested_validation_project(
    root: Path,
    *,
    inner_source: str = "def inner() -> str:\n    pass\n",
    nested_options: Sequence[str] = (),
    guard_reentry: bool = False,
    nested_in_thread: bool = False,
) -> Path:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "outer.py").write_text('def outer() -> str:\n    return "outer"\n')
    (root / "src" / "inner.py").write_text(inner_source)
    reentry_guard = ""
    if guard_reentry:
        reentry_guard = (
            '    count_path = Path(".nested-execution-count")\n'
            "    count = int(count_path.read_text()) + 1 if count_path.exists() else 1\n"
            "    count_path.write_text(str(count))\n"
            '    assert count == 1, "nested artifact coverage re-entered its own test command"\n'
        )
    nested_argv = ", ".join(repr(option) for option in nested_options)
    nested_suffix = f", {nested_argv}" if nested_argv else ""
    nested_call = (
        "    nested_args = [\n"
        '        "validate", "manifests/inner.manifest.yaml",\n'
        f'        "--mode", "implementation", "--no-chain", "--json"{nested_suffix},\n'
        "    ]\n"
    )
    if nested_in_thread:
        nested_call += (
            "    with ThreadPoolExecutor(max_workers=1) as executor:\n"
            "        nested_exit = executor.submit(main, nested_args).result()\n"
            "    assert nested_exit == 0\n"
        )
    else:
        nested_call += "    assert main(nested_args) == 0\n"
    (root / "tests" / "test_outer.py").write_text(
        "from concurrent.futures import ThreadPoolExecutor\n"
        "from maid_runner.cli.commands._main import main\n"
        "from pathlib import Path\n"
        "from src.inner import inner\n"
        "from src.outer import outer\n\n"
        "def test_outer_executes_and_nested_manifest_validates():\n"
        f"{reentry_guard}"
        '    assert outer() == "outer"\n'
        "    assert inner is not None\n"
        f"{nested_call}"
    )
    (root / "manifests" / "inner.manifest.yaml").write_text(
        """schema: "2"
goal: "Represent nested validation"
type: feature
files:
  edit:
    - path: src/inner.py
      artifacts:
        - kind: function
          name: inner
          args: []
          returns: str
  read:
    - tests/test_outer.py
validate:
  - python -m pytest -q tests/test_outer.py
"""
    )
    outer_manifest = root / "manifests" / "outer.manifest.yaml"
    outer_manifest.write_text(
        """schema: "2"
goal: "Exercise nested validation"
type: feature
files:
  edit:
    - path: src/outer.py
      artifacts:
        - kind: function
          name: outer
          args: []
          returns: str
  read:
    - tests/test_outer.py
validate:
  - python -m pytest -q tests/test_outer.py
"""
    )
    return outer_manifest
