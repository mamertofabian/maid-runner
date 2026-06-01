import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/ci-cd-integration.md"
GITHUB_GUIDE = ROOT / "docs/github-actions.md"
README = ROOT / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fenced_blocks(markdown: str) -> list[str]:
    return re.findall(r"```(?:yaml|groovy|bash|sh)?\n(.*?)```", markdown, re.DOTALL)


def _markdown_links(markdown: str) -> list[tuple[str, str]]:
    return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", markdown)


def test_ci_cd_integration_guide_covers_required_platforms() -> None:
    guide = _read(GUIDE)
    github_guide = _read(GITHUB_GUIDE)

    assert "_ci_cd_integration_guide" in guide
    assert "docs/github-actions.md" in guide
    assert "_github_actions_setup_guide" in github_guide

    for heading in (
        "## GitHub Actions",
        "## GitLab CI",
        "## Jenkins",
        "## CircleCI",
        "## Generic CI/CD Template",
    ):
        assert heading in guide

    linked_paths = {
        text.strip("`"): GUIDE.parent.joinpath(target).resolve()
        for text, target in _markdown_links(guide)
        if text.strip("`").startswith("docs/")
    }
    assert linked_paths["docs/github-actions.md"] == GITHUB_GUIDE.resolve()
    assert linked_paths["docs/troubleshooting.md"].exists()


def test_ci_cd_integration_guide_includes_working_examples() -> None:
    guide = _read(GUIDE)
    examples = "\n".join(_fenced_blocks(guide))

    for platform_file in (
        ".github/workflows/maid-validation.yml",
        ".gitlab-ci.yml",
        "Jenkinsfile",
        ".circleci/config.yml",
    ):
        assert platform_file in guide

    for command in (
        "uv sync --group dev",
        "uv run maid verify --base-ref",
        "uv run maid test --json",
    ):
        assert command in examples

    for artifact in (
        ".maid/maid-verify.json",
        ".maid/maid-test.json",
        "coverage.xml",
    ):
        assert artifact in examples

    assert "CI_MERGE_REQUEST_TARGET_BRANCH_NAME" in examples
    assert "uv run maid verify --no-changed-scope --json" in examples


def test_ci_cd_integration_guide_documents_troubleshooting_and_best_practices() -> None:
    guide = _read(GUIDE)

    assert "## Troubleshooting" in guide
    assert "## Best Practices" in guide

    for topic in (
        "base ref",
        "dependency installation",
        "json artifacts",
        "command integrity",
        "validator warnings",
    ):
        assert topic in guide.lower()

    for practice in (
        "pin MAID Runner",
        "run `maid verify` before `maid test`",
        "upload `.maid/maid-verify.json`",
        "preserve `maid test --json` as the contract gate",
    ):
        assert practice in guide


def test_readme_links_ci_cd_integration_guides() -> None:
    readme = _read(README)

    assert "_ci_cd_integration_entrypoint" in readme
    assert "docs/ci-cd-integration.md" in readme
    assert "docs/github-actions.md" in readme
