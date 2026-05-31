import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs/troubleshooting.md"
README = ROOT / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_troubleshooting_guide_covers_common_issue_threshold() -> None:
    guide = _read(GUIDE)
    issue_headings = re.findall(r"^### \d+\. ", guide, flags=re.MULTILINE)

    assert len(issue_headings) >= 20
    assert guide.count("Symptom:") >= 20
    assert guide.count("Likely cause:") >= 20
    assert guide.count("Fix:") >= 20


def test_troubleshooting_guide_uses_real_diagnostics_and_workflows() -> None:
    guide = _read(GUIDE)

    for code in (
        "E001",
        "E003",
        "E004",
        "E102",
        "E103",
        "E112",
        "E114",
        "E115",
        "E200",
        "E210",
        "E230",
        "E300",
        "E301",
        "E303",
        "E306",
        "E307",
        "E308",
        "E310",
        "E311",
        "E320",
    ):
        assert code in guide

    for command in (
        "maid validate",
        "maid test",
        "maid verify",
        "maid chain log",
        "maid audit supersessions",
        "maid learn",
        "maid recall",
    ):
        assert command in guide


def test_troubleshooting_guide_includes_faq_and_readme_entrypoint() -> None:
    guide = _read(GUIDE)
    readme = _read(README)

    assert "## FAQ" in guide
    assert guide.count("### FAQ:") >= 5
    assert "docs/troubleshooting.md" in readme
