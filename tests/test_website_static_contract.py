import re
from pathlib import Path
from xml.etree import ElementTree

import yaml


ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
HOMEPAGE = WEBSITE / "index.html"
WORKFLOW = ROOT / ".github/workflows/deploy-website.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow_trigger(workflow: dict) -> dict:
    """Read the YAML 1.2 `on` key across PyYAML loader versions."""
    return workflow.get("on", workflow.get(True, {}))


def test_homepage_matches_mockup_story_and_navigation() -> None:
    homepage = _read(HOMEPAGE)

    assert "<!doctype html>" in homepage.lower()
    assert '<html lang="en">' in homepage
    assert '<a class="skip-link" href="#main-content">' in homepage
    assert '<main id="main-content" tabindex="-1">' in homepage
    assert '<link rel="canonical" href="https://maidrunner.dev/">' in homepage
    assert "Make AI coding" in homepage
    assert "follow the plan" in homepage
    assert "Install MAID Runner" in homepage
    assert "Read the docs" in homepage
    assert "manifest.yaml" in homepage
    assert "maid validate" in homepage
    assert "HANDOFF READY" in homepage

    for section_id in ("why-maid", "workflow", "capabilities", "quickstart"):
        assert f'id="{section_id}"' in homepage

    for label in (
        "Why MAID Runner",
        "From plan to evidence",
        "Capabilities",
        "Works with your existing tools",
        "Quick start",
        "Build boldly. Verify honestly.",
    ):
        assert label in homepage

    for link in (
        'href="#why-maid"',
        'href="#workflow"',
        'href="#capabilities"',
        'href="#quickstart"',
        'href="https://github.com/mamertofabian/maid-runner"',
    ):
        assert link in homepage

    for label in (
        "Open source",
        "MIT licensed",
        "Python, TypeScript, JavaScript, Svelte",
        "Plan drift",
        "Test rewriting",
        "Scope expansion",
    ):
        assert label in homepage


def test_homepage_renders_workflow_capabilities_tools_and_quickstart() -> None:
    homepage = _read(HOMEPAGE)

    assert len(re.findall(r'class="workflow-step(?:\s|")', homepage)) == 7
    assert len(re.findall(r'class="capability-card(?:\s|")', homepage)) == 6

    for label in (
        "Plan",
        "Review",
        "Lock",
        "Prove red",
        "Implement",
        "Verify",
        "Learn",
    ):
        assert f"<h3>{label}</h3>" in homepage

    for tool in ("Claude Code", "Codex", "Cursor", "Windsurf", "Generic"):
        assert tool in homepage

    quickstart = homepage.split('id="quickstart"', 1)[1].split('class="final-cta"', 1)[
        0
    ]
    for command in (
        "pip install maid-runner",
        "maid init",
        "maid howto --section quickstart",
    ):
        assert command in quickstart
    assert "maid verify" not in quickstart
    assert "See the docs for detailed guides" in quickstart


def test_homepage_uses_final_local_brand_and_social_assets() -> None:
    homepage = _read(HOMEPAGE)
    stylesheet = _read(WEBSITE / "styles.css")
    script = _read(WEBSITE / "script.js")

    assert '<link rel="icon" href="assets/logo.png" type="image/png"' in homepage
    assert '<link rel="apple-touch-icon" href="assets/logo.png"' in homepage
    assert 'content="https://maidrunner.dev/assets/social-card.png"' in homepage
    assert homepage.count('src="assets/logo.png"') >= 2

    for reference in re.findall(r'(?:href|src)="([^"]+)"', homepage):
        if reference.startswith(("#", "/", "http://", "https://", "mailto:")):
            continue
        assert (WEBSITE / reference).is_file(), reference

    assert (WEBSITE / "assets/logo.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (
        (WEBSITE / "assets/social-card.png")
        .read_bytes()
        .startswith(b"\x89PNG\r\n\x1a\n")
    )
    for disposable in ("mockup-redesign.png", "logo.svg", "social-card-v2.png"):
        assert disposable not in homepage
        assert disposable not in stylesheet
        assert disposable not in script
        assert not (WEBSITE / "assets" / disposable).exists()


def test_mobile_navigation_covers_javascript_and_no_javascript_paths() -> None:
    homepage = _read(HOMEPAGE)
    stylesheet = _read(WEBSITE / "styles.css")
    script = _read(WEBSITE / "script.js")

    assert 'class="no-js"' in homepage
    assert 'aria-controls="primary-navigation"' in homepage
    assert 'navigation.classList.toggle("is-open", !isOpen)' in script
    assert 'navigation.querySelectorAll("a")' in script
    assert 'link.addEventListener("click", () => closeNavigation(true))' in script
    assert "if (restoreFocus)" in script
    assert 'event.key !== "Escape"' in script
    assert 'toggle.getAttribute("aria-expanded") !== "true"' in script
    assert "toggle.focus()" in script

    for selector in (
        "body.js .primary-nav",
        "body.no-js .nav-toggle",
        "body.no-js .primary-nav",
        "body.js .primary-nav.is-open",
    ):
        assert selector in stylesheet


def test_dark_surface_accessibility_contract_is_declared() -> None:
    stylesheet = _read(WEBSITE / "styles.css")

    for token in (
        "--bg:",
        "--surface:",
        "--text:",
        "--text-muted:",
        "--cyan:",
        "--green:",
        "--focus:",
    ):
        assert token in stylesheet

    assert "@media" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet
    assert ":focus-visible" in stylesheet

    for surface in (
        ".site-header :focus-visible",
        ".hero :focus-visible",
        ".section-dark :focus-visible",
        ".final-cta :focus-visible",
        ".site-footer :focus-visible",
        ".not-found :focus-visible",
    ):
        assert surface in stylesheet


def test_static_fallback_and_search_metadata_target_canonical_domain() -> None:
    homepage = _read(HOMEPAGE)
    fallback = _read(WEBSITE / "404.html")
    robots = _read(WEBSITE / "robots.txt")
    sitemap = _read(WEBSITE / "sitemap.xml")

    assert 'href="/"' in fallback
    assert 'href="/styles.css"' in fallback
    assert 'href="/assets/logo.png"' in fallback
    assert ".not-found .not-found-code" in fallback
    assert "404" in fallback
    assert "Sitemap: https://maidrunner.dev/sitemap.xml" in robots
    assert 'href="https://maidrunner.dev/"' in homepage

    root = ElementTree.fromstring(sitemap)
    locations = {
        element.text
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "loc"
    }
    assert locations == {"https://maidrunner.dev/"}


def test_pages_workflow_is_path_scoped_and_uploads_website_root() -> None:
    workflow = yaml.load(_read(WORKFLOW), Loader=yaml.BaseLoader)
    trigger = _workflow_trigger(workflow)
    push = trigger["push"]

    assert push["branches"] == ["main"]
    assert set(push["paths"]) == {
        "website/**",
        ".github/workflows/deploy-website.yml",
    }
    assert "workflow_dispatch" in trigger
    assert workflow["permissions"] == {
        "contents": "read",
        "pages": "write",
        "id-token": "write",
    }

    deploy_job = workflow["jobs"]["deploy"]
    steps = deploy_job["steps"]
    expected_actions = {
        "actions/checkout": "d23441a48e516b6c34aea4fa41551a30e30af803",
        "actions/configure-pages": "983d7736d9b0ae728b81ab479565c72886d7745b",
        "actions/upload-pages-artifact": "7b1f4a764d45c48632c6b24a0339c27f5614fb0b",
        "actions/deploy-pages": "d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e",
    }
    uses_steps = [step["uses"] for step in steps if "uses" in step]
    assert {uses.rsplit("@", 1)[0] for uses in uses_steps} == set(expected_actions)
    assert all(
        re.fullmatch(r"[0-9a-f]{40}", uses.rsplit("@", 1)[1]) for uses in uses_steps
    )

    for step in steps:
        uses = step.get("uses", "")
        if "@" not in uses:
            continue
        action, revision = uses.rsplit("@", 1)
        if action in expected_actions:
            assert revision == expected_actions[action]

    upload_step = next(
        step
        for step in steps
        if step.get("uses")
        == "actions/upload-pages-artifact@7b1f4a764d45c48632c6b24a0339c27f5614fb0b"
    )
    assert upload_step["with"]["path"] == "website"
    assert any(
        step.get("uses")
        == "actions/deploy-pages@d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e"
        for step in steps
    )
