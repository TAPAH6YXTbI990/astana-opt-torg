from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from typing import Optional

from .config import CrawlConfig
from .crawler import Crawler


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bitrix-crawl",
        description="Crawl a WordPress/WooCommerce site and parse pages with docling.",
    )
    parser.add_argument(
        "--config",
        default="crawler_config.toml",
        help="Path to the crawler TOML config (default: crawler_config.toml).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output_dir from the config.",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        help="Override rate_limit_s (seconds between requests).",
    )
    parser.add_argument(
        "--no-robots",
        action="store_true",
        help="Ignore robots.txt and crawl everything allowed by config.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Override max_pages (catalog pagination cap).",
    )
    parser.add_argument(
        "--max-total",
        type=int,
        default=None,
        help="Override max_total_pages (total pages cap).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        config = CrawlConfig.from_toml(args.config)
    except FileNotFoundError:
        print(f"Config not found: {args.config}", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Failed to load config: {exc}", file=sys.stderr)
        return 2

    if args.output_dir is not None:
        config = replace(config, output_dir=args.output_dir)
    if args.rate_limit is not None:
        config = replace(config, rate_limit_s=args.rate_limit)
    if args.no_robots:
        config = replace(config, respect_robots=False)
    if args.max_pages is not None:
        config = replace(config, max_pages=args.max_pages)
    if args.max_total is not None:
        config = replace(config, max_total_pages=args.max_total)

    try:
        config.validate()
    except ValueError as exc:
        print(f"Invalid config: {exc}", file=sys.stderr)
        return 2

    crawler = Crawler(config)
    crawler.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
