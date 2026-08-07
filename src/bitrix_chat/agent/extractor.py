from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import EXTRACTOR_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from .profile import ProfileStore

logger = logging.getLogger(__name__)

EXTRACTOR_SYSTEM_PROMPT = """Ты — система извлечения данных. Извлеки данные о клиенте из сообщения и верни ТОЛЬКО JSON.

Поля JSON (используй null если данных нет):
{
  "name": "имя клиента (только имя, без фамилии)",
  "company": "название компании",
  "phone": "телефон в формате +7XXXXXXXXXX или 8XXXXXXXXXX",
  "email": "email адрес",
  "city": "город",
  "country": "страна",
  "interests": ["список интересов из допустимых значений"],
  "volume": "объём закупки (например 'от 100 шт', '50000 тенге')",
  "client_type": "тип клиента из допустимых значений",
  "request_summary": "краткая суть запроса клиента",
  "interest_level": "уровень интереса"
}

ДОПУСТИМЫЕ ЗНАЧЕНИЯ interests (передавай как есть на русском):
- "Детская одежда"
- "Головные уборы"
- "Новорождёнка"
- "Текстиль"
- "Игрушки"

ДОПУСТИМЫЕ ЗНАЧЕНИЯ client_type (передавай как есть на русском):
- "Маркетплейс"
- "Магазин"
- "Интернет Магазин"
- "Оптовик"
- "Физ клиент"
- "СП"
- "Принты"
- "СМС Рассылка (Школьная форма)"

ДОПУСТИМЫЕ ЗНАЧЕНИЯ interest_level:
- "низкий"
- "средний"
- "высокий"

ПРАВИЛА:
- Извлекай ТОЛЬКО то, что явно указано в сообщении
- Не додумывай и не предполагай
- phone: приводи к формату +7XXXXXXXXXX (8→+7)
- interests: только из списка допустимых значений, если клиент упомянул категорию
- client_type: только из списка допустимых значений
- request_summary: 1-2 предложения о чём просит клиент
- interest_level: определи по формулировке ("хочу купить"=средний, "срочно нужно"=высокий, "просто смотрю"=низкий)
- Если ничего не извлек — верни пустой объект {}

Ответ: ТОЛЬКО JSON без пояснений, markdown или кода."""


class DataExtractor:
    """Извлекает данные клиента из сообщения через дешёвую LLM."""

    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=EXTRACTOR_MODEL,
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            temperature=0,
        )
        self._profile_store = ProfileStore()

    def extract(self, message: str, session_id: str) -> dict:
        """Извлекает данные из сообщения и сохраняет в профиль.

        Возвращает dict с извлечёнными данными.
        """
        if not message or not message.strip():
            return {}

        try:
            messages = [
                SystemMessage(content=EXTRACTOR_SYSTEM_PROMPT),
                HumanMessage(content=message),
            ]
            response = self._llm.invoke(messages)
            content = response.content if isinstance(response.content, str) else ""
            data = self._parse_json(content)
            if data:
                self._profile_store.update(session_id, **data)
                logger.info(
                    "data extracted and saved",
                    extra={
                        "session_id": session_id,
                        "fields": list(data.keys()),
                    },
                )
            return data
        except Exception:
            logger.exception("data extraction failed")
            return {}

    def _parse_json(self, text: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if v is not None and v != []}
            return {}
        except (json.JSONDecodeError, TypeError):
            logger.warning("failed to parse extractor response as JSON: %s", text[:200])
            return {}
