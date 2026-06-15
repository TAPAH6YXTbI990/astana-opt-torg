from __future__ import annotations

import argparse
import json
import sys

from .app_auth import AppAuthStore
from .config import get_settings
from .oauth_client import OAuthBitrixClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bind Open Lines event handler for Bitrix24 app")
    parser.add_argument(
        "--handler",
        default=None,
        help="Public HTTPS URL for ONOPENLINEMESSAGEADD handler",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    handler_url = args.handler or settings.bitrix_app_webhook_url
    if not handler_url:
        raise SystemExit("Handler URL is required. Pass --handler or set BITRIX_APP_WEBHOOK_URL.")

    auth_store = AppAuthStore(settings.bitrix_app_state_path)
    client = OAuthBitrixClient(
        client_id=settings.bitrix_client_id,
        client_secret=settings.bitrix_client_secret,
        auth_store=auth_store,
    )
    response = client.bind_event("ONOPENLINEMESSAGEADD", handler_url)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
