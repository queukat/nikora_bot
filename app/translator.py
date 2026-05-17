from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


DEFAULT_REPLACEMENTS: Dict[str, str] = {
    "„": "«",
    "“": "»",
    "”": "»",
    " /": "/",
    "/ ": "/",
    "  ": " ",
    "რძე": "молоко",
    "იოგურტი": "йогурт",
    "მაწონი": "мацони",
    "არაჟანი": "сметана",
    "ხაჭო": "творог",
    "ნაღები": "сливки",
    "კარაქი": "сливочное масло",
    "ყველი": "сыр",
    "სოსისი": "сосиски",
    "ძეხვი": "колбаса",
    "ქათამი": "курица",
    "თევზი": "рыба",
    "თინუსი": "тунец",
    "პური": "хлеб",
    "ლაფშა": "лапша",
    "პელმენი": "пельмени",
    "ხინკალი": "хинкали",
    "წიწიბურა": "гречка",
    "სიმინდი": "кукуруза",
    "ბარდა": "горошек",
    "ორცხობილა": "печенье",
    "ჩიფსი": "чипсы",
    "შოკოლადი": "шоколад",
    "კანფეტი": "конфеты",
    "ჩაი": "чай",
    "ყავა": "кофе",
    "ლუდი": "пиво",
    "ღვინო": "вино",
    "არაყი": "водка",
    "ვისკი": "виски",
    "ლიმონათი": "лимонад",
    "წვენი": "сок",
    "მაიონეზი": "майонез",
    "ზეთი": "масло",
    "პასტა": "паста",
    "სოუსი": "соус",
    "კარტოფილი": "картофель",
    "ხახვი": "лук",
    "ვაშლი": "яблоки",
    "ავოკადო": "авокадо",
    "მანგო": "манго",
    "პომელო": "помело",
    "შამპუნი": "шампунь",
    "საპონი": "мыло",
    "ხელსახოცი": "салфетки",
    "კგ": "кг",
    "ლ": "л",
    "მლ": "мл",
    "ც.": "шт.",
}

KA_TO_RU = {
    "ა": "а", "ბ": "б", "გ": "г", "დ": "д", "ე": "е", "ვ": "в", "ზ": "з", "თ": "т",
    "ი": "и", "კ": "к", "ლ": "л", "მ": "м", "ნ": "н", "ო": "о", "პ": "п", "ჟ": "ж",
    "რ": "р", "ს": "с", "ტ": "т", "უ": "у", "ფ": "ф", "ქ": "к", "ღ": "г", "ყ": "к",
    "შ": "ш", "ჩ": "ч", "ც": "ц", "ძ": "дз", "წ": "ц", "ჭ": "ч", "ხ": "х", "ჯ": "дж",
    "ჰ": "х",
}


def load_translations(path: Path) -> Dict[str, str]:
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
    except Exception:
        return {}
    return {}


def write_translation_template(path: Path, mapping: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class Translator:
    replacements: Dict[str, str]
    by_id: Dict[str, str]

    def reload(self, translations_path: Path) -> None:
        self.by_id = load_translations(translations_path)

    def title_for_id(self, item_id: Optional[str]) -> Optional[str]:
        if item_id and item_id in self.by_id:
            return self.clean(self.by_id[item_id])
        return None

    def clean(self, text: str) -> str:
        if not text:
            return ""

        s = text

        for k, v in self.replacements.items():
            s = s.replace(k, v)

        out = []
        for ch in s:
            out.append(KA_TO_RU.get(ch, ch))
        s = "".join(out)

        s = re.sub(r"\s+([,.;:!?])", r"\1", s)
        s = re.sub(r"\s*/\s*", "/", s)
        s = re.sub(r"\s{2,}", " ", s).strip()
        s = s.replace("« ", "«").replace(" »", "»")

        return s

    def to_ru(self, text: str, item_id: Optional[str] = None) -> str:
        from_dict = self.title_for_id(item_id)
        if from_dict:
            return from_dict

        if not text:
            return ""

        return self.clean(text)


def default_translator(translations_path: Path) -> Translator:
    return Translator(replacements=dict(DEFAULT_REPLACEMENTS), by_id=load_translations(translations_path))
