# Описание API взаимодействия с системой

## Входящие эндпоинты (бот принимает)

Бот предоставляет три webhook-эндпоинта, все поддерживают методы GET, POST, HEAD.

### 1. Основной webhook (события ботов в чатах)

**URL:** `/webhooks/bitrix24/{secret}`

Bitrix24 отправляет сюда события `ONIMBOTV2MESSAGEADD` — сообщения пользователей в чатах, где бот подключён.

```bash
curl -X POST "https://your-domain.example/webhooks/bitrix24/your-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "ONIMBOTV2MESSAGEADD",
    "data": {
      "bot": {"id": 123},
      "chat": {"dialogId": "chat_101"},
      "message": {"id": 456, "text": "Привет"},
      "user": {"id": 789, "bot": false}
    }
  }'
```

**Ответ:**
```json
{
  "status": "ok",
  "handled": true,
  "reason": "echo_sent",
  "echoed_text": "Привет"
}
```

### 2. Open Lines webhook

**URL:** `/webhooks/bitrix24/openlines/{secret}`

Отдельный webhook для событий открытых линий (ONOPENLINEMESSAGEADD).

```bash
curl -X POST "https://your-domain.example/webhooks/bitrix24/openlines/your-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "ONOPENLINEMESSAGEADD",
    "auth": {"application_token": "app_token_here"},
    "data": {
      "DATA": [{
        "connector": {"connector_id": "amo", "line_id": 1},
        "chat": {"id": "12345"},
        "message": {"user_id": "678", "id": 101, "text": "Здравствуйте"}
      }]
    }
  }'
```

**Ответ:**
```json
{
  "status": "ok",
  "handled": true,
  "reason": "echo_sent",
  "messages_count": 1
}
```

### 3. App webhook (установка приложения + Open Lines)

**URL:** `/webhooks/bitrix24/app/{secret}`

Универсальный endpoint для событий приложения. Принимает `ONAPPINSTALL` и `ONOPENLINEMESSAGEADD`.

**Установка приложения:**
```bash
curl -X POST "https://your-domain.example/webhooks/bitrix24/app/your-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "ONAPPINSTALL",
    "auth": {
      "access_token": "access_token_value",
      "refresh_token": "refresh_token_value",
      "client_endpoint": "https://bitrix24.example.com/rest/1/abc/",
      "server_endpoint": "https://oauth.bitrix24.tech/",
      "domain": "bitrix24.example.com",
      "member_id": "member_123",
      "application_token": "app_token_value"
    }
  }'
```

**Ответ:**
```json
{
  "status": "ok",
  "handled": true,
  "reason": "app_installed_and_bound"
}
```

### 4. Health check

```bash
curl "https://your-domain.example/health"
```

**Ответ:**
```json
{"status": "ok"}
```

---

## Исходящие вызовы к Bitrix24

### Через BitrixClient (webhook)

#### Отправка сообщения в чат

```bash
curl -X POST "https://your-domain.bitrix24.com/rest/123/bot_token_string/imbot.v2.Chat.Message.send" \
  -H "Content-Type: application/json" \
  -d '{
    "botId": 123,
    "botToken": "bot_token",
    "dialogId": "chat_101",
    "fields": {
      "message": "Ответ от бота",
      "urlPreview": false,
      "replyId": 456
    }
  }'
```

#### Регистрация бота

```bash
curl -X POST "https://your-domain.bitrix24.com/rest/123/bot_token_string/imbot.v2.Bot.register" \
  -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "code": "echo_bot",
      "type": "bot",
      "eventMode": "webhook",
      "webhookUrl": "https://your-domain.example/webhooks/bitrix24/your-secret",
      "isHidden": false,
      "isSupportOpenline": true,
      "properties": {"name": "Echo Bot"}
    },
    "botToken": "bot_token"
  }'
```

### Через OAuthBitrixClient (от имени приложения)

#### Привязка события

```bash
curl -X POST "https://your-domain.bitrix24.com/rest/1/abc/event.bind.json" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "ONOPENLINEMESSAGEADD",
    "handler": "https://your-domain.example/webhooks/bitrix24/app/your-secret",
    "auth": "access_token_from_app_auth"
  }'
```

#### Отправка сообщения в Open Lines сессию

```bash
curl -X POST "https://your-domain.bitrix24.com/rest/1/abc/imopenlines.bot.session.message.send.json" \
  -H "Content-Type: application/json" \
  -d '{
    "CHAT_ID": 12345,
    "NAME": "DEFAULT",
    "MESSAGE": "Ответ оператора",
    "auth": "access_token_from_app_auth"
  }'
```

#### Получение истории сессии Open Lines

```bash
curl -X POST "https://your-domain.bitrix24.com/rest/1/abc/imopenlines.session.history.get.json" \
  -H "Content-Type: application/json" \
  -d '{
    "CHAT_ID": 12345,
    "auth": "access_token_from_app_auth"
  }'
```

#### Получение диалога Open Lines

```bash
curl -X POST "https://your-domain.bitrix24.com/rest/1/abc/imopenlines.dialog.get.json" \
  -H "Content-Type: application/json" \
  -d '{
    "USER_CODE": "connector_id|line_id|connector_chat_id|user_id",
    "auth": "access_token_from_app_auth"
  }'
```

#### Отправка статуса доставки коннектора

```bash
curl -X POST "https://your-domain.bitrix24.com/rest/1/abc/imconnector.send.status.delivery.json" \
  -H "Content-Type: application/json" \
  -d '{
    "CONNECTOR": "amo",
    "LINE": 1,
    "MESSAGES": [{
      "im": {"chat_id": 123, "message_id": 456},
      "message": {"id": ["msg_id_1"], "date": 1700000000},
      "chat": {"id": "12345"}
    }],
    "auth": "access_token_from_app_auth"
  }'
```

### К внешнему сервису (от бота)

```bash
curl -X POST "https://builder.smartybotapps.ru/webhook/amoBitrixTest" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Текст сообщения пользователя",
    "session_id": "789"
  }'
```

**Ожидаемый ответ:**
```json
{"output": "Текст ответа от внешнего сервиса"}
```

---

## Проверка работоспособности

### Запуск сервера

```bash
uv run uvicorn bitrix_chat.main:app --host 0.0.0.0 --port 8000
```

### Быстрая проверка

```bash
curl "http://localhost:8000/health"
# Ответ: {"status":"ok"}

curl -I "http://localhost:8000/webhooks/bitrix24/test_secret"
# Ответ: {"status":"ok","method":"HEAD"}
```