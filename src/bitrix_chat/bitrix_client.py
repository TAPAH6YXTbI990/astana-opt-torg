from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import logging


@dataclass(slots=True)
class BitrixClient:
    rest_webhook_url: str
    bot_id: int
    bot_token: str
    _client: Any = field(init=False, repr=False, default=None)
    _logger: logging.Logger = field(init=False, repr=False, default_factory=lambda: logging.getLogger(__name__))

    def __post_init__(self) -> None:
        if self.rest_webhook_url:
            from fast_bitrix24 import Bitrix

            self._client = Bitrix(self.rest_webhook_url)

    def send_message(self, dialog_id: str, message: str, reply_id: int | None = None) -> object:
        if self._client is None:
            raise RuntimeError("BITRIX_REST_WEBHOOK_URL is not configured")

        fields: dict[str, object] = {
            "message": message,
            "urlPreview": False,
        }
        if reply_id is not None:
            fields["replyId"] = int(reply_id)

        response = self._client.call(
            "imbot.v2.Chat.Message.send",
            {
                "botId": self.bot_id,
                "botToken": self.bot_token,
                "dialogId": dialog_id,
                "fields": fields,
            },
        )
        self._logger.info(
            "sent bitrix message",
            extra={
                "dialog_id": dialog_id,
                "reply_id": reply_id,
                "response": response,
            },
        )
        return response

    def register_bot(self, fields: dict[str, object], bot_token: str | None = None) -> object:
        if self._client is None:
            raise RuntimeError("BITRIX_REST_WEBHOOK_URL is not configured")

        request_fields = dict(fields)
        if bot_token:
            request_fields["botToken"] = bot_token

        return self._client.call("imbot.v2.Bot.register", {"fields": request_fields})

    def send_connector_messages(
        self,
        connector: str,
        line: int,
        messages: list[dict[str, object]],
    ) -> object:
        if self._client is None:
            raise RuntimeError("BITRIX_REST_WEBHOOK_URL is not configured")

        response = self._client.call(
            "imconnector.send.messages",
            {
                "CONNECTOR": connector,
                "LINE": int(line),
                "MESSAGES": messages,
            },
        )
        self._logger.info(
            "sent openlines message",
            extra={
                "connector": connector,
                "line": line,
                "messages_count": len(messages),
                "response": response,
            },
        )
        return response

    def send_connector_delivery(
        self,
        connector: str,
        line: int,
        messages: list[dict[str, object]],
    ) -> object:
        if self._client is None:
            raise RuntimeError("BITRIX_REST_WEBHOOK_URL is not configured")

        response = self._client.call(
            "imconnector.send.status.delivery",
            {
                "CONNECTOR": connector,
                "LINE": int(line),
                "MESSAGES": messages,
            },
        )
        self._logger.info(
            "sent openlines delivery",
            extra={
                "connector": connector,
                "line": line,
                "messages_count": len(messages),
                "response": response,
            },
        )
        return response
