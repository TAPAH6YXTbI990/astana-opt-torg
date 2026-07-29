from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _iter_listish(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if not value:
            return []
        if all(str(key).isdigit() for key in value.keys()):
            return [
                value[key]
                for key in sorted(value.keys(), key=lambda item: int(str(item)))
            ]
        return [value]
    return []


def _lookup(mapping: Any, key: str) -> Any:
    if isinstance(mapping, dict):
        if key in mapping:
            return mapping[key]
        if key.lower() in mapping:
            return mapping[key.lower()]
        if key.upper() in mapping:
            return mapping[key.upper()]
    return None


def _resolve(data: Any, path: tuple[str, ...]) -> Any:
    current = data
    for key in path:
        current = _lookup(current, key)
        if current is None:
            return None
    return current


@dataclass(slots=True)
class IncomingEvent:
    raw: dict[str, Any]
    event_type: str
    bot_id: int | None
    dialog_id: str | None
    message_id: int | None
    message_text: str | None
    sender_id: int | None
    sender_is_bot: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "IncomingEvent":
        raw_data = _as_mapping(_lookup(payload, "data"))
        bot_data = _as_mapping(_lookup(payload, "bot") or _lookup(raw_data, "bot"))
        chat_data = _as_mapping(_lookup(payload, "chat") or _lookup(raw_data, "chat"))
        message_data = _as_mapping(
            _lookup(payload, "message") or _lookup(raw_data, "message")
        )
        user_data = _as_mapping(_lookup(payload, "user") or _lookup(raw_data, "user"))

        event_type = (
            _lookup(payload, "event")
            or _lookup(payload, "type")
            or _lookup(raw_data, "event")
            or ""
        )

        bot_id = _extract_bot_id(payload, raw_data, bot_data)
        dialog_id = _first_str(
            payload,
            ("dialogId",),
            ("chat", "dialogId"),
            ("data", "chat", "dialogId"),
            ("chat", "dialog_id"),
        ) or _first_str(
            raw_data,
            (
                "PARAMS",
                "DIALOG_ID",
            ),
            ("data", "PARAMS", "DIALOG_ID"),
            ("dialogId",),
            ("chat", "dialogId"),
        )

        message_text = _first_str(
            payload,
            ("message", "text"),
            ("data", "message", "text"),
            ("messageText",),
        ) or _first_str(
            raw_data,
            ("PARAMS", "MESSAGE"),
            ("data", "PARAMS", "MESSAGE"),
            ("message", "text"),
            ("messageText",),
        )

        message_id = _first_int(
            payload,
            ("message", "id"),
            ("data", "message", "id"),
            ("messageId",),
        ) or _first_int(
            raw_data,
            ("PARAMS", "MESSAGE_ID"),
            ("data", "PARAMS", "MESSAGE_ID"),
            ("messageId",),
            ("message", "id"),
        )

        sender_id = _first_int(
            payload,
            ("user", "id"),
            ("data", "user", "id"),
            ("user", "ID"),
        ) or _first_int(
            raw_data,
            ("PARAMS", "FROM_USER_ID"),
            ("data", "PARAMS", "FROM_USER_ID"),
            ("user", "ID"),
            ("user", "id"),
        )

        sender_is_bot = _first_bool(
            payload,
            ("user", "bot"),
            ("user", "bot"),
            ("user", "IS_BOT"),
            ("data", "user", "bot"),
        ) or _first_bool(
            raw_data,
            ("USER", "IS_BOT"),
            ("data", "USER", "IS_BOT"),
            ("user", "IS_BOT"),
            ("user", "bot"),
        )

        return cls(
            raw=payload,
            event_type=str(event_type),
            bot_id=bot_id,
            dialog_id=dialog_id,
            message_id=message_id,
            message_text=message_text,
            sender_id=sender_id,
            sender_is_bot=sender_is_bot,
        )


def _extract_bot_id(
    payload: dict[str, Any], raw_data: dict[str, Any], bot_data: dict[str, Any]
) -> int | None:
    candidate = (
        _lookup(bot_data, "id")
        or _lookup(bot_data, "ID")
        or _lookup(payload, "botId")
        or _lookup(raw_data, "botId")
        or _lookup(raw_data, "BOT_ID")
        or _lookup(payload, "bot_id")
    )
    try:
        if candidate not in (None, ""):
            return int(candidate)
    except (TypeError, ValueError):
        pass

    bot_block = _lookup(raw_data, "BOT")
    if isinstance(bot_block, dict):
        keys = list(bot_block.keys())
        if len(keys) == 1:
            try:
                return int(keys[0])
            except (TypeError, ValueError):
                pass
        bot_id = _first_int(bot_block, ("id",), ("ID",))
        if bot_id is not None:
            return bot_id
    return None


def _first_str(mapping: Any, *paths: tuple[str, ...]) -> str | None:
    for path in paths:
        value = _resolve(mapping, path)
        if value is not None and value != "":
            return str(value)
    return None


def _first_int(mapping: Any, *paths: tuple[str, ...]) -> int | None:
    for path in paths:
        value = _resolve(mapping, path)
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_bool(mapping: Any, *paths: tuple[str, ...]) -> bool:
    for path in paths:
        value = _resolve(mapping, path)
        if value is None or value == "":
            continue
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        return normalized in {"1", "true", "y", "yes"}
    return False


@dataclass(slots=True)
class ConnectorMessage:
    chat_id: str
    im_chat_id: int
    im_message_id: int
    user_id: str | None
    text: str | None


@dataclass(slots=True)
class ConnectorEvent:
    raw: dict[str, Any]
    event_type: str
    event_id: int | None
    connector_id: str | None
    line_id: int | None
    application_token: str | None
    messages: list[ConnectorMessage]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ConnectorEvent":
        data = _as_mapping(_lookup(payload, "data"))
        auth = _as_mapping(_lookup(payload, "auth"))
        event_type = str(_lookup(payload, "event") or "")
        event_id = _first_int(payload, ("eventId",), ("event_handler_id",))
        connector_id = _first_str(data, ("CONNECTOR",), ("connector",))
        line_id = _first_int(data, ("LINE",), ("line",))
        application_token = _first_str(
            auth, ("application_token",), ("applicationToken",)
        )

        messages_raw = _lookup(data, "MESSAGES")
        messages: list[ConnectorMessage] = []
        for item in _iter_listish(messages_raw):
            message = _parse_connector_message(item)
            if message is not None:
                messages.append(message)

        return cls(
            raw=payload,
            event_type=event_type,
            event_id=event_id,
            connector_id=connector_id,
            line_id=line_id,
            application_token=application_token,
            messages=messages,
        )


@dataclass(slots=True)
class AppInstallEvent:
    raw: dict[str, Any]
    event_type: str
    application_token: str | None
    auth: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AppInstallEvent":
        auth = _as_mapping(_lookup(payload, "auth"))
        event_type = str(_lookup(payload, "event") or "")
        application_token = _first_str(
            auth, ("application_token",), ("applicationToken",)
        )
        return cls(
            raw=payload,
            event_type=event_type,
            application_token=application_token,
            auth=auth,
        )


@dataclass(slots=True)
class OpenLineMessage:
    connector_id: str | None
    line_id: int | None
    chat_id: str | None
    connector_chat_id: str | None
    connector_user_id: int | None
    message_user_id: int | None
    message_id: str | None
    text: str | None
    is_system: bool


@dataclass(slots=True)
class OpenLineEvent:
    raw: dict[str, Any]
    event_type: str
    event_id: int | None
    application_token: str | None
    messages: list[OpenLineMessage]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OpenLineEvent":
        data = _as_mapping(_lookup(payload, "data"))
        auth = _as_mapping(_lookup(payload, "auth"))
        event_type = str(_lookup(payload, "event") or "")
        event_id = _first_int(payload, ("eventId",), ("event_handler_id",))
        application_token = _first_str(
            auth, ("application_token",), ("applicationToken",)
        )

        messages_raw = _lookup(data, "DATA")
        messages: list[OpenLineMessage] = []
        for item in _iter_listish(messages_raw):
            message = _parse_openline_message(item)
            if message is not None:
                messages.append(message)

        return cls(
            raw=payload,
            event_type=event_type,
            event_id=event_id,
            application_token=application_token,
            messages=messages,
        )


def _parse_openline_message(item: Any) -> OpenLineMessage | None:
    if not isinstance(item, dict):
        return None

    connector = _as_mapping(_lookup(item, "connector"))
    chat = _as_mapping(_lookup(item, "chat"))
    message = _as_mapping(_lookup(item, "message"))

    connector_id = _first_str(connector, ("connector_id",), ("connectorId",))
    line_id = _first_int(connector, ("line_id",), ("lineId",))
    connector_chat_id = _first_str(connector, ("chat_id",), ("chatId",))
    connector_user_id = _first_int(connector, ("user_id",), ("userId",))
    chat_id = _first_str(chat, ("id",))
    message_user_id = _first_int(message, ("user_id",), ("userId",))
    message_id = _first_str(message, ("id",))
    text = _first_str(message, ("text",))
    is_system = _first_bool(message, ("system",), ("is_system",), ("isSystem",))

    return OpenLineMessage(
        connector_id=connector_id,
        line_id=line_id,
        chat_id=chat_id,
        connector_chat_id=connector_chat_id,
        connector_user_id=connector_user_id,
        message_user_id=message_user_id,
        message_id=message_id,
        text=text,
        is_system=is_system,
    )


def _parse_connector_message(item: Any) -> ConnectorMessage | None:
    if not isinstance(item, dict):
        return None

    im_block = _as_mapping(_lookup(item, "im"))
    message_block = _as_mapping(_lookup(item, "message"))
    chat_block = _as_mapping(_lookup(item, "chat"))

    chat_id = _first_str(chat_block, ("id",))
    im_chat_id = _first_int(im_block, ("chat_id",), ("chatId",))
    im_message_id = _first_int(im_block, ("message_id",), ("messageId",))
    user_id = _first_str(message_block, ("user_id",), ("userId",))
    text = _first_str(message_block, ("text",))

    if chat_id is None or im_chat_id is None or im_message_id is None:
        return None

    return ConnectorMessage(
        chat_id=chat_id,
        im_chat_id=im_chat_id,
        im_message_id=im_message_id,
        user_id=user_id,
        text=text,
    )
