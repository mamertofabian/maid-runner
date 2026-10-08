"""Browser integration contract for the website's quick-start install section.

Renders website/index.html in headless Chromium and drives the install
section the way a visitor does: choosing a platform tab with the mouse or
keyboard, copying commands, following the installer script links, and
loading the page with JavaScript disabled.

Requires the Chromium build for the installed Playwright version:
    uv run playwright install chromium
"""

import contextlib
import functools
import http.server
import re
import threading
import urllib.parse
import urllib.request
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"

SHELL_COMMAND = "curl -LsSf https://maidrunner.dev/install.sh | sh"
POWERSHELL_COMMAND = "irm https://maidrunner.dev/install.ps1 | iex"
UV_COMMAND = "uv tool install maid-runner"
PIP_COMMAND = "pip install maid-runner"
INSTALL_COMMANDS = (SHELL_COMMAND, POWERSHELL_COMMAND, UV_COMMAND, PIP_COMMAND)

LINUX_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
WINDOWS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


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


@contextlib.contextmanager
def _homepage(
    user_agent: str = LINUX_USER_AGENT,
    javascript: bool = True,
    init_script: str | None = None,
):
    """Yield (page, origin) for the homepage scrolled to the install section."""
    from playwright.sync_api import sync_playwright

    with _site() as origin, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=user_agent,
                java_script_enabled=javascript,
            )
            context.grant_permissions(
                ["clipboard-read", "clipboard-write"], origin=origin
            )
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith(origin)
                    else route.abort()
                ),
            )
            if init_script:
                context.add_init_script(init_script)
            context.set_default_timeout(5000)
            page = context.new_page()
            page.goto(f"{origin}/index.html", wait_until="load")
            page.locator("#quickstart").scroll_into_view_if_needed()
            yield page, origin
        finally:
            browser.close()


def _visible_install_commands(page) -> list[str]:
    return [
        text.strip()
        for text in page.locator("#quickstart [data-command]:visible").all_inner_texts()
        if text.strip()
    ]


def _selected_tab(page) -> str:
    return page.locator('#quickstart [role="tab"][aria-selected="true"]').inner_text()


def _panel_for_tab(page, tab):
    return page.locator(f"#{tab.get_attribute('aria-controls')}")


def test_platform_tabs_show_one_installer_and_follow_the_keyboard() -> None:
    with _homepage() as (page, _origin):
        tabs = page.locator('#quickstart [role="tab"]')
        assert tabs.count() == 3, "the install section offers three platform tabs"
        initial_tab = _selected_tab(page)
        initial_commands = _visible_install_commands(page)
        initial_tabindexes = [
            tabs.nth(index).get_attribute("tabindex") for index in range(3)
        ]

        tabs.first.focus()
        page.keyboard.press("ArrowRight")
        after_right = (_selected_tab(page), _visible_install_commands(page))
        tabindexes_after_right = [
            tabs.nth(index).get_attribute("tabindex") for index in range(3)
        ]
        focused_after_right = page.evaluate(
            "document.activeElement.getAttribute('aria-selected')"
        )
        page.keyboard.press("End")
        after_end = (_selected_tab(page), _visible_install_commands(page))
        page.keyboard.press("Home")
        after_home = _selected_tab(page)
        page.keyboard.press("ArrowLeft")
        after_left_wrap = _selected_tab(page)
        tabs.nth(1).click()
        after_click = _visible_install_commands(page)
        tabindexes_after_click = [
            tabs.nth(index).get_attribute("tabindex") for index in range(3)
        ]

    assert "macOS" in initial_tab
    assert SHELL_COMMAND in initial_commands
    assert POWERSHELL_COMMAND not in initial_commands
    assert initial_tabindexes == ["0", "-1", "-1"]
    assert "Windows" in after_right[0]
    assert POWERSHELL_COMMAND in after_right[1]
    assert SHELL_COMMAND not in after_right[1]
    assert focused_after_right == "true"
    assert tabindexes_after_right == ["-1", "0", "-1"]
    assert tabindexes_after_click == ["-1", "0", "-1"]
    assert UV_COMMAND in after_end[1] and PIP_COMMAND in after_end[1]
    assert "macOS" in after_home
    assert "uv" in after_left_wrap
    assert after_click == after_right[1]


def test_windows_visitors_see_the_powershell_installer_first() -> None:
    with _homepage(user_agent=WINDOWS_USER_AGENT) as (page, _origin):
        assert page.locator('#quickstart [role="tab"]').count() == 3
        selected = _selected_tab(page)
        commands = _visible_install_commands(page)

    assert "Windows" in selected
    assert POWERSHELL_COMMAND in commands
    assert SHELL_COMMAND not in commands


def test_copy_buttons_copy_the_exact_command_and_confirm() -> None:
    from playwright.sync_api import expect

    copied: dict[str, str] = {}
    with _homepage() as (page, _origin):
        tabs = page.locator('#quickstart [role="tab"]')
        status = page.locator("#quickstart [data-copy-status]")
        assert tabs.count() == 3, "copy buttons live in the platform tab panels"
        assert "Copied" not in (status.text_content() or "")
        for index in range(tabs.count()):
            tabs.nth(index).click()
            panel = page.locator('#quickstart [role="tabpanel"]:visible')
            for row in panel.locator("[data-copy-row]").all():
                command = row.locator("[data-command]").inner_text().strip()
                page.evaluate("navigator.clipboard.writeText('')")
                status.evaluate("element => { element.textContent = ''; }")
                row.get_by_role("button", name=re.compile("copy", re.I)).click()
                expect(status).to_contain_text("Copied")
                page.wait_for_function(
                    "async () => (await navigator.clipboard.readText()) !== ''"
                )
                copied[command] = page.evaluate("navigator.clipboard.readText()")

    for command in INSTALL_COMMANDS:
        assert copied.get(command) == command
    assert all(command == text for command, text in copied.items())


def test_copied_is_announced_only_after_the_clipboard_write_resolves() -> None:
    from playwright.sync_api import expect

    pending_clipboard = """
      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: () => new Promise((resolve) => { window.__resolveCopy = resolve; }),
        },
      });
    """
    with _homepage(init_script=pending_clipboard) as (page, _origin):
        assert page.locator("#quickstart [data-copy-row]").count() > 0
        status = page.locator("#quickstart [data-copy-status]")
        page.locator('#quickstart [role="tabpanel"]:visible').get_by_role(
            "button", name=re.compile("copy", re.I)
        ).first.click()
        page.wait_for_function("typeof window.__resolveCopy === 'function'")
        page.wait_for_timeout(1500)
        before_resolve = status.text_content() or ""
        page.evaluate("window.__resolveCopy()")
        expect(status).to_contain_text("Copied")

    assert "Copied" not in before_resolve


def test_copy_failure_is_reported_instead_of_claiming_success() -> None:
    from playwright.sync_api import expect

    failing_clipboards = {
        "rejected": """
          Object.defineProperty(navigator, "clipboard", {
            value: { writeText: () => Promise.reject(new Error("denied")) },
          });
        """,
        "missing": """
          Object.defineProperty(navigator, "clipboard", { value: undefined });
        """,
    }
    for case, init_script in failing_clipboards.items():
        with _homepage(init_script=init_script) as (page, _origin):
            assert page.locator("#quickstart [data-copy-row]").count() > 0, case
            page.locator('#quickstart [role="tabpanel"]:visible').get_by_role(
                "button", name=re.compile("copy", re.I)
            ).first.click()
            status = page.locator("#quickstart [data-copy-status]")
            expect(status).to_contain_text(re.compile(r"couldn.t copy", re.I))
            page.wait_for_timeout(1500)
            status_text = status.inner_text()
            status_visible = status.is_visible()

        assert status_visible, case
        assert "Copied" not in status_text, case
        assert re.search(r"select .*manually", status_text, re.I), case


def test_installer_scripts_are_linked_for_review_with_pinning_help() -> None:
    with _homepage() as (page, origin):
        for name in ("install.sh", "install.ps1"):
            assert page.locator("#quickstart a", has_text=name).count() > 0, name
        links = {
            name: page.locator("#quickstart a", has_text=name).first.get_attribute(
                "href"
            )
            for name in ("install.sh", "install.ps1")
        }
        tabs = page.locator('#quickstart [role="tab"]')
        panels = {
            name: _panel_for_tab(page, tabs.filter(has_text=name).first).text_content()
            or ""
            for name in ("macOS", "Windows")
        }
        served = {
            name: urllib.request.urlopen(  # noqa: S310 - local test server
                urllib.parse.urljoin(f"{origin}/index.html", href)
            ).read()
            for name, href in links.items()
            if not urllib.parse.urlparse(href).netloc
        }

    assert all(
        not urllib.parse.urlparse(href).netloc for href in links.values()
    ), f"installer links must be same-origin relative paths: {links}"
    for name, body in served.items():
        assert body == (WEBSITE / name).read_bytes(), name
    shell_usage = (WEBSITE / "install.sh").read_text(encoding="utf-8")
    powershell = (WEBSITE / "install.ps1").read_text(encoding="utf-8")
    assert "[--version VERSION]" in shell_usage
    assert "[string]$Version" in powershell
    assert f"{SHELL_COMMAND} -s -- --version <version>" in panels["macOS"]
    assert re.search(
        r"irm https://maidrunner\.dev/install\.ps1.*-Version <version>",
        panels["Windows"],
    )


def test_install_section_is_complete_without_javascript() -> None:
    with _homepage(javascript=False) as (page, _origin):
        commands = _visible_install_commands(page)
        visible_tabs = page.locator('#quickstart [role="tab"]:visible').count()
        copy_buttons = page.locator("#quickstart").get_by_role(
            "button", name=re.compile("copy", re.I), include_hidden=True
        )
        visible_copy_buttons = sum(
            copy_buttons.nth(index).is_visible()
            for index in range(copy_buttons.count())
        )

    for command in INSTALL_COMMANDS:
        assert command in commands
    assert visible_tabs == 0
    assert visible_copy_buttons == 0
