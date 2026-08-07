from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from time import time
from uuid import uuid4
from urllib.request import Request, urlopen

from .agent.agent import Agent
from .agent.profile import ProfileStore
from .app_auth import AppAuth, AppAuthStore
from .bitrix_client import BitrixClient
from .events import (
    AppInstallEvent,
    ConnectorEvent,
    ConnectorMessage,
    IncomingEvent,
    OpenLineEvent,
    OpenLineMessage,
)
from .oauth_client import OAuthBitrixClient
from .storage import DedupStore


def _parse_lead_id(entity_data_1: str | None) -> int | None:
    """Parse lead ID from entity_data_1 format: 'Y|LEAD|{id}|...'"""
    if not entity_data_1:
        return None
    parts = entity_data_1.split("|")
    if len(parts) >= 3 and parts[1] == "LEAD":
        try:
            return int(parts[2])
        except (ValueError, TypeError):
            return None
    return None


_HANDOFF_PATTERN = re.compile(
    r"(менеджер|оператор|специалист|живой\s+человек|администратор|"
    r"связать|соединить|передать\s+запрос)",
    re.IGNORECASE,
)


def _normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"[^\d]", "", phone)
    if digits.startswith("8") and len(digits) == 11:
        return "+7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11:
        return "+" + digits
    if digits.startswith("7"):
        return "+" + digits
    return phone


@dataclass(slots=True)
class HandleResult:
    handled: bool
    reason: str
    echoed_text: str | None = None


class EchoMessageHandler:
    def __init__(
        self,
        bitrix_client: BitrixClient,
        dedup_store: DedupStore,
        bot_id: int,
    ) -> None:
        self._bitrix_client = bitrix_client
        self._dedup_store = dedup_store
        self._bot_id = bot_id
        self._logger = logging.getLogger(__name__)

    def handle(self, event: IncomingEvent) -> HandleResult:
        self._logger.info(
            "incoming bitrix event",
            extra={
                "event_type": event.event_type,
                "dialog_id": event.dialog_id,
                "message_id": event.message_id,
                "sender_id": event.sender_id,
                "sender_is_bot": event.sender_is_bot,
                "bot_id": event.bot_id,
            },
        )

        if event.event_type != "ONIMBOTV2MESSAGEADD":
            return HandleResult(False, f"ignored_event:{event.event_type}")

        if event.bot_id is not None and event.bot_id != self._bot_id:
            return HandleResult(False, "ignored_other_bot")

        if event.sender_is_bot or event.sender_id == self._bot_id:
            return HandleResult(False, "ignored_self_message")

        if not event.dialog_id:
            return HandleResult(False, "missing_dialog_id")

        if not event.message_text:
            return HandleResult(False, "missing_message_text")

        dedup_key = self._make_dedup_key(event)
        if self._dedup_store.seen(dedup_key):
            return HandleResult(False, "duplicate_event")

        response = self._bitrix_client.send_message(
            dialog_id=event.dialog_id,
            message=event.message_text,
            reply_id=event.message_id,
        )
        self._dedup_store.add(dedup_key)
        self._logger.info(
            "echoed message",
            extra={
                "event_type": event.event_type,
                "dialog_id": event.dialog_id,
                "message_id": event.message_id,
                "response": response,
            },
        )
        return HandleResult(True, "echo_sent", event.message_text)

    def _make_dedup_key(self, event: IncomingEvent) -> str:
        if event.message_id is not None:
            return f"{event.event_type}:{event.bot_id}:{event.dialog_id}:{event.message_id}"
        return (
            f"{event.event_type}:{event.bot_id}:{event.dialog_id}:{event.message_text}"
        )


class OpenLinesConnectorHandler:
    def __init__(
        self,
        bitrix_client: BitrixClient,
        dedup_store: DedupStore,
        auth_store: AppAuthStore,
        expected_application_token: str | None = None,
    ) -> None:
        self._bitrix_client = bitrix_client
        self._dedup_store = dedup_store
        self._auth_store = auth_store
        self._expected_application_token = expected_application_token or ""
        self._logger = logging.getLogger(__name__)

    def handle(self, event: ConnectorEvent) -> HandleResult:
        self._logger.info(
            "incoming openlines event",
            extra={
                "event_type": event.event_type,
                "event_id": event.event_id,
                "connector_id": event.connector_id,
                "line_id": event.line_id,
                "messages_count": len(event.messages),
            },
        )

        if event.event_type != "ONIMCONNECTORMESSAGEADD":
            return HandleResult(False, f"ignored_event:{event.event_type}")

        expected_token = self._expected_application_token
        stored_auth = self._auth_store.load()
        if stored_auth and stored_auth.application_token:
            expected_token = stored_auth.application_token

        if expected_token and event.application_token != expected_token:
            return HandleResult(False, "invalid_application_token")

        if not event.connector_id:
            return HandleResult(False, "missing_connector_id")

        if event.line_id is None:
            return HandleResult(False, "missing_line_id")

        handled = 0
        for message in event.messages:
            dedup_key = self._make_dedup_key(event, message)
            if self._dedup_store.seen(dedup_key):
                continue

            reply_text = message.text or ""
            if not reply_text.strip():
                continue

            outgoing_message_id = f"echo-{message.im_message_id}-{uuid4().hex}"
            now_ts = int(time())

            send_payload = [
                {
                    "user": {
                        "id": f"{event.connector_id}:echo-bot",
                        "name": "Echo Bot",
                    },
                    "message": {
                        "id": outgoing_message_id,
                        "date": now_ts,
                        "text": reply_text,
                    },
                    "chat": {
                        "id": message.chat_id,
                    },
                }
            ]

            delivery_payload = [
                {
                    "im": {
                        "chat_id": message.im_chat_id,
                        "message_id": message.im_message_id,
                    },
                    "message": {
                        "id": [outgoing_message_id],
                        "date": now_ts,
                    },
                    "chat": {
                        "id": message.chat_id,
                    },
                }
            ]

            self._bitrix_client.send_connector_messages(
                connector=event.connector_id,
                line=event.line_id,
                messages=send_payload,
            )
            self._bitrix_client.send_connector_delivery(
                connector=event.connector_id,
                line=event.line_id,
                messages=delivery_payload,
            )
            self._dedup_store.add(dedup_key)
            handled += 1
            self._logger.info(
                "echoed openlines message",
                extra={
                    "connector_id": event.connector_id,
                    "line_id": event.line_id,
                    "chat_id": message.chat_id,
                    "im_chat_id": message.im_chat_id,
                    "im_message_id": message.im_message_id,
                    "outgoing_message_id": outgoing_message_id,
                },
            )

        return HandleResult(
            bool(handled), "echo_sent" if handled else "duplicate_event"
        )

    def _make_dedup_key(self, event: ConnectorEvent, message: ConnectorMessage) -> str:
        return f"{event.event_type}:{event.connector_id}:{event.line_id}:{message.chat_id}:{message.im_message_id}"


class OpenLineMessageHandler:
    def __init__(
        self,
        bitrix_client: OAuthBitrixClient,
        dedup_store: DedupStore,
        auth_store: AppAuthStore,
        agent: Agent,
    ) -> None:
        self._bitrix_client = bitrix_client
        self._dedup_store = dedup_store
        self._auth_store = auth_store
        self._agent = agent
        self._profile_store = ProfileStore()
        self._logger = logging.getLogger(__name__)

    def _get_agent_answer(
        self, message_text: str, session_id: str
    ) -> tuple[str, bool, str | None]:
        self._logger.info(
            "requesting agent answer",
            extra={"session_id": session_id, "user_message": message_text[:100]},
        )
        result = self._agent.invoke(message_text, session_id)
        self._logger.info(
            "received agent answer",
            extra={
                "session_id": session_id,
                "answer": result.answer[:100],
                "handoff": result.handoff,
                "handoff_reason": result.handoff_reason,
            },
        )
        return result.answer, result.handoff, result.handoff_reason

    async def handle(self, event: OpenLineEvent) -> HandleResult:
        self._logger.info(
            "incoming openline event",
            extra={
                "event_type": event.event_type,
                "event_id": event.event_id,
                "messages_count": len(event.messages),
                "message_ids": [message.message_id for message in event.messages],
                "chat_ids": [message.chat_id for message in event.messages],
                "message_user_ids": [
                    message.message_user_id for message in event.messages
                ],
                "connector_user_ids": [
                    message.connector_user_id for message in event.messages
                ],
                "is_system_flags": [message.is_system for message in event.messages],
            },
        )

        if event.event_type != "ONOPENLINEMESSAGEADD":
            return HandleResult(False, f"ignored_event:{event.event_type}")

        stored_auth = self._auth_store.load()
        expected_token = (
            stored_auth.application_token
            if stored_auth and stored_auth.application_token
            else ""
        )
        if expected_token and event.application_token != expected_token:
            return HandleResult(False, "invalid_application_token")

        handled = 0
        for message in event.messages:
            dedup_key = self._make_dedup_key(event, message)
            if self._dedup_store.seen(dedup_key):
                self._logger.info(
                    "ignored duplicate openline message",
                    extra={
                        "chat_id": message.chat_id,
                        "connector_chat_id": message.connector_chat_id,
                        "connector_id": message.connector_id,
                        "line_id": message.line_id,
                        "message_id": message.message_id,
                    },
                )
                continue

            if message.connector_id != "vkgroup":
                self._logger.info(
                    "ignored message from non-vk connector",
                    extra={"connector_id": message.connector_id},
                )
                continue

            if message.is_system or message.message_user_id in (None, 0):
                self._logger.info(
                    "ignored system openline message",
                    extra={
                        "chat_id": message.chat_id,
                        "connector_chat_id": message.connector_chat_id,
                        "connector_id": message.connector_id,
                        "line_id": message.line_id,
                        "message_id": message.message_id,
                        "message_user_id": message.message_user_id,
                        "connector_user_id": message.connector_user_id,
                        "is_system": message.is_system,
                    },
                )
                continue

            if (
                message.connector_user_id is not None
                and message.message_user_id is not None
                and message.message_user_id != message.connector_user_id
            ):
                self._logger.info(
                    "ignored non-external openline message",
                    extra={
                        "chat_id": message.chat_id,
                        "connector_chat_id": message.connector_chat_id,
                        "connector_id": message.connector_id,
                        "line_id": message.line_id,
                        "message_id": message.message_id,
                        "message_user_id": message.message_user_id,
                        "connector_user_id": message.connector_user_id,
                    },
                )
                continue

            reply_text = (message.text or "").strip()
            if not reply_text:
                self._logger.info(
                    "ignored empty openline message",
                    extra={
                        "chat_id": message.chat_id,
                        "connector_chat_id": message.connector_chat_id,
                        "connector_id": message.connector_id,
                        "line_id": message.line_id,
                        "message_id": message.message_id,
                        "message_user_id": message.message_user_id,
                        "connector_user_id": message.connector_user_id,
                    },
                )
                continue

            target_chat_id = message.connector_chat_id or message.chat_id
            if (
                message.connector_id
                and message.line_id is not None
                and message.connector_chat_id is not None
                and message.message_user_id is not None
            ):
                user_code = f"{message.connector_id}|{message.line_id}|{message.connector_chat_id}|{message.message_user_id}"
                try:
                    dialog = await self._bitrix_client.get_openline_dialog(user_code)
                    dialog_result = (
                        dialog.get("result") if isinstance(dialog, dict) else None
                    )
                    if isinstance(dialog_result, dict):
                        resolved_chat_id = dialog_result.get("id") or dialog_result.get(
                            "ID"
                        )
                        if isinstance(resolved_chat_id, int) and resolved_chat_id > 0:
                            target_chat_id = resolved_chat_id
                        entity_data_1 = dialog_result.get("entity_data_1")
                        lead_id = _parse_lead_id(entity_data_1)
                        session_id = str(message.message_user_id)
                        if lead_id:
                            self._profile_store.update(
                                session_id, bitrix_lead_id=lead_id
                            )
                            self._logger.info(
                                "saved lead_id from dialog",
                                extra={"session_id": session_id, "lead_id": lead_id},
                            )
                        dialog_name = dialog_result.get("name")
                        if dialog_name and isinstance(dialog_name, str):
                            client_name = dialog_name.split(" - ")[0].strip()
                            if client_name:
                                self._profile_store.update(session_id, name=client_name)
                                self._logger.info(
                                    "saved name from dialog",
                                    extra={
                                        "session_id": session_id,
                                        "dialog_name": client_name,
                                    },
                                )
                except Exception:
                    self._logger.exception(
                        "failed to resolve openline dialog",
                        extra={"user_code": user_code},
                    )
            if target_chat_id is None:
                self._logger.info(
                    "ignored openline message without target chat id",
                    extra={
                        "chat_id": message.chat_id,
                        "connector_chat_id": message.connector_chat_id,
                        "connector_id": message.connector_id,
                        "line_id": message.line_id,
                        "message_id": message.message_id,
                        "message_user_id": message.message_user_id,
                        "connector_user_id": message.connector_user_id,
                    },
                )
                continue

            self._logger.info(
                "sending external answer request",
                extra={
                    "chat_id": message.chat_id,
                    "connector_chat_id": message.connector_chat_id,
                    "target_chat_id": target_chat_id,
                    "connector_id": message.connector_id,
                    "line_id": message.line_id,
                    "message_id": message.message_id,
                    "message_user_id": message.message_user_id,
                },
            )
            try:
                external_answer, handoff, handoff_reason = self._get_agent_answer(
                    message_text=reply_text,
                    session_id=str(message.message_user_id),
                )
                session_id = str(message.message_user_id)

                if handoff:
                    self._profile_store.update(
                        session_id,
                        handoff_needed=True,
                        handoff_reason=handoff_reason or "",
                    )
                    self._logger.info(
                        "handoff triggered",
                        extra={
                            "session_id": session_id,
                            "reason": handoff_reason,
                        },
                    )
                elif _HANDOFF_PATTERN.search(reply_text):
                    handoff = True
                    handoff_reason = (
                        "Клиент запросил живого специалиста (regex fallback)"
                    )
                    self._profile_store.update(
                        session_id, handoff_needed=True, handoff_reason=handoff_reason
                    )
                    self._logger.info(
                        "handoff triggered via regex fallback",
                        extra={
                            "session_id": session_id,
                            "reason": handoff_reason,
                        },
                    )

                profile = self._profile_store.get(session_id)
                self._logger.info(
                    "checking lead update condition",
                    extra={
                        "session_id": session_id,
                        "handoff_needed": profile.handoff_needed,
                        "lead_id": profile.bitrix_lead_id,
                        "phone": bool(profile.phone),
                        "email": bool(profile.email),
                    },
                )
                if profile.handoff_needed:
                    await self._update_lead_on_handoff(session_id, reply_text)
            except Exception:
                self._logger.exception(
                    "failed to get agent answer",
                    extra={
                        "chat_id": message.chat_id,
                        "message_id": message.message_id,
                        "message_user_id": message.message_user_id,
                    },
                )
                external_answer = (
                    "Извините, временно не могу ответить. Попробуйте позже."
                )

            response = await self._bitrix_client.send_openline_session_message(
                chat_id=target_chat_id,
                message=external_answer,
                name="DEFAULT",
            )
            self._dedup_store.add(dedup_key)
            handled += 1
            self._logger.info(
                "echoed openline message",
                extra={
                    "chat_id": message.chat_id,
                    "connector_chat_id": message.connector_chat_id,
                    "target_chat_id": target_chat_id,
                    "connector_id": message.connector_id,
                    "line_id": message.line_id,
                    "message_id": message.message_id,
                    "message_user_id": message.message_user_id,
                    "external_answer": external_answer,
                    "response": response,
                },
            )

        return HandleResult(
            bool(handled), "echo_sent" if handled else "duplicate_event"
        )

    def _make_dedup_key(self, event: OpenLineEvent, message: OpenLineMessage) -> str:
        return f"{event.event_type}:{message.connector_id}:{message.line_id}:{message.chat_id}:{message.message_id}"

    def _build_lead_title(
        self,
        phone: str | None,
        profile_name: str | None,
        city: str | None,
    ) -> str:
        normalized = _normalize_phone(phone)
        last4 = normalized[-4:] if normalized and len(normalized) >= 4 else "----"

        first_name = ""
        last_name = ""
        if profile_name:
            name_parts = profile_name.strip().split()
            first_name = name_parts[0] if name_parts else ""
            last_name = name_parts[1] if len(name_parts) > 1 else ""

        full_name = f"{first_name} {last_name}".strip() or "----"
        city_part = city or "----"
        phone_part = normalized or "----"

        return f"{last4} - {full_name} - {city_part} - {phone_part}"

    async def _update_lead_on_handoff(self, session_id: str, user_message: str) -> None:
        profile = self._profile_store.get(session_id)
        lead_id = profile.bitrix_lead_id

        INTERESTS_MAP = {
            "Детская одежда": 181,
            "Головные уборы": 182,
            "Новорождёнка": 183,
            "Текстиль": 342,
            "Игрушки": 344,
        }

        CLIENT_TYPE_MAP = {
            "Маркетплейс": 166,
            "Магазин": 167,
            "Интернет Магазин": 168,
            "Оптовик": 169,
            "Физ клиент": 288,
            "СП": 351,
            "Принты": 404,
            "СМС Рассылка (Школьная форма)": 407,
        }

        fields: dict[str, object] = {}

        if profile.name:
            fields["name"] = profile.name
        if profile.company:
            fields["companyTitle"] = profile.company

        phone = _normalize_phone(profile.phone)
        if phone:
            fields["fm"] = [{"typeId": "PHONE", "valueType": "WORK", "value": phone}]

        if profile.city or profile.country:
            city_country = ", ".join(filter(None, [profile.city, profile.country]))
            fields["UF_CRM_1714116487673"] = city_country

        interest_ids = []
        if profile.interests:
            for interest in profile.interests:
                mapped = INTERESTS_MAP.get(interest)
                if mapped is not None:
                    interest_ids.append(mapped)
        if interest_ids:
            fields["UF_CRM_1714983959598"] = interest_ids

        client_type_ids = []
        if profile.client_type:
            client_types = (
                [profile.client_type]
                if isinstance(profile.client_type, str)
                else profile.client_type
            )
            for ct in client_types:
                mapped = CLIENT_TYPE_MAP.get(ct)
                if mapped is not None:
                    client_type_ids.append(mapped)
            if "Физ клиент" in client_types:
                client_type_ids = [288]
        if client_type_ids:
            fields["UF_CRM_1714981399284"] = client_type_ids

        comments_parts: list[str] = []
        if profile.email:
            comments_parts.append(f"email: {profile.email}")
        if profile.volume:
            comments_parts.append(f"объём: {profile.volume}")
        if comments_parts:
            fields["comments"] = "\n".join(comments_parts)

        if not fields:
            self._logger.info(
                "no fields to update in lead",
                extra={"session_id": session_id, "lead_id": lead_id},
            )
            return

        try:
            title = self._build_lead_title(profile.phone, profile.name, profile.city)
            fields["title"] = title

            if lead_id:
                await self._bitrix_client.update_lead(lead_id, fields)
                self._logger.info(
                    "lead updated on handoff",
                    extra={
                        "session_id": session_id,
                        "lead_id": lead_id,
                        "title": title,
                    },
                )
            else:
                new_id = await self._bitrix_client.create_lead(fields)
                if new_id:
                    self._profile_store.update(session_id, bitrix_lead_id=new_id)
                    lead_id = new_id
                    self._logger.info(
                        "lead created on handoff",
                        extra={
                            "session_id": session_id,
                            "lead_id": new_id,
                            "title": title,
                        },
                    )

            if lead_id and (profile.phone or profile.email):
                timeline_parts: list[str] = []
                if profile.request_summary:
                    timeline_parts.append(f"Суть запроса: {profile.request_summary}")
                if profile.interest_level:
                    timeline_parts.append(f"Степень интереса: {profile.interest_level}")
                if profile.handoff_reason:
                    timeline_parts.append(f"Причина передачи: {profile.handoff_reason}")
                if timeline_parts:
                    await self._bitrix_client.add_timeline_comment(
                        lead_id, "\n".join(timeline_parts)
                    )
                    self._logger.info(
                        "timeline comment added",
                        extra={"session_id": session_id, "lead_id": lead_id},
                    )
        except Exception:
            self._logger.exception(
                "failed to update/create lead on handoff",
                extra={"session_id": session_id, "lead_id": lead_id},
            )


class AppInstallHandler:
    def __init__(
        self,
        auth_store: AppAuthStore,
        oauth_client: OAuthBitrixClient,
        handler_url: str,
    ) -> None:
        self._auth_store = auth_store
        self._oauth_client = oauth_client
        self._handler_url = handler_url
        self._logger = logging.getLogger(__name__)

    async def handle(self, event: AppInstallEvent) -> HandleResult:
        self._logger.info(
            "incoming app install", extra={"event_type": event.event_type}
        )

        if event.event_type != "ONAPPINSTALL":
            return HandleResult(False, f"ignored_event:{event.event_type}")

        auth = AppAuth.from_mapping(event.auth)
        if not auth.access_token or not auth.refresh_token:
            return HandleResult(False, "missing_auth")

        self._auth_store.save(auth)
        self._logger.info(
            "saved app auth",
            extra={
                "domain": auth.domain,
                "member_id": auth.member_id,
                "has_application_token": bool(auth.application_token),
            },
        )

        if not self._handler_url:
            return HandleResult(True, "app_installed_without_binding")

        try:
            response = await self._oauth_client.bind_event(
                "ONOPENLINEMESSAGEADD", self._handler_url
            )
        except Exception as exc:
            if "already binded" in str(exc).lower():
                self._logger.info("openline event already bound, skipping")
                return HandleResult(True, "already_bound")
            self._logger.exception("failed to bind openline event")
            return HandleResult(False, "bind_failed")

        self._logger.info(
            "bound openline event",
            extra={"handler_url": self._handler_url, "response": response},
        )
        return HandleResult(True, "app_installed_and_bound")
