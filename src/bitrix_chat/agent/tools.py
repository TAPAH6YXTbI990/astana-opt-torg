from __future__ import annotations

import logging

from langchain_core.tools import tool

from .profile import ProfileStore

logger = logging.getLogger(__name__)

_profile_store = ProfileStore()


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
    return [request_handoff]
