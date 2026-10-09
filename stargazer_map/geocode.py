"""Geocoding with OpenStreetMap Nominatim (1 request/second, cached on disk)."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def normalise_location(raw: str | None) -> str | None:
    if not raw:
        return None
    text = re.sub(r"[\U00010000-\U0010FFFF]", " ", raw)  # strip emoji
    text = re.sub(r"\s+", " ", text).strip(" ,.;|-/")
    if len(text) < 2:
        return None
    return text.lower()


def load_cache(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict, path: Path) -> None:
    path.write_text(
        json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


_last_call = 0.0


def nominatim(query: str, user_agent: str) -> dict | None:
    global _last_call
    wait = 1.1 - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
            "accept-language": "en",
        }
    )
    req = urllib.request.Request(f"{NOMINATIM_URL}?{params}", headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            results = json.load(resp)
    finally:
        _last_call = time.monotonic()
    if not results:
        return None
    hit = results[0]
    addr = hit.get("address", {})
    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or addr.get("county")
        or addr.get("state")
    )
    country = addr.get("country")
    label = ", ".join(p for p in (city, country) if p) or hit.get("display_name", query)
    return {
        "lat": round(float(hit["lat"]), 3),
        "lon": round(float(hit["lon"]), 3),
        "label": label,
        "country": country,
        "country_code": (addr.get("country_code") or "").upper() or None,
    }


def geocode_all(
    locations: set[str], cache: dict, cache_path: Path, max_new: int, user_agent: str
) -> None:
    """Geocode locations missing from the cache. A None entry means "nothing found"."""
    todo = sorted(loc for loc in locations if loc not in cache)
    if len(todo) > max_new:
        print(f"Geocoding {max_new} of {len(todo)} new locations (rest next run)")
        todo = todo[:max_new]
    else:
        print(f"Geocoding {len(todo)} new locations")
    for i, loc in enumerate(todo, 1):
        try:
            cache[loc] = nominatim(loc, user_agent)
        except Exception as exc:  # network hiccup: retry on the next run
            print(f"  geocode failed for {loc!r}: {exc}", file=sys.stderr)
            continue
        if i % 50 == 0:
            save_cache(cache, cache_path)
            print(f"  {i}/{len(todo)}")
    save_cache(cache, cache_path)
