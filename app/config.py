from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    telegram_token: str
    api_url: str
    base_url: str
    europroduct_enabled: bool
    europroduct_promo_url: str
    europroduct_base_url: str

    poll_seconds: int               # fallback, если daily выключен
    daily_poll_at: str              # "HH:MM" или "off"

    deals_page_size: int
    db_path: Path
    data_dir: Path
    translations_path: Path
    translation_memory_path: Path
    untranslated_path: Path

    http_timeout_s: float
    http_user_agent: str
    tz_name: str
    deals_cache_ttl_seconds: int
    europroduct_page_concurrency: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "off", "no", ""}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def load_config() -> Config:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    daily_poll_at = os.getenv("DAILY_POLL_AT", "09:00").strip()  # default: daily at 09:00
    if daily_poll_at.lower() in ("off", "none", "0", "false", ""):
        daily_poll_at = "off"

    return Config(
        telegram_token=token,
        api_url=os.getenv(
            "NIKORA_API_URL",
            "https://nikora.above.ge/json/sales.php?callback=JSON_CALLBACK",
        ).strip(),
        base_url=os.getenv("NIKORA_BASE_URL", "https://nikora.above.ge/").strip().rstrip("/") + "/",
        europroduct_enabled=_env_bool("EUROPRODUCT_ENABLED", True),
        europroduct_promo_url=os.getenv(
            "EUROPRODUCT_PROMO_URL",
            "https://europroduct.ge/en/products?Promo=1",
        ).strip(),
        europroduct_base_url=os.getenv(
            "EUROPRODUCT_BASE_URL",
            "https://europroduct.ge/",
        ).strip().rstrip("/") + "/",

        poll_seconds=_env_int("POLL_SECONDS", 300, 30, 86400),
        daily_poll_at=daily_poll_at,

        deals_page_size=_env_int("DEALS_PAGE_SIZE", 10, 1, 20),
        db_path=Path(os.getenv("DB_PATH", str(data_dir / "bot.db"))).resolve(),
        data_dir=data_dir,
        translations_path=Path(os.getenv("TRANSLATIONS_PATH", str(data_dir / "translations.json"))).resolve(),
        translation_memory_path=Path(
            os.getenv("TRANSLATION_MEMORY_PATH", str(data_dir / "translation_memory.json"))
        ).resolve(),
        untranslated_path=Path(os.getenv("UNTRANSLATED_PATH", str(data_dir / "untranslated.json"))).resolve(),

        http_timeout_s=_env_float("HTTP_TIMEOUT_S", 20.0, 2.0, 120.0),
        http_user_agent=os.getenv(
            "HTTP_UA",
            "Mozilla/5.0 (X11; Linux x86_64) nikora-telegram-bot/1.2",
        ),
        tz_name=os.getenv("TZ_NAME", "Asia/Tbilisi").strip() or "Asia/Tbilisi",
        deals_cache_ttl_seconds=_env_int("DEALS_CACHE_TTL_SECONDS", 3600, 30, 86400),
        europroduct_page_concurrency=_env_int("EUROPRODUCT_PAGE_CONCURRENCY", 4, 1, 10),
    )
