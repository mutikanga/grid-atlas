"""Static checks of web/: no external URLs, the fixed page sections, the shell, vendored files."""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "web"

# contracts.md section 10: the sections of each page (file names are fixed).
EXPECTED_SECTIONS = {
    "index.html": [],
    "losses.html": ["losses-monthly.js", "validation-snapshot.js", "recon-gate.js", "losses-elements.js",
                    "remedies-top10.js"],
    "n1.html": ["n1-summary.js", "n1-n0-issues.js", "n1-table.js", "n1-benchmark.js"],
    "kawanda.html": ["kawanda.js"],
    "sites.html": ["sites-headroom.js", "sites-ranking.js"],
    "dashboard.html": ["dashboard.js", "dashboard-forecast.js"],
    "imports.html": ["imports.js"],
    "about.html": ["about.js"],
}
NAV = ["index.html", "losses.html", "n1.html", "kawanda.html", "sites.html", "dashboard.html", "imports.html",
       "about.html"]
URL = re.compile(r"https?://", re.IGNORECASE)


class PageParser(HTMLParser):
    """Collects what the checks need from one page."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.sections: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.nav_links: list[str] = []
        self.tags: list[str] = []
        self._in_nav = 0

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        self.tags.append(tag)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "section" and "atlas-section" in a.get("class", "").split():
            self.sections.append(a)
        if tag == "script":
            self.scripts.append(a)
        if tag == "nav":
            self._in_nav += 1
        if tag == "a" and self._in_nav:
            self.nav_links.append(a.get("href", ""))

    def handle_endtag(self, tag):
        if tag == "nav":
            self._in_nav -= 1


def parse(page: str) -> PageParser:
    parser = PageParser()
    parser.feed((WEB / page).read_text(encoding="utf-8"))
    return parser


def own_web_files() -> list[Path]:
    """web/*.html plus everything under web/js and web/css (vendored files excluded)."""
    files = list(WEB.glob("*.html"))
    for sub in ("js", "css"):
        files += [p for p in (WEB / sub).rglob("*") if p.is_file()]
    return files


def test_no_external_urls():
    offenders = [str(p.relative_to(WEB)) for p in own_web_files() if URL.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"external URLs found in {offenders}"


def test_only_expected_pages_exist():
    assert sorted(p.name for p in WEB.glob("*.html")) == sorted(EXPECTED_SECTIONS)


@pytest.mark.parametrize("page", sorted(EXPECTED_SECTIONS))
def test_page_sections_match_contract(page):
    parsed = parse(page)
    modules = [s.get("data-module", "") for s in parsed.sections]
    assert modules == [f"js/sections/{name}" for name in EXPECTED_SECTIONS[page]]
    for section in parsed.sections:
        assert section.get("data-title"), f"{page}: section {section.get('data-module')} has no data-title"


@pytest.mark.parametrize("page", sorted(EXPECTED_SECTIONS))
def test_page_shell(page):
    parsed = parse(page)
    assert parsed.nav_links == NAV
    assert {"atlas-banner", "atlas-footer", "main"} <= parsed.ids
    assert "main" in parsed.tags and "footer" in parsed.tags
    assert any(s.get("type") == "module" and s.get("src") == "js/common.js" for s in parsed.scripts)
    for script in parsed.scripts:
        assert "src" in script, f"{page}: inline scripts break the CSP (script-src 'self')"


def test_map_page_shell():
    parsed = parse("index.html")
    assert {"map", "map-panel", "month-slider"} <= parsed.ids
    srcs = [s.get("src") for s in parsed.scripts]
    assert "js/map.js" in srcs and "vendor/leaflet/leaflet.js" in srcs


def test_common_js_exports_the_section_toolkit():
    text = (WEB / "js" / "common.js").read_text(encoding="utf-8")
    for name in ["api", "table", "chart", "fmt", "el", "downloads", "loadSections", "banner", "footer"]:
        assert re.search(rf"export (async )?function {name}\b", text), name
    # ctx carries exactly the contract's keys (plus extras).
    for key in ["api", "table", "chart", "fmt", "el", "downloads", "provenance", "params"]:
        assert re.search(rf"\b{key}\b", text.split("export function makeContext", 1)[1].split("}", 2)[0] + "}")


def test_own_sections_export_default_render():
    for name in ("imports.js", "about.js"):
        text = (WEB / "js" / "sections" / name).read_text(encoding="utf-8")
        assert "export default async function render(" in text, name


def test_vendored_files_match_versions_md():
    versions = (WEB / "vendor" / "VERSIONS.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([^`]+)` \| `[^`]+` \| `([0-9a-f]{64})` \|$", versions, re.MULTILINE)
    assert len(rows) >= 9
    for rel, digest in rows:
        path = WEB / "vendor" / rel
        assert path.is_file(), rel
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, rel
