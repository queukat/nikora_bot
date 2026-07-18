from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.translator import load_translation_memory, transliteration_similarity


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find Russian product names that are suspiciously close to raw Georgian transliteration."
    )
    parser.add_argument("--memory", type=Path, default=Path("data/translation_memory.json"))
    parser.add_argument("--min-score", type=float, default=0.90)
    parser.add_argument("--limit", type=int, default=0, help="0 prints every candidate")
    args = parser.parse_args()

    if not 0.0 <= args.min_score <= 1.0:
        parser.error("--min-score must be between 0 and 1")
    if args.limit < 0:
        parser.error("--limit cannot be negative")

    candidates = []
    for source, translation in load_translation_memory(args.memory).items():
        score = transliteration_similarity(source, translation)
        if score >= args.min_score:
            candidates.append(
                {
                    "score": round(score, 4),
                    "source": source,
                    "translation": translation,
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["source"]))
    if args.limit:
        candidates = candidates[: args.limit]

    print(json.dumps(candidates, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
