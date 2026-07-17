from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.translator import Translator, load_translation_memory, load_translations


def load_observations(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build reusable source-title translation memory from legacy ID translations.",
    )
    parser.add_argument("--translations", type=Path, required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--prefer-observations",
        action="store_true",
        help="Let the supplied observation translations replace older memory for the same normalized title.",
    )
    args = parser.parse_args()

    translations = load_translations(args.translations)
    observations = load_observations(args.observations)
    translator = Translator(
        replacements={},
        by_id=translations,
        fallback_glossary={},
        memory=load_translation_memory(args.output),
        memory_path=args.output,
    )

    imported = translator.import_translated_items(
        observations,
        prefer_observations=args.prefer_observations,
    )
    translator.save_memory()
    joined = sum(1 for item_id in observations if item_id in translations)
    print(
        f"translations={len(translations)} observations={len(observations)} "
        f"joined={joined} imported={imported} memory={len(translator.memory)} "
        f"ambiguous={len(translator.ambiguous_text_keys)}"
    )


if __name__ == "__main__":
    main()
