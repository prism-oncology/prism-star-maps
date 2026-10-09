#!/usr/bin/env python3
"""Render data/summary.json + data/stats/*.json into a static site in site/.

  site/index.html          overview: org-wide map + one card per repo
  site/<repo>.html         one map page per repository
  site/data/*.json         the aggregated stats (handy for other tools)
  site/assets/             style.css + map.js, copied from this folder
"""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

LEAFLET = "https://unpkg.com/leaflet@1.9.4/dist"
ASSETS = ("style.css", "map.js")  # copied from this folder into site/assets/


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else "–"


def page(title: str, crumb: str, heading: str, sub: str, body: str, places, org: str, generated: str) -> str:
    map_block = ""
    if places is not None:
        data = json.dumps(places, ensure_ascii=False).replace("</", "<\\/")
        map_block = (
            f'<script id="places" type="application/json">{data}</script>'
            f'<script src="{LEAFLET}/leaflet.js"></script>'
            '<script src="assets/map.js"></script>'
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="{LEAFLET}/leaflet.css">
<link rel="stylesheet" href="assets/style.css"></head>
<body>
<header><div class="crumb">{crumb}</div><h1>{heading}</h1><p class="sub">{sub}</p></header>
<main>{body}</main>
<footer>Updated {esc(generated[:16].replace('T', ' '))} UTC · Locations are self-reported on GitHub profiles,
geocoded with <a href="https://nominatim.openstreetmap.org/">OpenStreetMap Nominatim</a> ·
<a href="https://github.com/{esc(org)}/prism-star-maps">source</a></footer>
{map_block}
</body></html>
"""


def kpis(stats: dict, star_count=None) -> str:
    stargazers = stats.get("stargazers")
    located = stats.get("located")
    pct = f"{round(100 * located / stargazers)}%" if stargazers and located is not None else "–"
    items = []
    if star_count is not None:
        items.append((fmt(star_count), "stars"))
    items += [
        (fmt(stargazers), "stargazers read" if star_count is not None else "unique stargazers"),
        (fmt(located), "on the map"),
        (pct, "located"),
        (fmt(len(stats.get("countries") or [])), "countries"),
    ]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><b>{v}</b><span>{k}</span></div>' for v, k in items
    ) + "</div>"


def ranking_table(rows: list[dict], label_key: str, limit: int = 15) -> str:
    if not rows:
        return '<p class="sub">No located stargazers yet.</p>'
    top = rows[:limit]
    peak = max(r["count"] for r in top)
    trs = "".join(
        f'<tr><td>{esc(r[label_key])}</td><td class="n">{r["count"]}</td>'
        f'<td class="bar"><i style="width:{max(4, 100 * r["count"] / peak):.0f}%"></i></td></tr>'
        for r in top
    )
    return f"<table>{trs}</table>"


def detail_body(stats: dict, star_count=None) -> str:
    warn = ""
    if stats.get("error"):
        warn = f'<p class="warn">⚠ {esc(stats["error"])}'
        if stats.get("stale_since"):
            warn += f" Showing data from {esc(stats['stale_since'][:10])}."
        warn += "</p>"
    return (
        warn
        + kpis(stats, star_count)
        + '<div id="map"></div>'
        + '<div class="cols">'
        + f'<section><h2>Top countries</h2>{ranking_table(stats.get("countries") or [], "name")}</section>'
        + f'<section><h2>Top places</h2>{ranking_table(stats.get("places") or [], "label")}</section>'
        + "</div>"
    )


def main() -> None:
    summary = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
    org, generated = summary["org"], summary["generated_at"]

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "data").mkdir(parents=True)
    (SITE / "assets").mkdir()
    for name in ASSETS:
        shutil.copy(HERE / name, SITE / "assets" / name)
    for f in (DATA / "stats").glob("*.json"):
        shutil.copy(f, SITE / "data" / f.name)
    shutil.copy(DATA / "summary.json", SITE / "data" / "summary.json")

    # Per-repo pages
    for r in summary["repos"]:
        stats_file = DATA / "stats" / f"{r['repo']}.json"
        stats = json.loads(stats_file.read_text(encoding="utf-8"))
        crumb = f'<a href="index.html">{esc(org)}</a> / {esc(r["repo"])}'
        heading = f'<a href="{esc(r["url"])}" style="color:inherit">{esc(r["repo"])}</a>'
        if r.get("archived"):
            heading += '<span class="badge">archived</span>'
        (SITE / f"{r['repo']}.html").write_text(
            page(
                f"{r['repo']} stargazers",
                crumb,
                heading,
                esc(r.get("description") or "Where this repository's stargazers are."),
                detail_body(stats, r.get("star_count")),
                stats.get("places") or [],
                org,
                generated,
            ),
            encoding="utf-8",
        )

    # Index page
    overall = json.loads((DATA / "stats" / "_all.json").read_text(encoding="utf-8"))
    cards = []
    for r in sorted(summary["repos"], key=lambda r: -(r.get("star_count") or 0)):
        meta = f"★ {fmt(r.get('star_count'))}"
        if r.get("located") is not None:
            meta += f" · {fmt(r['located'])} mapped · {fmt(r.get('countries'))} countries"
        lang = f'<span class="badge">{esc(r["language"])}</span>' if r.get("language") else ""
        err = '<div class="warn">⚠ data unavailable</div>' if r.get("error") else ""
        cards.append(
            f'<a class="card" href="{esc(r["repo"])}.html"><h3>{esc(r["repo"])}{lang}</h3>'
            f'<p>{esc(r.get("description") or "")}</p><div class="meta">{meta}</div>{err}</a>'
        )
    body = (
        kpis(overall)
        + '<div id="map"></div>'
        + '<div class="cols">'
        + f'<section><h2>Top countries</h2>{ranking_table(overall.get("countries") or [], "name")}</section>'
        + f'<section><h2>Top places</h2>{ranking_table(overall.get("places") or [], "label")}</section>'
        + "</div>"
        + '<h2 style="margin-top:32px">Repositories</h2>'
        + f'<div class="grid">{"".join(cards)}</div>'
    )
    (SITE / "index.html").write_text(
        page(
            f"{org} star maps",
            f'<a href="https://github.com/{esc(org)}">github.com/{esc(org)}</a>',
            f"Where {esc(org)} stargazers are",
            f"One map per repository, rebuilt weekly from public GitHub profile locations.",
            body,
            overall.get("places") or [],
            org,
            generated,
        ),
        encoding="utf-8",
    )
    (SITE / ".nojekyll").write_text("")
    print(f"Built {len(summary['repos']) + 1} pages in {SITE}")


if __name__ == "__main__":
    main()
