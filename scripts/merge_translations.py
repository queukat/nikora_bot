from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


GEORGIAN_RE = re.compile(r"[ა-ჰ]")


def load_mapping(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")

    result: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        translation = str(raw_value).strip()
        if not key or not translation:
            raise ValueError(f"Empty translation key/value in {path}: {raw_key!r}")
        if GEORGIAN_RE.search(translation):
            raise ValueError(f"Georgian text remains in Russian translation {key!r} from {path}")
        result[key] = translation
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and merge ID translation overlays atomically.")
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    merged = load_mapping(args.base)
    base_count = len(merged)
    added = 0
    changed = 0
    for overlay_path in args.overlay:
        overlay = load_mapping(overlay_path)
        for item_id, translation in overlay.items():
            previous = merged.get(item_id)
            if previous is None:
                added += 1
            elif previous != translation:
                if not args.allow_overwrite:
                    raise ValueError(
                        f"Overlay {overlay_path} changes existing ID {item_id}; use --allow-overwrite after review"
                    )
                changed += 1
            merged[item_id] = translation

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = args.output.with_name(f".{args.output.name}.tmp")
    temp_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(args.output)
    print(f"base={base_count} added={added} changed={changed} output={len(merged)}")


if __name__ == "__main__":
    main()
