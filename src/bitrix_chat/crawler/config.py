from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; AstoptCrawler/1.0; +https://astopt.ru/bot)"
)

DEFAULT_EXCLUDE_PATTERNS = [
    r"/wp-admin/",
    r"/wp-login",
    r"wp-login\.php",
    r"/cart/",
    r"/checkout/",
    r"/my-account",
    r"/wishlist",
    r"/wc-api/",
    r"/feed/",
    r"add-to-cart",
    r"compare",
    r"\.css",
    r"\.js$",
    r"\.png$",
    r"\.jpg$",
    r"\.jpeg$",
    r"\.gif$",
    r"\.webp$",
    r"\.pdf$",
    r"\.svg$",
    r"\.woff2?$",
    r"\.ico$",
]

DEFAULT_PAGINATION_PATTERNS = [
    r"/page/\d+/?$",
    r"\?paged=\d+",
    r"\?product-page=\d+",
    r"\?page=\d+",
]

# Archive/category pages are treated as catalog: we follow their pagination
# and collect their product links (terminal), instead of stopping at depth 1.
DEFAULT_CATALOG_PATTERNS = [
    r"/product-category/",
    r"/shop/",
    r"/product-tag/",
    r"/tag/",
]

# Stripped from HTML before docling to reduce navigation/footer boilerplate.
DEFAULT_CLEAN_SELECTORS = [
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "aside",
    "footer",
]


@dataclass(frozen=True, slots=True)
class CrawlConfig:
    seeds: list[str]
    allowed_domain: str
    output_dir: str = "crawl_output"
    rate_limit_s: float = 1.0
    user_agent: str = DEFAULT_USER_AGENT
    respect_robots: bool = True
    use_sitemap: bool = False
    max_pages: int = 200
    max_total_pages: int = 2000
    exclude_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_EXCLUDE_PATTERNS)
    )
    pagination_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_PAGINATION_PATTERNS)
    )
    catalog_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_CATALOG_PATTERNS)
    )
    clean_selectors: list[str] = field(
        default_factory=lambda: list(DEFAULT_CLEAN_SELECTORS)
    )

    @classmethod
    def from_toml(cls, path: str) -> "CrawlConfig":
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return cls(
            seeds=list(data.get("seeds", [])),
            allowed_domain=str(data.get("allowed_domain", "")).strip(),
            output_dir=str(data.get("output_dir", "crawl_output")),
            rate_limit_s=float(data.get("rate_limit_s", 1.0)),
            user_agent=str(data.get("user_agent", DEFAULT_USER_AGENT)),
            respect_robots=bool(data.get("respect_robots", True)),
            use_sitemap=bool(data.get("use_sitemap", False)),
            max_pages=int(data.get("max_pages", 200)),
            max_total_pages=int(data.get("max_total_pages", 2000)),
            exclude_patterns=list(
                data.get("exclude_patterns", DEFAULT_EXCLUDE_PATTERNS)
            ),
            pagination_patterns=list(
                data.get("pagination_patterns", DEFAULT_PAGINATION_PATTERNS)
            ),
            catalog_patterns=list(
                data.get("catalog_patterns", DEFAULT_CATALOG_PATTERNS)
            ),
            clean_selectors=list(data.get("clean_selectors", DEFAULT_CLEAN_SELECTORS)),
        )

    def validate(self) -> None:
        if not self.seeds:
            raise ValueError("crawler config: 'seeds' must not be empty")
        if not self.allowed_domain:
            raise ValueError("crawler config: 'allowed_domain' must be set")
