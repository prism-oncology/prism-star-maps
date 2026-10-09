"""Regenerate stargazer_map/assets/countries.geojson from Natural Earth (public domain).

Uses the 110m shapes, plus the countries only the 50m set has (Singapore, Bahrain, ...),
keyed by ISO 3166-1 alpha-2 code (the `country_code` Nominatim returns), with
coordinates rounded to 0.01° to keep the file small.

    python tools/make_countries_geojson.py
"""

import json
import urllib.request
from pathlib import Path

URL = (
    "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2"
    "/geojson/ne_{}_admin_0_countries.geojson"
)
OUT = Path(__file__).resolve().parent.parent / "stargazer_map" / "assets" / "countries.geojson"


def load(resolution: str) -> list[dict]:
    with urllib.request.urlopen(URL.format(resolution), timeout=60) as resp:
        return json.load(resp)["features"]


def rounded(coords):
    if isinstance(coords[0], list):
        return [rounded(c) for c in coords]
    return [round(coords[0], 2), round(coords[1], 2)]


def main() -> None:
    features: dict[str, dict] = {}
    for resolution in ("110m", "50m"):
        for f in load(resolution):
            code = f["properties"]["ISO_A2_EH"]
            if code in features or not code or code == "-99":
                continue
            features[code] = {
                "type": "Feature",
                "id": code,
                "properties": {"name": f["properties"]["NAME"]},
                "geometry": {
                    "type": f["geometry"]["type"],
                    "coordinates": rounded(f["geometry"]["coordinates"]),
                },
            }
    collection = {
        "type": "FeatureCollection",
        "features": sorted(features.values(), key=lambda f: f["id"]),
    }
    OUT.write_text(json.dumps(collection, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(features)} countries, {OUT.stat().st_size // 1024} KB -> {OUT}")


if __name__ == "__main__":
    main()
