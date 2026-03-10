# save as: make_products_map.py
#
# Default run (no args):
#   python make_products_map.py
# reads:  sales.jsonp
# writes: products.json
#
# Optional override:
#   python make_products_map.py <sales.jsonp|url> <out.json>

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path


DEFAULT_IN = "sales.jsonp"
DEFAULT_OUT = "products.json"


def read_text(src: str) -> str:
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    return Path(src).read_text(encoding="utf-8")


def extract_jsonp_payload(text: str) -> str:
    """
    Accepts:
      JSON_CALLBACK([...])
    or plain JSON:
      [...]
    Returns the JSON array string.
    """
    t = text.strip()

    # JSONP wrapper: Something(...)
    m = re.match(r"^\s*[A-Za-z_]\w*\((.*)\)\s*;?\s*$", t, flags=re.S)
    if m:
        return m.group(1).strip()

    return t


def build_products_map(items: object) -> dict[str, str]:
    if not isinstance(items, list):
        raise ValueError("Expected JSON array (list)")

    out: dict[str, str] = {}
    for x in items:
        if not isinstance(x, dict):
            continue
        _id = x.get("id")
        title = x.get("title")
        if _id is None or title is None:
            continue
        out[str(_id)] = str(title)
    return out


def main(argv: list[str]) -> int:
    # Built-in launch variant:
    #   python make_products_map.py sales.jsonp products.json
    # But also allow running with no args at all.

    if len(argv) == 1:
        src, out_path = DEFAULT_IN, DEFAULT_OUT
    elif len(argv) == 3:
        src, out_path = argv[1], argv[2]
    else:
        print(
            "Usage:\n"
            "  python make_products_map.py\n"
            "  python make_products_map.py <sales.jsonp|url> <out.json>\n\n"
            f"Defaults:\n  in:  {DEFAULT_IN}\n  out: {DEFAULT_OUT}",
            file=sys.stderr,
        )
        return 2

    try:
        raw = read_text(src)
    except FileNotFoundError:
        print(f"Input file not found: {src}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Failed to read '{src}': {e}", file=sys.stderr)
        return 1

    payload = extract_jsonp_payload(raw)

    try:
        items = json.loads(payload)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON/JSONP: {e}", file=sys.stderr)
        return 1

    try:
        products = build_products_map(items)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    Path(out_path).write_text(
        json.dumps(products, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"OK: wrote {len(products)} items -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
