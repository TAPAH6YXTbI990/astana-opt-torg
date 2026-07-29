from __future__ import annotations

import logging
import re
import time
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

logger = logging.getLogger(__name__)

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "ref",
    "yclid",
}

EXCLUDE_PARAMS = {
    "min_price",
    "max_price",
    "orderby",
    "order",
    "add-to-cart",
    "q",
    "s",
    "lang",
}

EXCLUDE_PARAM_PREFIXES = ("filter_", "yith_", "pa_")


def normalize(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    query = parse_qsl(parts.query, keep_blank_values=False)
    kept: list[tuple[str, str]] = []
    for key, value in query:
        low = key.lower()
        if low in TRACKING_PARAMS:
            continue
        if low in EXCLUDE_PARAMS:
            continue
        if "filter" in low:
            continue
        if any(low.startswith(prefix) for prefix in EXCLUDE_PARAM_PREFIXES):
            continue
        kept.append((key, value))
    query_str = urlencode(kept)
    return urlunsplit((parts.scheme, parts.netloc, path, query_str, ""))


_SKIP_PREFIXES = ("#", "javascript:", "mailto:", "tel:", "data:", "blob:")


def extract_links(
    base_url: str,
    html_bytes: bytes,
    *,
    allowed_domain: str,
    exclude_patterns: list[str],
    pagination_patterns: list[str],
) -> list[tuple[str, bool]]:
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html_bytes, "lxml")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed to parse html for links: %s", exc)
        return []

    results: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(_SKIP_PREFIXES):
            continue
        abs_url = _join(base_url, href)
        if not abs_url:
            continue
        parts = urlsplit(abs_url)
        if parts.scheme not in ("http", "https"):
            continue
        if parts.netloc.lower() != allowed_domain.lower():
            continue
        norm = normalize(abs_url)
        if norm in seen:
            continue
        if any(re.search(pattern, norm) for pattern in exclude_patterns):
            continue
        is_pagination = any(
            re.search(pattern, norm) for pattern in pagination_patterns
        )
        seen.add(norm)
        results.append((norm, is_pagination))
    return results


def _join(base: str, href: str) -> str:
    from urllib.parse import urljoin, urlsplit

    try:
        if href.startswith(("http://", "https://", "//")):
            return urljoin(base, href)
        if href.startswith("/"):
            return urljoin(base, href)
        parts = urlsplit(base)
        root = f"{parts.scheme}://{parts.netloc}/"
        return urljoin(root, href)
    except Exception:  # pragma: no cover - defensive
        return ""
