import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.nikora_api import Deal
from app.translation_store import track_untranslated
from app.translator import default_translator


def make_deal(deal_id: str, title: str) -> Deal:
    return Deal(
        id=deal_id,
        title=title,
        image="",
        thumb="",
        crop="",
        old_price="",
        new_price="",
        start_date="",
        end_date="",
    )


class UntranslatedTrackingTests(unittest.TestCase):
    def test_removes_translated_ids_from_untranslated_dump(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            translations_path = tmp / "translations.json"
            untranslated_path = tmp / "untranslated.json"

            translations_path.write_text(
                json.dumps({"1": "Переведено"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            untranslated_path.write_text(
                json.dumps(
                    {
                        "1": {"orig": "ერთი", "fallback": "erti", "first_seen": "2026-04-03T00:00:00Z"},
                        "2": {"orig": "ორი", "fallback": "ori", "first_seen": "2026-04-03T00:00:00Z"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            translator = default_translator(translations_path)
            new_count = track_untranslated(untranslated_path, translator, [make_deal("2", "ორი")])

            self.assertEqual(new_count, 0)
            saved = json.loads(untranslated_path.read_text(encoding="utf-8"))
            self.assertNotIn("1", saved)
            self.assertIn("2", saved)

    def test_adds_only_new_untranslated_ids(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            translations_path = tmp / "translations.json"
            untranslated_path = tmp / "untranslated.json"

            translations_path.write_text(
                json.dumps({"1": "Переведено"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            untranslated_path.write_text(
                json.dumps(
                    {
                        "2": {"orig": "ორი", "fallback": "ori", "first_seen": "2026-04-03T00:00:00Z"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            translator = default_translator(translations_path)
            new_count = track_untranslated(
                untranslated_path,
                translator,
                [
                    make_deal("1", "ერთი"),
                    make_deal("2", "ორი"),
                    make_deal("3", "სამი"),
                ],
            )

            self.assertEqual(new_count, 1)
            saved = json.loads(untranslated_path.read_text(encoding="utf-8"))
            self.assertNotIn("1", saved)
            self.assertIn("2", saved)
            self.assertIn("3", saved)
            self.assertEqual(saved["3"]["orig"], "სამი")

    def test_reuses_translation_for_same_title_with_new_id(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            translations_path = tmp / "translations.json"
            untranslated_path = tmp / "untranslated.json"

            translations_path.write_text(
                json.dumps({"old-id": "Готовый перевод"}, ensure_ascii=False),
                encoding="utf-8",
            )
            untranslated_path.write_text(
                json.dumps(
                    {"old-id": {"orig": "პროდუქტი 0.75 ლ", "fallback": "", "first_seen": "old"}},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            translator = default_translator(translations_path)
            new_count = track_untranslated(
                untranslated_path,
                translator,
                [make_deal("new-id", "პროდუქტი 0,75 ლ")],
            )

            self.assertEqual(new_count, 0)
            self.assertEqual(translator.to_ru("პროდუქტი 0,75 ლ", "new-id"), "Готовый перевод")
            self.assertEqual(json.loads(untranslated_path.read_text(encoding="utf-8")), {})
            self.assertTrue((tmp / "translation_memory.json").exists())

    def test_corrupt_untranslated_file_is_not_overwritten(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            translations_path = tmp / "translations.json"
            untranslated_path = tmp / "untranslated.json"
            translations_path.write_text("{}", encoding="utf-8")
            untranslated_path.write_text("{broken", encoding="utf-8")

            translator = default_translator(translations_path)
            with self.assertRaises(RuntimeError):
                track_untranslated(untranslated_path, translator, [make_deal("1", "ერთი")])

            self.assertEqual(untranslated_path.read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
    unittest.main()
