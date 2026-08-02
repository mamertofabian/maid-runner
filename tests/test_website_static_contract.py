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


def _contrast_ratio(first: str, second: str) -> float:
    def relative_luminance(color: str) -> float:
        channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            (
                channel / 12.92
                if channel <= 0.03928
                else ((channel + 0.055) / 1.055) ** 2.4
            )
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    first_luminance = relative_luminance(first)
    second_luminance = relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _css_color(stylesheet: str, selector: str) -> str:
    resolved_color = None
    for block in re.finditer(
        r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}", stylesheet, re.DOTALL
    ):
        selectors = {item.strip() for item in block.group("selectors").split(",")}
        if selector not in selectors:
            continue
        color = re.search(r"color:\s*(#[0-9a-fA-F]{6})", block.group("body"))
        if color is not None:
            resolved_color = color.group(1)
    assert resolved_color is not None, selector
    return resolved_color


def test_homepage_contract_exposes_product_story_and_primary_actions() -> None:
    homepage = _read(HOMEPAGE)

    assert "<!doctype html>" in homepage.lower()
    assert '<html lang="en">' in homepage
    assert '<meta name="viewport"' in homepage
    assert "<main" in homepage
    assert '<a class="skip-link" href="#main-content">' in homepage
    assert '<main id="main-content" tabindex="-1">' in homepage
    assert '<link rel="canonical" href="https://maidrunner.dev/">' in homepage
    assert '<meta property="og:title"' in homepage
    assert '<meta property="og:image"' in homepage
    assert 'content="https://maidrunner.dev/assets/social-card.png"' in homepage
    assert "MAID Runner" in homepage
    assert "Acceptance" in homepage
    assert "Structural" in homepage
    assert "Unit" in homepage

    for section_id in ("why-maid", "workflow", "quickstart"):
        assert f'id="{section_id}"' in homepage

    assert 'href="https://github.com/mamertofabian/maid-runner"' in homepage
    assert 'href="https://pypi.org/project/maid-runner/"' in homepage

    quickstart = homepage.split('id="quickstart"', 1)[1].split('class="final-cta"', 1)[
        0
    ]
    assert "pip install maid-runner" in quickstart
    assert "maid init" in quickstart
    assert "maid howto --section quickstart" in quickstart
    assert "maid verify" not in quickstart


def test_homepage_assets_are_local_responsive_and_progressively_enhanced() -> None:
    homepage = _read(HOMEPAGE)
    stylesheet = _read(WEBSITE / "styles.css")
    script = _read(WEBSITE / "script.js")

    for reference in re.findall(r'(?:href|src)="([^"]+)"', homepage):
        if reference.startswith(("#", "/", "http://", "https://", "mailto:")):
            continue
        assert (WEBSITE / reference).is_file(), reference

    stylesheet_references = re.findall(
        r'<link[^>]+rel="stylesheet"[^>]+href="([^"]+)"', homepage
    )
    script_references = re.findall(r'<script[^>]+src="([^"]+)"', homepage)
    assert all(
        not reference.startswith(("http://", "https://"))
        for reference in (*stylesheet_references, *script_references)
    )
    assert "fonts.googleapis.com" not in homepage
    assert "@media" in stylesheet
    assert ":focus-visible" in stylesheet
    assert "prefers-reduced-motion" in stylesheet
    assert "addEventListener" in script
    assert "aria-expanded" in script
    assert 'class="no-js"' in homepage
    assert 'classList.replace("no-js", "js")' in script
    assert "alert(" not in script
    assert "confirm(" not in script
    assert "prompt(" not in script
    assert "https://" not in script

    social_card = WEBSITE / "assets/social-card.png"
    assert social_card.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_mobile_navigation_covers_javascript_and_no_javascript_paths() -> None:
    homepage = _read(HOMEPAGE)
    stylesheet = _read(WEBSITE / "styles.css")
    script = _read(WEBSITE / "script.js")

    assert 'navigation.classList.toggle("is-open", !isOpen)' in script
    assert 'navigation.querySelectorAll("a")' in script
    assert 'link.addEventListener("click", () => closeNavigation(true))' in script
    assert "if (restoreFocus)" in script
    assert 'event.key !== "Escape"' in script
    assert 'toggle.getAttribute("aria-expanded") !== "true"' in script
    assert "toggle.focus()" in script
    assert 'aria-controls="primary-navigation"' in homepage
    for selector in (
        "body.js .primary-nav",
        "body.no-js .nav-toggle",
        "body.no-js .primary-nav",
        "body.js .primary-nav.is-open",
    ):
        assert selector in stylesheet


def test_light_surface_text_colors_meet_wcag_aa_contrast() -> None:
    stylesheet = _read(WEBSITE / "styles.css")
    muted = re.search(r"--muted:\s*(#[0-9a-fA-F]{6})", stylesheet)
    focus_light = re.search(r"--focus-light:\s*(#[0-9a-fA-F]{6})", stylesheet)
    focus_dark = re.search(r"--focus-dark:\s*(#[0-9a-fA-F]{6})", stylesheet)

    assert muted is not None and focus_light is not None and focus_dark is not None
    assert _contrast_ratio(muted.group(1), "#f4f1ea") >= 4.5
    for selector in (".card-number", ".card-tag", ".card-footer"):
        assert _contrast_ratio(_css_color(stylesheet, selector), "#f4f1ea") >= 4.5
    for selector in (".quote-label", ".quote-source"):
        assert _contrast_ratio(_css_color(stylesheet, selector), "#eae7df") >= 4.5
    assert _contrast_ratio(_css_color(stylesheet, ".footer-meta"), "#050a14") >= 4.5
    for selector in (".terminal-shell", ".terminal-comment"):
        assert _contrast_ratio(_css_color(stylesheet, selector), "#101c31") >= 4.5
    assert _contrast_ratio(_css_color(stylesheet, ".terminal-muted"), "#08111f") >= 4.5
    assert _contrast_ratio(focus_light.group(1), "#f4f1ea") >= 3
    assert _contrast_ratio(focus_dark.group(1), "#08111f") >= 3
    for surface in (
        ".hero",
        ".section-dark",
        ".final-cta",
        ".site-footer",
        ".not-found",
    ):
        assert f"{surface} :focus-visible" in stylesheet


def test_static_fallback_and_search_metadata_target_canonical_domain() -> None:
    fallback = _read(WEBSITE / "404.html")
    stylesheet = _read(WEBSITE / "styles.css")
    robots = _read(WEBSITE / "robots.txt")
    sitemap = _read(WEBSITE / "sitemap.xml")

    assert "404" in fallback
    assert 'href="/"' in fallback
    assert 'href="/styles.css"' in fallback
    assert 'href="/assets/logo.svg"' in fallback
    assert ".not-found :focus-visible" in stylesheet
    assert ".not-found .not-found-code" in fallback
    assert "Sitemap: https://maidrunner.dev/sitemap.xml" in robots

    root = ElementTree.fromstring(sitemap)
    locations = {
        element.text
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "loc"
    }
    assert locations == {"https://maidrunner.dev/"}
    assert 'href="https://maidrunner.dev/"' in _read(HOMEPAGE)


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
