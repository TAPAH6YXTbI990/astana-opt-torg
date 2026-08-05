from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from .profile import ProfileStore

logger = logging.getLogger(__name__)

_profile_store = ProfileStore()


@tool
def update_client_profile(
    session_id: str,
    name: str | None = None,
    company: str | None = None,
    contact_info: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    city: str | None = None,
    country: str | None = None,
    interests: list[str] | None = None,
    volume: str | None = None,
    client_type: str | None = None,
    request_summary: str | None = None,
    interest_level: str | None = None,
    extra: str | None = None,
) -> str:
    """Сохрани информацию о клиенте. Вызывай когда клиент сообщает данные о себе: имя, город, тип бизнеса, интересы, объём закупки и т.д. Можно вызывать несколько раз, обновляя только новые данные."""
    fields: dict[str, Any] = {}
    if name is not None:
        fields["name"] = name
    if company is not None:
        fields["company"] = company
    if contact_info is not None:
        fields["contact_info"] = contact_info
    if phone is not None:
        fields["phone"] = phone
    if email is not None:
        fields["email"] = email
    if city is not None:
        fields["city"] = city
    if country is not None:
        fields["country"] = country
    if interests is not None:
        fields["interests"] = interests
    if volume is not None:
        fields["volume"] = volume
    if client_type is not None:
        fields["client_type"] = client_type
    if request_summary is not None:
        fields["request_summary"] = request_summary
    if interest_level is not None:
        fields["interest_level"] = interest_level
    if extra is not None:
        fields["extra"] = extra

    if not fields:
        return "Нет данных для обновления"

    profile = _profile_store.update(session_id, **fields)
    logger.info(
        "profile updated via tool",
        extra={"session_id": session_id, "fields": list(fields.keys())},
    )
    return f"Профиль обновлён: {profile.format_for_prompt()}"


@tool
def request_handoff(session_id: str, reason: str) -> str:
    """Передать диалог менеджеру. Вызывай когда клиент просит живого специалиста, вопрос отсутствует в базе знаний, нужен индивидуальный расчёт, подтверждение наличия/цены, клиент готов к оформлению, или запрос нестандартный."""
    _profile_store.update(session_id, handoff_needed=True, handoff_reason=reason)
    logger.info(
        "handoff requested via tool",
        extra={"session_id": session_id, "reason": reason},
    )
    return f"Запрошена передача менеджеру. Причина: {reason}"


def get_tools() -> list:
    return [update_client_profile, request_handoff]
