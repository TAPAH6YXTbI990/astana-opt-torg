from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from typing import Any
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .app_auth import AppAuth, AppAuthStore


_SENSITIVE_KEYS = {
    "auth",
    "access_token",
    "refresh_token",
    "client_secret",
    "bot_token",
    "token",
    "application_token",
}


def _sanitize_for_log(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if str(key).lower() in _SENSITIVE_KEYS else _sanitize_for_log(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_for_log(item) for item in value]
    return value


@dataclass(slots=True)
class OAuthBitrixClient:
    client_id: str
    client_secret: str
    auth_store: AppAuthStore
    _logger: logging.Logger = logging.getLogger(__name__)

    def _get_auth(self) -> AppAuth:
        auth = self.auth_store.load()
        if auth is None:
            raise RuntimeError("Application auth is not installed yet")
        return auth

    def _refresh_auth(self, auth: AppAuth) -> AppAuth:
        payload = urlencode(
            {
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": auth.refresh_token,
            }
        ).encode("utf-8")
        request = Request(
            "https://oauth.bitrix24.tech/oauth/token/",
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
        except URLError as exc:
            raise RuntimeError(f"OAuth token refresh failed: {exc}") from exc
        refreshed = AppAuth.from_mapping({**asdict(auth), **data})
        self.auth_store.save(refreshed)
        return refreshed

    def call(self, method: str, params: dict[str, Any]) -> object:
        auth = self._get_auth()
        endpoint = auth.client_endpoint.rstrip("/")
        url = f"{endpoint}/{method}.json"
        payload = {**params, "auth": auth.access_token}
        self._logger.info(
            "bitrix rest request method=%s url=%s body=%s",
            method,
            url,
            json.dumps(_sanitize_for_log(payload), ensure_ascii=False),
        )
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                response_text = response.read().decode("utf-8", errors="replace")
                self._logger.info(
                    "bitrix rest response method=%s url=%s body=%s",
                    method,
                    url,
                    response_text,
                )
                return json.loads(response_text)
        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 401:
                refreshed = self._refresh_auth(auth)
                retry_payload = {**params, "auth": refreshed.access_token}
                self._logger.info(
                    "bitrix rest retry method=%s url=%s body=%s",
                    method,
                    url,
                    json.dumps(_sanitize_for_log(retry_payload), ensure_ascii=False),
                )
                retry_body = json.dumps(retry_payload).encode("utf-8")
                retry_request = Request(
                    url,
                    data=retry_body,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    method="POST",
                )
                try:
                    with urlopen(retry_request, timeout=30) as response:
                        response_text = response.read().decode("utf-8", errors="replace")
                        self._logger.info(
                            "bitrix rest response method=%s url=%s body=%s",
                            method,
                            url,
                            response_text,
                        )
                        return json.loads(response_text)
                except URLError as retry_exc:
                    raise RuntimeError(f"REST retry failed after token refresh: {retry_exc}") from retry_exc
            raise RuntimeError(f"REST call failed with HTTP {exc.code}: {response_body}") from exc

    def bind_event(self, event: str, handler: str) -> object:
        response = self.call("event.bind", {"event": event, "handler": handler})
        self._logger.info("bound event", extra={"event": event, "handler": handler, "response": response})
        return response

    def get_openline_dialog(self, user_code: str) -> object:
        response = self.call(
            "imopenlines.dialog.get",
            {
                "USER_CODE": user_code,
            },
        )
        self._logger.info(
            "fetched openlines dialog",
            extra={"user_code": user_code, "response": response},
        )
        return response

    def send_connector_messages(self, connector: str, line: int, messages: list[dict[str, object]]) -> object:
        response = self.call(
            "imconnector.send.messages",
            {
                "CONNECTOR": connector,
                "LINE": int(line),
                "MESSAGES": messages,
            },
        )
        self._logger.info(
            "sent openlines message",
            extra={"connector": connector, "line": line, "messages_count": len(messages), "response": response},
        )
        return response

    def send_connector_delivery(self, connector: str, line: int, messages: list[dict[str, object]]) -> object:
        response = self.call(
            "imconnector.send.status.delivery",
            {
                "CONNECTOR": connector,
                "LINE": int(line),
                "MESSAGES": messages,
            },
        )
        self._logger.info(
            "sent openlines delivery",
            extra={"connector": connector, "line": line, "messages_count": len(messages), "response": response},
        )
        return response

    def send_openline_session_message(self, chat_id: int, message: str, name: str = "DEFAULT") -> object:
        response = self.call(
            "imopenlines.bot.session.message.send",
            {
                "CHAT_ID": int(chat_id),
                "NAME": name,
                "MESSAGE": message,
            },
        )
        self._logger.info(
            "sent openlines session message",
            extra={"chat_id": chat_id, "message_mode": name, "response": response},
        )
        return response

    def get_openline_session_history(self, chat_id: int) -> object:
        response = self.call(
            "imopenlines.session.history.get",
            {
                "CHAT_ID": int(chat_id),
            },
        )
        self._logger.info(
            "fetched openlines session history",
            extra={"chat_id": chat_id, "response": response},
        )
        return response
