from __future__ import annotations

import json
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .app_auth import AppAuthStore
from .bitrix_client import BitrixClient
from .config import Settings, get_settings
from .events import AppInstallEvent, OpenLineEvent, IncomingEvent
from .handlers import AppInstallHandler, EchoMessageHandler, OpenLineMessageHandler
from .payloads import load_payload
from .oauth_client import OAuthBitrixClient
from .storage import InMemoryDedupStore


_SENSITIVE_KEYS = {
    "auth",
    "access_token",
    "refresh_token",
    "client_secret",
    "bot_token",
    "token",
    "application_token",
}


def _sanitize_for_log(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: ("***" if str(key).lower() in _SENSITIVE_KEYS else _sanitize_for_log(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_for_log(item) for item in value]
    return value


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(title="Bitrix Chat Bot", version="0.1.0")
    app_auth_store = AppAuthStore(settings.bitrix_app_state_path)
    bitrix_client = BitrixClient(
        rest_webhook_url=settings.bitrix_rest_webhook_url,
        bot_id=settings.bitrix_bot_id,
        bot_token=settings.bitrix_bot_token,
    )
    oauth_client = OAuthBitrixClient(
        client_id=settings.bitrix_client_id,
        client_secret=settings.bitrix_client_secret,
        auth_store=app_auth_store,
    )
    dedup_store = InMemoryDedupStore()
    handler = EchoMessageHandler(bitrix_client, dedup_store, settings.bitrix_bot_id)
    app_install_handler = AppInstallHandler(
        app_auth_store,
        oauth_client,
        settings.bitrix_app_webhook_url,
    )
    openlines_handler = OpenLineMessageHandler(
        oauth_client,
        dedup_store,
        app_auth_store,
        settings.bitrix_openline_response_webhook_url,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    async def _handle_webhook(secret: str, request: Request) -> JSONResponse:
        logging.getLogger(__name__).info(
            "incoming bitrix webhook request",
            extra={
                "route": "bitrix24",
                "method": request.method,
                "path": str(request.url.path),
                "secret_len": len(secret),
                "secret_suffix": secret[-4:] if secret else "",
                "expected_secret_len": len(settings.inbound_secret),
                "expected_secret_suffix": settings.inbound_secret[-4:] if settings.inbound_secret else "",
            },
        )
        if secret != settings.inbound_secret:
            raise HTTPException(status_code=404, detail="not found")

        if request.method != "POST":
            return JSONResponse({"status": "ok", "method": request.method})

        payload = load_payload(await request.body(), request.headers.get("content-type", ""))
        logging.getLogger(__name__).info(
            "incoming app webhook payload=%s",
            json.dumps(_sanitize_for_log(payload), ensure_ascii=False),
        )
        event = IncomingEvent.from_payload(payload)

        try:
            result = handler.handle(event)
        except Exception as exc:  # pragma: no cover - operational safety
            logging.getLogger(__name__).exception("failed to handle bitrix webhook")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return JSONResponse(
            {
                "status": "ok",
                "handled": result.handled,
                "reason": result.reason,
                "echoed_text": result.echoed_text,
            }
        )

    @app.api_route("/webhooks/bitrix24/{secret}", methods=["GET", "POST", "HEAD"])
    async def bitrix24_webhook(secret: str, request: Request) -> JSONResponse:
        return await _handle_webhook(secret, request)

    async def _handle_openlines_webhook(secret: str, request: Request) -> JSONResponse:
        logging.getLogger(__name__).info(
            "incoming bitrix webhook request",
            extra={
                "route": "bitrix24/openlines",
                "method": request.method,
                "path": str(request.url.path),
                "secret_len": len(secret),
                "secret_suffix": secret[-4:] if secret else "",
                "expected_secret_len": len(settings.inbound_secret),
                "expected_secret_suffix": settings.inbound_secret[-4:] if settings.inbound_secret else "",
            },
        )
        if secret != settings.inbound_secret:
            raise HTTPException(status_code=404, detail="not found")

        if request.method != "POST":
            return JSONResponse({"status": "ok", "method": request.method})

        payload = load_payload(await request.body(), request.headers.get("content-type", ""))
        logging.getLogger(__name__).info(
            "incoming openlines webhook payload=%s",
            json.dumps(_sanitize_for_log(payload), ensure_ascii=False),
        )
        event = OpenLineEvent.from_payload(payload)

        try:
            result = openlines_handler.handle(event)
        except Exception as exc:  # pragma: no cover - operational safety
            logging.getLogger(__name__).exception("failed to handle openline webhook")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        if result.reason == "invalid_application_token":
            raise HTTPException(status_code=403, detail="invalid application token")

        return JSONResponse(
            {
                "status": "ok",
                "handled": result.handled,
                "reason": result.reason,
                "messages_count": len(event.messages),
            }
        )

    @app.api_route("/webhooks/bitrix24/openlines/{secret}", methods=["GET", "POST", "HEAD"])
    async def bitrix24_openlines_webhook(secret: str, request: Request) -> JSONResponse:
        return await _handle_openlines_webhook(secret, request)

    async def _handle_app_webhook(secret: str, request: Request) -> JSONResponse:
        logging.getLogger(__name__).info(
            "incoming bitrix webhook request",
            extra={
                "route": "bitrix24/app",
                "method": request.method,
                "path": str(request.url.path),
                "secret_len": len(secret),
                "secret_suffix": secret[-4:] if secret else "",
                "expected_secret_len": len(settings.inbound_secret),
                "expected_secret_suffix": settings.inbound_secret[-4:] if settings.inbound_secret else "",
            },
        )
        if secret != settings.inbound_secret:
            raise HTTPException(status_code=404, detail="not found")

        if request.method != "POST":
            return JSONResponse({"status": "ok", "method": request.method})

        payload = load_payload(await request.body(), request.headers.get("content-type", ""))
        logging.getLogger(__name__).info(
            "incoming app install payload=%s",
            json.dumps(_sanitize_for_log(payload), ensure_ascii=False),
        )
        event_type = str(payload.get("event", ""))

        if event_type == "ONAPPINSTALL":
            event = AppInstallEvent.from_payload(payload)
            try:
                result = app_install_handler.handle(event)
            except Exception as exc:  # pragma: no cover - operational safety
                logging.getLogger(__name__).exception("failed to handle app install")
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            return JSONResponse({"status": "ok", "handled": result.handled, "reason": result.reason})

        if event_type == "ONOPENLINEMESSAGEADD":
            event = OpenLineEvent.from_payload(payload)
            try:
                result = openlines_handler.handle(event)
            except Exception as exc:  # pragma: no cover - operational safety
                logging.getLogger(__name__).exception("failed to handle app openline event")
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            if result.reason == "invalid_application_token":
                raise HTTPException(status_code=403, detail="invalid application token")
            return JSONResponse(
                {
                    "status": "ok",
                    "handled": result.handled,
                    "reason": result.reason,
                    "messages_count": len(event.messages),
                }
            )

        return JSONResponse({"status": "ok", "handled": False, "reason": f"ignored_event:{event_type}"})

    @app.api_route("/webhooks/bitrix24/app/{secret}", methods=["GET", "POST", "HEAD"])
    async def bitrix24_app_webhook(secret: str, request: Request) -> JSONResponse:
        return await _handle_app_webhook(secret, request)

    return app


app = create_app()
