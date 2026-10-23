import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE = ROOT / "website" / "index.html"

PROBLEM_TITLES = (
    "Plan drift",
    "Test rewriting",
    'Self-reported "done"',
    "Rules that live in one tool",
)


def _homepage() -> str:
    return HOMEPAGE.read_text(encoding="utf-8")


def _section(homepage: str, section_id: str) -> str:
    """The markup of one top-level section, from its id to the next section."""
    start = homepage.index(f'id="{section_id}"')
    end = homepage.find("<section", start)
    return homepage[start : end if end != -1 else len(homepage)]


def _text(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def test_why_section_pairs_four_problems_with_their_answers() -> None:
    why = _section(_homepage(), "why-maid")
    cards = re.split(r'<article\b[^>]*\bclass="[^"]*\bproblem-card\b[^"]*"', why)[1:]

    titles = []
    for card in cards:
        title = re.search(r"<h3[^>]*>(.*?)</h3>", card, re.S)
        assert title, "every problem card has a heading"
        titles.append(
            _text(html.unescape(title.group(1))).replace("“", '"').replace("”", '"')
        )
    answers = [
        (
            _text(card.split('class="problem-answer"', 1)[1])
            if "problem-answer" in card
            else ""
        )
        for card in cards
    ]

    assert "Governs the artifacts your agents produce" in why
    assert "not just the prompts they follow" in why
    assert titles == list(PROBLEM_TITLES)
    assert all(answers), "every problem names MAID's answer"
    assert "plan lock" in answers[0] and "declared files" in answers[0]
    assert "can't quietly rewrite" in answers[0]
    assert "only declared files and operations are allowed" in answers[0]
    assert "fail before the change" in answers[1]
    assert "delete a function's body and require your tests to fail" in answers[1]
    assert "Python, opt-in" in answers[1]
    assert "Structure, behavior, and scope are verified" in answers[2]
    assert "independently reviewed" in answers[2]
    assert "manifest is the contract" in answers[3]
    assert "deterministic, AST-level contract" in answers[3]
    assert "not prose an agent reinterprets" in answers[3]
    assert "or any harness" in answers[3]
    for tool in ("Claude Code", "Codex", "Cursor", "Windsurf"):
        assert tool in _text(cards[3])


def test_homepage_states_each_differentiator_in_one_place() -> None:
    # Page body only: social metadata in <head> summarizes the product and is
    # outside this change.
    homepage = _homepage().split('<main id="main-content"', 1)[1]

    assert 'class="strengths"' not in homepage
    assert "strength-card" not in homepage
    assert 'id="capabilities"' not in homepage
    assert "capability-card" not in homepage
    assert 'href="#capabilities"' not in homepage
    for retired_title in (
        "Machine-checkable contracts",
        "Plan locks",
        "Scope enforcement",
        "Tamper-evident planning",
        "Portable across agents",
        "Evidence-backed handoff",
        "Proven, not just covered",
        "Scope expansion",
        "Three-stream validation",
        "Outcome learning",
    ):
        assert retired_title not in homepage
    for claim in (
        "delete a function's body",
        "plan lock becomes the contract",
        "independently reviewed before handoff",
        "Tests must fail before the change",
        "deterministic, AST-level contract",
    ):
        assert homepage.count(claim) == 1, claim


def test_navigation_and_sections_put_quick_start_after_the_workflow() -> None:
    homepage = _homepage()
    nav = homepage.split('id="primary-navigation"', 1)[1].split("</nav>", 1)[0]
    in_page_links = re.findall(r'href="#([\w-]+)"', nav)
    section_order = sorted(
        ("why-maid", "workflow", "quickstart", "maid-in-practice"),
        key=lambda section_id: homepage.index(f'id="{section_id}"'),
    )

    assert in_page_links == ["why-maid", "workflow", "quickstart", "maid-in-practice"]
    assert section_order == in_page_links
    assert homepage.index('id="maid-in-practice"') < homepage.index('class="final-cta"')
