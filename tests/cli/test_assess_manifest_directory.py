"""Behavioral contract for manifest-directory-aware change assessment."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import yaml

from maid_runner.cli.commands._main import build_parser, main


DEFAULT_MANIFEST_DIR = "apps/default/manifests/"


def _write_manifest(path: Path, declared_path: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": f"Cover {declared_path}",
                "type": "fix",
                "created": "2026-08-25T00:00:00Z",
                "files": {"scope": [{"path": declared_path, "reason": "fixture"}]},
                "validate": ["python -c 'print(1)'"],
            },
            sort_keys=False,
        )
    )


def _init_monorepo(tmp_path: Path) -> str:
    (tmp_path / ".maidrc.yaml").write_text(
        yaml.safe_dump({"manifest_dir": DEFAULT_MANIFEST_DIR})
    )
    default_source = tmp_path / "apps/default/src/value.py"
    default_source.parent.mkdir(parents=True)
    default_source.write_text("VALUE = 1\n")
    _write_manifest(
        tmp_path / "apps/default/manifests/default.manifest.yaml",
        "apps/default/src/value.py",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "maid@example.test"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "MAID Test"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _add_app_change(tmp_path: Path, app: str) -> str:
    relative_source = f"apps/{app}/src/value.py"
    source = tmp_path / relative_source
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 2\n")
    _write_manifest(
        tmp_path / f"apps/{app}/manifests/{app}.manifest.yaml",
        relative_source,
    )
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    return f"apps/{app}/manifests"


def _assess_json(
    tmp_path: Path, baseline: str, monkeypatch, capsys, *extra: str
) -> tuple[int, dict]:
    monkeypatch.chdir(tmp_path)
    exit_code = main(["assess", "--since", baseline, "--json", *extra])
    return exit_code, json.loads(capsys.readouterr().out)


def test_assess_selects_changed_nondefault_manifest_directory(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    baseline = _init_monorepo(tmp_path)
    selected = _add_app_change(tmp_path, "studyfinder")

    exit_code, document = _assess_json(tmp_path, baseline, monkeypatch, capsys)

    assert exit_code == 0
    assert document["manifest_dir"] == selected
    assert document["manifest_dir_source"] == "changed-manifest"
    assert document["verify_argv"].count("--manifest-dir") == 1
    flag_index = document["verify_argv"].index("--manifest-dir")
    assert document["verify_argv"][flag_index + 1] == selected


def test_assess_explicit_manifest_directory_overrides_changed_candidate(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    baseline = _init_monorepo(tmp_path)
    _add_app_change(tmp_path, "studyfinder")

    exit_code, document = _assess_json(
        tmp_path,
        baseline,
        monkeypatch,
        capsys,
        "--manifest-dir",
        DEFAULT_MANIFEST_DIR,
    )

    assert exit_code == 0
    assert document["manifest_dir"] == DEFAULT_MANIFEST_DIR
    assert document["manifest_dir_source"] == "explicit"
    assert "--manifest-dir" in document["verify_argv"]
    assert DEFAULT_MANIFEST_DIR in document["verify_argv"]


def test_assess_rejects_multiple_changed_manifest_directories(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    baseline = _init_monorepo(tmp_path)
    _add_app_change(tmp_path, "studyfinder")
    _add_app_change(tmp_path, "another")

    exit_code, document = _assess_json(tmp_path, baseline, monkeypatch, capsys)

    assert exit_code == 2
    assert "multiple changed manifest directories" in document["error"].lower()
    assert "--manifest-dir" in document["error"]


def test_assess_falls_back_to_config_when_no_manifest_changed(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    baseline = _init_monorepo(tmp_path)
    source = tmp_path / "apps/default/src/value.py"
    source.write_text("VALUE = 3\n")

    exit_code, document = _assess_json(tmp_path, baseline, monkeypatch, capsys)

    assert exit_code == 0
    assert document["manifest_dir"] == DEFAULT_MANIFEST_DIR
    assert document["manifest_dir_source"] == "configured"
    assert "--manifest-dir" not in document["verify_argv"]


def test_assess_parser_accepts_manifest_directory_override() -> None:
    omitted = build_parser().parse_args(["assess", "--since", "HEAD"])
    explicit = build_parser().parse_args(
        ["assess", "--since", "HEAD", "--manifest-dir", "apps/example/manifests"]
    )

    assert omitted.manifest_dir is None
    assert explicit.manifest_dir == "apps/example/manifests"
