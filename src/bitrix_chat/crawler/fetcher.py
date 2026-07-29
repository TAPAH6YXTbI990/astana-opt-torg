from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

DEFAULT_TAGS_TO_STRIP = ("script", "style", "noscript", "iframe", "template")


def _extract_title(html_bytes: bytes) -> Optional[str]:
    try:
        soup = BeautifulSoup(html_bytes, "lxml")
    except Exception:  # pragma: no cover - defensive
        return None
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        return title_tag.string.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)[:200]
    return None


def _clean(html_bytes: bytes, selectors: list[str]) -> bytes:
    try:
        soup = BeautifulSoup(html_bytes, "lxml")
    except Exception:  # pragma: no cover - defensive
        return html_bytes

    for tag in DEFAULT_TAGS_TO_STRIP:
        for element in soup.find_all(tag):
            element.decompose()

    for selector in selectors:
        try:
            for element in soup.select(selector):
                element.decompose()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("invalid clean selector %r: %s", selector, exc)

    return str(soup).encode("utf-8")


def fetch(
    url: str,
    *,
    user_agent: str,
    timeout: float = 30.0,
    retries: int = 3,
    selectors: Optional[list[str]] = None,
) -> tuple[bytes, bytes, Optional[str]]:
    """Return (raw html bytes, cleaned html bytes, page title).

    Links should be extracted from ``raw`` (nothing stripped), while the
    cleaned copy is meant for the docling content parse.
    """
    headers = dict(DEFAULT_HEADERS)
    headers["User-Agent"] = user_agent

    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(
                timeout=timeout, follow_redirects=True, headers=headers
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                raw = response.content
                title = _extract_title(raw)
                cleaned = _clean(raw, selectors or [])
                return raw, cleaned, title
        except Exception as exc:
            last_exc = exc
            logger.warning("fetch attempt %d failed for %s: %s", attempt, url, exc)
            time.sleep(min(2**attempt, 10))

    raise RuntimeError(f"failed to fetch {url}: {last_exc}")
