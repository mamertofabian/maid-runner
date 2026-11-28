"""Behavioral contract for the published PyPI download statistics.

The website's distribution section and the README publish download counts
recorded in website/data/download-stats.json. These tests pin that both
surfaces show floor-rounded values of the recorded counts, keep the source,
date, and automated-download caveats visible, and never present downloads as
users or installs.

The browser test requires the Chromium build for the installed Playwright
version:
    uv run playwright install chromium
"""

import contextlib
import functools
import html
import http.server
import json
import re
import threading
from collections.abc import Iterator
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
HOMEPAGE = WEBSITE / "index.html"
DOWNLOAD_STATS = WEBSITE / "data" / "download-stats.json"
README = ROOT / "README.md"

COUNT_KEYS = ("distributionDownloads", "packageManagerDownloads", "countries")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
WIDTHS = (280, 320, 390, 560, 820, 1000, 1440, 1920)
CLAIM_PATTERN = re.compile(
    r"\b\d[\d,.]*\s*K?\+?\s+(?:\w+\s+){0,2}"
    r"(?:users|installs|installations|developers|customers)\b",
    re.IGNORECASE,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _stats() -> dict:
    return json.loads(_read(DOWNLOAD_STATS))


def _text(markup: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", markup)).split())


def _distribution_section() -> str:
    homepage = _read(HOMEPAGE)
    match = re.search(r'<section\b[^>]*\bid="distribution"', homepage)
    assert match, 'website/index.html has a <section id="distribution">'
    end = homepage.find("</section>", match.start())
    return homepage[match.start() : end]


def _english_date(value: str) -> str:
    day = date.fromisoformat(value)
    return f"{MONTHS[day.month - 1]} {day.day}, {day.year}"


def _compact(count: int) -> str:
    if count >= 10_000:
        return f"{count // 1000}K+"
    if count >= 1000:
        return f"{count // 100 / 10:.1f}K+"
    return str(count)


def _readme_figure(count: int) -> str:
    if count >= 10_000:
        return f"{count // 1000 * 1000:,}+"
    if count >= 1000:
        return f"{count // 100 * 100:,}+"
    return str(count)


def test_download_stats_json_records_source_date_counts_and_caveats() -> None:
    stats = _stats()

    semantics = " ".join(stats["semantics"].values()).lower()

    assert "bigquery" in stats["source"].lower()
    assert "pypi" in stats["source"].lower()
    assert date.fromisoformat(stats["updatedAt"])
    for key in COUNT_KEYS:
        assert isinstance(stats["counts"][key], int) and stats["counts"][key] > 0
    assert (
        stats["counts"]["packageManagerDownloads"]
        <= stats["counts"]["distributionDownloads"]
    )
    assert "automated" in semantics
    assert "unique users" in semantics


def test_distribution_section_sits_between_hero_and_why_section() -> None:
    homepage = _read(HOMEPAGE)
    section = _distribution_section()

    position = homepage.index('id="distribution"')

    assert homepage.index('class="hero"') < position < homepage.index('id="why-maid"')
    assert "Open-source. Tool-agnostic. Built for reliability." in _text(section)


def test_distribution_tiles_show_floor_rounded_json_counts() -> None:
    stats = _stats()
    section = _distribution_section()

    shown = dict(
        re.findall(r'data-download-stat="(\w+)"[^>]*>\s*([^<]+?)\s*<', section)
    )
    expected = {key: _compact(stats["counts"][key]) for key in COUNT_KEYS}
    text = _text(section)

    assert shown == expected
    assert "MIT" in text and "Open-source license" in text
    for label in (
        "PyPI distribution downloads",
        "Package-manager downloads",
        "Countries in download records",
    ):
        assert label in text


def test_distribution_note_states_source_date_and_limits() -> None:
    stats = _stats()
    section = _distribution_section()

    text = _text(section)

    assert f'<time datetime="{stats["updatedAt"]}">' in section
    assert _english_date(stats["updatedAt"]) in text
    assert "PyPI public BigQuery dataset" in text
    assert "automated and repeated downloads" in text
    assert "not unique users" in text
    assert "No usage telemetry" in text


def test_distribution_section_links_github_and_pypi() -> None:
    section = _distribution_section()

    assert 'href="https://github.com/mamertofabian/maid-runner"' in section
    assert 'href="https://pypi.org/project/maid-runner/"' in section
    assert "View on GitHub" in _text(section)
    assert "View on PyPI" in _text(section)


def test_readme_has_download_badges_and_no_user_or_install_badges() -> None:
    readme = _read(README)

    badges = re.findall(r"\[!\[([^\]]*)\]\(([^)]*)\)\]\(([^)]*)\)", readme)
    alts = [alt.lower() for alt, _, _ in badges]

    assert (
        "PyPI Downloads",
        "https://static.pepy.tech/badge/maid-runner",
        "https://pepy.tech/project/maid-runner",
    ) in badges
    assert (
        "Monthly Downloads",
        "https://static.pepy.tech/badge/maid-runner/month",
        "https://pepy.tech/project/maid-runner",
    ) in badges
    assert not [
        alt for alt in alts if re.search(r"\b(users|installs|installations)\b", alt)
    ]


def test_readme_download_section_matches_json_with_caveats() -> None:
    stats = _stats()
    readme = _read(README)
    match = re.search(r"^## Downloads and privacy\n(.*?)(?=^## )", readme, re.M | re.S)
    assert match, "README.md has a '## Downloads and privacy' section"

    section = " ".join(match.group(1).split())
    counts = stats["counts"]

    assert (
        f"{_readme_figure(counts['distributionDownloads'])} distribution downloads"
        in section
    )
    assert f"{_readme_figure(counts['packageManagerDownloads'])}" in section
    assert f"{counts['countries']} countries" in section
    assert _english_date(stats["updatedAt"]) in section
    assert "PyPI public BigQuery dataset" in section
    assert "automated and repeated downloads" in section
    assert "not unique users" in section
    assert "pepy.tech" in section
    assert "no usage telemetry" in section.lower()


def test_page_and_readme_never_claim_users_installs_or_developers() -> None:
    page_text = _text(_read(HOMEPAGE).split('<main id="main-content"', 1)[1])
    readme = _read(README)

    claims = CLAIM_PATTERN.findall(page_text) + CLAIM_PATTERN.findall(readme)

    assert claims == []


_MEASURE_SCRIPT = """
() => {
  const section = document.querySelector("#distribution");
  if (!section) return null;
  const box = (el) => el.getBoundingClientRect();
  const s = box(section);
  const tiles = [...section.querySelectorAll(".distribution-stat")];
  const note = section.querySelector(".distribution-note");
  const visible = (el) => {
    const b = box(el);
    const style = getComputedStyle(el);
    return b.width > 0 && b.height > 0 && style.visibility === "visible" &&
      style.display !== "none" && Number(style.opacity) > 0;
  };
  return {
    tileCount: tiles.length,
    hiddenTiles: tiles.filter((el) => !visible(el)).length,
    noteVisible: Boolean(note && visible(note)),
    tilesOutside: tiles.filter((el) => {
      const b = box(el);
      return b.left < s.left - 1 || b.right > s.right + 1;
    }).length,
    overflowing: [...section.querySelectorAll(".distribution-stat, .distribution-stat *")]
      .filter((el) => el.clientWidth && el.scrollWidth > el.clientWidth + 1)
      .map((el) => el.className),
    pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
  };
}
"""


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextlib.contextmanager
def _site() -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(WEBSITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_distribution_tiles_render_inside_viewport_at_phone_and_desktop_widths() -> (
    None
):
    from playwright.sync_api import sync_playwright

    measurements: dict[int, dict | None] = {}
    with _site() as origin, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.url.startswith(origin)
                        else route.abort()
                    ),
                )
                page.goto(f"{origin}/index.html", wait_until="load")
                measurements[width] = page.evaluate(_MEASURE_SCRIPT)
                page.close()
        finally:
            browser.close()

    broken = {
        width: result
        for width, result in measurements.items()
        if result is None
        or result["tileCount"] != 4
        or result["hiddenTiles"]
        or not result["noteVisible"]
        or result["tilesOutside"]
        or result["overflowing"]
        or result["pageOverflow"] > 0
    }

    assert broken == {}, f"Distribution tiles must render fully on screen: {broken}"
