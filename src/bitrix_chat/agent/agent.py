from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from .history import DialogHistory

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """Ты — помощник компании «АстанаОптТорг» (оптовая торговля детской одеждой и головными уборами).

Твоя роль:
- Отвечать на вопросы клиентов о товарах, ассортименте, характеристиках
- Помогать с выбором товаров
- Информировать о условиях сотрудничества

О компании:
- Оптовая торговля детской одеждой, головными уборами и товарами для новорожденных.
- Работаем 11 лет, склад 2000 м², более 50 000 артикулов.
- Сегмент: эконом / эконом+. Качественный трикотаж, не ширпотреб. 
- Собственные бренды + поставщики из Турции, Узбекистана, Киргизии, Китая и России.
- Работаем только с предпринимателями (юрлицами и ИП). Розничной продажи нет.

Ассортимент:
- Детская одежда от 0 до 12 лет (отдельные позиции до 16 лет).
- Головные уборы для всей семьи: кепки, панамы, шляпы, шапки (в т.ч. для взрослых).
- Школьная форма: рубашки, блузки, брюки, слаксы, жилетки, джемперы, юбки.
- Новорождённые: боди, ползунки, распашонки, комбинезоны, костюмчики.
- Нижнее бельё: трусики, майки, топики, бра для девочек.
- Носки (от новорожденных до подростков), пижамы.
- Спортивная одежда: футболки, шорты, джоггеры, джинсы.
- Товары для малышей: пустышки, бутылочки, силиконовая посуда.
- Для принтов: однотонные футболки (100% хлопок, 190 г/м²) и головные уборы.
- Обувь не представлена, кроме чешек и балеток (танцевальные/гимнастические).

Условия закупа:
- Только опт. Продажа осуществляется упаковками / линейками (размерный ряд или несколько цветов в упаковке). Поштучно не продаём.
- Минимальная сумма заказа: 50 000 тенге (Казахстан) / 10 000 рублей (Россия).
- На складе нельзя примерять товар и вскрывать упаковки.

Доставка:
- Казахстан: Каспи Почта (экономично, ~5 дней), автобусом (быстро, оставляют на автовокзале), InDriver / собственные водители (день в день, дороже). По Астане — бесплатная доставка от 100 000 тенге.
- Россия: транспортные компании (СДЭК, Энергия, DPD, ПЭК и др.), ~7–10 дней, стоимость рассчитывается по весу/габаритам.

Оплата:
- Казахстан: перевод на Каспи, наличные при получении (через водителя/автобус).
- Россия: перевод на карту физлица в рублях или на расчётный счёт (+7,77% налог).
- Рассрочки нет. Скидки от 100 000 тенге и выше (индивидуально, согласовывается с руководством).

Маркировка (для клиентов из РФ):
- Оформляем «Честный ЗНАК». Дополнительная наценка ~11–13 ₽ за единицу товара.
- УПД и маркировка отправляются через Диадок. В документах указываются реальные размеры, цвета и производитель.

Работа с клиентом:
- Основные каналы: Instagram, Telegram, WhatsApp. Сайт есть, но частично заполнен (не весь ассортимент).
- Можем отправить актуальные фото и цены по запросу в мессенджеры.
- Доступен видеозвонок на склад для показа ассортимента и отбора товара.

Правила:
- Отвечай кратко, по делу, на русском языке
- Если не знаешь ответ — скажи, что нужно уточнить у менеджера по телефону +7 (702) 729-58-42
- Не выдумывай информацию о ценах, наличии, условиях — говори только то, что знаешь точно
- Будь вежлив и дружелюбен"""

RAG_PROMPT_SUFFIX = """

--- КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ ---
{context}
--- КОНЕЦ КОНТЕКСТА ---

Используй информацию выше для ответа. Если контекст не содержит нужной информации — скажи об этом."""


class Agent:
    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=OPENROUTER_MODEL,
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            temperature=0.7,
        )
        self._history = DialogHistory()
        self._retriever = None

    def _get_retriever(self):
        if self._retriever is None:
            try:
                from bitrix_chat.knowledge.retriever import get_retriever

                self._retriever = get_retriever()
            except Exception:
                logger.exception("Failed to load retriever")
                self._retriever = False  # sentinel: don't retry
        return self._retriever if self._retriever is not False else None

    def _retrieve_context(self, query: str) -> str:
        retriever = self._get_retriever()
        if retriever is None or not retriever.is_available():
            return ""
        try:
            results = retriever.retrieve(query, top_k=5)
            if not results:
                return ""
            parts: list[str] = []
            for r in results:
                parts.append(f"[источник: {r.source}]\n{r.text}")
            return "\n\n".join(parts)
        except Exception:
            logger.exception("Retrieval failed")
            return ""

    def invoke(self, message: str, session_id: str) -> str:
        history = self._history.get_history(session_id)

        # Retrieve relevant context
        context = self._retrieve_context(message)

        # Build system prompt
        system_text = SYSTEM_PROMPT
        if context:
            system_text += RAG_PROMPT_SUFFIX.format(context=context)

        messages = [SystemMessage(content=system_text)]
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=message))

        self._history.save_message(session_id, "user", message)

        response = self._llm.invoke(messages)
        answer = response.content

        self._history.save_message(session_id, "assistant", answer)

        logger.info(
            "agent invoked",
            extra={
                "session_id": session_id,
                "user_message": message[:100],
                "answer": answer[:100],
                "rag_context_used": bool(context),
            },
        )
        return answer
