import json
import re
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
HOMEPAGE = WEBSITE / "index.html"
PRACTICE_STATS = WEBSITE / "data" / "practice-stats.json"
VERCEL_CONFIG = ROOT / "vercel.json"
DEPLOYMENT_DOCS = WEBSITE / "README.md"
PAGES_WORKFLOW = ROOT / ".github/workflows/deploy-website.yml"
WORKFLOWS = ROOT / ".github/workflows"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_homepage_matches_mockup_story_and_navigation() -> None:
    homepage = _read(HOMEPAGE)

    assert "<!doctype html>" in homepage.lower()
    assert '<html lang="en">' in homepage
    assert '<a class="skip-link" href="#main-content">' in homepage
    assert '<main id="main-content" tabindex="-1">' in homepage
    assert '<link rel="canonical" href="https://maidrunner.dev/">' in homepage
    assert "Don't just trust AI code" in homepage
    assert "Verify it." in homepage
    assert "machine-checkable contract" in homepage
    assert "under Claude, Codex, Cursor, or any agent" in homepage
    assert "Install MAID Runner" in homepage
    assert "Read the docs" in homepage
    assert "manifest.yaml" in homepage
    assert "maid validate" in homepage
    assert "HANDOFF READY" in homepage

    for section_id in (
        "why-maid",
        "workflow",
        "capabilities",
        "maid-in-practice",
        "quickstart",
    ):
        assert f'id="{section_id}"' in homepage

    for label in (
        "Why MAID Runner",
        "From plan to evidence",
        "Capabilities",
        "MAID in practice",
        "The tool is developed under the rules it enforces.",
        "Works with your existing tools",
        "Quick start",
        "Build boldly. Verify honestly.",
    ):
        assert label in homepage

    for link in (
        'href="#why-maid"',
        'href="#workflow"',
        'href="#capabilities"',
        'href="#maid-in-practice"',
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


def test_homepage_leads_with_core_strengths() -> None:
    homepage = _read(HOMEPAGE)

    # The page leads with what makes MAID different, not a single "follow the
    # plan" note: it governs the artifacts agents produce, across any harness.
    assert "Governs the artifacts your agents produce" in homepage
    assert "not just the prompts they follow" in homepage

    for strength in (
        "Machine-checkable contracts",
        "Tamper-evident planning",
        "Portable across agents",
        "Evidence-backed handoff",
    ):
        assert strength in homepage

    # The superseded single-note headline must not linger in the hero or the
    # social/search metadata.
    assert "Make AI coding follow the plan" not in homepage


def test_homepage_surfaces_knockout_strength() -> None:
    homepage = _read(HOMEPAGE)

    # Differential knockout is surfaced as a strength: deep verification can
    # delete a declared function's body and require the tests to fail, proving
    # the tests exercise the code rather than just executing a line. This is the
    # README-documented --knockout gate, presented without over-promising.
    assert "Proven, not just covered" in homepage
    assert "delete a function's body and require your tests to fail" in homepage

    # The "test rewriting" answer names the knockout defense, so a gutted test
    # that no longer asserts anything cannot quietly pass.
    assert "knock out the code to confirm a test actually fails without it" in homepage


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


def test_homepage_renders_maid_in_practice_section() -> None:
    homepage = _read(HOMEPAGE)
    stats = json.loads(_read(PRACTICE_STATS))
    practice = homepage.split('id="maid-in-practice"', 1)[1].split(
        'id="quickstart"', 1
    )[0]

    assert "MAID Runner is not only a workflow we recommend" in practice
    assert "The framework dogfoods itself." in practice
    assert (
        "manifest → plan lock → red evidence → implementation → review → outcome"
        in practice
    )
    assert "Strict verification" in practice
    assert "required before handoff" in practice

    runner = stats["maidRunner"]
    csharp = stats["csharpValidator"]
    for value in (
        runner["manifests"],
        runner["tests"],
        runner["maidCommandGroups"],
        csharp["manifests"],
        csharp["tests"],
    ):
        assert str(value) in practice

    assert "validated manifests" in practice
    assert "passing tests" in practice
    assert "MAID validation command groups" in practice
    assert "MAID Validator for C#" in practice
    assert "A separate plugin developed under MAID." in practice
    assert "Python 3.10–3.14" in practice
    assert "Private production projects" in practice
    assert "Used beyond demonstration repositories." in practice
    assert "Real projects. Real constraints. Private by design." in practice
    assert "Built something with MAID?" in practice

    for phrase in (
        "scoped feature and maintenance work",
        "plan review before implementation",
        "test-driven changes with red evidence",
        "independent AI-assisted implementation review",
        "evidence-backed handoff before merge or release",
    ):
        assert phrase in practice

    assert (
        'href="https://github.com/mamertofabian/maid-runner/tree/main/manifests"'
        in practice
    )
    assert 'href="https://github.com/mamertofabian/maid-validator-csharp"' in practice
    assert (
        'href="https://github.com/mamertofabian/maid-runner/issues/new?title=Showcase%3A%20"'
        in practice
    )
    assert "Explore the MAID Runner manifests" in practice
    assert "View the C# validator on GitHub" in practice
    assert "Share your project" in practice

    for excluded in ("maid-runner-mcp", "vscode-maid", "maid-lsp"):
        assert excluded not in practice

    stylesheet = _read(WEBSITE / "styles.css")
    for selector in (
        ".practice-section",
        ".practice-featured-card",
        ".practice-workflow-rail",
        ".practice-stats",
        ".practice-secondary-grid",
        ".practice-private-icon",
        ".practice-share",
    ):
        assert selector in stylesheet


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
        ".practice-section :focus-visible",
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


def test_vercel_is_the_only_declared_website_deployment() -> None:
    config = json.loads(_read(VERCEL_CONFIG))
    deployment_docs = _read(DEPLOYMENT_DOCS)
    homepage = _read(HOMEPAGE)
    fallback = _read(WEBSITE / "404.html")
    robots = _read(WEBSITE / "robots.txt")
    sitemap = _read(WEBSITE / "sitemap.xml")

    assert config == {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "outputDirectory": "website",
    }
    assert not PAGES_WORKFLOW.exists()

    pages_markers = (
        "actions/configure-pages",
        "actions/upload-pages-artifact",
        "actions/deploy-pages",
        "pages: write",
        "github-pages",
    )
    for workflow in (*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")):
        content = _read(workflow)
        for marker in pages_markers:
            assert marker not in content, (workflow, marker)

    for crawl_surface in (homepage, fallback, robots, sitemap):
        assert "http://maidrunner.dev" not in crawl_surface
        assert "://www.maidrunner.dev" not in crawl_surface

    for phrase in (
        "Vercel",
        "https://maidrunner.dev/",
        "Root Directory",
        "Output Directory",
        '"website"',
        "Page with redirect",
        "www",
        "HTTP",
        "308",
    ):
        assert phrase in deployment_docs

    assert "GitHub Pages" in deployment_docs
    assert "Deleting the workflow does not disable GitHub Pages" in deployment_docs
    assert "Settings → Pages" in deployment_docs
