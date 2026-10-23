"""Browser integration contract for the website's rendered typography.

These tests render the static site in headless Chromium and assert on the
computed styles the browser actually applies, instead of parsing CSS source.
Runtime evidence covers the cascade, custom properties, media queries,
pseudo-elements, transforms, zoom, and font adjustments without modelling them.

Requires the Chromium build for the installed Playwright version:
    uv run playwright install chromium
"""

import functools
import http.server
import threading
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"

INDEX = "/index.html"
NOT_FOUND = "/404.html"

# Both edges and the middle of every stylesheet breakpoint band
# (<=560, <=820, <=1000, wide), plus small-phone and large-desktop widths.
VIEWPORT_WIDTHS = (
    280,
    320,
    390,
    560,
    561,
    700,
    820,
    821,
    900,
    1000,
    1001,
    1440,
    1920,
)

# Every conditional group the stylesheet may use. Pinning the set (read from
# the browser's own CSSOM) means no condition the widths above cannot reach,
# such as a touch-only or ultra-wide query, can hide undersized text.
ALLOWED_CONDITIONS = {
    "@media (hover: hover)",
    "@media (max-width: 1000px)",
    "@media (max-width: 820px)",
    "@media (max-width: 560px)",
    "@media (prefers-reduced-motion: reduce)",
}

TEXT_FLOOR_PX = 12.0
BODY_COPY_FLOOR_PX = 15.0
TRACKING_FLOOR_EM = -0.04
SIZE_TOLERANCE_PX = 0.01
TRACKING_TOLERANCE_EM = 0.0005

BODY_COPY_SELECTORS = {
    INDEX: (
        ".hero-lede",
        ".problem-card p",
        ".problem-answer",
        ".workflow-step p",
        ".practice-intro p:not(.practice-tagline)",
        ".practice-featured-card > p:not(.practice-kicker):not(.practice-workflow-rail)",
        ".practice-card > p:not(.practice-kicker):not(.practice-private-closing)",
        ".practice-private-list li",
        ".practice-private-closing",
        ".practice-share-note",
        ".quickstart-copy p",
    ),
    NOT_FOUND: (".not-found p:not(.not-found-code)",),
}
# The violet label inside each problem answer is a label, held to the 12px floor.
BODY_COPY_LABELS = ".problem-answer span"

DISPLAY_HEADING_SELECTORS = (".hero h1", ".section h2", ".final-cta h2")

SMALL_CAPS_FEATURES = ("smcp", "c2sc", "pcap", "c2pc")


class Scenario(NamedTuple):
    path: str
    width: int
    mode: str  # "desktop", "touch", "no-js", "reduced-motion", or "nav-open"
    height: int = 900


_MEASURE_SCRIPT = """
({bodySelectors, bodyLabels, headingSelectors}) => {
  const describe = (el) => {
    const id = el.id ? `#${el.id}` : "";
    const cls = el.classList.length ? `.${[...el.classList].join(".")}` : "";
    return `${el.tagName.toLowerCase()}${id}${cls}`;
  };
  const ownText = (el) =>
    [...el.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .map((node) => node.textContent)
      .join("")
      .trim();
  // Rendered scale from layout box versus painted box. offsetWidth and
  // offsetHeight are rounded to whole pixels, so a dimension within 1px of its
  // layout size is treated as unscaled; real shrinking moves it much further.
  const renderScale = (el) => {
    const rect = el.getBoundingClientRect();
    const scales = [];
    for (const [painted, layout] of [
      [rect.width, el.offsetWidth],
      [rect.height, el.offsetHeight],
    ]) {
      if (layout > 0 && painted > 0 && Math.abs(painted - layout) > 1) {
        scales.push(painted / layout);
      }
    }
    return scales.length ? Math.min(...scales) : 1;
  };
  const sample = (el, pseudo, scale) => {
    const style = getComputedStyle(el, pseudo);
    const fontSize = parseFloat(style.fontSize);
    const spacing = style.letterSpacing === "normal" ? 0 : parseFloat(style.letterSpacing);
    return {
      element: describe(el) + (pseudo || ""),
      text: ownText(el).slice(0, 40),
      fontSize,
      renderedSize: fontSize * scale,
      trackingEm: fontSize ? spacing / fontSize : 0,
      fontSizeAdjust: style.fontSizeAdjust,
      fontVariantCaps: style.fontVariantCaps,
      fontFeatureSettings: style.fontFeatureSettings,
    };
  };
  const hasGeneratedText = (el, pseudo) => {
    const content = getComputedStyle(el, pseudo).content;
    return !["none", "normal", '""', "''"].includes(content);
  };
  const measure = (el) => {
    const scale = renderScale(el);
    const samples = [];
    if (ownText(el)) {
      samples.push(sample(el, null, scale));
      samples.push(sample(el, "::first-line", scale));
      samples.push(sample(el, "::first-letter", scale));
    }
    for (const pseudo of ["::before", "::after"]) {
      if (hasGeneratedText(el, pseudo)) samples.push(sample(el, pseudo, scale));
    }
    const box = getComputedStyle(el);
    if (box.display === "list-item" && box.listStyleType !== "none") {
      samples.push(sample(el, "::marker", scale));
    }
    return samples;
  };

  const elements = [...document.body.querySelectorAll("*")].filter(
    (el) => !["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(el.tagName)
  );
  const text = elements.flatMap(measure);

  const labels = new Set(document.querySelectorAll(bodyLabels));
  const bodyCopy = {};
  for (const selector of bodySelectors) {
    const roots = [...document.querySelectorAll(selector)];
    const members = roots.flatMap((root) => [root, ...root.querySelectorAll("*")]);
    bodyCopy[selector] = members
      .filter((el) => ownText(el) && !labels.has(el))
      .flatMap(measure);
  }

  const headings = {};
  for (const selector of headingSelectors) {
    headings[selector] = [...document.querySelectorAll(selector)].map((el) => {
      const style = getComputedStyle(el);
      return {
        element: describe(el),
        text: el.textContent.trim().slice(0, 40),
        wrapStyle: style.getPropertyValue("text-wrap-style"),
        wrapMode: style.getPropertyValue("text-wrap-mode"),
      };
    });
  }

  const conditions = [];
  const fontFaceAdjustments = [];
  const visit = (rules) => {
    for (const rule of rules) {
      if (rule instanceof CSSFontFaceRule) {
        const adjust = rule.style.getPropertyValue("size-adjust");
        if (adjust && adjust !== "100%") fontFaceAdjustments.push(rule.cssText);
      } else if (rule instanceof CSSMediaRule) {
        conditions.push(`@media ${rule.conditionText}`);
      } else if (rule instanceof CSSStyleRule) {
        // Plain style rule; any nested rules are visited below.
      } else if (
        (typeof CSSGroupingRule !== "undefined" && rule instanceof CSSGroupingRule) ||
        (typeof CSSImportRule !== "undefined" && rule instanceof CSSImportRule) ||
        (typeof CSSLayerStatementRule !== "undefined" && rule instanceof CSSLayerStatementRule)
      ) {
        const text = rule.cssText;
        conditions.push((text.includes("{") ? text.slice(0, text.indexOf("{")) : text).trim());
      }
      if (rule.cssRules) visit(rule.cssRules);
    }
  };
  for (const sheet of document.styleSheets) visit(sheet.cssRules);

  return { text, bodyCopy, headings, conditions, fontFaceAdjustments };
}
"""


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def _scenarios() -> list[Scenario]:
    scenarios = [
        Scenario(path, width, "desktop")
        for path in (INDEX, NOT_FOUND)
        for width in VIEWPORT_WIDTHS
    ]
    scenarios += [
        Scenario(path, width, mode)
        for path in (INDEX, NOT_FOUND)
        for width, mode in (
            (390, "touch"),
            (390, "no-js"),
            (1440, "no-js"),
            (390, "reduced-motion"),
            (1440, "reduced-motion"),
        )
    ]
    # A landscape phone: short viewport, touch input.
    scenarios += [Scenario(path, 844, "touch", 390) for path in (INDEX, NOT_FOUND)]
    scenarios.append(Scenario(INDEX, 390, "nav-open"))
    return scenarios


def _measure_all(website: Path) -> dict[Scenario, dict]:
    """Render every scenario in headless Chromium and return its measurements."""
    from playwright.sync_api import sync_playwright

    handler = functools.partial(_QuietHandler, directory=str(website))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    arguments = {
        "bodyLabels": BODY_COPY_LABELS,
        "headingSelectors": list(DISPLAY_HEADING_SELECTORS),
    }
    measurements: dict[Scenario, dict] = {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for scenario in _scenarios():
                    context = browser.new_context(
                        viewport={"width": scenario.width, "height": scenario.height},
                        is_mobile=scenario.mode == "touch",
                        has_touch=scenario.mode == "touch",
                        java_script_enabled=scenario.mode != "no-js",
                        reduced_motion=(
                            "reduce"
                            if scenario.mode == "reduced-motion"
                            else "no-preference"
                        ),
                    )
                    context.route(
                        "**/*",
                        lambda route: (
                            route.continue_()
                            if route.request.url.startswith(origin)
                            else route.abort()
                        ),
                    )
                    page = context.new_page()
                    page.goto(origin + scenario.path, wait_until="load")
                    if scenario.mode == "nav-open":
                        page.click(".nav-toggle")
                        page.wait_for_selector(".primary-nav.is-open")
                    measurements[scenario] = page.evaluate(
                        _MEASURE_SCRIPT,
                        {
                            **arguments,
                            "bodySelectors": list(BODY_COPY_SELECTORS[scenario.path]),
                        },
                    )
                    context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    return measurements


_rendered_cache: dict[Path, dict[Scenario, dict]] = {}


def _rendered(website: Path | None = None) -> dict[Scenario, dict]:
    """Measurements for a website directory, rendered once per test session."""
    website = website or WEBSITE
    if website not in _rendered_cache:
        _rendered_cache[website] = _measure_all(website)
    return _rendered_cache[website]


def test_no_rendered_text_is_smaller_than_twelve_pixels() -> None:
    rendered = _rendered()

    unexpected_conditions = sorted(
        {
            condition
            for page in rendered.values()
            for condition in page["conditions"]
            if condition not in ALLOWED_CONDITIONS
        }
    )
    undersized = [
        (*scenario, item["element"], item["text"], round(item["renderedSize"], 2))
        for scenario, page in rendered.items()
        for item in page["text"]
        if min(item["fontSize"], item["renderedSize"])
        < TEXT_FLOOR_PX - SIZE_TOLERANCE_PX
    ]
    shrunk = [
        (*scenario, item["element"], item["fontSizeAdjust"], item["fontVariantCaps"])
        for scenario, page in rendered.items()
        for item in page["text"]
        if item["fontSizeAdjust"] != "none"
        or item["fontVariantCaps"] != "normal"
        or any(
            feature in item["fontFeatureSettings"] for feature in SMALL_CAPS_FEATURES
        )
    ] + [
        (*scenario, rule)
        for scenario, page in rendered.items()
        for rule in page["fontFaceAdjustments"]
    ]

    assert all(page["text"] for page in rendered.values()), "every page renders text"
    assert unexpected_conditions == [], (
        "The stylesheet may only use the pinned conditional groups that the "
        f"rendered widths cover: {unexpected_conditions}"
    )
    assert shrunk == [], (
        "Text must not be visually shrunk through font-size-adjust, small caps, "
        f"or @font-face size-adjust: {shrunk}"
    )
    assert undersized == [], (
        f"Every piece of text must render at {TEXT_FLOOR_PX:g}px or larger in "
        f"every scenario: {undersized}"
    )


def test_body_copy_renders_at_the_reading_floor() -> None:
    rendered = _rendered()

    for scenario, page in rendered.items():
        for selector in BODY_COPY_SELECTORS[scenario.path]:
            items = page["bodyCopy"][selector]
            undersized = [
                (item["element"], item["text"], round(item["renderedSize"], 2))
                for item in items
                if min(item["fontSize"], item["renderedSize"])
                < BODY_COPY_FLOOR_PX - SIZE_TOLERANCE_PX
            ]

            assert items, f"{selector} must match rendered copy in {scenario}"
            assert undersized == [], (
                f"{selector} renders below {BODY_COPY_FLOOR_PX:g}px in {scenario}: "
                f"{undersized}"
            )


def test_rendered_tracking_never_tightens_past_the_legibility_floor() -> None:
    rendered = _rendered()

    too_tight = [
        (*scenario, item["element"], item["text"], round(item["trackingEm"], 4))
        for scenario, page in rendered.items()
        for item in page["text"]
        if item["trackingEm"] < TRACKING_FLOOR_EM - TRACKING_TOLERANCE_EM
    ]

    assert too_tight == [], (
        f"Letter-spacing tighter than {TRACKING_FLOOR_EM}em collapses glyphs such "
        f'as the apostrophe in "Don\'t": {too_tight}'
    )


def test_display_headings_render_with_balanced_wrapping() -> None:
    rendered = _rendered()

    for scenario, page in rendered.items():
        if scenario.path != INDEX:
            continue
        for selector in DISPLAY_HEADING_SELECTORS:
            headings = page["headings"][selector]
            unbalanced = [
                heading
                for heading in headings
                if heading["wrapStyle"] != "balance" or heading["wrapMode"] != "wrap"
            ]

            assert headings, f"{selector} must render in {scenario}"
            assert unbalanced == [], (
                f"{selector} must wrap with text-wrap: balance in {scenario} so no "
                f"headline leaves an orphaned word: {unbalanced}"
            )


def test_maid_runner_ci_installs_chromium_before_running_website_tests() -> None:
    import yaml

    workflows = ROOT / ".github" / "workflows"
    jobs = {
        "maid-test.yml": ("maid-test", "Run MAID test contract"),
        "maid-validation.yml": ("maid-validation", "Run MAID validation gate"),
        "publish.yml": ("test", "Run MAID tests"),
    }
    install_command = "uv run playwright install --with-deps chromium"
    inline_guard = '[[ "${{ github.repository }}" == "mamertofabian/maid-runner" ]]'
    step_guards = {
        "github.repository == 'mamertofabian/maid-runner'",
        "${{ github.repository == 'mamertofabian/maid-runner' }}",
    }

    for filename, (job_name, test_step) in jobs.items():
        workflow = yaml.safe_load((workflows / filename).read_text(encoding="utf-8"))
        triggers = workflow.get(True) or workflow.get("on") or {}
        steps = workflow["jobs"][job_name]["steps"]
        names = [step.get("name", "") for step in steps]
        installs = [
            (index, step)
            for index, step in enumerate(steps)
            if install_command
            in [line.strip() for line in step.get("run", "").splitlines()]
        ]

        assert installs, f"{filename} must install Chromium for browser tests"
        index, step = installs[0]
        assert index < names.index(
            test_step
        ), f"{filename} must install Chromium before {test_step!r}"
        if "workflow_call" in triggers:
            gated = (
                f"if {inline_guard}; then"
                in [line.strip() for line in step.get("run", "").splitlines()]
                or str(step.get("if", "")).strip() in step_guards
            )
            assert gated, (
                f"reusable {filename} must only install Chromium for maid-runner "
                "itself, not for downstream repositories"
            )
