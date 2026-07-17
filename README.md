# Nikora + Europroduct Deals Telegram Bot (VPS Ubuntu)

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
- `EUROPRODUCT_ENABLED` — включить акции Europroduct (по умолчанию `true`)
- `EUROPRODUCT_PROMO_URL` (по умолчанию `https://europroduct.ge/en/products?Promo=1`)
- `EUROPRODUCT_BASE_URL` (по умолчанию `https://europroduct.ge/`)
- `DATA_DIR` (по умолчанию `./data`)
- `TRANSLATION_MEMORY_PATH` — память переводов по исходному названию
- `DEALS_PAGE_SIZE` — сколько акций показывать на странице
- `DEALS_CACHE_TTL_SECONDS` — TTL общего кэша акций (по умолчанию 3600)
- `EUROPRODUCT_PAGE_CONCURRENCY` — параллельность обхода страниц (по умолчанию 4)
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
- `/deals` — список активных акций Nikora и Europroduct
- `/search` или `/search <запрос>` — поиск по акциям, ID или названию магазина
- `/subs` — список подписок
- `/unsubscribe <id>` — снять подписку по ID
- `/check <id>` — проверить доступность картинки товара
- `/settings` — напоминания и словарь
- `/untranslated` — выгрузить список непереведённых товаров

Также можно просто отправить текст, ID товара или название магазина, бот воспримет это как быстрый поиск.

## 5) Подписки

- В `/deals` и результатах поиска есть кнопка `⭐ Подписаться`
- В карточке подписанного товара доступна кнопка `✅ Отписаться`
- В `/subs` можно открыть товар из подписок или удалить подписку кнопкой `❌`
- В `⚙️ Настройки` можно выбрать, за сколько дней присылать напоминание о завершении акции

Бот уведомит, если по подписке поменялись данные (цена/даты/картинка/название) или акция пропала из списка.

Примечание: у Europroduct на странице акций обычно нет дат начала/окончания, поэтому напоминания по сроку окончания работают только для акций, где дата указана источником.

## 6) Переводы без повторной работы

- `data/translations.json` — явные переводы по ID; они имеют наивысший приоритет.
- `data/translation_memory.json` — автоматически переиспользуемые переводы по нормализованному исходному названию.
- `data/untranslated.json` — только позиции, для которых нет ни ID-перевода, ни безопасного совпадения в памяти.

После добавления ID-переводов нажми «Перезагрузить словарь». Пока исходные названия ещё есть в `untranslated.json`, бот перенесёт пары `название → перевод` в память и удалит уже обработанные позиции при следующем обновлении.

Для одноразовой миграции старой выгрузки:

```bash
python -m scripts.build_translation_memory \
  --translations data/translations.json \
  --observations data/untranslated.old.json \
  --output data/translation_memory.json
```

Неоднозначные нормализованные названия намеренно не переиспользуются.

## License

<!-- commercial-license-policy -->
This project is licensed for non-commercial use under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0.txt).
Commercial use, resale, paid distribution, marketplace publication, SaaS hosting, or bundling into a paid product requires separate written permission from the author.
Project names, logos, package identifiers, store listings, screenshots, and other branding assets are not licensed for use in forks or redistributed builds.
