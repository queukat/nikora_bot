from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx

from .utils import parse_jsonp


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

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Deal":
        return Deal(
            id=str(d.get("id", "")).strip(),
            title=str(d.get("title", "")).strip(),
            image=str(d.get("image", "")).strip(),
            thumb=str(d.get("thumb", "")).strip(),
            crop=str(d.get("crop", "")).strip(),
            old_price=str(d.get("old_price", "")).strip(),
            new_price=str(d.get("new_price", "")).strip(),
            start_date=str(d.get("start_date", "")).strip(),
            end_date=str(d.get("end_date", "")).strip(),
        )


class NikoraApi:
    def __init__(self, api_url: str, base_url: str, timeout_s: float, user_agent: str) -> None:
        self._api_url = api_url
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            timeout=timeout_s,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
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
