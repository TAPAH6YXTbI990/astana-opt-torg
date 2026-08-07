"""Extract product URLs from category/tag .md files in crawl_output.

Reads product-tag_*.md and product-category_*.md, extracts unique product URLs
(pattern: /shop/.../<slug>/), deduplicates, and writes product_urls.txt.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


# Product URL pattern: https://astopt.ru/shop/.../<slug>/
# Excludes: pagination (/page/N/), category pages, tag pages
PRODUCT_URL_RE = re.compile(r"https?://astopt\.ru/shop/(?!page/\d)([^\s\)\"']+)")

# Markdown link pattern: [text](url)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://astopt\.ru/shop/[^\)]+)\)")

# Pages to skip (non-product patterns)
SKIP_PATTERNS = [
    r"/page/\d",
    r"/product-category/",
    r"/product-tag/",
    r"/tag/",
    r"/blog/",
    r"/author/",
    r"/cart/",
    r"/checkout/",
    r"/my-account/",
    r"/order-tracking/",
    r"/refund_returns/",
    r"/privacy-policy/",
    r"/about-us/",
    r"/contact-us/",
]


def is_product_url(url: str) -> bool:
    """Check if URL is a product page (not pagination, category, etc.)."""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, url):
            return False
    # Product URLs end with a slug (not empty, not /)
    path = url.split("astopt.ru")[-1].rstrip("/")
    if not path or path == "/shop":
        return False
    # Must have at least 2 path segments under /shop/
    segments = [s for s in path.split("/") if s]
    return len(segments) >= 2


def extract_from_file(filepath: Path) -> list[tuple[str, str]]:
    """Extract (url, name) pairs from a single .md file."""
    content = filepath.read_text(encoding="utf-8")
    results = []
    seen = set()

    for match in MD_LINK_RE.finditer(content):
        name = match.group(1).strip()
        url = match.group(2).strip()

        # Clean URL: remove query params, fragments
        url = url.split("?")[0].split("#")[0].rstrip("/")

        if url in seen:
            continue
        if not is_product_url(url):
            continue

        seen.add(url)
        results.append((url, name))

    return results


def main() -> None:
    crawl_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("crawl_output")
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("product_urls.txt")

    if not crawl_dir.exists():
        print(f"Error: {crawl_dir} not found", file=sys.stderr)
        sys.exit(1)

    # Find all tag and category files
    tag_files = list(crawl_dir.glob("product-tag_*.md"))
    category_files = list(crawl_dir.glob("product-category_*.md"))
    all_files = tag_files + category_files

    print(
        f"Scanning {len(all_files)} files ({len(tag_files)} tags, {len(category_files)} categories)"
    )

    all_urls: dict[str, str] = {}  # url -> name
    source_map: dict[str, list[str]] = {}  # url -> [source files]

    for filepath in sorted(all_files):
        items = extract_from_file(filepath)
        for url, name in items:
            if url not in all_urls:
                all_urls[url] = name
                source_map[url] = []
            source_map[url].append(filepath.name)

    # Sort by URL
    sorted_urls = sorted(all_urls.items())

    # Write output (no BOM)
    output_file.write_text(
        "\n".join(url for url, _ in sorted_urls) + "\n",
        encoding="utf-8",
    )

    # Write report
    report_file = output_file.with_suffix(".report.md")
    lines = [
        f"# Product URL Extraction Report",
        f"",
        f"**Source**: {crawl_dir}",
        f"**Files scanned**: {len(all_files)} ({len(tag_files)} tags, {len(category_files)} categories)",
        f"**Unique product URLs found**: {len(sorted_urls)}",
        f"",
        f"## URLs",
        f"",
    ]
    for url, name in sorted_urls:
        sources = ", ".join(Path(s).stem for s in source_map[url])
        lines.append(f"- `{url}` — {name} (from: {sources})")

    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Found {len(sorted_urls)} unique product URLs")
    print(f"Written to: {output_file}")
    print(f"Report: {report_file}")


if __name__ == "__main__":
    main()
