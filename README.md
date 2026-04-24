# VPN Telegram Bot — Remnawave + platega.io

Бот для продажи VPN-подписок через Telegram. Выдача доступа — через панель [Remnawave](https://remna.st),
приём платежей — через [platega.io](https://platega.io) (СБП, карты, крипта).

## Возможности

- Выбор тарифа из заданного списка и автогенерация ссылки на оплату.
- Приём callback от platega.io → автоматическое создание/продление пользователя в Remnawave.
- Команда «Мой VPN» — выдача `subscription_url` и срока действия подписки.
- Проверка статуса платежа по кнопке «Я оплатил».
- Админ-команды `/stats` и `/grant <telegram_id> <days>`.
- Асинхронная архитектура (aiogram 3 + httpx + SQLAlchemy async).
- Поставляется с `Dockerfile` и `docker-compose.yml` (SQLite по умолчанию, Postgres опционально).

## Архитектура

```
┌──────────────┐         ┌────────────────┐        ┌──────────────┐
│  Telegram    │ ◄─────► │  bot (aiogram) │ ◄────► │  Remnawave   │
│  @BotFather  │         │  + webhook     │        │  panel API   │
└──────────────┘         │  + SQLAlchemy  │        └──────────────┘
                         │                │
                         │                │        ┌──────────────┐
                         │                │ ◄────► │  platega.io  │
                         └────────────────┘        └──────────────┘
```

Один процесс поднимает и long-polling Telegram, и HTTP-сервер `aiohttp` для приёма платежных callback'ов
от platega.io на `POST /platega/callback`.

## Быстрый старт

### 1. Установка

```bash
git clone https://github.com/<you>/vpn-telegram-bot.git
cd vpn-telegram-bot
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# отредактируйте .env — см. таблицу ниже
```

### 2. Запуск в Docker

```bash
cp .env.example .env
# отредактируйте .env
docker compose up -d --build
```

По умолчанию поднимается только контейнер бота + Postgres. Чтобы использовать SQLite, просто
оставьте `DATABASE_URL=sqlite+aiosqlite:///./data/vpnbot.sqlite3` и удалите сервис `db` из
`docker-compose.yml`.

### 3. Публичный callback-URL

Бот должен быть доступен по HTTPS извне, чтобы platega.io мог отправлять callback. Поставьте перед
ним nginx/Caddy/traefik с валидным сертификатом и пробросьте `/platega/callback` на порт `8080`.
В личном кабинете platega.io (Настройки → Callback URLs) укажите полный URL, например:

```
https://bot.example.com/platega/callback
```

Этот же URL должен быть указан в `.env` как `PLATEGA_CALLBACK_URL`.

> ⚠️ platega.io **не принимает** HTTP, приватные IP, self-signed сертификаты и localhost.

## Переменные окружения

| Переменная | Назначение |
| --- | --- |
| `BOT_TOKEN` | Токен бота от @BotFather. |
| `ADMIN_IDS` | Список Telegram ID (через запятую), имеющих доступ к `/stats` и `/grant`. |
| `DATABASE_URL` | SQLAlchemy URL. По умолчанию SQLite в `./data/vpnbot.sqlite3`. |
| `REMNAWAVE_BASE_URL` | URL панели Remnawave. |
| `REMNAWAVE_TOKEN` | API-токен из раздела «API Tokens» панели. |
| `REMNAWAVE_CADDY_TOKEN` | Опционально — токен для обхода Caddy-аутентификации. |
| `REMNAWAVE_SQUAD_UUIDS` | UUID внутренних скуадов (через запятую). Если пусто — прикрепляется единственный доступный скуад. |
| `REMNAWAVE_TRAFFIC_LIMIT_GB` | Квота трафика на пользователя, ГБ (0 = без лимита). |
| `PLATEGA_MERCHANT_ID` | MerchantId из кабинета platega.io. |
| `PLATEGA_SECRET` | API-ключ из кабинета platega.io. |
| `PLATEGA_BASE_URL` | Базовый URL API platega.io (оставьте по умолчанию). |
| `PLATEGA_PAYMENT_METHOD` | Метод оплаты: `2` — СБП/QR, `3` — карта, `11/12/13` — крипта. |
| `PLATEGA_CALLBACK_URL` | Ваш публичный URL callback. |
| `PLATEGA_RETURN_URL` | Куда редиректить клиента после успешной оплаты (например, ссылка на бота). |
| `PLATEGA_FAIL_URL` | Куда редиректить при отмене. |
| `WEBHOOK_HOST` / `WEBHOOK_PORT` | Адрес и порт aiohttp-сервера (по умолчанию `0.0.0.0:8080`). |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR`. |
| `SUPPORT_USERNAME` | `@username` поддержки, показывается в разделе «Помощь». |

## Тарифы

Список тарифов живёт в `bot/services/tariffs.py`. Отредактируйте константу `TARIFFS`, чтобы
изменить цены и длительности. Поле `code` у существующих тарифов менять **нельзя** — оно сохраняется
в платежах и используется для фулфилмента после оплаты.

```python
TARIFFS = (
    Tariff(code="1m", title="1 месяц",  days=30, price_rub=80),
    Tariff(code="3m", title="3 месяца", days=90, price_rub=220),  # скидка 20 ₽
)
```

Чтобы добавить более длинные тарифы (6/12 мес), достаточно дописать строки —
их `code` должен быть уникальным, всё остальное подхватится автоматически.

## Как работает покупка

1. `/start` — создаётся запись в локальной БД.
2. «🛒 Купить VPN» → выбор тарифа.
3. Бот дергает `POST /transaction/process` у platega.io и получает `redirect`-URL.
4. Клиент переходит по ссылке, оплачивает, возвращается в бота.
5. platega.io шлёт callback `POST /platega/callback` со статусом `CONFIRMED` или `CANCELED`.
6. При `CONFIRMED` бот вызывает Remnawave API:
   - если в БД ещё нет `remnawave_uuid` — `POST /api/users` (создаёт пользователя на весь срок тарифа);
   - если уже есть — `PATCH /api/users` с новым `expireAt = max(now, expireAt) + days`.
7. Бот отправляет пользователю ссылку `subscription_url` из Remnawave.

## Админ-команды

| Команда | Описание |
| --- | --- |
| `/stats` | Кол-во пользователей, активных подписок, подтверждённых платежей, выручка. |
| `/grant <telegram_id> <days>` | Выдать/продлить подписку вручную без оплаты. |

## Тестирование

```bash
ruff check .
pytest
```

Smoke-test (`tests/test_imports.py`) проверяет, что все модули импортируются, и валидирует тарифный
каталог — запускается в CI.

## Отладка

- `GET /health` возвращает `200 ok` — используйте для uptime-проверок.
- Логи идут в stdout в формате `YYYY-MM-DD HH:MM:SS LEVEL name: message`.
- Для отладки callback'ов platega.io можно временно выставить `LOG_LEVEL=DEBUG`.

## Лицензия

MIT.
