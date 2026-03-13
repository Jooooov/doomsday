"""
HTML Content Extractor

Converts raw HTML bytes into structured content using BeautifulSoup4 + lxml.

Design principles
-----------------
- Boilerplate removal: strips nav, footer, sidebar, ads, scripts, styles.
- Main content detection: looks for <main>, <article>, role="main", then
  falls back to <body> with boilerplate elements removed.
- Text normalisation: collapses whitespace, removes control characters.
- Metadata extraction: <title>, <h1>, <meta> tags, headings, internal links.
- Safe defaults: all public methods return empty strings / empty lists on
  any parse error rather than propagating exceptions.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup, Tag  # type: ignore
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# HTML elements whose entire subtree is considered boilerplate
_BOILERPLATE_TAGS = frozenset({
    "script", "style", "noscript", "iframe",
    "nav", "header", "footer", "aside",
    "form", "button", "input", "select", "textarea",
    "svg", "canvas", "figure",  # Often decorative
})

# CSS class / id fragments that signal navigation/ad boilerplate
_BOILERPLATE_PATTERNS = re.compile(
    r"(nav|navbar|header|footer|sidebar|breadcrumb|cookie|banner|"
    r"advertisement|social|share|related|comment|pagination|menu|"
    r"widget|skip|utility|topbar|modal|overlay)",
    re.IGNORECASE,
)

# Preferred parser order (lxml is fastest; html.parser is stdlib fallback)
_PARSER_PREFERENCE = ["lxml", "html5lib", "html.parser"]

# Whitespace normalisation
_MULTI_WHITESPACE = re.compile(r"\s{2,}")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract(
    html_bytes: bytes,
    base_url: str = "",
    *,
    save_html: bool = False,
    parser: str | None = None,
) -> Dict[str, Any]:
    """
    Parse raw HTML and return a structured content dict.

    Parameters
    ----------
    html_bytes:   Raw HTTP response body.
    base_url:     Absolute URL used to resolve relative links.
    save_html:    When True, include the raw inner-HTML of the main block.
    parser:       Force a specific BeautifulSoup parser (None = auto).

    Returns
    -------
    Dict with keys:
        title       str | None
        content_text str | None
        content_html str | None  (only populated when save_html=True)
        content_hash str | None
        headings    list[{level, text}]
        links       list[{href, text}]
        meta_tags   dict
        word_count  int
        language    str
    """
    empty = _empty_result()

    if not BS4_AVAILABLE:
        empty["error"] = "beautifulsoup4 not installed"
        return empty

    try:
        soup = _parse(html_bytes, parser)
    except Exception as exc:  # noqa: BLE001
        empty["error"] = f"HTML parse error: {exc}"
        return empty

    # --- Content extraction ---
    title = _extract_title(soup)
    main_block = _find_main_block(soup)
    _strip_boilerplate(main_block or soup)

    content_html = str(main_block) if (save_html and main_block) else None
    content_text = _extract_text(main_block or soup)
    content_hash = _hash(content_text) if content_text else None

    return {
        "title": title,
        "content_text": content_text,
        "content_html": content_html,
        "content_hash": content_hash,
        "headings": _extract_headings(main_block or soup),
        "links": _extract_links(soup, base_url=base_url),
        "meta_tags": _extract_meta_tags(soup),
        "word_count": len(content_text.split()) if content_text else 0,
        "language": _detect_language(soup),
        "error": None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _empty_result() -> Dict[str, Any]:
    return {
        "title": None,
        "content_text": None,
        "content_html": None,
        "content_hash": None,
        "headings": [],
        "links": [],
        "meta_tags": {},
        "word_count": 0,
        "language": "en",
        "error": None,
    }


def _parse(html_bytes: bytes, parser: str | None) -> "BeautifulSoup":
    """Parse HTML with the best available parser."""
    if not BS4_AVAILABLE:
        raise RuntimeError("beautifulsoup4 not installed")

    candidates = [parser] if parser else _PARSER_PREFERENCE
    last_exc: Exception | None = None
    for p in candidates:
        try:
            return BeautifulSoup(html_bytes, p)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise RuntimeError(f"No working HTML parser found; last error: {last_exc}")


def _extract_title(soup: "BeautifulSoup") -> Optional[str]:
    """Return page title: <title> → first <h1> → None."""
    tag = soup.find("title")
    if tag and tag.get_text(strip=True):
        return _normalise_text(tag.get_text())

    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return _normalise_text(h1.get_text())

    return None


def _find_main_block(soup: "BeautifulSoup") -> Optional["Tag"]:
    """
    Locate the primary content element.

    Priority order:
    1. <main> element
    2. [role="main"] attribute
    3. <article> element
    4. <div id="content"> / <div class="content">
    5. None → caller uses full <body>
    """
    # 1. <main>
    main = soup.find("main")
    if main:
        return main

    # 2. role="main"
    role_main = soup.find(attrs={"role": "main"})
    if role_main:
        return role_main

    # 3. <article>
    article = soup.find("article")
    if article:
        return article

    # 4. id/class hints
    for selector in [
        {"id": "content"}, {"id": "main-content"}, {"id": "primary"},
        {"class": "content"}, {"class": "main-content"}, {"class": "page-content"},
    ]:
        el = soup.find(attrs=selector)
        if el:
            return el

    return None


def _strip_boilerplate(el: "BeautifulSoup | Tag") -> None:
    """Remove boilerplate sub-elements from the content tree in-place."""
    if not BS4_AVAILABLE:
        return

    for tag in el.find_all(_BOILERPLATE_TAGS):
        tag.decompose()

    # Remove elements whose class or id suggests navigation/advertising
    for tag in el.find_all(True):
        classes = " ".join(tag.get("class", []))
        tag_id = tag.get("id", "")
        if _BOILERPLATE_PATTERNS.search(classes) or _BOILERPLATE_PATTERNS.search(tag_id):
            tag.decompose()


def _extract_text(el: "BeautifulSoup | Tag") -> Optional[str]:
    """
    Extract normalised plain text from a BeautifulSoup element.

    - Uses get_text(separator=" ") to preserve word boundaries across tags.
    - Normalises Unicode to NFC.
    - Collapses whitespace runs.
    - Strips leading/trailing whitespace per line.
    """
    if not BS4_AVAILABLE or el is None:
        return None

    raw = el.get_text(separator=" ", strip=False)
    # Unicode normalisation
    raw = unicodedata.normalize("NFC", raw)
    # Remove control chars
    raw = _CONTROL_CHARS.sub("", raw)
    # Collapse whitespace
    lines = [_MULTI_WHITESPACE.sub(" ", line).strip() for line in raw.splitlines()]
    # Remove blank lines (keep structure somewhat intact with single newlines)
    cleaned = "\n".join(line for line in lines if line)
    return cleaned if cleaned else None


def _extract_headings(el: "BeautifulSoup | Tag") -> List[Dict[str, str]]:
    """Return ordered list of headings: [{level: 'h2', text: '…'}, …]."""
    if not BS4_AVAILABLE or el is None:
        return []
    headings = []
    for tag in el.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = _normalise_text(tag.get_text())
        if text:
            headings.append({"level": tag.name, "text": text})
    return headings


def _extract_links(
    soup: "BeautifulSoup",
    *,
    base_url: str = "",
) -> List[Dict[str, str]]:
    """
    Return internal links as [{href, text}, …].

    Only same-domain or relative links are kept; external links are dropped.
    """
    if not BS4_AVAILABLE or soup is None:
        return []

    base_domain = _domain(base_url)
    links = []
    seen_hrefs: set = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        # Resolve relative URLs
        absolute = urljoin(base_url, href) if base_url else href

        # Filter: only keep same-domain links
        if base_domain and _domain(absolute) not in (base_domain, ""):
            continue

        if absolute in seen_hrefs:
            continue
        seen_hrefs.add(absolute)

        text = _normalise_text(a.get_text())
        links.append({"href": absolute, "text": text or ""})

    return links[:200]  # cap at 200 to keep JSONB column sane


def _extract_meta_tags(soup: "BeautifulSoup") -> Dict[str, str]:
    """Extract useful <meta> tag values."""
    if not BS4_AVAILABLE or soup is None:
        return {}

    meta: Dict[str, str] = {}

    # Standard meta: description, keywords, author
    for name in ("description", "keywords", "author", "robots"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            meta[name] = tag["content"].strip()[:500]

    # Open Graph
    for prop in ("og:title", "og:description", "og:type", "og:url", "og:image"):
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            meta[prop] = tag["content"].strip()[:500]

    # DC / Twitter
    for name in ("twitter:title", "twitter:description"):
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            meta[name] = tag["content"].strip()[:500]

    return meta


def _detect_language(soup: "BeautifulSoup") -> str:
    """Detect document language from <html lang="…"> attribute."""
    if not BS4_AVAILABLE:
        return "en"
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        lang = str(html_tag["lang"]).split("-")[0].lower().strip()
        if lang and len(lang) <= 5:
            return lang
    return "en"


def _normalise_text(text: str) -> str:
    """Collapse whitespace and strip a text fragment."""
    return _MULTI_WHITESPACE.sub(" ", text).strip()


def _hash(text: str) -> str:
    """SHA-256 hex digest of UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _domain(url: str) -> str:
    """Extract the netloc (domain) from a URL, or empty string on failure."""
    try:
        return urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return ""
