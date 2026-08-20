"""Behavioral contract for deterministic verify-profile assessment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from maid_runner.core.change_assessment import AssessmentTier
except ModuleNotFoundError:
    pass


def _signals(
    *paths: str,
    public_artifact_changes: int = 0,
    risk_priorities: tuple[str, ...] = (),
):
    from maid_runner.core import change_assessment

    return change_assessment.ChangeSignalSummary(
        changed_paths=tuple(paths),
        sensitive_paths=(),
        public_artifact_changes=public_artifact_changes,
        risk_priorities=risk_priorities,
    )


def _init_changed_repo(tmp_path: Path, path: str = "src/widget.py") -> str:
    from subprocess import run

    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def value():\n    return 1\n")
    run(["git", "init", "-q"], cwd=tmp_path, check=True)
    run(["git", "config", "user.email", "maid@example.test"], cwd=tmp_path, check=True)
    run(["git", "config", "user.name", "MAID Test"], cwd=tmp_path, check=True)
    run(["git", "add", "."], cwd=tmp_path, check=True)
    run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
    baseline = run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target.write_text("def value():\n    return 2\n")
    return baseline


def test_small_non_sensitive_change_recommends_a_light_tier() -> None:
    from maid_runner.core import change_assessment

    recommendation = change_assessment.recommend_verify_profile(
        _signals("src/widget.py")
    )

    assert isinstance(recommendation, change_assessment.VerifyProfileRecommendation)
    assert recommendation.tier is AssessmentTier.LOW
    assert recommendation.profile == "handoff"
    assert recommendation.rationale
    assert recommendation.human_gate_expected is False


def test_sensitive_path_change_recommends_a_higher_tier(tmp_path: Path) -> None:
    from maid_runner.core import change_assessment
    from maid_runner.core.diff_scope import DiffScopeBaseline

    ordinary = change_assessment.recommend_verify_profile(_signals("src/widget.py"))
    sensitive = change_assessment.recommend_verify_profile(
        change_assessment.ChangeSignalSummary(
            changed_paths=("src/auth/session.py",),
            sensitive_paths=("src/auth/session.py",),
            public_artifact_changes=0,
            risk_priorities=(),
        )
    )
    critical = change_assessment.recommend_verify_profile(
        change_assessment.ChangeSignalSummary(
            changed_paths=tuple(f"src/auth/module_{index}.py" for index in range(8)),
            sensitive_paths=("src/auth/module_0.py",),
            public_artifact_changes=0,
            risk_priorities=("critical",),
        )
    )

    assert ordinary.tier is AssessmentTier.LOW
    assert sensitive.tier is AssessmentTier.HIGH
    assert sensitive.profile == "deep"
    assert critical.tier is AssessmentTier.CRITICAL
    assert critical.human_gate_expected is True

    baseline = _init_changed_repo(tmp_path)
    representative_sensitive_paths = {
        "src/auth_service.py": "VALUE = 1\n",
        "src/oauth_client.py": "VALUE = 1\n",
        "src/AUTHService.py": "VALUE = 1\n",
        "src/authz.py": "VALUE = 1\n",
        "src/rbac.py": "VALUE = 1\n",
        "src/acl.py": "VALUE = 1\n",
        "src/security_policy.py": "VALUE = 1\n",
        "db/schema.sql": "select 1;\n",
        ".gitlab-ci.yml": "test: {}\n",
        ".circleci/config.yml": "test: {}\n",
        ".travis.yml": "language: python\n",
        "bitbucket-pipelines.yml": "pipelines: {}\n",
        "ci.yml": "test: {}\n",
        "scripts/build.sh": "#!/bin/sh\n",
        "build.gradle": "plugins {}\n",
        "Cargo.toml": "[package]\nname = 'demo'\n",
        "go.mod": "module example.test/demo\n",
        "CMakeLists.txt": "project(demo)\n",
        "pom.xml": "<project />\n",
    }
    for path, content in representative_sensitive_paths.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    ordinary_workflow_notes = tmp_path / "docs/.github/workflows-notes.md"
    ordinary_workflow_notes.parent.mkdir(parents=True, exist_ok=True)
    ordinary_workflow_notes.write_text("Workflow documentation only.\n")
    ordinary_security_docs = {
        "docs/security-guide.md": "Security documentation only.\n",
        "docs/manifest-format.md": "Manifest documentation only.\n",
    }
    for path, content in ordinary_security_docs.items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    gathered = change_assessment.assess_change_signals(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=baseline),
    )

    assert set(representative_sensitive_paths) <= set(gathered.sensitive_paths)
    assert "docs/.github/workflows-notes.md" not in gathered.sensitive_paths
    assert set(ordinary_security_docs).isdisjoint(gathered.sensitive_paths)
    assert change_assessment.recommend_verify_profile(gathered).tier in {
        AssessmentTier.HIGH,
        AssessmentTier.CRITICAL,
    }


def test_larger_blast_radius_recommends_a_higher_tier() -> None:
    from maid_runner.core import change_assessment

    small = change_assessment.recommend_verify_profile(_signals("src/one.py"))
    medium = change_assessment.recommend_verify_profile(
        _signals("src/one.py", "src/two.py", "src/three.py")
    )
    large = change_assessment.recommend_verify_profile(
        _signals(*(f"src/module_{index}.py" for index in range(8)))
    )
    wide_build = change_assessment.recommend_verify_profile(
        change_assessment.ChangeSignalSummary(
            changed_paths=("build.gradle",)
            + tuple(f"src/module_{index}.py" for index in range(7)),
            sensitive_paths=("build.gradle",),
            public_artifact_changes=0,
            risk_priorities=(),
        )
    )
    wide_public_api = change_assessment.recommend_verify_profile(
        change_assessment.ChangeSignalSummary(
            changed_paths=tuple(f"src/module_{index}.py" for index in range(8)),
            sensitive_paths=(),
            public_artifact_changes=1,
            risk_priorities=(),
        )
    )

    assert small.tier is AssessmentTier.LOW
    assert medium.tier is AssessmentTier.MEDIUM
    assert large.tier is AssessmentTier.HIGH
    assert large.profile == "deep"
    assert wide_build.tier is AssessmentTier.HIGH
    assert wide_build.human_gate_expected is False
    assert wide_public_api.tier is AssessmentTier.HIGH
    assert wide_public_api.human_gate_expected is False


def test_recommendation_is_deterministic_for_identical_signals(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.core import change_assessment

    signals = _signals(
        "src/api.py", "src/service.py", risk_priorities=("medium", "low")
    )
    first = change_assessment.recommend_verify_profile(signals)
    monkeypatch.chdir(tmp_path)
    second = change_assessment.recommend_verify_profile(signals)

    assert first == second


def test_assess_output_cannot_lower_or_set_an_enforcement_gate(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands.assess import cmd_assess
    from maid_runner.core.change_assessment import assess_change_signals

    baseline = _init_changed_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert callable(cmd_assess)
    assert callable(assess_change_signals)
    exit_code = main(["assess", "--since", baseline, "--json"])
    document = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert document["verify_argv"] == [
        "maid",
        "verify",
        "--profile",
        document["profile"],
        "--since",
        baseline,
    ]
    assert not any(
        flag in document["verify_argv"]
        for flag in ("--advisory", "--no-changed-scope", "--allow-empty")
    )
    assert set(document) >= {
        "tier",
        "profile",
        "rationale",
        "human_gate_expected",
        "signals",
        "verify_command",
    }


def test_assessment_is_repeatable_and_does_not_create_cache(tmp_path: Path) -> None:
    from maid_runner.core.change_assessment import assess_change_signals
    from maid_runner.core.diff_scope import DiffScopeBaseline

    baseline = _init_changed_repo(tmp_path)
    scope = DiffScopeBaseline(source="since", commitish=baseline)

    first = assess_change_signals(tmp_path, scope)
    second = assess_change_signals(tmp_path, scope)

    assert first == second
    assert first.changed_paths == ("src/widget.py",)
    assert not (tmp_path / ".maid/cache").exists()


def test_routine_lifecycle_files_do_not_inflate_material_change(tmp_path: Path) -> None:
    from maid_runner.core.change_assessment import assess_change_signals
    from maid_runner.core.diff_scope import DiffScopeBaseline

    baseline = _init_changed_repo(tmp_path)
    manifest = tmp_path / "manifests/task.manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "schema: '2'\ngoal: task\ntype: fix\n"
        "files:\n  edit:\n  - path: src/widget.py\n"
    )
    lock = tmp_path / ".maid/plan-locks/task.lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text("{}\n")

    signals = assess_change_signals(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=baseline),
    )

    assert signals.changed_paths == ("src/widget.py",)
    assert signals.sensitive_paths == ()


def test_manifest_only_change_remains_sensitive(tmp_path: Path) -> None:
    from subprocess import run

    from maid_runner.core.change_assessment import assess_change_signals
    from maid_runner.core.diff_scope import DiffScopeBaseline

    manifest = tmp_path / "manifests/task.manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("schema: '2'\ngoal: original\ntype: fix\nfiles: {}\n")
    run(["git", "init", "-q"], cwd=tmp_path, check=True)
    run(["git", "config", "user.email", "maid@example.test"], cwd=tmp_path, check=True)
    run(["git", "config", "user.name", "MAID Test"], cwd=tmp_path, check=True)
    run(["git", "add", "."], cwd=tmp_path, check=True)
    run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
    baseline = run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    manifest.write_text("schema: '2'\ngoal: revised\ntype: fix\nfiles: {}\n")

    signals = assess_change_signals(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=baseline),
    )

    assert signals.changed_paths == ("manifests/task.manifest.yaml",)
    assert signals.sensitive_paths == ("manifests/task.manifest.yaml",)


def test_unrelated_material_change_cannot_hide_manifest(tmp_path: Path) -> None:
    from subprocess import run

    from maid_runner.core.change_assessment import (
        AssessmentTier,
        assess_change_signals,
        recommend_verify_profile,
    )
    from maid_runner.core.diff_scope import DiffScopeBaseline

    notes = tmp_path / "README.md"
    notes.write_text("original\n")
    run(["git", "init", "-q"], cwd=tmp_path, check=True)
    run(["git", "config", "user.email", "maid@example.test"], cwd=tmp_path, check=True)
    run(["git", "config", "user.name", "MAID Test"], cwd=tmp_path, check=True)
    run(["git", "add", "."], cwd=tmp_path, check=True)
    run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
    baseline = run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    notes.write_text("revised\n")
    manifest = tmp_path / "manifests/security-policy.manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("schema: '2'\ngoal: policy\ntype: fix\nfiles: {}\n")

    signals = assess_change_signals(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=baseline),
    )

    assert "manifests/security-policy.manifest.yaml" in signals.sensitive_paths
    assert recommend_verify_profile(signals).tier is AssessmentTier.HIGH


def test_custom_manifest_directory_lifecycle_pair_is_calibrated(
    tmp_path: Path,
) -> None:
    from maid_runner.core.change_assessment import assess_change_signals
    from maid_runner.core.diff_scope import DiffScopeBaseline

    baseline = _init_changed_repo(tmp_path)
    manifest = tmp_path / "custom-manifests/task.manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "schema: '2'\ngoal: task\ntype: fix\n"
        "files:\n  edit:\n  - path: src/widget.py\n"
    )
    lock = tmp_path / ".maid/plan-locks/task.lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text("{}\n")

    signals = assess_change_signals(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=baseline),
        manifest_dir="custom-manifests/",
    )

    assert signals.changed_paths == ("src/widget.py",)
    assert signals.sensitive_paths == ()


def test_nested_active_manifest_lifecycle_pair_is_calibrated(tmp_path: Path) -> None:
    from maid_runner.core.change_assessment import assess_change_signals
    from maid_runner.core.diff_scope import DiffScopeBaseline

    baseline = _init_changed_repo(tmp_path)
    manifest = tmp_path / "manifests/team/task.manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "schema: '2'\ngoal: task\ntype: fix\n"
        "files:\n  edit:\n  - path: src/widget.py\n"
    )
    lock = tmp_path / ".maid/plan-locks/task.lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text("{}\n")

    signals = assess_change_signals(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=baseline),
    )

    assert signals.changed_paths == ("src/widget.py",)
    assert signals.sensitive_paths == ()


@pytest.mark.parametrize("baseline_flag", ["--since", "--base-ref"])
def test_deep_recommendation_command_retains_handoff_gates(
    tmp_path: Path, monkeypatch, capsys, baseline_flag: str
) -> None:
    from maid_runner.cli.commands._main import main

    baseline = _init_changed_repo(tmp_path, "src/auth/session.py")
    monkeypatch.chdir(tmp_path)

    exit_code = main(["assess", baseline_flag, baseline, "--json"])
    document = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert document["profile"] == "deep"
    assert document["verify_argv"] == [
        "maid",
        "verify",
        "--profile",
        "deep",
        "--test-scope",
        "task",
        "--require-plan-lock",
        "--require-red-evidence",
        baseline_flag,
        baseline,
    ]


def test_assess_requires_a_baseline_and_json_is_single_document(capsys) -> None:
    from maid_runner.cli.commands._main import main

    exit_code = main(["assess", "--json"])
    output = capsys.readouterr().out

    assert exit_code == 2
    assert json.loads(output)["error"].startswith("E115")
    assert output.count("{") == 1

    empty_exit = main(["assess", "--since", "", "--json"])
    empty_output = capsys.readouterr().out
    assert empty_exit == 2
    assert json.loads(empty_output)["error"].startswith("E116")

    both_exit = main(["assess", "--since", "", "--base-ref", "HEAD", "--json"])
    both_output = capsys.readouterr().out
    assert both_exit == 2
    assert json.loads(both_output)["error"].startswith("E116")


def test_assess_is_registered_and_documented() -> None:
    from maid_runner.cli.commands._main import build_parser

    parser = build_parser()
    args = parser.parse_args(["assess", "--base-ref", "origin/main"])
    readme = Path("README.md").read_text()

    assert args.command == "assess"
    assert args.base_ref == "origin/main"
    assert "| `maid assess` |" in readme
