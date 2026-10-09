"""Render <data_dir>/summary.json + stats/*.json into a static site:

index.html          overview: org-wide map + one card per repo
<repo>.html         one map page per repository
data/*.json         the aggregated stats (handy for other tools)
assets/             style.css + map.js, copied from stargazer_map/assets/
"""

from __future__ import annotations

import html
import json
import shutil
from importlib import resources
from pathlib import Path

LEAFLET = "https://unpkg.com/leaflet@1.9.4/dist"
ASSETS = ("style.css", "map.js")


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else "–"


def page(
    title: str,
    crumb: str,
    heading: str,
    sub: str,
    body: str,
    places,
    repository: str,
    generated: str,
) -> str:
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
<footer>Updated {esc(generated[:16].replace("T", " "))} UTC ·
Locations are self-reported on GitHub profiles, geocoded with
<a href="https://nominatim.openstreetmap.org/">OpenStreetMap Nominatim</a> ·
<a href="https://github.com/{esc(repository)}">source</a></footer>
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
    return (
        '<div class="kpis">'
        + "".join(f'<div class="kpi"><b>{v}</b><span>{k}</span></div>' for v, k in items)
        + "</div>"
    )


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


def map_and_rankings(stats: dict) -> str:
    countries = ranking_table(stats.get("countries") or [], "name")
    places = ranking_table(stats.get("places") or [], "label")
    return (
        '<div id="map"></div><div class="cols">'
        f"<section><h2>Top countries</h2>{countries}</section>"
        f"<section><h2>Top places</h2>{places}</section></div>"
    )


def detail_body(stats: dict, star_count=None) -> str:
    warn = ""
    if stats.get("error"):
        warn = f'<p class="warn">⚠ {esc(stats["error"])}'
        if stats.get("stale_since"):
            warn += f" Showing data from {esc(stats['stale_since'][:10])}."
        warn += "</p>"
    return warn + kpis(stats, star_count) + map_and_rankings(stats)


def build(data_dir: Path | str = "data", site_dir: Path | str = "site") -> Path:
    """Regenerate `site_dir` from scratch and return its path."""
    data_dir, site_dir = Path(data_dir), Path(site_dir)
    summary = json.loads((data_dir / "summary.json").read_text(encoding="utf-8"))
    org, generated = summary["org"], summary["generated_at"]
    repository = summary.get("repository") or org

    if site_dir.exists():
        shutil.rmtree(site_dir)
    (site_dir / "data").mkdir(parents=True)
    (site_dir / "assets").mkdir()
    assets = resources.files("stargazer_map") / "assets"
    for name in ASSETS:
        (site_dir / "assets" / name).write_bytes((assets / name).read_bytes())
    for f in (data_dir / "stats").glob("*.json"):
        shutil.copy(f, site_dir / "data" / f.name)
    shutil.copy(data_dir / "summary.json", site_dir / "data" / "summary.json")

    # Per-repo pages
    for r in summary["repos"]:
        stats_file = data_dir / "stats" / f"{r['repo']}.json"
        stats = json.loads(stats_file.read_text(encoding="utf-8"))
        crumb = f'<a href="index.html">{esc(org)}</a> / {esc(r["repo"])}'
        heading = f'<a href="{esc(r["url"])}" style="color:inherit">{esc(r["repo"])}</a>'
        if r.get("archived"):
            heading += '<span class="badge">archived</span>'
        (site_dir / f"{r['repo']}.html").write_text(
            page(
                f"{r['repo']} stargazers",
                crumb,
                heading,
                esc(r.get("description") or "Where this repository's stargazers are."),
                detail_body(stats, r.get("star_count")),
                stats.get("places") or [],
                repository,
                generated,
            ),
            encoding="utf-8",
        )

    # Index page
    overall = json.loads((data_dir / "stats" / "_all.json").read_text(encoding="utf-8"))
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
        + map_and_rankings(overall)
        + '<h2 style="margin-top:32px">Repositories</h2>'
        + f'<div class="grid">{"".join(cards)}</div>'
    )
    (site_dir / "index.html").write_text(
        page(
            f"{org} star maps",
            f'<a href="https://github.com/{esc(org)}">github.com/{esc(org)}</a>',
            f"Where {esc(org)} stargazers are",
            "One map per repository, rebuilt weekly from public GitHub profile locations.",
            body,
            overall.get("places") or [],
            repository,
            generated,
        ),
        encoding="utf-8",
    )
    (site_dir / ".nojekyll").write_text("")
    print(f"Built {len(summary['repos']) + 1} pages in {site_dir}")
    return site_dir
