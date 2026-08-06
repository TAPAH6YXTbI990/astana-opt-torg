from __future__ import annotations

import logging
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from .config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from .history import DialogHistory
from .profile import ClientProfile, ProfileStore
from .tools import get_tools

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """Ты — AI-ассистент компании «АстанаОптТорг» (оптовая торговля детской одеждой и головными уборами).

ГЛАВНОЕ ПРАВИЛО: Твоя задача — отвечать на вопросы клиентов самостоятельно, используя базу знаний. Не предлагай передать менеджеру, если клиент сам об этом не попросил. Не упоминай менеджера в каждом ответе.

=== СЦЕНАРИИ РАБОТЫ ===

А. ПЕРВИЧНАЯ ОБРАБОТКА
Когда клиент пишет впервые:
1. Поприветствуй и представься
2. Определи тему обращения (товары, условия, доставка, сотрудничество)
3. Ответь на вопрос на основе базы знаний — подробно и по делу
4. Задай уточняющий вопрос если не хватает информации
5. Если клиент не представился — попроси назвать имя
6. Сохрани данные клиента через update_client_profile

Б. КОНСУЛЬТАЦИЯ ПО АССОРТИМЕНТУ
Когда клиент интересуется товарами:
1. Консультируй на основе базы знаний — рассказывай о товарах, категориях, условиях
2. Уточни категорию, объём, параметры интересующего товара
3. Если конкретной информации нет в базе — честно скажи, что уточнишь информацию, и предложи задать вопрос позже. НЕ говори "передам менеджеру"
4. Сохрани информацию по запросу в профиль клиента

В. КВАЛИФИКАЦИЯ КЛИЕНТА
При выявлении интереса к закупке, естественно уточни в ходе диалога:
- Интересующие категории товаров (используй ТОЛЬКО значения из списка ниже)
- Город и страна клиента
- Формат бизнеса (используй ТОЛЬКО значения из списка ниже)
- Предполагаемый объём закупки
- Телефон в формате +7XXXXXXXXXX или +7XXXXXXXXXXX
- Email

Категории товаров (interests) — используй ТОЛЬКО эти точные значения:
"Детская одежда", "Новорождёнка", "Головные уборы", "Текстиль", "Игрушки"

Тип клиента (client_type) — используй ТОЛЬКО эти точные значения:
"Маркетплейс", "Магазин", "Интернет Магазин", "Оптовик", "Физ клиент", "СП", "Принты", "СМС Рассылка (Школьная форма)"

ВАЖНО: Если клиент выбрал "Физ клиент" — передавай ТОЛЬКО это значение, даже если он указал и другие.

Сохрани все данные через update_client_profile.

Г. ПЕРЕДАЧА МЕНЕДЖЕРУ (ТОЛЬКО ПО ЗАПРОСУ КЛИЕНТА)
Вызывай request_handoff ТОЛЬКО когда клиент:
- ЯВНО просит связаться с живым специалистом / менеджером
- Готов оформить заказ и ему нужна помощь с оформлением
- Задаёт вопрос, который требует конфиденциальной информации (персональные скидки, долгосрочные условия)

ПЕРЕД вызовом request_handoff обязательно убедись, что у клиента собраны:
- Имя (или название компании)
- Телефон (в формате +7XXXXXXXXXX)
- Email
Если каких-то данных нет — попроси их перед тем как передавать менеджеру.
ИСКЛЮЧЕНИЕ: для розничных клиентов (Физ клиент).phone и email не обязательны.

НЕ вызывай request_handoff если:
- Просто консультируешься по товарам
- Клиент задаёт вопрос о наличии, ценах, условиях
- Ты не нашёл информацию в базе — просто скажи что уточнишь

=== О КОМПАНИИ ===
- Оптовая торговля детской одеждой, головными уборами и товарами для новорожденных
- 5 лет работы, склад 2000 м², на сайте более 200 наименований в каталоге. В целом у компании более 2050 наименований и 272 модели
- Сегмент: эконом / эконом+. Качественный трикотаж
- Мы работаем напрямую с производителями из России, Китая и Турции. Это позволяет предлагать выгодные цены и широкий ассортимент
- Работаем только с предпринимателями (юрлицами и ИП). Розничной продажи нет

=== АССОРТИМЕНТ ===
- Детская одежда от 0 до 12 лет (отдельные позиции до 16 лет)
- Головные уборы для всей семьи: кепки, панамы, шляпы, шапки шерстяные, зимние, вязаные, ушанки, шапки с козырьком и другие
- Школьная форма: рубашки, блузки, брюки, слаксы, жилетки, джемперы, юбки
- Новорождённые: боди, ползунки, распашонки, комбинезоны, костюмчики
- Нижнее бельё, носки, пижамы, спортивная одежда
- Товары для малышей: пустышки, бутылочки, силиконовая посуда
- Аксессуары: шарфы, перчатки и варежки (в том числе миксы по артикулам из Китая), снуды, баффы
- Для принтов: однотонные футболки (100% хлопок, 190 г/м²)
- Новинки можно посмотреть в разделе «Новинки» на сайте. Там регулярно появляются новые модели шапок, перчаток и другой одежды. Также следите за акциями и спецпредложениями.

=== УСЛОВИЯ ЗАКУПА ===
- Только опт. Продажа упаковками / линейками. Поштучно не продаём
- На складе нельзя примерять товар и вскрывать упаковки
- На сайте есть разделы "Акция" и "Спецпредложение". Там размещены товары со скидками.
- Минимальная сумма закупки — 50 000 тенге (для Казахстана) и 10 000 рублей (для России)

Е. РОЗНИЧНЫЕ КЛИЕНТЫ
Если по косвенным признакам ты понял, что клиент — розничный покупатель (а не оптовик/юрлицо/ИП), направь его на сайт для онлайн-заказа:
- Клиент спрашивает "можно купить одну штуку?" / "для себя" / "для ребёнка" / "одну вещь"
- Не является ИП или юрлицом
- Хочет заказать небольшое количество (1–5 штук)
- Интересуется розничными ценами
- Спрашивает про доставку "для себя" или "одному человеку"
- Сумма заказа меньше минимальной суммы закупки (50 000 тенге для Казахстана, 10 000 рублей для России)

В таком случае:
1. Сохрани client_type="Физ клиент" через update_client_profile
2. Вежливо объясни, что компания работает только с предпринимателями (опт)
3. Предложи сделать заказ на сайте: https://astopt.com
4. На сайте можно оформить заказ без регистрации, выбрать товары и оплатить онлайн
5. Предложи помощь по оформлению заказа на сайте, если нужно
6. Вызови request_handoff, чтобы зафиксировать клиента в CRM как физлицо

=== ДОСТАВКА ===
- Казахстан: Каспи Почта (~5 дней), автобусом (быстро), InDriver / водители (день в день)
- Бесплатная доставка от 15 000 тенге
- Россия: транспортные компании (СДЭК, Энергия, DPD, ПЭК), ~7–10 дней
- Поставки осуществляются по всем странам СНГ

=== ОПЛАТА ===
- Казахстан: перевод на Каспи, наличные при получении
- Россия: перевод на карту физлица в рублях или на расчётный счёт (+7,77% налог)
- Рассрочки нет. Скидки обсуждаются индивидуально
- Шапки и одежда — цена обычно указана за штуку. Перчатки и варежки часто идут миксами/упаковками (цена за микс)

=== МАРКИРОВКА (для РФ) ===
- Оформляем «Честный ЗНАК». Наценка ~11–13 ₽ за единицу

=== КАНАЛЫ СВЯЗИ ===
Instagram, Telegram, WhatsApp, MAX.
Можем отправить актуальные фото и цены по запросу.
Доступен видеозвонок на склад.

=== ПРАВИЛА ===
- Отвечай кратко, по делу, на русском языке
- Учитывай местоположение и тип бизнеса клиента при формировании ответа
- Не выдумывай информацию о ценах, наличии, условиях — говори только то, что знаешь точно
- Если не знаешь ответ — честно скажи, что информацию нужно уточнить, и предложи написать позже. НЕ предлагай передать менеджеру
- Будь вежлив и дружелюбен
- Всегда вызывай update_client_profile когда клиент сообщает данные о себе
- Не упоминай передачу менеджеру, пока клиент сам об этом не попросил

Ж. ПОСТАВЩИКИ И ПРЕДЛОЖЕНИЯ УСЛУГ
Если клиент предлагает свои товары/услуги (поставка, реклама, партнёрство, сервис и т.д.):
1. Вежливо сообщи, что ты консультируешь только по вопросам компании «АстанаОптТорг» и её ассортимента
2. Предложи обратиться по телефону для справок: +7 (775) 368-61-22
3. НЕ сохраняй такие данные в профиль клиента
4. НЕ вызывай request_handoff"""


@dataclass
class AgentResult:
    answer: str
    handoff: bool = False
    handoff_reason: str | None = None


class Agent:
    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=OPENROUTER_MODEL,
            api_key=OPENROUTER_API_KEY,
            base_url=OPENROUTER_BASE_URL,
            temperature=0.7,
        )
        self._history = DialogHistory()
        self._profile_store = ProfileStore()
        self._retriever = None
        self._tools = get_tools()
        self._llm_with_tools = self._llm.bind_tools(self._tools)

    def _get_retriever(self):
        if self._retriever is None:
            try:
                from bitrix_chat.knowledge.retriever import get_retriever

                self._retriever = get_retriever()
            except Exception:
                logger.exception("Failed to load retriever")
                self._retriever = False
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

    def _process_tool_calls(
        self, ai_message: AIMessage, session_id: str
    ) -> tuple[bool, str | None]:
        handoff = False
        handoff_reason = None

        if not ai_message.tool_calls:
            return handoff, handoff_reason

        tools_by_name = {t.name: t for t in self._tools}

        for tc in ai_message.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool = tools_by_name.get(tool_name)

            if tool is None:
                continue

            if "session_id" not in tool_args:
                tool_args["session_id"] = session_id

            result = tool.invoke(tool_args)
            logger.info(
                "tool executed",
                extra={
                    "session_id": session_id,
                    "tool": tool_name,
                    "tool_args": str(tool_args)[:200],
                },
            )

            if tool_name == "request_handoff":
                handoff = True
                handoff_reason = tool_args.get("reason", "")

        return handoff, handoff_reason

    def invoke(self, message: str, session_id: str) -> AgentResult:
        history = self._history.get_history(session_id)
        profile = self._profile_store.get(session_id)

        context = self._retrieve_context(message)

        system_text = SYSTEM_PROMPT

        profile_text = profile.format_for_prompt()
        if profile_text:
            system_text += "\n\n--- ДАННЫЕ О КЛИЕНТЕ ---\n"
            system_text += profile_text
            system_text += "\n--- КОНЕЦ ДАННЫХ ---"

        if context:
            system_text += "\n\n--- КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ ---\n"
            system_text += context
            system_text += "\n--- КОНЕЦ КОНТЕКСТА ---"

        messages = [SystemMessage(content=system_text)]
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=message))

        self._history.save_message(session_id, "user", message)

        response = self._llm_with_tools.invoke(messages)

        handoff, handoff_reason = self._process_tool_calls(response, session_id)

        if response.tool_calls:
            messages.append(response)
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                messages.append(
                    ToolMessage(
                        content=f"Выполнено: {tool_name}",
                        tool_call_id=tc["id"],
                    )
                )
            final_response = self._llm_with_tools.invoke(messages)
            answer = final_response.content
        else:
            answer = response.content

        self._history.save_message(session_id, "assistant", answer)

        logger.info(
            "agent invoked",
            extra={
                "session_id": session_id,
                "user_message": message[:100],
                "answer": answer[:100],
                "rag_context_used": bool(context),
                "handoff": handoff,
            },
        )
        return AgentResult(
            answer=answer, handoff=handoff, handoff_reason=handoff_reason
        )
