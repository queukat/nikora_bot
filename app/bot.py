from __future__ import annotations

import json
import logging
import re
import html
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Dict, List, Optional, Any

from dateutil import tz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Config, load_config
from .nikora_api import Deal, NikoraApi
from .storage import Storage, Subscription
from .translator import default_translator, write_translation_template
from .utils import parse_ddmmyyyy, stable_hash, to_iso_now

log = logging.getLogger("nikora_bot")

SEARCH_PAGE_SIZE = 5  # чтобы поиск не спамил
SEARCH_CANCEL_WORDS = {"отмена", "cancel", "стоп", "menu", "меню"}
DEALS_CACHE_KEY = "deals_cache"
DEALS_CACHE_AT_KEY = "deals_cache_at"


def h(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=False)


# ---------- untranslated dump ----------

def _load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json_file(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def track_untranslated(cfg: Config, tr, deals: List[Deal]) -> int:
    """
    Сбрасывает в data/untranslated.json новые товары, которых нет в translations.json.
    Формат:
      {
        "17533": {"orig": "...", "fallback": "...", "first_seen": "2026-02-19T...Z"}
      }
    """
    out_path = cfg.untranslated_path
    existing = _load_json_file(out_path)
    translated_ids = {item_id for item_id in existing if item_id in tr.by_id}
    for item_id in translated_ids:
        existing.pop(item_id, None)

    now = to_iso_now()
    new_count = 0

    for d in deals:
        if not d.id:
            continue
        if d.id in tr.by_id:  # уже переведён словарём
            continue
        if d.id in existing:
            continue

        existing[d.id] = {
            "orig": d.title,
            "fallback": tr.to_ru(d.title, d.id),  # транслит/фолбэк
            "first_seen": now,
        }
        new_count += 1

    if new_count > 0 or translated_ids:
        _save_json_file(out_path, existing)

    return new_count


# ---------- UI keyboards ----------

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔥 Акции", callback_data="menu|deals|0"),
                InlineKeyboardButton("🔎 Поиск", callback_data="menu|search"),
            ],
            [
                InlineKeyboardButton("⭐ Подписки", callback_data="menu|subs"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="menu|settings"),
            ],
        ]
    )


def deal_kb(deal_id: str, subscribed: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("✅ Отписаться" if subscribed else "⭐ Подписаться",
                               callback_data=("unsub|" if subscribed else "sub|") + deal_id)]]
    )


def settings_kb(remind_days: int) -> InlineKeyboardMarkup:
    presets = [0, 1, 2, 3, 5, 7]
    row: List[InlineKeyboardButton] = []
    for d in presets:
        label = f"{d}д" if d else "выкл"
        if d == remind_days:
            label = f"✅ {label}"
        row.append(InlineKeyboardButton(label, callback_data=f"setrem|{d}"))
    return InlineKeyboardMarkup(
        [
            row,
            [
                InlineKeyboardButton("📝 Экспорт словаря", callback_data="settings|export_dict"),
                InlineKeyboardButton("🔄 Перезагрузить словарь", callback_data="settings|reload_dict"),
            ],
            [InlineKeyboardButton("📥 Непереведённые", callback_data="settings|untranslated")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu|back")],
        ]
    )


def deals_nav_kb(page: int, page_size: int, total: int) -> InlineKeyboardMarkup:
    max_page = max(0, (total - 1) // page_size) if total > 0 else 0
    prev_page = max(0, page - 1)
    next_page = min(max_page, page + 1)

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"menu|deals|{prev_page}"))
    buttons.append(InlineKeyboardButton(f"📄 {page+1}/{max_page+1}", callback_data="noop|x"))
    if page < max_page:
        buttons.append(InlineKeyboardButton("➡️ Дальше", callback_data=f"menu|deals|{next_page}"))

    return InlineKeyboardMarkup(
        [
            buttons,
            [
                InlineKeyboardButton("🔄 Обновить", callback_data="menu|deals|0|refresh"),
                InlineKeyboardButton("🔎 Поиск", callback_data="menu|search"),
            ],
            [
                InlineKeyboardButton("⭐ Подписки", callback_data="menu|subs"),
                InlineKeyboardButton("🏠 Меню", callback_data="menu|back"),
            ],
        ]
    )


def subs_list_kb(item_ids: List[str]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for item_id in item_ids:
        rows.append(
            [
                InlineKeyboardButton(f"👁 {item_id}", callback_data=f"subshow|{item_id}"),
                InlineKeyboardButton(f"❌ {item_id}", callback_data=f"unsublist|{item_id}"),
            ]
        )

    rows.append([InlineKeyboardButton("🔄 Обновить", callback_data="menu|subs")])
    rows.append([InlineKeyboardButton("🏠 Меню", callback_data="menu|back")])
    return InlineKeyboardMarkup(rows)


def search_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔥 Акции", callback_data="menu|deals|0")],
            [InlineKeyboardButton("🏠 Меню", callback_data="menu|back")],
        ]
    )


def search_nav_kb(page: int, page_size: int, total: int) -> InlineKeyboardMarkup:
    max_page = max(0, (total - 1) // page_size) if total > 0 else 0
    prev_page = max(0, page - 1)
    next_page = min(max_page, page + 1)

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"search|{prev_page}"))
    buttons.append(InlineKeyboardButton(f"📄 {page+1}/{max_page+1}", callback_data="noop|x"))
    if page < max_page:
        buttons.append(InlineKeyboardButton("➡️ Дальше", callback_data=f"search|{next_page}"))

    return InlineKeyboardMarkup(
        [
            buttons,
            [
                InlineKeyboardButton("🔎 Новый поиск", callback_data="menu|search"),
                InlineKeyboardButton("⭐ Подписки", callback_data="menu|subs"),
            ],
            [
                InlineKeyboardButton("🔥 Акции", callback_data="menu|deals|0"),
                InlineKeyboardButton("🏠 Меню", callback_data="menu|back"),
            ],
        ]
    )


# ---------- formatting ----------

def _deal_deadline_label(cfg: Config, deal: Deal) -> str:
    if not deal.end_date:
        return "⏳ До конца: дата не указана"
    days_left = days_left_local(cfg, deal.end_date)
    if days_left is None:
        return "⏳ До конца: дата не распознана"
    if days_left < 0:
        return "⏳ Акция завершена"
    if days_left == 0:
        return "⏳ До конца: сегодня"
    if days_left == 1:
        return "⏳ До конца: 1 день"
    return f"⏳ До конца: {days_left} дн."


def _settings_text(remind_days: int) -> str:
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"Напоминать за: <b>{remind_days} дн.</b> до конца акции "
        f"({ 'выкл' if remind_days == 0 else 'вкл' }).\n\n"
        "Выбери интервал кнопками ниже."
    )


def _build_subs_screen(subs: List[Subscription], by_id: Dict[str, Deal], tr) -> tuple[str, List[str]]:
    active_count = 0
    item_ids: List[str] = []
    lines: List[str] = [f"⭐ <b>Твои подписки</b>: {len(subs)}"]

    for s in subs:
        item_ids.append(s.item_id)
        deal = by_id.get(s.item_id)
        if deal:
            active_count += 1
        name = tr.to_ru(deal.title, deal.id) if deal else subscription_title(s, tr)
        state = "🟢 активна" if deal else "⚪ закончилась или не в текущих акциях"
        lines.append(f"• <b>{h(name)}</b>\n  <code>{h(s.item_id)}</code> - {state}")

    lines.insert(1, f"Сейчас активных: {active_count}")
    return "\n".join(lines), item_ids


def save_subscription_snapshot(storage: Storage, chat_id: int, deal: Deal, title_ru: str) -> None:
    storage.update_item_snapshot(
        chat_id,
        deal.id,
        title_original=deal.title,
        title_ru=title_ru,
        old_price=deal.old_price,
        new_price=deal.new_price,
        start_date=deal.start_date,
        end_date=deal.end_date,
    )


def save_subscription_snapshot_for_all(storage: Storage, deal: Deal, title_ru: str) -> None:
    storage.update_item_snapshot_for_all(
        deal.id,
        title_original=deal.title,
        title_ru=title_ru,
        old_price=deal.old_price,
        new_price=deal.new_price,
        start_date=deal.start_date,
        end_date=deal.end_date,
    )


def subscription_title(sub: Subscription, tr) -> str:
    for value in (sub.title_ru, tr.title_for_id(sub.item_id), sub.title_original):
        if value:
            title = tr.clean(str(value))
            if title:
                return title
    return "Название не сохранено"


def format_subscription_snapshot(sub: Subscription, tr) -> str:
    lines = [
        f"🛒 <b>{h(subscription_title(sub, tr))}</b>",
        f"🆔 <code>{h(sub.item_id)}</code>",
    ]
    if sub.new_price or sub.old_price:
        lines.append(f"💸 {h(sub.new_price or '?')} (было {h(sub.old_price or '?')})")
    if sub.start_date or sub.end_date:
        lines.append(f"📅 {h(sub.start_date or '?')} → {h(sub.end_date or '?')}")
    return "\n".join(lines)


def _is_cancel_text(text: str) -> bool:
    return _norm(text) in SEARCH_CANCEL_WORDS


def format_deal(cfg: Config, deal: Deal, title_ru: str) -> str:
    dates = f"{h(deal.start_date)} → {h(deal.end_date)}"
    deadline = _deal_deadline_label(cfg, deal)
    return (
        f"🛒 <b>{h(title_ru)}</b>\n"
        f"🆔 <code>{h(deal.id)}</code>\n"
        f"💸 {h(deal.new_price)} (было {h(deal.old_price)})\n"
        f"📅 {dates}\n"
        f"{deadline}"
    )


async def send_deal_message(
    bot,
    chat_id: int,
    cfg: Config,
    api: NikoraApi,
    deal: Deal,
    title_ru: str,
    subscribed: bool,
    prefix: str = "",
) -> Optional[int]:
    caption = (prefix + "\n\n" if prefix else "") + format_deal(cfg, deal, title_ru)
    urls = api.best_photo_urls(deal)  # 1) image 2) crop 3) thumb
    kb = deal_kb(deal.id, subscribed)

    last_err: Optional[Exception] = None
    for u in urls:
        if not u:
            continue
        try:
            sent = await bot.send_photo(
                chat_id=chat_id,
                photo=u,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            return getattr(sent, "message_id", None)
        except Exception as e:
            last_err = e
            continue

    extra = f"\n🖼 {h(urls[0])}" if urls else ""
    sent = await bot.send_message(
        chat_id=chat_id,
        text=caption + extra + (f"\n(error={h(repr(last_err))})" if last_err else ""),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )
    return getattr(sent, "message_id", None)


# ---------- deals cache ----------


def _deals_render_key(chat_id: int) -> str:
    return f"deals_rendered:{chat_id}"


def _save_deals_rendered(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_ids: List[int]) -> None:
    key = _deals_render_key(chat_id)
    context.user_data[key] = [int(mid) for mid in message_ids if isinstance(mid, int) and mid > 0]


async def _clear_deals_rendered(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    key = _deals_render_key(chat_id)
    raw_ids = context.user_data.get(key)
    context.user_data.pop(key, None)

    if not isinstance(raw_ids, list):
        return

    for mid in raw_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=int(mid))
        except Exception:
            continue


def is_deal_active(cfg: Config, deal: Deal) -> bool:
    # end_date задан в формате DD-MM-YYYY; фильтруем только точно завершившиеся акции.
    if not deal.end_date:
        return True
    dl = days_left_local(cfg, deal.end_date)
    if dl is None:
        return True
    return dl >= 0


def deal_sort_key(deal: Deal) -> tuple[int, int, str]:
    end_dt = parse_ddmmyyyy(deal.end_date)
    if end_dt is None:
        return (1, 10**9, deal.id)
    return (0, end_dt.date().toordinal(), deal.id)


def _deals_cache_ttl_seconds(cfg: Config) -> int:
    return max(30, min(cfg.poll_seconds, 900))


def _store_deals_cache(app_data: Dict[str, Any], deals: List[Deal]) -> None:
    app_data[DEALS_CACHE_KEY] = deals
    app_data[DEALS_CACHE_AT_KEY] = datetime.now(tz.UTC)


def _get_cached_deals(app_data: Dict[str, Any], cfg: Config) -> Optional[List[Deal]]:
    deals = app_data.get(DEALS_CACHE_KEY)
    cached_at = app_data.get(DEALS_CACHE_AT_KEY)
    if not isinstance(deals, list) or not isinstance(cached_at, datetime):
        return None

    age_s = (datetime.now(tz.UTC) - cached_at).total_seconds()
    if age_s > _deals_cache_ttl_seconds(cfg):
        return None
    return deals


async def get_deals_cached(context: ContextTypes.DEFAULT_TYPE, force_refresh: bool) -> List[Deal]:
    app_data = context.application.bot_data
    api: NikoraApi = app_data["api"]
    cfg: Config = app_data["cfg"]
    tr = app_data["translator"]

    if not force_refresh:
        cached = _get_cached_deals(app_data, cfg)
        if cached is not None:
            return cached

    deals = await api.fetch_deals()
    deals = [d for d in deals if is_deal_active(cfg, d)]
    deals.sort(key=deal_sort_key)
    _store_deals_cache(app_data, deals)

    # сбрасываем новые непереведённые
    track_untranslated(cfg, tr, deals)

    return deals


# ---------- commands ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await _clear_deals_rendered(context, chat_id)
    await update.effective_message.reply_text(
        "Привет! Я помогаю быстро находить акции Nikora.\n\n"
        "• Нажми «🔥 Акции», чтобы листать все предложения.\n"
        "• Нажми «🔎 Поиск» или просто отправь текст/ID — найду сразу.\n"
        "• В карточке товара жми «⭐ Подписаться», чтобы получать обновления.",
        reply_markup=main_menu_kb(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await _clear_deals_rendered(context, chat_id)
    await update.effective_message.reply_text(
        "Команды:\n"
        "/deals — список акций\n"
        "/search — режим поиска\n"
        "/search <запрос> — быстрый поиск (например: /search кофе)\n"
        "/subs — твои подписки\n"
        "/unsubscribe <id> — снять подписку по ID\n"
        "/check <id> — проверить картинку товара\n"
        "/settings — напоминания и словарь\n\n"
        "Подсказка: можно просто отправить слово, и я выполню поиск.",
        reply_markup=main_menu_kb(),
    )


async def cmd_deals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_deals(update, context, page=0, force_refresh=False)


async def cmd_subs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_subs(update, context)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_settings(update, context)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args:
        query_text = " ".join(context.args).strip()
        if query_text:
            await run_search(update, context, query_text=query_text, page=0)
            return
    await show_search_prompt(update, context)


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]

    if not context.args or not context.args[0].strip():
        await update.effective_message.reply_text(
            "Укажи ID товара: /unsubscribe <id>",
            reply_markup=main_menu_kb(),
        )
        return

    item_id = context.args[0].strip()
    chat_id = update.effective_chat.id

    if not storage.is_subscribed(chat_id, item_id):
        await update.effective_message.reply_text(
            f"Подписки на {item_id} сейчас нет.",
            reply_markup=main_menu_kb(),
        )
        return

    storage.unsubscribe(chat_id, item_id)
    await update.effective_message.reply_text(
        f"Подписка на {item_id} удалена.",
        reply_markup=main_menu_kb(),
    )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    api: NikoraApi = context.application.bot_data["api"]

    if not context.args or not context.args[0].strip():
        await update.effective_message.reply_text(
            "Укажи ID товара: /check <id>",
            reply_markup=main_menu_kb(),
        )
        return

    item_id = context.args[0].strip()

    try:
        deals = await api.fetch_deals()
    except Exception as e:
        log.exception("check fetch_deals failed for %s: %r", item_id, e)
        await update.effective_message.reply_text(
            "Не удалось получить список акций. Попробуй позже.",
            reply_markup=main_menu_kb(),
        )
        return

    deal = next((d for d in deals if d.id == item_id), None)
    if deal is None:
        await update.effective_message.reply_text(
            f"Товар с ID {item_id} не найден в текущих акциях.",
            reply_markup=main_menu_kb(),
        )
        return

    urls = api.best_photo_urls(deal)
    if not urls:
        await update.effective_message.reply_text(
            f"У товара {item_id} нет URL картинки.",
            reply_markup=main_menu_kb(),
        )
        return

    lines = [f"Проверка картинок для {item_id}:"]
    for url in urls:
        probe = await api.probe_url(url)
        status = probe.get("status", "-")
        content_type = probe.get("content_type", "-")
        method = probe.get("method", "-")
        ok = "ok" if probe.get("ok") == "true" else "fail"
        error = probe.get("error")
        line = f"[{ok}] {method} {status} {content_type} {url}"
        if error:
            line += f" error={error}"
        lines.append(line)

    await update.effective_message.reply_text("\n".join(lines), reply_markup=main_menu_kb())


async def cmd_untranslated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: Config = context.application.bot_data["cfg"]
    path = cfg.untranslated_path
    if not path.exists():
        await update.effective_message.reply_text("Пока нет непереведённых ✅", reply_markup=main_menu_kb())
        return
    await update.effective_message.reply_document(
        document=path.open("rb"),
        filename=path.name,
        caption="📥 Непереведённые (id, orig, fallback).",
    )


# ---------- screens ----------

async def show_deals(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, force_refresh: bool) -> None:
    app_data = context.application.bot_data
    api: NikoraApi = app_data["api"]
    storage: Storage = app_data["storage"]
    tr = app_data["translator"]
    cfg: Config = app_data["cfg"]

    chat_id = update.effective_chat.id
    deals = await get_deals_cached(context, force_refresh=force_refresh)
    total = len(deals)

    page_size = cfg.deals_page_size
    max_page = max(0, (total - 1) // page_size) if total > 0 else 0
    page = max(0, min(page, max_page))

    rendered_ids: List[int] = []

    if total == 0:
        await _clear_deals_rendered(context, chat_id)
        msg = await context.bot.send_message(chat_id=chat_id, text="Пока нет активных акций 😿", reply_markup=main_menu_kb())
        _save_deals_rendered(context, chat_id, [msg.message_id])
        return

    start = page * page_size
    end = min(total, start + page_size)
    chunk = deals[start:end]

    await _clear_deals_rendered(context, chat_id)

    header = await context.bot.send_message(chat_id=chat_id, text=f"🔥 Акции: {start+1}-{end} из {total}")
    rendered_ids.append(header.message_id)

    for d in chunk:
        title_ru = tr.to_ru(d.title, d.id)
        subscribed = storage.is_subscribed(chat_id, d.id)
        if subscribed:
            save_subscription_snapshot(storage, chat_id, d, title_ru)
        sent_id = await send_deal_message(
            bot=context.bot,
            chat_id=chat_id,
            cfg=cfg,
            api=api,
            deal=d,
            title_ru=title_ru,
            subscribed=subscribed,
        )
        if sent_id:
            rendered_ids.append(sent_id)

    nav = await context.bot.send_message(
        chat_id=chat_id,
        text="Листай дальше 👇",
        reply_markup=deals_nav_kb(page, page_size, total),
    )
    rendered_ids.append(nav.message_id)
    _save_deals_rendered(context, chat_id, rendered_ids)


async def show_subs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app_data = context.application.bot_data
    storage: Storage = app_data["storage"]
    tr = app_data["translator"]

    chat_id = update.effective_chat.id
    await _clear_deals_rendered(context, chat_id)
    subs = storage.list_subs(chat_id)

    if not subs:
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="Подписок пока нет. Открой «Акции» или «Поиск» и нажми «Подписаться».",
            reply_markup=main_menu_kb(),
        )
        _save_deals_rendered(context, chat_id, [msg.message_id])
        return

    deals = await get_deals_cached(context, force_refresh=False)
    by_id: Dict[str, Deal] = {d.id: d for d in deals if d.id}
    for sub in subs:
        deal = by_id.get(sub.item_id)
        if deal:
            save_subscription_snapshot(storage, chat_id, deal, tr.to_ru(deal.title, deal.id))

    text, item_ids = _build_subs_screen(subs, by_id, tr)

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=subs_list_kb(item_ids),
    )
    _save_deals_rendered(context, chat_id, [msg.message_id])


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage: Storage = context.application.bot_data["storage"]
    chat_id = update.effective_chat.id
    await _clear_deals_rendered(context, chat_id)
    remind_days = storage.get_remind_days(chat_id)
    text = _settings_text(remind_days)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=settings_kb(remind_days),
    )
    _save_deals_rendered(context, chat_id, [msg.message_id])


async def show_search_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await _clear_deals_rendered(context, chat_id)
    context.user_data["awaiting_search"] = True
    context.user_data.pop("search_query", None)
    context.user_data.pop("search_page", None)

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🔎 Введи слово для поиска (например: молоко, йогурт, кофе) или ID товара.\n"
            "Можно отменить словом «отмена» и вернуться в меню."
        ),
        reply_markup=search_prompt_kb(),
    )
    _save_deals_rendered(context, chat_id, [msg.message_id])


def _norm(s: str) -> str:
    s = (s or "").lower().replace("ё", "е").strip()
    s = re.sub(r"(?<=\d)[,.](?=\d)", ".", s)
    s = s.replace("«", " ").replace("»", " ").replace('"', " ")
    s = re.sub(r"[^0-9a-zа-яა-ჰ%+./ ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _matches_query(query: str, deal: Deal, tr) -> bool:
    q = _norm(query)
    if not q:
        return False

    if q in _norm(deal.id):
        return True

    haystack = " ".join(
        _norm(value)
        for value in (
            deal.title,
            tr.to_ru(deal.title, deal.id),
            tr.clean(deal.title),
        )
        if value
    )

    if q in haystack:
        return True

    terms = [term for term in q.split(" ") if term]
    return bool(terms) and all(term in haystack for term in terms)


async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str, page: int) -> None:
    app_data = context.application.bot_data
    api: NikoraApi = app_data["api"]
    storage: Storage = app_data["storage"]
    tr = app_data["translator"]
    cfg: Config = app_data["cfg"]

    chat_id = update.effective_chat.id
    deals = await get_deals_cached(context, force_refresh=False)

    matches: List[Deal] = []
    for d in deals:
        if _matches_query(query_text, d, tr):
            matches.append(d)

    total = len(matches)
    max_page = max(0, (total - 1) // SEARCH_PAGE_SIZE) if total > 0 else 0
    page = max(0, min(page, max_page))

    context.user_data["search_query"] = query_text
    context.user_data["search_page"] = page
    context.user_data["awaiting_search"] = False

    if total == 0:
        await _clear_deals_rendered(context, chat_id)
        context.user_data["awaiting_search"] = True
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text="Ничего не нашёл 😿\nВведи другой запрос или ID товара.",
            reply_markup=search_prompt_kb(),
        )
        _save_deals_rendered(context, chat_id, [msg.message_id])
        return

    start = page * SEARCH_PAGE_SIZE
    end = min(total, start + SEARCH_PAGE_SIZE)
    chunk = matches[start:end]
    rendered_ids: List[int] = []

    await _clear_deals_rendered(context, chat_id)

    header = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔎 Поиск: «{h(query_text)}» - {start+1}-{end} из {total}",
        parse_mode=ParseMode.HTML,
    )
    rendered_ids.append(header.message_id)

    for d in chunk:
        title_ru = tr.to_ru(d.title, d.id)
        subscribed = storage.is_subscribed(chat_id, d.id)
        if subscribed:
            save_subscription_snapshot(storage, chat_id, d, title_ru)
        sent_id = await send_deal_message(
            bot=context.bot,
            chat_id=chat_id,
            cfg=cfg,
            api=api,
            deal=d,
            title_ru=title_ru,
            subscribed=subscribed,
        )
        if sent_id:
            rendered_ids.append(sent_id)

    nav = await context.bot.send_message(
        chat_id=chat_id,
        text="Листай результаты 👇",
        reply_markup=search_nav_kb(page, SEARCH_PAGE_SIZE, total),
    )
    rendered_ids.append(nav.message_id)
    _save_deals_rendered(context, chat_id, rendered_ids)


async def export_dict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app_data = context.application.bot_data
    api: NikoraApi = app_data["api"]
    tr = app_data["translator"]
    cfg: Config = app_data["cfg"]

    deals = await api.fetch_deals()
    track_untranslated(cfg, tr, deals)

    mapping = {d.id: tr.to_ru(d.title, d.id) for d in deals if d.id}

    out_path = cfg.data_dir / "translations.template.json"
    write_translation_template(out_path, mapping)

    await update.effective_message.reply_document(
        document=out_path.open("rb"),
        filename="translations.template.json",
        caption="📝 Шаблон словаря переводов. Сохрани как data/translations.json и перезагрузи словарь.",
    )


async def reload_dict(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    app_data = context.application.bot_data
    tr = app_data["translator"]
    cfg: Config = app_data["cfg"]

    tr.reload(cfg.translations_path)
    await update.effective_message.reply_text(
        f"Ок, словарь перезагружен: {cfg.translations_path.name}",
        reply_markup=main_menu_kb(),
    )


# ---------- message handler (for search input) ----------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_message.text:
        return

    raw_text = update.effective_message.text.strip()
    if not raw_text:
        return

    if context.user_data.get("awaiting_search"):
        if _is_cancel_text(raw_text):
            context.user_data["awaiting_search"] = False
            await _clear_deals_rendered(context, update.effective_chat.id)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Поиск отменён. Меню 👇",
                reply_markup=main_menu_kb(),
            )
            return
        await run_search(update, context, query_text=raw_text, page=0)
        return

    if _is_cancel_text(raw_text):
        await _clear_deals_rendered(context, update.effective_chat.id)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Меню 👇",
            reply_markup=main_menu_kb(),
        )
        return

    text_norm = _norm(raw_text)
    if text_norm.startswith("поиск ") or text_norm.startswith("search "):
        parts = raw_text.split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            await show_search_prompt(update, context)
            return
        await run_search(update, context, query_text=parts[1].strip(), page=0)
        return

    # UX: любое обычное текстовое сообщение интерпретируем как быстрый поиск.
    await run_search(update, context, query_text=raw_text, page=0)


# ---------- callbacks ----------

async def _refresh_subs_message(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    app_data = context.application.bot_data
    storage: Storage = app_data["storage"]
    tr = app_data["translator"]

    chat_id = query.message.chat_id
    subs = storage.list_subs(chat_id)
    if not subs:
        await query.edit_message_text("Подписок больше нет ✅", reply_markup=main_menu_kb())
        return

    deals = await get_deals_cached(context, force_refresh=False)
    by_id: Dict[str, Deal] = {d.id: d for d in deals if d.id}
    for sub in subs:
        deal = by_id.get(sub.item_id)
        if deal:
            save_subscription_snapshot(storage, chat_id, deal, tr.to_ru(deal.title, deal.id))

    text, item_ids = _build_subs_screen(subs, by_id, tr)

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=subs_list_kb(item_ids),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    answered = False

    async def answer_once(text: Optional[str] = None) -> None:
        nonlocal answered
        if answered:
            return
        try:
            if text:
                await query.answer(text=text, show_alert=False)
            else:
                await query.answer()
        except Exception:
            pass
        answered = True

    app_data = context.application.bot_data
    storage: Storage = app_data["storage"]
    cfg: Config = app_data["cfg"]

    data = (query.data or "").strip()

    if data.startswith("noop|"):
        await answer_once()
        return

    if data.startswith("menu|"):
        parts = data.split("|")
        action = parts[1] if len(parts) > 1 else ""

        if action == "deals":
            await answer_once()
            page = 0
            force = False
            if len(parts) >= 3:
                try:
                    page = int(parts[2])
                except Exception:
                    page = 0
            if len(parts) >= 4 and parts[3] == "refresh":
                force = True
            await show_deals(update, context, page=page, force_refresh=force)
            return

        if action == "subs":
            await answer_once()
            await show_subs(update, context)
            return

        if action == "settings":
            await answer_once()
            await show_settings(update, context)
            return

        if action == "search":
            await answer_once()
            await show_search_prompt(update, context)
            return

        if action == "back":
            await answer_once()
            context.user_data["awaiting_search"] = False
            await _clear_deals_rendered(context, query.message.chat_id)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Меню 👇",
                reply_markup=main_menu_kb(),
            )
            return

    if data.startswith("search|"):
        await answer_once()
        try:
            page = int(data.split("|", 1)[1])
        except Exception:
            page = 0
        qtxt = context.user_data.get("search_query")
        if not qtxt:
            await query.message.reply_text("Сначала сделай поиск.", reply_markup=main_menu_kb())
            return
        await run_search(update, context, query_text=str(qtxt), page=page)
        return

    if data.startswith("setrem|"):
        try:
            days = int(data.split("|", 1)[1])
        except Exception:
            days = 3
        storage.set_remind_days(query.message.chat_id, days)
        await answer_once(f"Напоминания: {days} дн.")
        await query.edit_message_text(
            _settings_text(days),
            parse_mode=ParseMode.HTML,
            reply_markup=settings_kb(days),
        )
        return

    if data == "settings|export_dict":
        await answer_once()
        await export_dict(update, context)
        return

    if data == "settings|reload_dict":
        await answer_once("Словарь обновлён")
        await reload_dict(update, context)
        return

    if data == "settings|untranslated":
        await answer_once()
        path = cfg.untranslated_path
        if not path.exists():
            await query.message.reply_text("Пока нет непереведённых ✅", reply_markup=main_menu_kb())
            return
        await query.message.reply_document(
            document=path.open("rb"),
            filename=path.name,
            caption="📥 Непереведённые (id, orig, fallback).",
        )
        return

    if data.startswith("unsublist|"):
        await answer_once("Подписка удалена")
        item_id = data.split("|", 1)[1].strip()
        storage.unsubscribe(query.message.chat_id, item_id)
        await _refresh_subs_message(query, context)
        return

    if data.startswith("subshow|"):
        await answer_once()
        item_id = data.split("|", 1)[1].strip()
        tr = app_data["translator"]
        api: NikoraApi = app_data["api"]
        chat_id = query.message.chat_id
        deals = await get_deals_cached(context, force_refresh=False)
        deal = next((d for d in deals if d.id == item_id), None)
        if deal is None:
            sub = next((s for s in storage.list_subs(chat_id) if s.item_id == item_id), None)
            details = f"\n\n{format_subscription_snapshot(sub, tr)}" if sub else f"\n\n🆔 <code>{h(item_id)}</code>"
            await query.message.reply_text(
                f"По подписке сейчас нет активной акции.{details}",
                parse_mode=ParseMode.HTML,
            )
            return

        title_ru = tr.to_ru(deal.title, deal.id)
        subscribed = storage.is_subscribed(chat_id, deal.id)
        if subscribed:
            save_subscription_snapshot(storage, chat_id, deal, title_ru)
        await send_deal_message(
            bot=context.bot,
            chat_id=chat_id,
            cfg=cfg,
            api=api,
            deal=deal,
            title_ru=title_ru,
            subscribed=subscribed,
            prefix="⭐ <b>Из подписок</b>",
        )
        return

    if "|" in data:
        action, item_id = data.split("|", 1)
        item_id = item_id.strip()
        if action == "sub":
            await answer_once("Подписка добавлена")
            storage.upsert_subscribe(query.message.chat_id, item_id)
            tr = app_data["translator"]
            deals = await get_deals_cached(context, force_refresh=False)
            deal = next((d for d in deals if d.id == item_id), None)
            if deal:
                save_subscription_snapshot(storage, query.message.chat_id, deal, tr.to_ru(deal.title, deal.id))
            await query.edit_message_reply_markup(reply_markup=deal_kb(item_id, subscribed=True))
        elif action == "unsub":
            await answer_once("Подписка удалена")
            storage.unsubscribe(query.message.chat_id, item_id)
            await query.edit_message_reply_markup(reply_markup=deal_kb(item_id, subscribed=False))

    await answer_once()


# ---------- periodic polling ----------

def days_left_local(cfg: Config, end_date_str: str) -> Optional[int]:
    end_dt = parse_ddmmyyyy(end_date_str)
    if not end_dt:
        return None

    tzinfo = tz.gettz(cfg.tz_name) or tz.UTC
    today = datetime.now(tzinfo).date()
    end_day = end_dt.astimezone(tzinfo).date()
    return (end_day - today).days


async def poll_and_notify(context: ContextTypes.DEFAULT_TYPE) -> None:
    app_data = context.application.bot_data
    api: NikoraApi = app_data["api"]
    storage: Storage = app_data["storage"]
    tr = app_data["translator"]
    cfg: Config = app_data["cfg"]

    try:
        deals = await api.fetch_deals()
    except Exception as e:
        log.exception("fetch_deals failed: %r", e)
        return

    # сбрасываем новые непереведённые
    track_untranslated(cfg, tr, deals)

    active_deals = [d for d in deals if is_deal_active(cfg, d)]
    active_deals.sort(key=deal_sort_key)
    _store_deals_cache(app_data, active_deals)
    by_id: Dict[str, Deal] = {d.id: d for d in active_deals if d.id}
    for deal in active_deals:
        save_subscription_snapshot_for_all(storage, deal, tr.to_ru(deal.title, deal.id))
    now = to_iso_now()

    for sub in list(storage.iter_all_subscriptions()):
        deal = by_id.get(sub.item_id)

        if deal is None:
            if sub.is_active:
                try:
                    await context.bot.send_message(
                        chat_id=sub.chat_id,
                        text=(
                            "ℹ️ <b>Акция закончилась или пропала из списка</b>\n\n"
                            f"{format_subscription_snapshot(sub, tr)}"
                        ),
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
                storage.mark_inactive(sub.chat_id, sub.item_id)
            continue

        payload = {
            "id": deal.id,
            "title": deal.title,
            "old_price": deal.old_price,
            "new_price": deal.new_price,
            "start_date": deal.start_date,
            "end_date": deal.end_date,
            "image": deal.image,
            "thumb": deal.thumb,
            "crop": deal.crop,
        }
        h = stable_hash(payload)

        should_send_update = (sub.last_hash_sent != h) or (not sub.is_active)
        if should_send_update:
            title_ru = tr.to_ru(deal.title, deal.id)
            save_subscription_snapshot(storage, sub.chat_id, deal, title_ru)
            sent_ok = False
            try:
                await send_deal_message(
                    bot=context.bot,
                    chat_id=sub.chat_id,
                    cfg=cfg,
                    api=api,
                    deal=deal,
                    title_ru=title_ru,
                    subscribed=True,
                    prefix="🔔 <b>Обновление по подписке</b>",
                )
                sent_ok = True
            except Exception as e:
                log.warning("failed to send subscription update chat=%s item=%s: %r", sub.chat_id, sub.item_id, e)
            if sent_ok:
                storage.update_seen_and_hash(sub.chat_id, sub.item_id, now, h)

        remind_days = storage.get_remind_days(sub.chat_id)
        if remind_days > 0 and deal.end_date:
            dl = days_left_local(cfg, deal.end_date)
            if dl is not None and dl == remind_days:
                if sub.last_end_reminder_sent != deal.end_date:
                    title_ru = tr.to_ru(deal.title, deal.id)
                    sent_ok = False
                    try:
                        await send_deal_message(
                            bot=context.bot,
                            chat_id=sub.chat_id,
                            cfg=cfg,
                            api=api,
                            deal=deal,
                            title_ru=title_ru,
                            subscribed=True,
                            prefix=f"⏳ <b>Напоминание</b>\nЗакончится через {remind_days} дн.",
                        )
                        sent_ok = True
                    except Exception as e:
                        log.warning("failed to send reminder chat=%s item=%s: %r", sub.chat_id, sub.item_id, e)
                    if sent_ok:
                        storage.update_end_reminder_sent(sub.chat_id, sub.item_id, deal.end_date)


# ---------- app lifecycle ----------

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


async def on_shutdown(app: Application) -> None:
    api: NikoraApi = app.bot_data.get("api")
    storage: Storage = app.bot_data.get("storage")
    if api:
        await api.close()
    if storage:
        storage.close()


def _parse_daily_time(cfg: Config) -> Optional[dt_time]:
    if not cfg.daily_poll_at or cfg.daily_poll_at.lower() in ("off", "none", "0", "false"):
        return None
    m = re.match(r"^\s*(\d{1,2})\s*:\s*(\d{1,2})\s*$", cfg.daily_poll_at)
    if not m:
        raise ValueError(f"Bad DAILY_POLL_AT format: {cfg.daily_poll_at!r} (expected HH:MM)")
    hh = int(m.group(1))
    mm = int(m.group(2))
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"Bad DAILY_POLL_AT value: {cfg.daily_poll_at!r}")
    tzinfo = tz.gettz(cfg.tz_name) or tz.UTC
    return dt_time(hour=hh, minute=mm, tzinfo=tzinfo)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    cfg = load_config()

    storage = Storage(cfg.db_path)
    schema_sql = read_text(Path(__file__).resolve().parents[1] / "schema.sql")
    storage.init_schema(schema_sql)

    api = NikoraApi(
        api_url=cfg.api_url,
        base_url=cfg.base_url,
        timeout_s=cfg.http_timeout_s,
        user_agent=cfg.http_user_agent,
    )

    translator = default_translator(cfg.translations_path)

    app = Application.builder().token(cfg.telegram_token).build()
    app.bot_data["cfg"] = cfg
    app.bot_data["storage"] = storage
    app.bot_data["api"] = api
    app.bot_data["translator"] = translator

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("deals", cmd_deals))
    app.add_handler(CommandHandler("subs", cmd_subs))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("untranslated", cmd_untranslated))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # --- schedule polling ---
    daily_time = _parse_daily_time(cfg)
    if daily_time is not None:
        app.job_queue.run_daily(poll_and_notify, time=daily_time)
        log.info("Polling scheduled daily at %s (%s)", cfg.daily_poll_at, cfg.tz_name)
    else:
        app.job_queue.run_repeating(poll_and_notify, interval=cfg.poll_seconds, first=5)
        log.info("Polling scheduled every %ss", cfg.poll_seconds)

    app.post_shutdown = on_shutdown

    log.info("Starting bot with polling...")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
