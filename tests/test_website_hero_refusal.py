"""Contract for the homepage hero's manifest and verify preview.

The hero shows the product's core artifact and its gate, so it must be the
real thing. The manifest on the page must pass MAID's v2 schema. The terminal
on the page must be the literal output of `maid verify --summary` run against
that very manifest in a scratch repository: first refused because of a stray
undeclared file, then passing after the file is removed. Only the
timing-dependent "Duration:" lines and blank lines are trimmed.
"""

import contextlib
import functools
import html
import http.server
import os
import re
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"
HOMEPAGE = WEBSITE / "index.html"

_SERVICE = """\
def login(email: str) -> bool:
    return bool(email)
"""
_SERVICE_WITH_RESET = (
    _SERVICE
    + """

def reset_password(email: str) -> bool:
    return "@" in email
"""
)
_TEST = """\
from src.auth.service import reset_password


def test_reset_password_accepts_known_email():
    assert reset_password("a@example.com") is True
"""
_STRAY = """\
def remember(email: str) -> str:
    return email
"""


def _block(page: str, class_name: str) -> str:
    start = page.index(f'class="console-panel {class_name}"')
    return page[start : page.index("</article>", start)]


def _manifest_lines(page: str) -> list[str]:
    """The hero manifest exactly as authored: one line per code element."""
    panel = _block(page, "manifest-panel")
    lines = re.findall(r"<code[^>]*>(.*?)</code>", panel, re.S)
    return [html.unescape(re.sub(r"<[^>]+>", "", line)) for line in lines]


def _transcript_lines(page: str) -> list[str]:
    """The hero terminal transcript, line by line, indentation preserved."""
    panel = _block(page, "validation-panel")
    pre = re.search(r"<pre[^>]*>(.*?)</pre>", panel, re.S)
    assert pre, "the terminal panel holds its transcript in a <pre>"
    text = html.unescape(re.sub(r"<[^>]+>", "", pre.group(1)))
    return [line.rstrip() for line in text.strip("\n").splitlines()]


def _declared_paths(manifest: dict) -> set[str]:
    files = manifest.get("files", {})
    paths = set()
    for section in ("create", "edit", "scope", "delete", "read"):
        for entry in files.get(section) or []:
            paths.add(entry if isinstance(entry, str) else entry["path"])
    return paths


def _trim(output: str) -> list[str]:
    return [
        line.rstrip()
        for line in output.splitlines()
        if line.strip() and not line.strip().startswith("Duration:")
    ]


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "PYTEST_", "MAID_"))
    }
    # Ignore the machine's own git config: signing, hooks, or excludes there
    # must not change the scratch run.
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def _git(cwd: Path, *args: str) -> None:
    completed = _run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=MAID",
            "-c",
            "user.email=maid@example.com",
            *args,
        ],
        cwd,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def _maid_verify(cwd: Path) -> list[str]:
    completed = _run(
        [
            sys.executable,
            "-c",
            "import sys; from maid_runner.cli.commands._main import main; "
            "sys.exit(main(sys.argv[1:]))",
            "verify",
            "--summary",
            "--since",
            "main",
        ],
        cwd,
    )
    return _trim(completed.stdout + completed.stderr)


def test_hero_manifest_passes_the_real_v2_schema() -> None:
    import yaml

    from maid_runner.core.manifest import validate_manifest_schema

    source = "\n".join(_manifest_lines(HOMEPAGE.read_text(encoding="utf-8")))
    manifest = yaml.safe_load(source)

    assert isinstance(manifest, dict), source
    assert validate_manifest_schema(manifest) == []
    edits = manifest["files"].get("edit") or []
    assert edits, "the hero shows the file it changes"
    for artifact in (a for entry in edits for a in entry["artifacts"]):
        assert "args" in artifact and "returns" in artifact, artifact


def test_hero_transcript_is_a_real_maid_verify_run(tmp_path: Path) -> None:
    page = HOMEPAGE.read_text(encoding="utf-8")
    lines = _transcript_lines(page)
    prompts = [index for index, line in enumerate(lines) if line.startswith("$ ")]
    assert len(prompts) == 3, lines
    command = "$ maid verify --summary --since main"
    assert lines[prompts[0]] == command and lines[prompts[2]] == command, lines
    removal = re.fullmatch(r"\$ rm (\S+)", lines[prompts[1]])
    assert removal, lines[prompts[1]]
    stray = removal.group(1)
    assert not Path(stray).is_absolute() and ".." not in Path(stray).parts, stray

    repo = tmp_path / "hero"
    (repo / "src" / "auth").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "manifests").mkdir()
    for package in ("src", "src/auth", "tests"):
        (repo / package / "__init__.py").write_text("")
    (repo / "src/auth/service.py").write_text(_SERVICE)
    (repo / "tests/test_reset.py").write_text(_TEST)
    (repo / "manifests/add-password-recovery.manifest.yaml").write_text(
        "\n".join(_manifest_lines(page)) + "\n"
    )
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-q", "-b", "add-password-recovery")
    (repo / "src/auth/service.py").write_text(_SERVICE_WITH_RESET)
    (repo / stray).write_text(_STRAY)

    refused = _maid_verify(repo)
    (repo / stray).unlink()
    passing = _maid_verify(repo)

    assert refused[0].startswith("VERIFY: FAIL"), refused
    assert passing[0].startswith("VERIFY: PASS"), passing
    assert lines[prompts[0] + 1 : prompts[1]] == refused
    assert lines[prompts[2] + 1 :] == passing
    assert "HANDOFF READY" in _block(page, "validation-panel").split("</pre>", 1)[1]


def test_hero_refusal_names_a_file_the_manifest_does_not_declare() -> None:
    import yaml

    page = HOMEPAGE.read_text(encoding="utf-8")
    manifest = yaml.safe_load("\n".join(_manifest_lines(page)))
    lines = _transcript_lines(page)
    removal = next(line for line in lines if line.startswith("$ rm "))
    stray = removal.removeprefix("$ rm ")

    assert stray not in _declared_paths(manifest)
    assert any(line.strip() == stray for line in lines), "the refusal names it"


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@contextlib.contextmanager
def _site() -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(WEBSITE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


_LAYOUT_SCRIPT = """
() => {
  const panels = [...document.querySelectorAll(".hero-console .console-panel")];
  const boxes = panels.map((panel) => panel.getBoundingClientRect());
  const problems = [];
  const label = (el) => el.textContent.trim().slice(0, 30);
  panels.forEach((panel, index) => {
    const own = boxes[index];
    for (const el of panel.querySelectorAll("*")) {
      const hasText = [...el.childNodes].some(
        (node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim()
      );
      if (!hasText) continue;
      const style = getComputedStyle(el);
      const alpha = style.color.match(/rgba?\\(([^)]+)\\)/);
      const transparent = alpha && alpha[1].split(",").length === 4 &&
        parseFloat(alpha[1].split(",")[3]) === 0;
      if (!el.checkVisibility({ opacityProperty: true, visibilityProperty: true }) ||
          transparent) {
        problems.push(["hidden", label(el)]);
        continue;
      }
      for (const rect of el.getClientRects()) {
        if (rect.width < 1 || rect.height < 1) continue;
        if (rect.left < own.left - 1 || rect.right > own.right + 1 ||
            rect.top < own.top - 1 || rect.bottom > own.bottom + 1) {
          problems.push(["outside its panel", label(el)]);
        }
        if (rect.top < 0 || rect.bottom > innerHeight || rect.left < 0 ||
            rect.right > innerWidth) {
          problems.push(["off screen", label(el)]);
        }
        boxes.forEach((other, otherIndex) => {
          if (otherIndex === index) return;
          const x = Math.min(rect.right, other.right) - Math.max(rect.left, other.left);
          const y = Math.min(rect.bottom, other.bottom) - Math.max(rect.top, other.top);
          if (x > 0 && y > 0) problems.push(["under the other panel", label(el)]);
        });
        const hit = document.elementFromPoint(
          (rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2
        );
        if (hit && hit !== el && !el.contains(hit)) {
          problems.push(["covered", label(el)]);
        }
      }
    }
  });
  const codes = [...document.querySelectorAll(".manifest-panel .code-window code")];
  return {
    panels: panels.length,
    problems,
    renderedManifest: codes.map((code) => code.innerText),
  };
}
"""


def test_hero_panels_show_all_their_text_without_overlap() -> None:
    from playwright.sync_api import sync_playwright

    expected_manifest = _manifest_lines(HOMEPAGE.read_text(encoding="utf-8"))
    failures: dict[int, dict] = {}
    with _site() as origin, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for width in (320, 360, 390, 820, 1001, 1440, 1920):
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
                page.add_style_tag(
                    content=".hero-console, .hero-console * "
                    "{ pointer-events: auto !important; }"
                )
                height = page.evaluate(
                    "Math.ceil(document.querySelector('.hero-console')"
                    ".getBoundingClientRect().height) + 40"
                )
                page.set_viewport_size({"width": width, "height": max(900, height)})
                page.evaluate(
                    "window.scrollTo(0, document.querySelector('.hero-console')"
                    ".getBoundingClientRect().top + scrollY - 20)"
                )
                result = page.evaluate(_LAYOUT_SCRIPT)
                if (
                    result["panels"] != 2
                    or result["problems"]
                    or result["renderedManifest"] != expected_manifest
                ):
                    failures[width] = result
                page.close()
        finally:
            browser.close()

    assert failures == {}, f"Hero preview problems by width: {failures}"
