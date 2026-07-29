"""Re-crawl product URLs with improved cleaning.

Reads product_urls.txt, fetches each page with enhanced clean_selectors,
and saves clean .md files to knowledge/raw/.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from ..crawler.fetcher import fetch
from ..crawler.parser import parse_html


# Patterns to remove from markdown (post-processing)
NOISE_PATTERNS = [
    # Navigation
    r"^#{1,3}\s+Корзина.*$",
    r"^\[Главная\].*$",
    r"^\[Каталог\].*$",
    r"^\[О нас\].*$",
    r"^\[Наши новости\].*$",
    r"^\[Контакты\].*$",
    # Social share buttons
    r"^Share this\.\.\..*$",
    r"^Share on Facebook.*$",
    r"^Pin on Pinterest.*$",
    r"^Tweet about this.*$",
    r"^Share on LinkedIn.*$",
    r"^\[Facebook\].*$",
    r"^\[Pinterest\].*$",
    r"^\[Twitter\].*$",
    r"^\[Linkedin\].*$",
    # Footer block
    r"^\[X\]\(#\).*$",
    r"^Прямые поставки.*$",
    r"^\[Подробнее\]\(about-us\).*$",
    r"^### Время работы.*$",
    r"^\+7 \(\d+\).*$",
    r"^с \d+ до \d+.*$",
    r"^ТЦ .*$",
    r"^\[Подписаться\].*$",
    r"^© \d{4}.*$",
    # Image placeholders
    r"^<!-- image -->$",
    # Compare/buy buttons
    r"^\[Сравнить\].*$",
    r"^\[Купить в 1 клик\].*$",
    r"^\[Add to cart\].*$",
    r"^\?add-to-cart=\d+.*$",
    # Rating/reviews noise
    r"^\(\[Отзывы\]\(#reviews\)\).*$",
    r"^\[\(Отзывы\)\]\(#reviews\).*$",
    # Tabs
    r"^\- \[Дополнительно\].*$",
    r"^\- \[Reviews.*$",
    # Partial footer remnants
    r"^с \d+:\d+ до \d+:\d+.*$",
    r"^пр-т .*$",
    r"^ул\. .*$",
    r"^г\. .*$",
]

NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.MULTILINE)

# Breadcrumb pattern: [text](url) ... [text](url) Product Name
BREADCRUMB_RE = re.compile(r"^\[.+\]\(.+\)\s+(.+)$")


def clean_markdown(text: str) -> str:
    """Remove noise patterns from markdown, extract product name."""
    lines = text.split("\n")
    cleaned = []
    product_name = None

    for line in lines:
        stripped = line.strip()

        # Try to extract product name from breadcrumb before removing
        if product_name is None:
            breadcrumb_match = BREADCRUMB_RE.match(stripped)
            if breadcrumb_match:
                product_name = breadcrumb_match.group(1).strip()
                continue

        # Skip noise patterns
        if NOISE_RE.match(stripped):
            continue

        # Skip "#### Корзина" and similar widget headers
        if stripped.startswith("####") and any(
            kw in stripped for kw in ["Корзина", "Cart", "Basket"]
        ):
            continue

        # Skip empty lines that follow noise (collapse multiple empty lines)
        if not stripped and cleaned and not cleaned[-1].strip():
            continue

        cleaned.append(line)

    # Prepend product name as H1 if found
    if product_name:
        cleaned.insert(0, f"# {product_name}")
        cleaned.insert(1, "")

    return "\n".join(cleaned)


# Enhanced selectors to remove navigation, footer, product cards, etc.
PRODUCT_CLEAN_SELECTORS = [
    # Default selectors
    "script",
    "style",
    "noscript",
    "nav",
    "header",
    "aside",
    "footer",
    # Navigation menus
    ".nav-sidebar",
    ".main-navigation",
    ".site-header",
    ".site-footer",
    ".menu",
    "[class*='menu']",
    ".breadcrumb",
    "#secondary",
    ".widget-area",
    # Product-specific noise
    ".product-navigation",
    ".woocommerce-breadcrumb",
    ".woocommerce-product-gallery",
    ".product_meta",
    ".woocommerce-tabs",
    ".cart",
    ".quantity",
    "#reviews",
    "#comments",
    ".related",
    ".upsells",
    ".cross-sells",
    # Social/share buttons
    ".social-sharing",
    ".share",
    ".yith-wcwl-add-to-wishlist",
    ".yith-wocompare",
]


def main() -> None:
    urls_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("product_urls.txt")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("knowledge/raw")
    rate_limit = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5

    if not urls_file.exists():
        print(f"Error: {urls_file} not found", file=sys.stderr)
        sys.exit(1)

    urls = [line.strip().lstrip("\ufeff") for line in urls_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Loaded {len(urls)} product URLs")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Track progress
    success = 0
    failed = 0
    skipped = 0

    for i, url in enumerate(urls, 1):
        # Generate filename from URL
        slug = url.split("astopt.com/")[-1].replace("/", "_").strip("_")
        md_path = output_dir / f"{slug}.md"

        # Skip if already fetched
        if md_path.exists():
            skipped += 1
            continue

        try:
            raw, cleaned, title = fetch(
                url,
                user_agent="Mozilla/5.0 (compatible; AstoptCrawler/1.0; +https://astopt.com/bot)",
                selectors=PRODUCT_CLEAN_SELECTORS,
            )

            # Parse with docling
            doc = parse_html(cleaned)
            markdown = doc.export_to_markdown()

            # Post-process: remove noise from markdown
            markdown = clean_markdown(markdown)

            # Write clean markdown
            md_path.write_text(markdown, encoding="utf-8")
            success += 1

            if i % 10 == 0 or i == len(urls):
                print(f"Progress: {i}/{len(urls)} (success={success}, failed={failed}, skipped={skipped})")

        except Exception as exc:
            failed += 1
            print(f"Error fetching {url}: {exc}", file=sys.stderr)

        time.sleep(rate_limit)

    print(f"\nDone: {success} fetched, {failed} failed, {skipped} skipped")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
