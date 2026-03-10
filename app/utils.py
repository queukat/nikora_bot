from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from dateutil import tz


_JSONP_RE = re.compile(r"^[a-zA-Z0-9_$]+\((.*)\)\s*;?\s*$", re.DOTALL)


def parse_jsonp(payload: str) -> Any:
    payload = payload.strip()
    m = _JSONP_RE.match(payload)
    if m:
        return json.loads(m.group(1))
    # fallback: maybe server returns plain JSON
    return json.loads(payload)


def to_iso_now() -> str:
    return datetime.now(tz=tz.UTC).isoformat()


def parse_ddmmyyyy(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    # expected: "19-02-2026"
    try:
        dt = datetime.strptime(s, "%d-%m-%Y")
        return dt.replace(tzinfo=tz.UTC)
    except Exception:
        return None


def stable_hash(obj: Dict[str, Any]) -> str:
    # stable hash for deal content to avoid repeat notifications
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
