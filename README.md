# Nikora Deals Telegram Bot (VPS Ubuntu)

<!-- public-repo-status -->
> Status: Active personal tool. Issues are kept simple; pull requests are welcome only when they match the current scope.


## 1) Установка

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

mkdir -p ~/nikora_bot && cd ~/nikora_bot
# сюда положи файлы как в структуре проекта

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 2) Переменные окружения

Минимум:

- `TELEGRAM_BOT_TOKEN` — токен бота

Опционально:

- `DAILY_POLL_AT` — ежедневная проверка в формате `HH:MM` (по умолчанию `09:00`)
- `POLL_SECONDS` — интервал проверки в секундах, если `DAILY_POLL_AT=off`
- `NIKORA_API_URL` (по умолчанию `https://nikora.above.ge/json/sales.php?callback=JSON_CALLBACK`)
- `NIKORA_BASE_URL` (по умолчанию `https://nikora.above.ge/`)
- `DATA_DIR` (по умолчанию `./data`)
- `DEALS_PAGE_SIZE` — сколько акций показывать на странице
- `TZ_NAME` — таймзона для расчёта дедлайнов и daily polling

Пример:

```bash
export TELEGRAM_BOT_TOKEN="123:abc"
export DAILY_POLL_AT=off
export POLL_SECONDS=180
```

## 3) Запуск вручную

```bash
source .venv/bin/activate
python -m app.bot
```

## 4) Команды

- `/start` — открыть главное меню
- `/help` — показать команды и подсказку по поиску
- `/deals` — список активных акций
- `/search` или `/search <запрос>` — поиск по акциям
- `/subs` — список подписок
- `/unsubscribe <id>` — снять подписку по ID
- `/check <id>` — проверить доступность картинки товара
- `/settings` — напоминания и словарь
- `/untranslated` — выгрузить список непереведённых товаров

Также можно просто отправить текст или ID товара, бот воспримет это как быстрый поиск.

## 5) Подписки

- В `/deals` и результатах поиска есть кнопка `⭐ Подписаться`
- В карточке подписанного товара доступна кнопка `✅ Отписаться`
- В `/subs` можно открыть товар из подписок или удалить подписку кнопкой `❌`
- В `⚙️ Настройки` можно выбрать, за сколько дней присылать напоминание о завершении акции

Бот уведомит, если по подписке поменялись данные (цена/даты/картинка/название) или акция пропала из списка.
