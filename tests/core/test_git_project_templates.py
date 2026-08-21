"""Behavioral contract for reusable real-Git test project templates."""

from __future__ import annotations

import builtins
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

import pytest

from tests.cli import test_plan_cmd_stash_implementation as stash_policy
from tests.cli import test_plan_cmd_stash_import_obstruction as obstruction_policy
from tests.cli import test_plan_legacy_baseline_cmd as legacy_policy
from tests.cli.test_plan_cmd_stash_implementation import _write_tracked_project
from tests.cli.test_plan_cmd_stash_import_obstruction import (
    _write_locked_full_stack_project,
)
from tests.cli.test_plan_legacy_baseline_cmd import _write_committed_legacy_project


_PYTEST_TERMINAL_ELAPSED = re.compile(
    r"(?m)^(?P<prefix>(?:(?:\d+ (?:failed|passed|skipped|xfailed|xpassed|"
    r"deselected|error|errors|warning|warnings))(?:, )?)+ in )"
    r"\d+(?:\.\d+)?s(?P<suffix>[ \t]*=*[ \t]*(?:\r?\n)?)\Z"
)


def _git(project_root: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=MAID Test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _stable_lock_payload(project_root: Path, slug: str) -> dict[str, Any]:
    payload = json.loads(
        (project_root / ".maid" / "plan-locks" / f"{slug}.lock.json").read_text()
    )
    payload.pop("created_at", None)
    red_evidence = payload.get("red_evidence")
    if isinstance(red_evidence, dict):
        red_evidence.pop("captured_at", None)
        commands = red_evidence.get("commands")
        if isinstance(commands, list):
            for command in commands:
                if not isinstance(command, dict):
                    continue
                output_tail = command.get("output_tail")
                if isinstance(output_tail, str):
                    command["output_tail"] = _PYTEST_TERMINAL_ELAPSED.sub(
                        r"\g<prefix><elapsed>s\g<suffix>", output_tail
                    )
    return payload


def _tracked_non_lock_blobs(project_root: Path) -> dict[str, str]:
    paths = _git(project_root, "ls-files").splitlines()
    return {
        path: _git(project_root, "rev-parse", f"HEAD:{path}")
        for path in paths
        if not path.startswith(".maid/plan-locks/")
    }


def test_stable_lock_payload_ignores_only_pytest_elapsed_time(tmp_path: Path) -> None:
    first = tmp_path / "first" / ".maid" / "plan-locks"
    second = tmp_path / "second" / ".maid" / "plan-locks"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    base = {
        "revision": 4,
        "red_evidence": {
            "red": True,
            "commands": [
                {
                    "command": "python -m pytest tests/test_demo.py -q",
                    "exit_code": 1,
                    "classification": "red",
                    "output_tail": (
                        "1 failed in 12.34s\n" "1 failed, 2 passed in 0.01s"
                    ),
                }
            ],
        },
    }
    (first / "demo.lock.json").write_text(json.dumps(base))
    changed = json.loads(json.dumps(base))
    changed["red_evidence"]["commands"][0]["output_tail"] = (
        "1 failed in 12.34s\n" "1 failed, 2 passed in 1.27s"
    )
    (second / "demo.lock.json").write_text(json.dumps(changed))

    assert _stable_lock_payload(tmp_path / "first", "demo") == _stable_lock_payload(
        tmp_path / "second", "demo"
    )
    variants = []
    for mutate in (
        lambda value: value.update(revision=5),
        lambda value: value["red_evidence"]["commands"][0].update(exit_code=2),
        lambda value: value["red_evidence"]["commands"][0].update(
            classification="invalid"
        ),
        lambda value: value["red_evidence"]["commands"][0].update(
            command="python -m pytest tests/other.py -q"
        ),
        lambda value: value["red_evidence"]["commands"][0].update(
            output_tail=("1 failed in 12.34s\n" "2 failed, 1 passed in 1.27s")
        ),
        lambda value: value["red_evidence"]["commands"][0].update(
            output_tail=("1 failed in 12.35s\n" "1 failed, 2 passed in 1.27s")
        ),
    ):
        variant = json.loads(json.dumps(changed))
        mutate(variant)
        variants.append(variant)
    for variant in variants:
        (second / "demo.lock.json").write_text(json.dumps(variant))
        assert _stable_lock_payload(tmp_path / "first", "demo") != _stable_lock_payload(
            tmp_path / "second", "demo"
        )


def test_template_clone_has_independent_index_and_worktree(
    tmp_path: Path,
) -> None:
    from tests.support.git_project_templates import (
        GitProjectTemplateFactory,
        clone_git_project_template,
    )

    factory = GitProjectTemplateFactory(tmp_path / "templates")
    template = factory.get("legacy-baseline")
    first = clone_git_project_template(template, tmp_path / "first")
    second = clone_git_project_template(template, tmp_path / "second")

    (first / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 2\n", encoding="utf-8"
    )
    _git(first, "add", "src/demo.py")

    assert _git(first, "status", "--porcelain") == "M  src/demo.py"
    assert _git(second, "status", "--porcelain") == ""
    assert (
        (second / "src" / "demo.py").read_text(encoding="utf-8").endswith("return 1\n")
    )


def test_template_source_remains_byte_and_status_clean_after_clone_mutation(
    tmp_path: Path,
) -> None:
    from tests.support.git_project_templates import (
        GitProjectTemplateFactory,
        clone_git_project_template,
    )

    factory = GitProjectTemplateFactory(tmp_path / "templates")
    template = factory.get("legacy-baseline")
    original_tree = _git(template.source_root, "rev-parse", "HEAD^{tree}")
    clone = clone_git_project_template(template, tmp_path / "clone")

    (clone / "tests" / "test_demo.py").write_text("assert False\n", encoding="utf-8")
    _git(clone, "add", "tests/test_demo.py")
    _git(clone, "commit", "-qm", "mutate clone")

    assert _git(template.source_root, "status", "--porcelain") == ""
    assert _git(template.source_root, "rev-parse", "HEAD^{tree}") == original_tree
    assert template.revision == _git(template.source_root, "rev-parse", "HEAD")


def test_template_setup_runs_once_for_multiple_policy_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support.git_project_templates import (
        GitProjectTemplate,
        GitProjectTemplateFactory,
    )

    from tests.support.git_project_templates import clone_git_project_template

    calls: list[tuple[str, ...]] = []
    real_run = subprocess.run

    def recording_run(argv, *args, **kwargs):
        calls.append(tuple(str(item) for item in argv))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    factory = GitProjectTemplateFactory(tmp_path / "templates")
    before = factory.build_count

    first = factory.get("legacy-baseline")
    second = factory.get("legacy-baseline")
    clone_git_project_template(first, tmp_path / "first")
    clone_git_project_template(second, tmp_path / "second")

    git_actions = [
        next(
            (
                part
                for part in command[1:]
                if part in {"init", "config", "commit", "clone"}
            ),
            None,
        )
        for command in calls
        if command and command[0] == "git"
    ]

    assert first is second
    assert isinstance(first, GitProjectTemplate)
    assert factory.root.is_dir()
    assert factory.build_count == before + 1
    assert git_actions.count("init") == 1
    assert git_actions.count("config") == 2
    assert git_actions.count("commit") == 1
    assert git_actions.count("clone") == 2


def test_session_fixture_exposes_factory_contract(tmp_path: Path) -> None:
    from tests.conftest import git_project_template_factory
    from tests.support.git_project_templates import GitProjectTemplateFactory

    factory = GitProjectTemplateFactory(tmp_path / "factory")

    assert factory.root == tmp_path / "factory"
    assert factory.build_count == 0
    assert callable(git_project_template_factory)


def test_session_fixture_executes_factory_body(tmp_path_factory) -> None:
    from tests.conftest import git_project_template_factory
    from tests.support.git_project_templates import GitProjectTemplateFactory

    fixture_body = git_project_template_factory.__wrapped__(tmp_path_factory)
    factory = next(fixture_body)

    assert isinstance(factory, GitProjectTemplateFactory)
    assert factory.root.parent == tmp_path_factory.getbasetemp()
    assert factory.root.name.startswith("git-project-templates")
    with pytest.raises(StopIteration):
        next(fixture_body)


def test_session_fixture_isolates_and_restores_ambient_git_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.conftest import (
        _GIT_CONFIG_ISOLATION,
        _GIT_REPOSITORY_POINTERS,
        _isolate_git_repository_environment,
    )

    inherited = {name: f"/ambient/{name.lower()}" for name in _GIT_REPOSITORY_POINTERS}
    inherited.update(
        {
            "GIT_CONFIG_GLOBAL": "/ambient/global.gitconfig",
            "GIT_CONFIG_NOSYSTEM": "0",
        }
    )
    for name, value in inherited.items():
        monkeypatch.setenv(name, value)
    fixture_body = _isolate_git_repository_environment.__wrapped__()

    next(fixture_body)

    assert all(name not in os.environ for name in _GIT_REPOSITORY_POINTERS)
    assert {
        name: os.environ[name] for name in _GIT_CONFIG_ISOLATION
    } == _GIT_CONFIG_ISOLATION

    with pytest.raises(StopIteration):
        next(fixture_body)
    assert {name: os.environ[name] for name in inherited} == inherited

    for name in inherited:
        monkeypatch.delenv(name)
    absent_body = _isolate_git_repository_environment.__wrapped__()
    next(absent_body)
    with pytest.raises(StopIteration):
        next(absent_body)
    assert all(name not in os.environ for name in inherited)


def test_fixture_loader_reraises_transitive_module_import_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests import conftest

    real_import = builtins.__import__

    def fail_import(name, *args, **kwargs):
        if name == "tests.support.git_project_templates":
            raise ModuleNotFoundError("support is absent", name=name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_import)
    assert conftest.load_git_project_template_factory() is None

    def fail_transitive_import(name, *args, **kwargs):
        if name == "tests.support.git_project_templates":
            raise ModuleNotFoundError(
                "transitive dependency is absent", name="transitive_dependency"
            )
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_transitive_import)
    with pytest.raises(ModuleNotFoundError) as exc_info:
        conftest.load_git_project_template_factory()

    assert exc_info.value.name == "transitive_dependency"


def test_template_and_legacy_builder_expose_equivalent_initial_git_state(
    tmp_path: Path,
) -> None:
    from tests.support.git_project_templates import (
        GitProjectTemplateFactory,
        clone_git_project_template,
    )

    legacy_root = tmp_path / "legacy"
    _write_committed_legacy_project(legacy_root)
    factory = GitProjectTemplateFactory(tmp_path / "templates")
    template = factory.get("legacy-baseline")
    clone = clone_git_project_template(template, tmp_path / "templated")

    assert _git(clone, "rev-parse", "HEAD^{tree}") == _git(
        legacy_root, "rev-parse", "HEAD^{tree}"
    )
    assert _git(clone, "status", "--porcelain") == ""
    assert _git(legacy_root, "status", "--porcelain") == ""
    assert _git(clone, "remote") == _git(legacy_root, "remote") == ""


@pytest.mark.parametrize(
    ("shape", "slug", "builder"),
    [
        ("stash-red-contract", "demo-task", _write_tracked_project),
        (
            "stash-import-obstruction",
            "full-stack",
            _write_locked_full_stack_project,
        ),
    ],
)
def test_stash_templates_match_bespoke_committed_git_state(
    tmp_path: Path,
    shape: str,
    slug: str,
    builder,
) -> None:
    from tests.support.git_project_templates import (
        GitProjectTemplateFactory,
        clone_git_project_template,
    )

    bespoke = tmp_path / "bespoke"
    bespoke.mkdir()
    builder(bespoke)
    factory = GitProjectTemplateFactory(tmp_path / "templates")
    clone = clone_git_project_template(factory.get(shape), tmp_path / "templated")

    assert _tracked_non_lock_blobs(clone) == _tracked_non_lock_blobs(bespoke)
    assert _stable_lock_payload(clone, slug) == _stable_lock_payload(bespoke, slug)
    assert _git(clone, "rev-list", "--count", "HEAD") == _git(
        bespoke, "rev-list", "--count", "HEAD"
    )
    assert _git(clone, "log", "--format=%s") == _git(bespoke, "log", "--format=%s")
    assert _git(clone, "status", "--porcelain") == ""
    assert _git(bespoke, "status", "--porcelain") == ""
    assert _git(clone, "remote") == _git(bespoke, "remote") == ""


def test_template_factory_rejects_unsupported_or_escaping_shape_without_writes(
    tmp_path: Path,
) -> None:
    from tests.support.git_project_templates import (
        GitProjectTemplateFactory,
        build_git_project_template,
    )

    factory_root = tmp_path / "templates"
    factory = GitProjectTemplateFactory(factory_root)

    with pytest.raises(ValueError, match="Unsupported Git project template shape"):
        factory.get("../escape")
    with pytest.raises(ValueError, match="Unsupported Git project template shape"):
        build_git_project_template(tmp_path / "direct", "unsupported")

    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "direct").exists()
    assert factory.build_count == 0


def test_distinct_template_shape_builds_distinct_committed_state(
    tmp_path: Path,
) -> None:
    from tests.support.git_project_templates import (
        GitProjectTemplate,
        GitProjectTemplateFactory,
        build_git_project_template,
    )

    factory = GitProjectTemplateFactory(tmp_path / "templates")
    legacy = factory.get("legacy-baseline")
    stash = factory.get("stash-red-contract")

    assert legacy.shape == "legacy-baseline"
    assert stash.shape == "stash-red-contract"
    assert legacy.revision != stash.revision
    assert _git(legacy.source_root, "rev-parse", "HEAD^{tree}") != _git(
        stash.source_root, "rev-parse", "HEAD^{tree}"
    )

    direct = build_git_project_template(tmp_path / "direct", "legacy-baseline")
    assert isinstance(direct, GitProjectTemplate)
    assert _git(direct.source_root, "status", "--porcelain") == ""


def test_policy_builders_use_templates_when_factory_is_explicit(
    tmp_path: Path,
) -> None:
    from tests.support.git_project_templates import GitProjectTemplateFactory

    factory = GitProjectTemplateFactory(tmp_path / "templates")
    before = factory.build_count

    assert callable(legacy_policy._write_committed_legacy_project)
    assert callable(stash_policy._write_tracked_project)
    assert callable(obstruction_policy._write_locked_full_stack_project)

    _write_committed_legacy_project(tmp_path / "legacy-one", template_factory=factory)
    _write_tracked_project(tmp_path / "stash-one", template_factory=factory)
    _write_locked_full_stack_project(
        tmp_path / "obstruction-one", template_factory=factory
    )
    after_first_round = factory.build_count

    _write_committed_legacy_project(tmp_path / "legacy-two", template_factory=factory)
    _write_tracked_project(tmp_path / "stash-two", template_factory=factory)
    _write_locked_full_stack_project(
        tmp_path / "obstruction-two", template_factory=factory
    )

    assert after_first_round == before + 3
    assert factory.build_count == after_first_round
