from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "website"


def test_every_html_page_loads_configured_google_analytics_tag() -> None:
    measurement_id = "G-B6F335E4MM"
    html_pages = sorted(WEBSITE.rglob("*.html"))

    assert html_pages
    for page in html_pages:
        document = page.read_text(encoding="utf-8")
        head = document.split("<head>", 1)[1].split("</head>", 1)[0]
        expected_tokens = (
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={measurement_id}"></script>',
            "window.dataLayer = window.dataLayer || [];",
            "function gtag(){dataLayer.push(arguments);}",
            "gtag('js', new Date());",
            f"gtag('config', '{measurement_id}');",
        )

        for token in expected_tokens:
            assert document.count(token) == 1, page.relative_to(WEBSITE)
            assert head.count(token) == 1, page.relative_to(WEBSITE)
