from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx

from .utils import parse_jsonp

log = logging.getLogger("nikora_bot.deals")


@dataclass(frozen=True)
class Deal:
    id: str
    title: str
    image: str
    thumb: str
    crop: str
    old_price: str
    new_price: str
    start_date: str
    end_date: str
    source: str = "nikora"
    source_label: str = "Nikora"
    raw_id: str = ""
    product_url: str = ""

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Deal":
        deal_id = str(d.get("id", "")).strip()
        return Deal(
            id=deal_id,
            title=str(d.get("title", "")).strip(),
            image=str(d.get("image", "")).strip(),
            thumb=str(d.get("thumb", "")).strip(),
            crop=str(d.get("crop", "")).strip(),
            old_price=str(d.get("old_price", "")).strip(),
            new_price=str(d.get("new_price", "")).strip(),
            start_date=str(d.get("start_date", "")).strip(),
            end_date=str(d.get("end_date", "")).strip(),
            source="nikora",
            source_label="Nikora",
            raw_id=deal_id,
        )


class NikoraApi:
    def __init__(self, api_url: str, base_url: str, timeout_s: float, user_agent: str) -> None:
        self._api_url = api_url
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            timeout=timeout_s,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_deals(self) -> List[Deal]:
        r = await self._client.get(self._api_url)
        r.raise_for_status()
        data = parse_jsonp(r.text)

        if not isinstance(data, list):
            raise ValueError(f"Unexpected API format: expected list, got {type(data)}")

        deals: List[Deal] = []
        for item in data:
            if isinstance(item, dict):
                deal = Deal.from_dict(item)
                if deal.id:
                    deals.append(deal)
        return deals

    def abs_url(self, maybe_relative: str) -> str:
        s = (maybe_relative or "").strip()
        if not s:
            return ""
        # If already absolute
        if s.startswith("http://") or s.startswith("https://"):
            return s
        return urljoin(self._base_url, s.lstrip("/"))

    def best_photo_urls(self, deal: Deal) -> List[str]:
        """
        ВАЖНО: full-size = deal.image (обычно 500x500).
        crop/thumb могут быть 120x120 — используем только как fallback.
        """
        candidates = []
        for v in [deal.image, deal.crop, deal.thumb]:
            u = self.abs_url(v)
            if u and u not in candidates:
                candidates.append(u)
        return candidates

    async def probe_url(self, url: str) -> Dict[str, str]:
        """
        Проверка доступности картинки/ресурса.
        Некоторые сервера не любят HEAD — поэтому делаем GET с Range.
        """
        if not url:
            return {"ok": "false", "error": "empty url"}

        try:
            # пробуем HEAD
            head = await self._client.head(url)
            if 200 <= head.status_code < 400:
                return {
                    "ok": "true",
                    "status": str(head.status_code),
                    "content_type": head.headers.get("content-type", ""),
                    "content_length": head.headers.get("content-length", ""),
                    "final_url": str(head.url),
                    "method": "HEAD",
                }
        except Exception:
            pass

        try:
            # fallback: GET range
            get = await self._client.get(url, headers={"Range": "bytes=0-1023"})
            return {
                "ok": "true" if 200 <= get.status_code < 400 else "false",
                "status": str(get.status_code),
                "content_type": get.headers.get("content-type", ""),
                "content_length": get.headers.get("content-length", ""),
                "final_url": str(get.url),
                "method": "GET(Range)",
            }
        except Exception as e:
            return {"ok": "false", "error": repr(e)}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


class _EuroproductPromoParser(HTMLParser):
    _PRODUCT_ID_RE = re.compile(r"/products/product/([A-Za-z0-9]+)")
    _PAGINATION_RE = re.compile(r"/products/page-(\d+)\?Promo=1")

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self.page_count = 1
        self.deals: List[Deal] = []

        self._card: Dict[str, str] | None = None
        self._card_div_depth = 0
        self._capture_title = False
        self._capture_new_price = False
        self._capture_old_price = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        href = attr_map.get("href", "").strip()
        self._update_page_count(href)

        classes = set((attr_map.get("class", "") or "").split())
        if tag == "div" and self._card is None and {"product-grid-item", "js-product-item"} <= classes:
            self._card = {
                "raw_id": "",
                "title": "",
                "image": "",
                "new_price": "",
                "old_price": "",
                "product_url": "",
                "fallback_title": "",
            }
            self._card_div_depth = 1
            self._capture_title = False
            self._capture_new_price = False
            self._capture_old_price = False
            return

        if self._card is None:
            return

        if tag == "div":
            self._card_div_depth += 1

        if tag == "a":
            data_id = attr_map.get("data-id", "").strip()
            if data_id and not self._card["raw_id"]:
                self._card["raw_id"] = data_id

            if href and "/products/product/" in href:
                product_url = urljoin(self._base_url, href)
                if not self._card["product_url"]:
                    self._card["product_url"] = product_url
                if not self._card["raw_id"]:
                    match = self._PRODUCT_ID_RE.search(product_url)
                    if match:
                        self._card["raw_id"] = match.group(1)

        if tag == "img":
            src = attr_map.get("src", "").strip()
            alt = _clean_text(attr_map.get("alt", ""))
            if src and "tag.svg" not in src.lower() and not self._card["image"]:
                self._card["image"] = urljoin(self._base_url, src)
            if alt and alt.lower() != "tag icon" and not self._card["fallback_title"]:
                self._card["fallback_title"] = alt

        if tag == "h2" and "product-name" in classes:
            self._capture_title = True
        elif tag == "span" and "new" in classes:
            self._capture_new_price = True
        elif tag == "span" and "old" in classes:
            self._capture_old_price = True

    def handle_data(self, data: str) -> None:
        if self._card is None:
            return
        if self._capture_title:
            self._card["title"] += data
        if self._capture_new_price:
            self._card["new_price"] += data
        if self._capture_old_price:
            self._card["old_price"] += data

    def handle_endtag(self, tag: str) -> None:
        if self._card is None:
            return

        if tag == "h2":
            self._capture_title = False
        elif tag == "span":
            self._capture_new_price = False
            self._capture_old_price = False
        elif tag == "div":
            self._card_div_depth -= 1
            if self._card_div_depth == 0:
                self._finish_card()

    def _finish_card(self) -> None:
        assert self._card is not None
        raw_id = _clean_text(self._card["raw_id"])
        title = _clean_text(self._card["title"]) or _clean_text(self._card["fallback_title"])
        image = _clean_text(self._card["image"])
        new_price = _clean_text(self._card["new_price"])
        old_price = _clean_text(self._card["old_price"])
        product_url = _clean_text(self._card["product_url"])

        if raw_id and new_price:
            self.deals.append(
                Deal(
                    id=f"europroduct:{raw_id}",
                    title=title,
                    image=image,
                    thumb="",
                    crop="",
                    old_price=old_price,
                    new_price=new_price,
                    start_date="",
                    end_date="",
                    source="europroduct",
                    source_label="Europroduct",
                    raw_id=raw_id,
                    product_url=product_url,
                )
            )

        self._card = None
        self._card_div_depth = 0
        self._capture_title = False
        self._capture_new_price = False
        self._capture_old_price = False

    def _update_page_count(self, href: str) -> None:
        if not href:
            return
        match = self._PAGINATION_RE.search(href)
        if match:
            self.page_count = max(self.page_count, int(match.group(1)))


class EuroproductApi:
    MAX_PAGES = 100

    def __init__(
        self,
        promo_url: str,
        base_url: str,
        timeout_s: float,
        user_agent: str,
        page_concurrency: int = 4,
    ) -> None:
        self._promo_url = promo_url
        self._base_url = base_url
        self._prefer_english = "/en/" in promo_url
        self._page_concurrency = max(1, min(int(page_concurrency), 10))
        self._client = httpx.AsyncClient(
            timeout=timeout_s,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=self._page_concurrency + 2,
                max_keepalive_connections=self._page_concurrency,
            ),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_deals(self) -> List[Deal]:
        try:
            primary = await self._fetch_locale(english=self._prefer_english)
            if primary:
                return primary
            raise ValueError("preferred locale returned no promo products")
        except Exception as primary_error:
            log.warning("Europroduct preferred locale failed, trying fallback: %r", primary_error)
            fallback = await self._fetch_locale(english=not self._prefer_english)
            if not fallback:
                raise ValueError("fallback locale returned no promo products") from primary_error
            return fallback

    async def _fetch_locale(self, english: bool) -> List[Deal]:
        first_html = await self._fetch_html(self._first_page_url(english=english))
        first_deals, page_count = self.parse_promo_page(first_html, self._base_url)
        total_pages = min(max(page_count, 1), self.MAX_PAGES)
        if page_count > self.MAX_PAGES:
            log.warning("Europroduct page count capped: reported=%s cap=%s", page_count, self.MAX_PAGES)

        deals_by_id = {deal.id: deal for deal in first_deals if deal.id}
        page_numbers = list(range(2, total_pages + 1))
        for start in range(0, len(page_numbers), self._page_concurrency):
            batch_numbers = page_numbers[start:start + self._page_concurrency]
            results = await asyncio.gather(
                *(self._fetch_html(self._promo_page_url(page_no, english=english)) for page_no in batch_numbers),
                return_exceptions=True,
            )
            for page_no, result in zip(batch_numbers, results):
                if isinstance(result, BaseException):
                    log.warning("Europroduct promo page %s failed: %r", page_no, result)
                    continue
                page_deals, _ = self.parse_promo_page(result, self._base_url)
                for deal in page_deals:
                    if deal.id:
                        deals_by_id.setdefault(deal.id, deal)
        return list(deals_by_id.values())

    async def _fetch_html(self, url: str) -> str:
        response = await self._client.get(url)
        response.raise_for_status()
        return response.text

    def _first_page_url(self, english: bool) -> str:
        prefix = "en/" if english else ""
        return urljoin(self._base_url, f"{prefix}products?Promo=1")

    def _promo_page_url(self, page_no: int, english: bool) -> str:
        prefix = "en/" if english else ""
        return urljoin(self._base_url, f"{prefix}products/page-{page_no}?Promo=1")

    @staticmethod
    def parse_promo_page(html: str, base_url: str) -> tuple[List[Deal], int]:
        parser = _EuroproductPromoParser(base_url)
        parser.feed(html)
        parser.close()
        return parser.deals, parser.page_count

    @staticmethod
    def _merge_locales(primary: List[Deal], fallback: List[Deal]) -> List[Deal]:
        fallback_by_raw = {deal.raw_id: deal for deal in fallback if deal.raw_id}
        merged: List[Deal] = []
        seen_raw_ids = set()

        for deal in primary:
            fallback_deal = fallback_by_raw.get(deal.raw_id)
            merged_deal = deal
            if fallback_deal is not None:
                merged_deal = replace(
                    deal,
                    title=deal.title or fallback_deal.title,
                    image=deal.image or fallback_deal.image,
                    old_price=deal.old_price or fallback_deal.old_price,
                    new_price=deal.new_price or fallback_deal.new_price,
                    product_url=deal.product_url or fallback_deal.product_url,
                )
            if merged_deal.title:
                merged.append(merged_deal)
                seen_raw_ids.add(merged_deal.raw_id)

        for deal in fallback:
            if not deal.raw_id or deal.raw_id in seen_raw_ids:
                continue
            if deal.title:
                merged.append(deal)
                seen_raw_ids.add(deal.raw_id)

        return merged


class DealsApi:
    def __init__(self, nikora: NikoraApi, europroduct: EuroproductApi | None = None) -> None:
        self._nikora = nikora
        self._europroduct = europroduct
        self._last_failed_sources: set[str] = set()

    async def close(self) -> None:
        await self._nikora.close()
        if self._europroduct is not None:
            await self._europroduct.close()

    async def fetch_deals(self) -> List[Deal]:
        deals: List[Deal] = []
        errors: List[Exception] = []
        self._last_failed_sources = set()

        try:
            deals.extend(await self._nikora.fetch_deals())
        except Exception as exc:
            log.warning("Nikora fetch failed: %r", exc)
            errors.append(exc)
            self._last_failed_sources.add("nikora")

        if self._europroduct is not None:
            try:
                deals.extend(await self._europroduct.fetch_deals())
            except Exception as exc:
                log.warning("Europroduct fetch failed: %r", exc)
                errors.append(exc)
                self._last_failed_sources.add("europroduct")

        if deals:
            return deals
        if errors:
            raise errors[0]
        return deals

    def best_photo_urls(self, deal: Deal) -> List[str]:
        if deal.source == "nikora":
            return self._nikora.best_photo_urls(deal)

        candidates: List[str] = []
        for value in [deal.image, deal.crop, deal.thumb]:
            item = (value or "").strip()
            if item and item not in candidates:
                candidates.append(item)
        return candidates

    async def probe_url(self, url: str) -> Dict[str, str]:
        return await self._nikora.probe_url(url)

    def failed_sources(self) -> set[str]:
        return set(self._last_failed_sources)
