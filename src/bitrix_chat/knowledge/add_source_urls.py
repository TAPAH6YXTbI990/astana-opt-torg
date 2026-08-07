"""Add source URLs to product .md files in knowledge/raw/.

Reads product_urls.txt to get slug→URL mapping, appends **Источник:** line
to each .md file.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    urls_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("product_urls.txt")
    raw_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("knowledge/raw")

    if not urls_file.exists():
        print(f"Error: {urls_file} not found", file=sys.stderr)
        sys.exit(1)

    # Build slug→URL mapping
    url_map: dict[str, str] = {}
    for line in urls_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        slug = line.split("astopt.ru/")[-1].replace("/", "_").strip("_")
        url_map[slug] = line

    updated = 0
    for filepath in sorted(raw_dir.glob("*.md")):
        content = filepath.read_text(encoding="utf-8")

        # Skip if already has source
        if "**Источник:**" in content:
            continue

        url = url_map.get(filepath.stem)
        if not url:
            continue

        # Append source URL
        content = content.rstrip() + f"\n\n**Источник:** {url}\n"
        filepath.write_text(content, encoding="utf-8")
        updated += 1

    print(f"Updated {updated} files")


if __name__ == "__main__":
    main()
