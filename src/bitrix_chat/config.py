from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    bitrix_rest_webhook_url: str
    bitrix_bot_id: int
    bitrix_bot_token: str
    inbound_secret: str
    bitrix_client_id: str
    bitrix_client_secret: str
    bitrix_app_state_path: str
    bitrix_app_webhook_url: str
    bitrix_openline_response_webhook_url: str
    log_level: str = "INFO"


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        bitrix_rest_webhook_url=os.getenv("BITRIX_REST_WEBHOOK_URL", "").strip(),
        bitrix_bot_id=int(os.getenv("BITRIX_BOT_ID", "0") or 0),
        bitrix_bot_token=os.getenv("BITRIX_BOT_TOKEN", "").strip(),
        inbound_secret=os.getenv("BITRIX_INBOUND_SECRET", "change-me").strip(),
        bitrix_client_id=os.getenv("BITRIX_CLIENT_ID", "").strip(),
        bitrix_client_secret=os.getenv("BITRIX_CLIENT_SECRET", "").strip(),
        bitrix_app_state_path=os.getenv("BITRIX_APP_STATE_PATH", ".bitrix/app_auth.json").strip(),
        bitrix_app_webhook_url=os.getenv("BITRIX_APP_WEBHOOK_URL", "").strip(),
        bitrix_openline_response_webhook_url=os.getenv(
            "BITRIX_OPENLINE_RESPONSE_WEBHOOK_URL",
            "https://builder.smartybotapps.ru/webhook/amoBitrixTest",
        ).strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
