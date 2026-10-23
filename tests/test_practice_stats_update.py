import functools
import http.server
import json
import re
import shutil
import sys
import threading
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"

VALIDATE_OUTPUT = """\
...
Validation Results: 704 manifests
  Passed: 333
  Failed: 0
  Skipped: 371 (superseded)
  Duration: 9774ms
"""
PYTEST_OUTPUT = """\
........................................................ [ 99%]
5572 passed, 20 skipped, 19 warnings in 136.87s (0:02:16)
"""
MAID_TEST_OUTPUT = """\
Test Results: 308 commands
  Passed: 308
  Failed: 0
  Duration: 181234ms
  PASS [website-distill-why-section] uv run maid validate ...
"""
MAID_TEST_TWO_SECTION_OUTPUT = """\
Test Results: 12 commands
  Passed: 11
  Failed: 1
  Duration: 5000ms

Acceptance Tests (Stream 1): 2 commands
  Passed: 2
  Failed: 0
"""
EXPECTED_COMMANDS = [
    ["uv", "run", "maid", "validate"],
    ["uv", "run", "python", "-m", "pytest", "tests/", "-q", "-n", "auto"],
    ["uv", "run", "maid", "test"],
]
FAKE_TODAY = date(2031, 1, 2)
FAKE_TODAY_TEXT = "January 2, 2031"
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


def _stats() -> dict:
    return {
        "semantics": {"manifests": "..."},
        "maidRunner": {
            "updatedAt": "2026-08-04",
            "manifests": 484,
            "tests": 3698,
            "maidCommandGroups": 218,
        },
        "csharpValidator": {"updatedAt": "2026-08-04", "manifests": 7, "tests": 116},
    }


def _fake_runner(outputs: dict[str, str]):
    calls: list[list[str]] = []

    def run(command: list[str]) -> str:
        calls.append(command)
        joined = " ".join(command)
        for marker, output in outputs.items():
            if marker in joined:
                return output
        raise AssertionError(f"unexpected command {joined}")

    return run, calls


def _passing_runner():
    return _fake_runner(
        {
            "maid validate": VALIDATE_OUTPUT,
            "pytest": PYTEST_OUTPUT,
            "maid test": MAID_TEST_OUTPUT,
        }
    )


def test_parsers_read_counts_from_command_output() -> None:
    from scripts.update_practice_stats import (
        parse_maid_test_command_count,
        parse_pytest_passed_count,
        parse_validated_manifest_count,
    )

    assert parse_validated_manifest_count(VALIDATE_OUTPUT) == 704
    assert parse_pytest_passed_count(PYTEST_OUTPUT) == 5572
    assert (
        parse_pytest_passed_count(
            PYTEST_OUTPUT + "warning: a stderr line mentioning 1 passed\n"
        )
        == 5572
    )
    assert parse_maid_test_command_count(MAID_TEST_OUTPUT) == 308


def test_parsers_refuse_failing_or_unrecognized_runs() -> None:
    from scripts.update_practice_stats import (
        parse_maid_test_command_count,
        parse_pytest_passed_count,
        parse_validated_manifest_count,
    )

    failing = [
        (
            parse_validated_manifest_count,
            VALIDATE_OUTPUT.replace("Failed: 0", "Failed: 2"),
        ),
        (parse_pytest_passed_count, "5570 passed, 2 failed, 20 skipped in 99.0s"),
        (parse_pytest_passed_count, "5570 passed, 1 error in 9.0s"),
        (
            parse_pytest_passed_count,
            "FAILED tests/x.py::t - AssertionError: expected '3 passed'\n"
            "10 failed, 5 passed in 1.0s\n",
        ),
        (
            parse_pytest_passed_count,
            "E AssertionError: expected '3 passed'\n5 failed in 1.0s\n",
        ),
        (
            parse_pytest_passed_count,
            "ERROR tests/x.py - ImportError: 2 passed\n1 error in 0.5s\n",
        ),
        (
            parse_validated_manifest_count,
            "Failed: 0\nValidation Results: 5 manifests\n  Passed: 3\n  Failed: 2\n",
        ),
        (
            parse_maid_test_command_count,
            MAID_TEST_OUTPUT.replace("Failed: 0", "Failed: 1"),
        ),
        (parse_maid_test_command_count, MAID_TEST_TWO_SECTION_OUTPUT),
    ]
    for parser in (
        parse_validated_manifest_count,
        parse_pytest_passed_count,
        parse_maid_test_command_count,
    ):
        failing.append((parser, "no recognizable summary here"))

    for parser, output in failing:
        with pytest.raises(ValueError):
            parser(output)


def test_collect_maid_runner_counts_uses_each_command_output() -> None:
    from scripts.update_practice_stats import collect_maid_runner_counts

    run, calls = _passing_runner()

    counts = collect_maid_runner_counts(run)

    assert counts == {"manifests": 704, "tests": 5572, "maidCommandGroups": 308}
    assert sorted(calls) == sorted(EXPECTED_COMMANDS)


def test_refresh_practice_stats_updates_only_maid_runner_and_its_date() -> None:
    from scripts.update_practice_stats import refresh_practice_stats

    original = _stats()
    counts = {"manifests": 704, "tests": 5572, "maidCommandGroups": 308}

    refreshed = refresh_practice_stats(original, counts, FAKE_TODAY)

    assert refreshed["maidRunner"] == {"updatedAt": FAKE_TODAY.isoformat(), **counts}
    assert refreshed["csharpValidator"] == original["csharpValidator"]
    assert refreshed["semantics"] == original["semantics"]
    assert original["maidRunner"]["manifests"] == 484, "input is not mutated"


def test_render_practice_stats_html_mirrors_values_and_dates() -> None:
    from scripts.update_practice_stats import render_practice_stats_html

    # Deliberately not in JSON key order: values must be matched by key.
    html = (
        '<span data-stat="csharpValidator.manifests">7</span>'
        '<time data-stat-date="csharpValidator" datetime="2026-08-04">August 4, 2026</time>'
        '<span data-stat="maidRunner.maidCommandGroups">218</span>'
        '<span data-stat="maidRunner.tests">3698</span>'
        '<time data-stat-date="maidRunner" datetime="2026-08-04">August 4, 2026</time>'
        '<span data-stat="maidRunner.manifests">484</span>'
    )
    stats = _stats()
    stats["maidRunner"] = {
        "updatedAt": FAKE_TODAY.isoformat(),
        "manifests": 704,
        "tests": 5572,
        "maidCommandGroups": 308,
    }

    rendered = render_practice_stats_html(html, stats)

    assert '<span data-stat="maidRunner.manifests">704</span>' in rendered
    assert '<span data-stat="maidRunner.tests">5572</span>' in rendered
    assert '<span data-stat="maidRunner.maidCommandGroups">308</span>' in rendered
    assert (
        f'<time data-stat-date="maidRunner" datetime="{FAKE_TODAY.isoformat()}">'
        f"{FAKE_TODAY_TEXT}</time>"
    ) in rendered
    assert '<span data-stat="csharpValidator.manifests">7</span>' in rendered
    assert (
        '<time data-stat-date="csharpValidator" datetime="2026-08-04">'
        "August 4, 2026</time>"
    ) in rendered


def test_render_practice_stats_html_rejects_unknown_stat_keys() -> None:
    from scripts.update_practice_stats import render_practice_stats_html

    with pytest.raises(KeyError):
        render_practice_stats_html(
            '<span data-stat="maidRunner.coverage">90</span>', _stats()
        )
    # A page missing a mirrored value or a date must not be half-updated.
    with pytest.raises(ValueError):
        render_practice_stats_html(
            '<span data-stat="maidRunner.manifests">484</span>', _stats()
        )


def test_run_command_returns_output_and_raises_on_failure() -> None:
    from scripts.update_practice_stats import run_command

    output = run_command(
        [sys.executable, "-c", "print('Validation Results: 1 manifests')"]
    )

    assert "Validation Results: 1 manifests" in output
    with pytest.raises(RuntimeError):
        run_command([sys.executable, "-c", "import sys; print('boom'); sys.exit(3)"])


def test_update_practice_stats_rewrites_json_and_page_together(tmp_path: Path) -> None:
    from scripts.update_practice_stats import update_practice_stats

    website = tmp_path / "website"
    shutil.copytree(WEBSITE, website)
    run, _calls = _passing_runner()

    update_practice_stats(website, run, FAKE_TODAY)

    stats = json.loads((website / "data" / "practice-stats.json").read_text())
    page = (website / "index.html").read_text()
    assert stats["maidRunner"]["updatedAt"] == FAKE_TODAY.isoformat()
    assert stats["maidRunner"]["manifests"] == 704
    assert (
        '<span class="practice-stat-value" data-stat="maidRunner.tests">5572</span>'
        in page
    )
    assert f'datetime="{FAKE_TODAY.isoformat()}">{FAKE_TODAY_TEXT}</time>' in page


def test_update_practice_stats_leaves_files_untouched_when_a_run_fails(
    tmp_path: Path,
) -> None:
    from scripts.update_practice_stats import update_practice_stats

    website = tmp_path / "website"
    shutil.copytree(WEBSITE, website)
    names = ("data/practice-stats.json", "index.html")
    before = {name: (website / name).read_bytes() for name in names}
    run, _calls = _fake_runner(
        {
            "maid validate": VALIDATE_OUTPUT,
            "pytest": "5570 passed, 2 failed in 99.0s",
            "maid test": MAID_TEST_OUTPUT,
        }
    )

    with pytest.raises(ValueError):
        update_practice_stats(website, run, FAKE_TODAY)

    for name in names:
        assert (website / name).read_bytes() == before[name], name


def test_published_page_matches_practice_stats_json_with_visible_dates() -> None:
    stats = json.loads((WEBSITE / "data" / "practice-stats.json").read_text())
    page = (WEBSITE / "index.html").read_text()

    mirrored = dict(re.findall(r'data-stat="([\w.]+)">([^<]*)<', page))
    cards = {
        "maidRunner": page.split('class="practice-featured-card"', 1)[1].split(
            'class="practice-secondary-grid"', 1
        )[0],
        "csharpValidator": page.split("MAID Validator for C#", 1)[1].split(
            "Private production projects", 1
        )[0],
    }

    assert "updatedAt" not in stats, "dates live per project, not at the top level"
    for project in ("maidRunner", "csharpValidator"):
        section = stats[project]
        dated = date.fromisoformat(section["updatedAt"])
        visible = f"{MONTHS[dated.month - 1]} {dated.day}, {dated.year}"
        expected_date = (
            f'as of <time data-stat-date="{project}" '
            f'datetime="{section["updatedAt"]}">{visible}</time>'
        )
        assert expected_date in " ".join(cards[project].split()), project
        for key, value in section.items():
            if key != "updatedAt":
                assert mirrored.get(f"{project}.{key}") == str(value), (project, key)
    assert set(mirrored) == {
        f"{project}.{key}"
        for project in ("maidRunner", "csharpValidator")
        for key in stats[project]
        if key != "updatedAt"
    }


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def test_practice_dates_render_visibly_on_desktop_and_phone() -> None:
    from playwright.sync_api import sync_playwright

    handler = functools.partial(_QuietHandler, directory=str(WEBSITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    counts: dict[int, int] = {}
    hidden: dict[int, list[str]] = {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for width in (390, 1440):
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
                    dates = page.locator("time[data-stat-date]")
                    counts[width] = dates.count()
                    hidden[width] = [
                        dates.nth(index).get_attribute("data-stat-date") or ""
                        for index in range(dates.count())
                        if not dates.nth(index).is_visible()
                    ]
                    page.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()

    assert counts == {390: 2, 1440: 2}
    assert hidden == {390: [], 1440: []}
