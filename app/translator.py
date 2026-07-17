from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


log = logging.getLogger("nikora_bot.translator")


DEFAULT_REPLACEMENTS: Dict[str, str] = {
    "„": "«",
    "“": "»",
    "”": "»",
    " /": "/",
    "/ ": "/",
    "  ": " ",
}

DEFAULT_FALLBACK_GLOSSARY: Dict[str, str] = {
    "შვრიის ფანტელი": "овсяные хлопья",
    "თეთრი შოკოლადით": "с белым шоколадом",
    "რძიანი შოკოლადით": "с молочным шоколадом",
    "შავი შოკოლადით": "с темным шоколадом",
    "მარცვლეულის": "злаковый",
    "დაფქვილი": "молотый",
    "ხსნადი": "растворимый",
    "ფილტრის": "для фильтра",
    "ორგანული": "органический",
    "კლასიკური": "классический",
    "გარგრით": "с абрикосом",
    "ასორტი": "ассорти",
    "კრეკერი": "крекер",
    "ფანტელი": "хлопья",
    "ბატონი": "батончик",
    "ორცხობილა": "печенье",
    "იოგურტი": "йогурт",
    "შოკოლადი": "шоколад",
    "ნაღები": "сливки",
    "კარაქი": "масло",
    "ყავა": "кофе",
    "ჩაი": "чай",
    "რძე": "молоко",
    "წყალი": "вода",
    "ლუდი": "пиво",
    "ღვინო": "вино",
    "წვენი": "сок",
}

KA_TO_RU = {
    "ა": "а", "ბ": "б", "გ": "г", "დ": "д", "ე": "е", "ვ": "в", "ზ": "з", "თ": "т",
    "ი": "и", "კ": "к", "ლ": "л", "მ": "м", "ნ": "н", "ო": "о", "პ": "п", "ჟ": "ж",
    "რ": "р", "ს": "с", "ტ": "т", "უ": "у", "ფ": "ф", "ქ": "к", "ღ": "г", "ყ": "к",
    "შ": "ш", "ჩ": "ч", "ც": "ц", "ძ": "дз", "წ": "ц", "ჭ": "ч", "ხ": "х", "ჯ": "дж",
    "ჰ": "х",
}


def _load_string_mapping(path: Path, label: str) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            out: Dict[str, str] = {}
            for k, v in data.items():
                kk = str(k).strip()
                vv = str(v).strip()
                if kk and vv:
                    out[kk] = vv
            return out
        raise RuntimeError(f"Expected a JSON object in {label} file: {path}")
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Could not load {label} file {path}: {exc}") from exc


def load_translations(path: Path) -> Dict[str, str]:
    return _load_string_mapping(path, "translations")


def load_translation_memory(path: Path) -> Dict[str, str]:
    return _load_string_mapping(path, "translation memory")


def load_fallback_glossary(path: Path) -> Dict[str, str]:
    merged = dict(DEFAULT_FALLBACK_GLOSSARY)
    if not path.exists():
        return merged

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k, v in data.items():
                kk = str(k).strip()
                vv = str(v).strip()
                if kk and vv:
                    merged[kk] = vv
    except Exception as exc:
        log.warning("Could not load fallback glossary %s: %r", path, exc)
    return merged


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def write_translation_template(path: Path, mapping: Dict[str, str]) -> None:
    _write_json_atomic(path, mapping)


def normalize_source_text(text: str) -> str:
    """Canonical key for safe, exact-enough reuse across changing product IDs."""
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = re.sub(r"(?<=\d)[,.](?=\d)", " decimal ", value)
    value = re.sub(r"[^\w%]+", " ", value, flags=re.UNICODE)
    value = value.replace("_", " ")
    return re.sub(r"\s+", " ", value).strip()


def normalize_units(text: str) -> str:
    s = text
    s = re.sub(r"(\d)\s*კგ\b", r"\1 кг", s)
    s = re.sub(r"(\d)\s*მლ\b", r"\1 мл", s)
    s = re.sub(r"(\d)\s*ლ\b", r"\1 л", s)
    s = re.sub(r"(\d)\s*გრ\b", r"\1 г", s)
    s = re.sub(r"(\d)\s*გ\b", r"\1 г", s)
    s = re.sub(r"(\d)\s*ც\.?\b", r"\1 шт.", s)
    return s


@dataclass
class Translator:
    replacements: Dict[str, str]
    by_id: Dict[str, str]
    fallback_glossary: Dict[str, str]
    memory: Dict[str, str]
    memory_path: Path
    by_text: Dict[str, str] = field(init=False, default_factory=dict)
    ambiguous_text_keys: set[str] = field(init=False, default_factory=set)
    _memory_dirty: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        self._rebuild_text_index()

    def reload(self, translations_path: Path, memory_path: Optional[Path] = None) -> None:
        next_memory_path = memory_path or self.memory_path
        next_by_id = load_translations(translations_path)
        next_glossary = load_fallback_glossary(translations_path.with_name("fallback_glossary.json"))
        next_memory = load_translation_memory(next_memory_path)

        self.by_id = next_by_id
        self.fallback_glossary = next_glossary
        self.memory_path = next_memory_path
        self.memory = next_memory
        self._memory_dirty = False
        self._rebuild_text_index()

    def _rebuild_text_index(self) -> None:
        by_text: Dict[str, str] = {}
        ambiguous: set[str] = set()
        for source_text, translation in self.memory.items():
            key = normalize_source_text(source_text)
            if not key or key in ambiguous:
                continue
            previous = by_text.get(key)
            if previous is not None and previous != translation:
                by_text.pop(key, None)
                ambiguous.add(key)
                continue
            by_text[key] = translation
        self.by_text = by_text
        self.ambiguous_text_keys = ambiguous
        if ambiguous:
            log.warning("Translation memory contains %d ambiguous normalized keys", len(ambiguous))

    def has_translation(self, text: str, item_id: Optional[str] = None) -> bool:
        if item_id and item_id in self.by_id:
            return True
        key = normalize_source_text(text)
        return bool(key and key in self.by_text)

    def remember(self, source_text: str, translation: str) -> bool:
        source = str(source_text or "").strip()
        value = str(translation or "").strip()
        key = normalize_source_text(source)
        if not source or not value or not key:
            return False

        if key in self.ambiguous_text_keys:
            self._drop_ambiguous_key(key, source)
            return False
        exact = self.memory.get(source)
        if exact == value:
            return False
        if exact is not None and exact != value:
            self._drop_ambiguous_key(key, source)
            return False

        existing = self.by_text.get(key)
        if existing == value:
            return False
        if existing is not None and existing != value:
            self._drop_ambiguous_key(key, source)
            return False

        self.memory[source] = value
        self.by_text[key] = value
        self._memory_dirty = True
        return True

    def _drop_ambiguous_key(self, key: str, source: str) -> None:
        if key not in self.ambiguous_text_keys:
            log.warning("Dropping ambiguous translation-memory source: %r", source)
        removed = False
        for remembered_source in list(self.memory):
            if normalize_source_text(remembered_source) == key:
                self.memory.pop(remembered_source, None)
                removed = True
        self.by_text.pop(key, None)
        self.ambiguous_text_keys.add(key)
        self._memory_dirty = self._memory_dirty or removed

    def import_translated_items(self, observations: Mapping[str, Any], prefer_observations: bool = False) -> int:
        if prefer_observations:
            return self._import_preferred_translated_items(observations)

        imported = 0
        for item_id, payload in observations.items():
            translation = self.by_id.get(str(item_id).strip())
            if not translation or not isinstance(payload, Mapping):
                continue
            if self.remember(str(payload.get("orig", "")), translation):
                imported += 1
        return imported

    def _import_preferred_translated_items(self, observations: Mapping[str, Any]) -> int:
        grouped: Dict[str, list[tuple[str, str]]] = {}
        for item_id, payload in observations.items():
            translation = self.by_id.get(str(item_id).strip())
            if not translation or not isinstance(payload, Mapping):
                continue
            source = str(payload.get("orig", "")).strip()
            key = normalize_source_text(source)
            if source and key:
                grouped.setdefault(key, []).append((source, translation))

        imported = 0
        for key, values in grouped.items():
            translations = {translation for _, translation in values}
            if len(translations) != 1:
                self._drop_ambiguous_key(key, values[0][0])
                continue

            source, translation = values[0]
            current = self.by_text.get(key)
            if current == translation and key not in self.ambiguous_text_keys:
                continue
            for remembered_source in list(self.memory):
                if normalize_source_text(remembered_source) == key:
                    self.memory.pop(remembered_source, None)
            self.memory[source] = translation
            self.by_text[key] = translation
            self.ambiguous_text_keys.discard(key)
            self._memory_dirty = True
            imported += 1
        return imported

    def observe_explicit_translation(self, item_id: str, source_text: str) -> bool:
        translation = self.by_id.get(str(item_id or "").strip())
        return bool(translation and self.remember(source_text, translation))

    def save_memory(self) -> bool:
        if not self._memory_dirty:
            return False
        _write_json_atomic(self.memory_path, self.memory)
        self._memory_dirty = False
        return True

    def to_ru(self, text: str, item_id: Optional[str] = None) -> str:
        if item_id and item_id in self.by_id:
            return self.by_id[item_id]

        if not text:
            return ""

        memory_translation = self.by_text.get(normalize_source_text(text))
        if memory_translation is not None:
            return memory_translation

        s = text

        for k, v in self.replacements.items():
            s = s.replace(k, v)

        s = normalize_units(s)

        for k, v in sorted(self.fallback_glossary.items(), key=lambda item: len(item[0]), reverse=True):
            s = s.replace(k, v)

        out = []
        for ch in s:
            out.append(KA_TO_RU.get(ch, ch))
        s = "".join(out)

        # Пытаемся сделать товарные названия чуть читабельнее.
        s = re.sub(r"'([^']+)'", r"«\1»", s)
        s = re.sub(r"(\d)\s*(кг|г|л|мл|шт\.)\b", r"\1 \2", s)

        # чуть лечим пробелы/единицы
        s = re.sub(r"\s{2,}", " ", s).strip()
        s = s.replace("« ", "«").replace(" »", "»")

        return s


def default_translator(translations_path: Path, memory_path: Optional[Path] = None) -> Translator:
    resolved_memory_path = memory_path or translations_path.with_name("translation_memory.json")
    return Translator(
        replacements=dict(DEFAULT_REPLACEMENTS),
        by_id=load_translations(translations_path),
        fallback_glossary=load_fallback_glossary(translations_path.with_name("fallback_glossary.json")),
        memory=load_translation_memory(resolved_memory_path),
        memory_path=resolved_memory_path,
    )
