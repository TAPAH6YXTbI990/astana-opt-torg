"""Build unified catalog from clean product .md files.

Reads knowledge/raw/*.md, extracts structured product data,
and generates catalog.json + catalog.md.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


# Patterns to extract from product markdown
PRICE_RE = re.compile(r"₸\s*([\d\s,\.]+)")
SKU_RE = re.compile(r"SKU:\s*(\S+)", re.IGNORECASE)
STOCK_RE = re.compile(r"(\d+)\s*(?:in stock|в наличии)", re.IGNORECASE)
CATEGORY_RE = re.compile(r"Category:\s*(.+?)(?:\n|$)", re.IGNORECASE)


def extract_product_data(filepath: Path, url: str) -> dict | None:
    """Extract structured product data from a clean .md file."""
    content = filepath.read_text(encoding="utf-8")

    # Skip empty or very short files
    if len(content) < 50:
        return None

    # Extract name (first heading)
    name_match = re.search(r"^#\s+(.+?)$", content, re.MULTILINE)
    if not name_match:
        name = filepath.stem.replace("_", " ").replace("-", " ").title()
    else:
        name = name_match.group(1).strip()

    # Extract price
    price_match = PRICE_RE.search(content)
    price = None
    if price_match:
        price_str = price_match.group(1).replace(" ", "").replace(",", ".")
        try:
            price = float(price_str)
        except ValueError:
            pass

    # Extract stock
    stock_match = STOCK_RE.search(content)
    stock = int(stock_match.group(1)) if stock_match else None

    # Extract attributes from table (skip separator rows)
    attributes = {}
    table_rows = re.findall(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|$", content, re.MULTILINE)
    for key, value in table_rows:
        key = key.strip()
        value = value.strip()
        # Skip separator rows (contain only dashes and colons)
        if re.match(r"^[-:\s|]+$", key) or re.match(r"^[-:\s|]+$", value):
            continue
        if key and value:
            attributes[key] = value

    # Build description from attributes
    description = None
    if attributes:
        desc_parts = []
        for key, value in attributes.items():
            # Clean up any remaining table characters
            clean_value = value.rstrip("|").strip()
            desc_parts.append(f"{key}: {clean_value}")
        description = "; ".join(desc_parts[:5])  # First 5 attributes

    # Extract category path from URL
    category_path = None
    if url:
        path_parts = url.split("astopt.com/")[-1].split("/")
        if len(path_parts) > 1:
            category_path = " > ".join(path_parts[:-1])

    return {
        "name": name,
        "description": description,
        "price": price,
        "stock": stock,
        "attributes": attributes,
        "category_path": category_path,
        "url": url,
        "source_file": filepath.name,
    }


def main() -> None:
    raw_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("knowledge/raw")
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("knowledge/catalog")

    if not raw_dir.exists():
        print(f"Error: {raw_dir} not found", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load URL mapping if available
    urls_file = Path("product_urls.txt")
    url_map = {}
    if urls_file.exists():
        for line in urls_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                slug = line.split("astopt.com/")[-1].replace("/", "_").strip("_")
                url_map[slug] = line

    # Process all .md files
    products = []
    for filepath in sorted(raw_dir.glob("*.md")):
        url = url_map.get(filepath.stem, "")
        product = extract_product_data(filepath, url)
        if product:
            products.append(product)

    # Sort by category then name
    products.sort(key=lambda p: (p.get("category_path") or "", p.get("name") or ""))

    # Write JSON
    json_path = output_dir / "catalog.json"
    json_path.write_text(
        json.dumps(products, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Write Markdown
    md_path = output_dir / "catalog.md"
    lines = [
        "# Каталог товаров АстанаОптТорг",
        "",
        f"Всего товаров: {len(products)}",
        "",
    ]

    # Group by category
    current_category = None
    for product in products:
        cat = product.get("category_path") or "Без категории"
        if cat != current_category:
            current_category = cat
            lines.extend(["", f"## {cat}", ""])

        name = product.get("name") or "Без названия"
        price = f"₸ {product['price']:,.2f}" if product.get("price") else "Цена не указана"
        sku = f"Артикул: {product['sku']}" if product.get("sku") else ""
        stock = product['stock'] if product.get("stock") is not None else None
        desc = product.get("description") or ""

        lines.extend([
            f"### {name}",
            "",
            f"**Цена:** {price}",
        ])
        if stock is not None:
            if stock is not None:
                lines.append(f"**Остаток:** {stock} шт")
        if product.get("attributes"):
            lines.extend(["", "**Характеристики:**", ""])
            for key, value in product["attributes"].items():
                # Clean up table characters
                clean_value = value.rstrip("|").strip()
                lines.append(f"- {key}: {clean_value}")
        if product.get("url"):
            lines.extend(["", f"[Подробнее]({product['url']})"])
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Built catalog: {len(products)} products")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
