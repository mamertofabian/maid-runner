"""Regression tests for release workflow prerequisites."""

from __future__ import annotations

from pathlib import Path

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


def _run_steps_for_job(workflow_path: Path, job_name: str) -> list[str]:
    workflow = yaml.safe_load(workflow_path.read_text())
    steps = workflow["jobs"][job_name]["steps"]
    return [step["run"] for step in steps if "run" in step]


def test_publish_workflow_installs_npm_dependencies_before_maid_tests() -> None:
    runs = _run_steps_for_job(Path(".github/workflows/publish.yml"), "test")

    npm_install_index = runs.index("npm ci")
    maid_test_index = runs.index("uv run maid test")
    full_pytest_index = runs.index("uv run python -m pytest tests/ -v")

    assert npm_install_index < maid_test_index
    assert npm_install_index < full_pytest_index


def test_package_data_includes_claude_skills() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    package_data = pyproject["tool"]["setuptools"]["package-data"]["maid_runner"]
    claude_skills = [item for item in package_data if item.startswith("claude/skills/")]
    claude_agent_payload = [
        item for item in package_data if item.startswith("claude/agents/")
    ]

    assert "claude/skills/*/SKILL.md" in claude_skills
    assert claude_agent_payload == ["claude/agents/*.md"]
    assert "claude/commands/*.md" not in package_data


def test_python_310_tomli_fallback_dependency_is_locked() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    dev_dependencies = pyproject["dependency-groups"]["dev"]
    tomli_dev_dependency = any(
        dependency.startswith("tomli>=") for dependency in dev_dependencies
    )
    tomli_lock_entry = "tomli" in Path("uv.lock").read_text()

    assert tomli_dev_dependency
    assert tomli_lock_entry


def test_claude_manifest_and_docs_describe_maid_skill_distribution() -> None:
    manifest = yaml.safe_load(Path(".claude/manifest.json").read_text())
    generated_manifest = yaml.safe_load(
        Path("maid_runner/claude/manifest.json").read_text()
    )
    skills_distributable = manifest["skills"]["distributable"]
    agents_distributable = manifest["agents"]["distributable"]
    commands_distributable = manifest["commands"]["distributable"]
    generated_agents_distributable = generated_manifest["agents"]["distributable"]
    generated_commands_distributable = generated_manifest["commands"]["distributable"]
    maid_planner_skill = "maid-planner" in skills_distributable
    maid_plan_review_skill = "maid-plan-review" in skills_distributable
    maid_implementer_skill = "maid-implementer" in skills_distributable
    maid_implementation_review_skill = (
        "maid-implementation-review" in skills_distributable
    )
    maid_evolver_skill = "maid-evolver" in skills_distributable
    maid_auditor_skill = "maid-auditor" in skills_distributable
    maid_incident_logger_skill = "maid-incident-logger" in skills_distributable
    maid_implementation_reviewer_agent = Path(
        ".claude/agents/maid-implementation-reviewer.md"
    )
    maid_skills_workflow = Path("CLAUDE.md").read_text()
    repo_level_claude_install = Path("README.md").read_text()
    current_maid_skill_distribution = Path("docs/agent-skills.md").read_text()

    assert not Path("skills").exists()
    assert agents_distributable == ["maid-implementation-reviewer.md"]
    assert commands_distributable == []
    assert generated_agents_distributable == ["maid-implementation-reviewer.md"]
    assert generated_commands_distributable == []
    assert maid_planner_skill
    assert maid_plan_review_skill
    assert maid_implementer_skill
    assert maid_implementation_review_skill
    assert maid_evolver_skill
    assert maid_auditor_skill
    assert maid_incident_logger_skill
    assert maid_implementation_reviewer_agent.is_file()
    assert "maid skills workflow" in maid_skills_workflow.lower()
    assert "repo-level Claude install" in repo_level_claude_install
    assert "current MAID skill distribution" in current_maid_skill_distribution
    assert ".claude/skills/" in current_maid_skill_distribution
