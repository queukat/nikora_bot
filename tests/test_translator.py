import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.translator import default_translator, transliteration_similarity


class TranslatorTests(unittest.TestCase):
    def test_transliteration_quality_score_detects_raw_fallback(self) -> None:
        source = "„ჰეფი“ ვაფლის ჩხირი 150 გ"
        self.assertGreaterEqual(transliteration_similarity(source, "«хефи» вафлис чхири 150 г"), 0.99)
        self.assertLess(transliteration_similarity(source, "Hefi, вафельные палочки, 150 г"), 0.80)

    def test_reviewed_hefi_translation_overrides_old_transliteration(self) -> None:
        translator = default_translator(Path("data/translations.json"), Path("data/translation_memory.json"))
        self.assertEqual(
            translator.to_ru("„ჰეფი“ ვაფლის ჩხირი 150 გ", "16196"),
            "Hefi, вафельные палочки, 150 г",
        )

    def test_smart_fallback_for_europroduct_title(self) -> None:
        translator = default_translator(Path("missing-translations.json"))
        result = translator.to_ru("შვრიის ფანტელი 'სოლნიშკო' გარგრით 300გ")
        self.assertEqual(result, "овсяные хлопья «солнишко» с абрикосом 300 г")

    def test_glossary_terms_mix_with_latin_brand(self) -> None:
        translator = default_translator(Path("missing-translations.json"))
        result = translator.to_ru("კრეკერი Huober Brezel ორგანული ასორტი 'PARTY' კლასიკური 200 გ")
        self.assertEqual(result, "крекер Huober Brezel органический ассорти «PARTY» классический 200 г")

    def test_translation_memory_reuses_title_across_ids(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            translations = tmp / "translations.json"
            memory = tmp / "translation_memory.json"
            translations.write_text("{}", encoding="utf-8")
            memory.write_text(
                json.dumps({"„Марка“ პროდუქტი 0.75 ლ": "Перевод 0,75 л"}, ensure_ascii=False),
                encoding="utf-8",
            )

            translator = default_translator(translations, memory)

            self.assertTrue(translator.has_translation('«марка» პროდუქტი 0,75 ლ', "new-id"))
            self.assertEqual(translator.to_ru('«марка» პროდუქტი 0,75 ლ', "new-id"), "Перевод 0,75 л")

    def test_ambiguous_memory_is_not_reused(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            translations = tmp / "translations.json"
            memory = tmp / "translation_memory.json"
            translations.write_text("{}", encoding="utf-8")
            memory.write_text(
                json.dumps({"A/B": "Первый", "A B": "Второй"}, ensure_ascii=False),
                encoding="utf-8",
            )

            translator = default_translator(translations, memory)

            self.assertFalse(translator.has_translation("A-B", "new-id"))
            self.assertNotIn(translator.to_ru("A-B", "new-id"), {"Первый", "Второй"})

    def test_preferred_observation_replaces_older_memory(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            translations = tmp / "translations.json"
            memory = tmp / "translation_memory.json"
            translations.write_text(
                json.dumps({"new-id": "Нормальный русский"}, ensure_ascii=False),
                encoding="utf-8",
            )
            memory.write_text(
                json.dumps({"პროდუქტი 0.75 ლ": "Старый вариант"}, ensure_ascii=False),
                encoding="utf-8",
            )
            translator = default_translator(translations, memory)

            imported = translator.import_translated_items(
                {"new-id": {"orig": "პროდუქტი 0,75 ლ"}},
                prefer_observations=True,
            )

            self.assertEqual(imported, 1)
            self.assertEqual(translator.to_ru("პროდუქტი 0.75 ლ", "another-id"), "Нормальный русский")


if __name__ == "__main__":
    unittest.main()
