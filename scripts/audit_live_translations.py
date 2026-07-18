from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.nikora_api import DealsApi, EuroproductApi, NikoraApi
from app.translator import default_translator, transliteration_similarity


async def run(args: argparse.Namespace) -> None:
    translator = default_translator(args.translations, args.memory)
    api = DealsApi(
        nikora=NikoraApi(args.nikora_api_url, args.nikora_base_url, args.timeout, args.user_agent),
        europroduct=EuroproductApi(
            args.europroduct_url,
            args.europroduct_base_url,
            args.timeout,
            args.user_agent,
            page_concurrency=args.page_concurrency,
        ),
    )
    try:
        deals = await api.fetch_deals()
    finally:
        await api.close()

    candidates = []
    for deal in deals:
        translation = translator.to_ru(deal.title, deal.id)
        score = transliteration_similarity(deal.title, translation)
        if score >= args.min_score:
            candidates.append(
                {
                    "id": deal.id,
                    "source": deal.source,
                    "score": round(score, 4),
                    "title": deal.title,
                    "translation": translation,
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["id"]))
    print(
        json.dumps(
            {
                "total_deals": len(deals),
                "failed_sources": sorted(api.failed_sources()),
                "candidates": candidates,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit currently available deals for raw Georgian transliteration.")
    parser.add_argument("--translations", type=Path, default=Path("data/translations.json"))
    parser.add_argument("--memory", type=Path, default=Path("data/translation_memory.json"))
    parser.add_argument("--min-score", type=float, default=0.90)
    parser.add_argument("--nikora-api-url", default="https://nikora.above.ge/json/sales.php?callback=JSON_CALLBACK")
    parser.add_argument("--nikora-base-url", default="https://nikora.above.ge/")
    parser.add_argument("--europroduct-url", default="https://europroduct.ge/en/products?Promo=1")
    parser.add_argument("--europroduct-base-url", default="https://europroduct.ge/")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--page-concurrency", type=int, default=4)
    parser.add_argument("--user-agent", default="nikora-bot-translation-audit/1.0")
    args = parser.parse_args()
    if not 0.0 <= args.min_score <= 1.0:
        parser.error("--min-score must be between 0 and 1")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
