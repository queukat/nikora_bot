from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_mapping(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return {str(key): str(value).strip() for key, value in data.items() if str(key).strip() and str(value).strip()}


def write_json_atomic(path: Path, data: dict[str, str]) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply reviewed source-title corrections to translation memory and matching ID translations."
    )
    parser.add_argument("--translations", type=Path, default=Path("data/translations.json"))
    parser.add_argument("--memory", type=Path, default=Path("data/translation_memory.json"))
    parser.add_argument("--corrections", type=Path, required=True, help="JSON mapping source title to reviewed Russian text")
    args = parser.parse_args()

    translations = load_mapping(args.translations)
    memory = load_mapping(args.memory)
    corrections = load_mapping(args.corrections)

    missing = sorted(source for source in corrections if source not in memory)
    if missing:
        raise ValueError(f"Correction sources missing from translation memory: {missing!r}")

    previous_to_new: dict[str, str] = {}
    for source, reviewed in corrections.items():
        previous = memory[source]
        conflicting = previous_to_new.get(previous)
        if conflicting is not None and conflicting != reviewed:
            raise ValueError(f"One old translation has conflicting replacements: {previous!r}")
        previous_to_new[previous] = reviewed

    updated_ids = 0
    for item_id, previous in list(translations.items()):
        reviewed = previous_to_new.get(previous)
        if reviewed is not None and reviewed != previous:
            translations[item_id] = reviewed
            updated_ids += 1

    for source, reviewed in corrections.items():
        memory[source] = reviewed

    write_json_atomic(args.translations, translations)
    write_json_atomic(args.memory, memory)
    print(f"reviewed_sources={len(corrections)} updated_ids={updated_ids}")


if __name__ == "__main__":
    main()
