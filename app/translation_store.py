from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

from .translator import Translator
from .utils import to_iso_now


class TranslatableDeal(Protocol):
    id: str
    title: str


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not load JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return value


def write_json_object_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def track_untranslated(path: Path, translator: Translator, deals: Iterable[TranslatableDeal]) -> int:
    """Update untranslated items and teach translation memory from explicit ID translations."""
    deal_list = list(deals)
    existing = load_json_object(path)
    memory_changes = translator.import_translated_items(existing)

    for deal in deal_list:
        if deal.id:
            memory_changes += int(translator.observe_explicit_translation(deal.id, deal.title))

    cleaned: dict[str, Any] = {}
    removed_count = 0
    for item_id, payload in existing.items():
        source_text = payload.get("orig", "") if isinstance(payload, Mapping) else ""
        if translator.has_translation(str(source_text), str(item_id)):
            removed_count += 1
            continue
        cleaned[str(item_id)] = payload

    now = to_iso_now()
    new_count = 0
    changed_count = 0
    for deal in deal_list:
        item_id = str(deal.id or "").strip()
        if not item_id or translator.has_translation(deal.title, item_id):
            continue

        previous = cleaned.get(item_id)
        first_seen = previous.get("first_seen", now) if isinstance(previous, Mapping) else now
        payload = {
            "orig": deal.title,
            "fallback": translator.to_ru(deal.title, item_id),
            "first_seen": first_seen,
        }
        if previous is None:
            new_count += 1
        elif previous != payload:
            changed_count += 1
        cleaned[item_id] = payload

    if memory_changes:
        translator.save_memory()
    if new_count or changed_count or removed_count or cleaned != existing:
        write_json_object_atomic(path, cleaned)
    return new_count
