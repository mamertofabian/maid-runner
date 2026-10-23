"""Browser integration contract for the MAID in practice section on phones.

Renders website/index.html in headless Chromium at phone through desktop
widths and measures the rendered geometry a visitor sees.

Requires the Chromium build for the installed Playwright version:
    uv run playwright install chromium
"""

import contextlib
import functools
import http.server
import threading
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"

WIDTHS = (280, 320, 390, 560, 561, 700, 820, 821, 1000, 1001, 1440, 1920)
PHONE_WIDTHS = (280, 320, 390, 560)

_MEASURE_SCRIPT = """
() => {
  const box = (el) => el.getBoundingClientRect();
  const overlap = (a, b) =>
    Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) *
    Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const card = document.querySelector(".practice-card-private");
  const icon = document.querySelector(".practice-card-private .practice-private-icon");
  const heading = document.querySelector(".practice-card-private h3");
  const stats = [...document.querySelectorAll(".practice-featured-card .practice-stat")];
  const grids = [...document.querySelectorAll(".practice-stats")];
  const outside = grids.flatMap((grid) => {
    const g = box(grid);
    return [...grid.querySelectorAll(".practice-stat")]
      .filter((el) => {
        const b = box(el);
        return b.left < g.left - 1 || b.right > g.right + 1;
      })
      .map((el) => el.textContent.trim().slice(0, 30));
  });
  const overflowing = [...document.querySelectorAll(".practice-stat, .practice-stat *")]
    .filter((el) => el.clientWidth && el.scrollWidth > el.clientWidth + 1)
    .map((el) => el.className);
  const iconBox = icon ? box(icon) : null;
  const iconStyle = icon ? getComputedStyle(icon) : null;
  return {
    hasIcon: Boolean(card && icon && heading),
    iconHeadingOverlap: icon && heading ? overlap(iconBox, box(heading)) : null,
    iconVisible: Boolean(
      iconStyle && iconStyle.display !== "none" && iconStyle.visibility === "visible"
    ),
    iconSize: iconBox ? [Math.round(iconBox.width), Math.round(iconBox.height)] : null,
    iconInsideCardAboveHeading: Boolean(
      iconBox &&
        iconBox.top >= box(card).top - 0.5 &&
        iconBox.bottom <= box(heading).top + 0.5
    ),
    statCount: stats.length,
    statRows: new Set(stats.map((el) => Math.round(box(el).top))).size,
    compactRows: [...document.querySelectorAll(".practice-stats-compact")].map(
      (grid) =>
        new Set(
          [...grid.querySelectorAll(".practice-stat")].map((el) => Math.round(box(el).top))
        ).size
    ),
    statsOutsideGrid: outside,
    pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
    overflowing,
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


def _measure(widths: tuple[int, ...]) -> dict[int, dict]:
    from playwright.sync_api import sync_playwright

    measurements: dict[int, dict] = {}
    with _site() as origin, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for width in widths:
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
    return measurements


def test_private_projects_icon_never_covers_its_heading() -> None:
    measurements = _measure(WIDTHS)

    covered = {
        width: result["iconHeadingOverlap"]
        for width, result in measurements.items()
        if result["iconHeadingOverlap"]
    }

    misplaced = {
        width: (result["iconVisible"], result["iconSize"])
        for width, result in measurements.items()
        if not (
            result["iconVisible"]
            and result["iconSize"][0] >= 24
            and result["iconSize"][1] >= 28
            and result["iconInsideCardAboveHeading"]
        )
    }

    assert all(result["hasIcon"] for result in measurements.values())
    assert misplaced == {}, (
        "The shield icon must stay visible at full size, inside its card and "
        f"above the heading: {misplaced}"
    )
    assert covered == {}, (
        "The private-projects shield icon overlaps its heading (px² by width): "
        f"{covered}"
    )


def test_featured_practice_stats_fit_in_two_rows_on_phones() -> None:
    measurements = _measure(PHONE_WIDTHS)

    too_tall = {
        width: result["statRows"]
        for width, result in measurements.items()
        if result["statRows"] > 2
    }
    overflowing = {
        width: result["overflowing"]
        for width, result in measurements.items()
        if result["overflowing"]
    }

    compact_too_tall = {
        width: result["compactRows"]
        for width, result in measurements.items()
        if any(rows > 2 for rows in result["compactRows"])
    }
    spilling = {
        width: (result["statsOutsideGrid"], result["pageOverflow"])
        for width, result in measurements.items()
        if result["statsOutsideGrid"] or result["pageOverflow"] > 0
    }

    assert all(result["statCount"] == 4 for result in measurements.values())
    assert compact_too_tall == {}, f"Compact stats exceed two rows: {compact_too_tall}"
    assert spilling == {}, f"Stats must stay inside their grid: {spilling}"
    assert (
        too_tall == {}
    ), f"The four MAID Runner stats should take at most two rows on phones: {too_tall}"
    assert overflowing == {}, f"Stat text must fit its card: {overflowing}"
