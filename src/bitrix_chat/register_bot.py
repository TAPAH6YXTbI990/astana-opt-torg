from __future__ import annotations

import argparse
import json
import os
from dotenv import load_dotenv

from .bitrix_client import BitrixClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Register a Bitrix24 chat bot")
    parser.add_argument("--code", required=True, help="Unique bot code inside the app")
    parser.add_argument("--name", required=True, help="Bot display name")
    parser.add_argument("--bot-token", required=True, help="Bot token to store in Bitrix24 for webhook auth")
    parser.add_argument("--webhook-url", required=True, help="Public webhook URL for inbound events")
    parser.add_argument("--type", default="bot", help="Bot type: bot, network, openline, supervisor, personal")
    parser.add_argument("--hidden", action="store_true", help="Register bot as hidden")
    parser.add_argument("--openline", action="store_true", help="Enable Open Lines support")
    parser.add_argument("--background-id", default=None, help="Optional chat background id")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    rest_webhook_url = os.getenv("BITRIX_REST_WEBHOOK_URL", "").strip()

    if not rest_webhook_url:
        parser.error("BITRIX_REST_WEBHOOK_URL must be set in the environment")

    client = BitrixClient(rest_webhook_url=rest_webhook_url, bot_id=0, bot_token=args.bot_token)
    fields: dict[str, object] = {
        "code": args.code,
        "type": args.type,
        "eventMode": "webhook",
        "webhookUrl": args.webhook_url,
        "isHidden": bool(args.hidden),
        "isSupportOpenline": bool(args.openline),
        "properties": {
            "name": args.name,
        },
    }
    if args.background_id is not None:
        fields["backgroundId"] = args.background_id

    response = client.register_bot(fields, bot_token=args.bot_token)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
