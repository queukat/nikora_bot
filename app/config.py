from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    telegram_token: str
    api_url: str
    base_url: str

    poll_seconds: int               # fallback, если daily выключен
    daily_poll_at: str              # "HH:MM" или "off"

    deals_page_size: int
    db_path: Path
    data_dir: Path
    translations_path: Path
    untranslated_path: Path

    http_timeout_s: float
    http_user_agent: str
    tz_name: str


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

        poll_seconds=int(os.getenv("POLL_SECONDS", "300")),
        daily_poll_at=daily_poll_at,

        deals_page_size=int(os.getenv("DEALS_PAGE_SIZE", "10")),
        db_path=Path(os.getenv("DB_PATH", str(data_dir / "bot.db"))).resolve(),
        data_dir=data_dir,
        translations_path=Path(os.getenv("TRANSLATIONS_PATH", str(data_dir / "translations.json"))).resolve(),
        untranslated_path=Path(os.getenv("UNTRANSLATED_PATH", str(data_dir / "untranslated.json"))).resolve(),

        http_timeout_s=float(os.getenv("HTTP_TIMEOUT_S", "20")),
        http_user_agent=os.getenv(
            "HTTP_UA",
            "Mozilla/5.0 (X11; Linux x86_64) nikora-telegram-bot/1.2",
        ),
        tz_name=os.getenv("TZ_NAME", "Asia/Tbilisi").strip() or "Asia/Tbilisi",
    )
