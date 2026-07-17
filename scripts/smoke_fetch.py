from __future__ import annotations

import argparse
import asyncio
import json
import time

from app.nikora_api import DealsApi, EuroproductApi, NikoraApi


async def run(args: argparse.Namespace) -> None:
    nikora = NikoraApi(args.nikora_api_url, args.nikora_base_url, args.timeout, args.user_agent)
    europroduct = EuroproductApi(
        args.europroduct_url,
        args.europroduct_base_url,
        args.timeout,
        args.user_agent,
        page_concurrency=args.page_concurrency,
    )
    api = DealsApi(nikora=nikora, europroduct=europroduct)
    started = time.monotonic()
    try:
        deals = await api.fetch_deals()
    finally:
        await api.close()

    by_source: dict[str, int] = {}
    for deal in deals:
        by_source[deal.source] = by_source.get(deal.source, 0) + 1
    print(
        json.dumps(
            {
                "total": len(deals),
                "by_source": by_source,
                "failed_sources": sorted(api.failed_sources()),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and parse both deal sources without starting Telegram.")
    parser.add_argument(
        "--nikora-api-url",
        default="https://nikora.above.ge/json/sales.php?callback=JSON_CALLBACK",
    )
    parser.add_argument("--nikora-base-url", default="https://nikora.above.ge/")
    parser.add_argument("--europroduct-url", default="https://europroduct.ge/en/products?Promo=1")
    parser.add_argument("--europroduct-base-url", default="https://europroduct.ge/")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--page-concurrency", type=int, default=4)
    parser.add_argument("--user-agent", default="nikora-bot-smoke-test/1.0")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
