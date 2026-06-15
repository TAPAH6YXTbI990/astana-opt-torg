# Настройка параметров .env

## Общая информация

Все параметры конфигурации проекта задаются через переменные окружения. Для этого используется файл `.env` в корне проекта. Переменные загружаются автоматически при старте приложения через `python-dotenv`.

Файл `.env` **не должен** добавляться в систему контроля версий. Для примера используется `.env.example`.

---

## Перечень переменных окружения

### Обязательные параметры

| Переменная | Тип | Описание | Пример |
|------------|-----|----------|--------|
| `BITRIX_REST_WEBHOOK_URL` | строка | REST webhook URL из Bitrix24 для вызовов REST API от имени бота. Формат: `https://your-domain.bitrix24.com/rest/{user_id}/{webhook_code}/` | `https://mycompany.bitrix24.com/rest/1/abc123def456/` |
| `BITRIX_BOT_ID` | целое число | ID зарегистрированного бота в Bitrix24. Получается после регистрации бота через `bitrix-register-bot` | `123` |
| `BITRIX_BOT_TOKEN` | строка | Токен бота для аутентификации в методах `imbot.v2.*`. Указывается при регистрации бота | `your_bot_token_string` |
| `BITRIX_INBOUND_SECRET` | строка | Секретная строка для проверки подлинности входящих webhook-запросов от Bitrix24. Должна совпадать с токеном в URL webhook | `my-secret-token-12345` |
| `BITRIX_CLIENT_ID` | строка | Client ID локального приложения Bitrix24. Получается в разделе «Разработчикам» → «Другие» → «Локальное приложение» | `local.app_id` |
| `BITRIX_CLIENT_SECRET` | строка | Client secret локального приложения Bitrix24 | `secret_key_from_bitrix` |
| `BITRIX_APP_STATE_PATH` | строка | Путь к файлу для сохранения OAuth-токенов приложения (после ONAPPINSTALL). Относительный или абсолютный путь | `.bitrix/app_auth.json` |
| `BITRIX_APP_WEBHOOK_URL` | строка | Публичный URL endpoint, который Bitrix24 должен вызвать для привязки событий через `event.bind`. Указывается без секрета | `https://your-domain.example/webhooks/bitrix24/app/your-secret` |

### Опциональные параметры

| Переменная | Тип | Значение по умолчанию | Описание |
|------------|-----|----------------------|----------|
| `BITRIX_OPENLINE_RESPONSE_WEBHOOK_URL` | строка | `https://builder.smartybotapps.ru/webhook/amoBitrixTest` | URL внешнего сервиса, который генерирует ответы на сообщения пользователей Open Lines. Принимает POST-запрос `{"message":"...","session_id":"..."}` и возвращает `{"output":"..."}` |
| `LOG_LEVEL` | строка | `INFO` | Уровень логирования. Допустимые значения: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

---

## Пример файла .env

```env
BITRIX_REST_WEBHOOK_URL=https://mycompany.bitrix24.com/rest/1/abc123def456/
BITRIX_BOT_ID=123
BITRIX_BOT_TOKEN=your_bot_token_string
BITRIX_INBOUND_SECRET=my-secret-token-12345
BITRIX_CLIENT_ID=local.app_id
BITRIX_CLIENT_SECRET=secret_key_from_bitrix
BITRIX_APP_STATE_PATH=.bitrix/app_auth.json
BITRIX_APP_WEBHOOK_URL=https://your-domain.example/webhooks/bitrix24/app/my-secret-token-12345
BITRIX_OPENLINE_RESPONSE_WEBHOOK_URL=https://builder.smartybotapps.ru/webhook/amoBitrixTest
LOG_LEVEL=INFO
```

---

## Порядок получения значений

### 1. BITRIX_REST_WEBHOOK_URL
1. Откройте Bitrix24 → Администрирование → Разработчикам → Другое → Другие
2. Или: Администрирование → Автоматизация → Бизнес-процессы → REST API
3. Нажмите «Получить webhook»
4. Скопируйте URL

### 2. BITRIX_BOT_ID и BITRIX_BOT_TOKEN
Выполните регистрацию бота через CLI:

```bash
uv run bitrix-register-bot \
  --code echo_bot \
  --name "Echo Bot" \
  --bot-token your_bot_token \
  --webhook-url https://your-domain.example/webhooks/bitrix24/your-secret
```

В ответе будет JSON с `bot.id` — это `BITRIX_BOT_ID`.

### 3. BITRIX_CLIENT_ID и BITRIX_CLIENT_SECRET
1. Откройте Bitrix24 → Администрирование → Разработчикам → Другое → Локальное приложение
2. Создайте новое приложение или используйте существующее
3. Скопируйте `client_id` и `client_secret`

### 4. BITRIX_INBOUND_SECRET
Придумайте любую секретную строку. Она должна совпадать с токеном в URL вашего webhook.

Например, если URL: `https://your-domain.example/webhooks/bitrix24/my123secret`, то `BITRIX_INBOUND_SECRET=my123secret`.

### 5. BITRIX_APP_WEBHOOK_URL
Соберите из публичного домена вашего сервера и пути:

```
https://{ваш_домен}/webhooks/bitrix24/app/{BITRIX_INBOUND_SECRET}
```

---

## Автоматическая привязка событий

После установки приложения (`ONAPPINSTALL`) бот автоматически вызывает `event.bind` для события `ONOPENLINEMESSAGEADD` с URL из `BITRIX_APP_WEBHOOK_URL`. Это означает, что вручную привязывать событие не нужно, если приложение устанавливается заново.

Если приложение было установлено до добавления этой функциональности, привяжите событие вручную:

```bash
uv run bitrix-bind-openlines --handler https://your-domain.example/webhooks/bitrix24/app/your-secret
```

---

## Хранение токенов приложения

Токены приложения (`access_token`, `refresh_token`, `application_token` и др.) автоматически сохраняются в файл по пути `BITRIX_APP_STATE_PATH`. При первом вызове OAuth-клиент читает токены из этого файла. При обновлении токена (refresh) файл перезаписывается.

Убедитесь, что директория для файла существует и доступна для записи. Бот создаёт директорию автоматически, если она не существует.