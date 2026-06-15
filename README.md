# Bitrix Chat Bot

Минимальный webhook-бот для Bitrix24.

## Что делает первая версия

- принимает событие `ONIMBOTV2MESSAGEADD` от Bitrix24;
- извлекает текст сообщения и `dialogId`;
- отправляет сообщение пользователя обратно в тот же чат как эхо;
- игнорирует повторные события и сообщения от самого бота.

## Архитектура

- `FastAPI` принимает webhook от Bitrix24;
- `fast-bitrix24` используется как REST-клиент для вызовов `imbot.v2.*`;
- обработчик событий содержит только бизнес-логику;
- in-memory хранилище защищает от дублей в рамках одного процесса.

## Переменные окружения

- `BITRIX_REST_WEBHOOK_URL` - REST webhook Bitrix24 для исходящих вызовов
- `BITRIX_BOT_ID` - ID зарегистрированного бота
- `BITRIX_BOT_TOKEN` - bot token, который нужен для `imbot.v2.*`
- `BITRIX_INBOUND_SECRET` - секрет в URL inbound webhook нашего сервиса
- `BITRIX_CLIENT_ID` - `client_id` локального приложения
- `BITRIX_CLIENT_SECRET` - `client_secret` локального приложения
- `BITRIX_APP_STATE_PATH` - путь для сохранения OAuth-токенов приложения после `ONAPPINSTALL`
- `BITRIX_APP_WEBHOOK_URL` - публичный URL обработчика, который Bitrix24 должен привязать через `event.bind`
- `BITRIX_OPENLINE_RESPONSE_WEBHOOK_URL` - внешний сервис, который генерирует ответ на сообщение пользователя
- `BITRIX_OPENLINES_WEBHOOK_URL` - публичный URL обработчика для `ONOPENLINEMESSAGEADD`
- `LOG_LEVEL` - уровень логирования, по умолчанию `INFO`

## Запуск

```bash
uv run uvicorn bitrix_chat.main:app --host 0.0.0.0 --port 8000
```

Пример inbound URL для Bitrix24:

```text
https://your-domain.example/webhooks/bitrix24/your-secret
```

Для Open Lines-коннектора используйте отдельный URL:

```text
https://your-domain.example/webhooks/bitrix24/openlines/your-secret
```

Для локального приложения Bitrix24 обычно вызывает установочный callback на:

```text
https://your-domain.example/webhooks/bitrix24/app/your-secret
```

Этот endpoint принимает `ONAPPINSTALL`, сохраняет OAuth-данные приложения и автоматически вызывает `event.bind` для `ONOPENLINEMESSAGEADD`.
Токен `application_token` берется из `ONAPPINSTALL` и сохраняется внутри состояния приложения, вручную задавать его в `.env` больше не нужно.

Наша задача здесь - принять установочный webhook, зарегистрировать подписку на `ONOPENLINEMESSAGEADD`, обработать событие и отправить ответ обратно через `imopenlines.bot.session.message.send`.
Перед отправкой ответа сообщение пользователя уходит в внешний сервис `POST`-запросом в формате `{"message":"...","session_id":"..."}`.
Ответ внешнего сервиса должен быть JSON вида `{"output":"..."}`.

Если приложение уже было установлено до этой правки, можно один раз вручную привязать событие командой:

```bash
uv run bitrix-bind-openlines --handler https://your-domain.example/webhooks/bitrix24/app/your-secret
```

## Регистрация бота

После создания `BITRIX_REST_WEBHOOK_URL` можно зарегистрировать бота командой:

```bash
uv run bitrix-register-bot \
  --code echo_bot \
  --name "Echo Bot" \
  --bot-token your_bot_token \
  --webhook-url https://your-domain.example/webhooks/bitrix24/your-secret
```

Команда вернёт JSON с данными зарегистрированного бота, включая `bot.id`.
После этого:

- `BITRIX_BOT_ID` нужно установить в этот `id`;
- `BITRIX_BOT_TOKEN` нужно установить в тот же `your_bot_token`;
- можно запускать webhook-сервис.

## Что дальше

- добавить персистентное хранилище для дедупликации;
- заменить эхо на вызов нейросети;
- добавить логирование входящих payloads и метрики;
- при необходимости вынести отправку ответа в очередь.
