from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from collections import deque
from typing import Optional
from urllib.parse import urlparse

import httpx

from .config import CrawlConfig
from .fetcher import fetch
from .links import extract_links, normalize
from .storage import Storage

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self, config: CrawlConfig) -> None:
        self.config = config
        self.visited: set[str] = set()
        self.storage = Storage(config.output_dir)
        self.visited.update(self.storage.load_visited())
        self._pagination_count = 0
        self._total = 0
        self.rp: Optional[object] = None

        if config.respect_robots:
            try:
                from urllib.robotparser import RobotFileParser

                rp = RobotFileParser()
                rp.set_url(f"https://{config.allowed_domain}/robots.txt")
                rp.read()
                self.rp = rp
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning("could not read robots.txt, allowing all: %s", exc)
                self.rp = None

    def _allowed(self, url: str) -> bool:
        if self.rp is None:
            return True
        try:
            return bool(self.rp.can_fetch(self.config.user_agent, url))  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive
            return True

    def run(self) -> int:
        queue: deque[tuple[str, bool]] = deque()
        seed_set = {normalize(seed) for seed in self.config.seeds}
        for seed in seed_set:
            queue.append((seed, True))

        if self.config.use_sitemap:
            for sitemap_url in self._sitemap_urls():
                queue.append((normalize(sitemap_url), True))

        processed = 0
        while queue:
            url, is_catalog = queue.popleft()
            if url in self.visited:
                continue
            if not self._allowed(url):
                logger.info("robots disallow: %s", url)
                self.visited.add(url)
                continue

            time.sleep(self.config.rate_limit_s)

            try:
                raw, cleaned, title = fetch(
                    url,
                    user_agent=self.config.user_agent,
                    selectors=self.config.clean_selectors,
                )
            except Exception as exc:
                logger.error("fetch error %s: %s", url, exc)
                self.visited.add(url)
                continue

            try:
                from .parser import parse_html

                doc = parse_html(cleaned)
            except Exception as exc:
                logger.error("parse error %s: %s", url, exc)
                self.visited.add(url)
                continue

            self.storage.save(url, doc, title=title, is_catalog=is_catalog)
            self.visited.add(url)
            processed += 1
            self._total += 1

            if not is_catalog:
                continue

            if self._total >= self.config.max_total_pages:
                logger.info("reached max_total_pages=%d, stopping", self.config.max_total_pages)
                break

            links = extract_links(
                url,
                raw,
                allowed_domain=self.config.allowed_domain,
                exclude_patterns=self.config.exclude_patterns,
                pagination_patterns=self.config.pagination_patterns,
            )
            for link, is_pagination in links:
                if link in self.visited:
                    continue
                # Archive/category pages are treated as catalog so we follow
                # their pagination and collect their product links (terminals).
                link_is_catalog = is_pagination or any(
                    re.search(pattern, link)
                    for pattern in self.config.catalog_patterns
                )
                if link_is_catalog:
                    if is_pagination and self._pagination_count >= self.config.max_pages:
                        continue
                    if is_pagination:
                        self._pagination_count += 1
                    queue.append((link, True))
                else:
                    queue.append((link, False))

        logger.info("crawl finished: processed=%d", processed)
        return processed

    def _sitemap_urls(self, depth: int = 0) -> list[str]:
        if depth > 2:
            return []
        candidates = [
            f"https://{self.config.allowed_domain}/sitemap.xml",
            f"https://{self.config.allowed_domain}/sitemap_index.xml",
        ]
        urls: list[str] = []
        headers = {"User-Agent": self.config.user_agent}
        for candidate in candidates:
            try:
                with httpx.Client(
                    timeout=20, follow_redirects=True, headers=headers
                ) as client:
                    response = client.get(candidate)
                    if response.status_code != 200:
                        continue
                    root = ET.fromstring(response.content)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.warning("sitemap fetch failed %s: %s", candidate, exc)
                continue

            sub_sitemaps: list[str] = []
            for element in root.iter():
                if not element.tag.endswith("loc") or not element.text:
                    continue
                loc = element.text.strip()
                if element.tag.endswith("sitemap") or root.tag.endswith("sitemapindex"):
                    sub_sitemaps.append(loc)
                else:
                    urls.append(loc)

            for sub in sub_sitemaps:
                urls.extend(self._sitemap_urls_from(sub, depth + 1))

        domain = self.config.allowed_domain.lower()
        return [
            u for u in urls if urlparse(u).netloc.lower() == domain
        ]

    def _sitemap_urls_from(self, url: str, depth: int) -> list[str]:
        if depth > 2:
            return []
        headers = {"User-Agent": self.config.user_agent}
        found: list[str] = []
        try:
            with httpx.Client(
                timeout=20, follow_redirects=True, headers=headers
            ) as client:
                response = client.get(url)
                if response.status_code != 200:
                    return found
                root = ET.fromstring(response.content)
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("sitemap fetch failed %s: %s", url, exc)
            return found

        sub: list[str] = []
        for element in root.iter():
            if not element.tag.endswith("loc") or not element.text:
                continue
            loc = element.text.strip()
            if root.tag.endswith("sitemapindex"):
                sub.append(loc)
            else:
                found.append(loc)
        for s in sub:
            found.extend(self._sitemap_urls_from(s, depth + 1))
        return found
