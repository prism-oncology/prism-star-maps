#!/usr/bin/env python3
"""Render data/summary.json + data/stats/*.json into a static site in site/.

  site/index.html          overview: org-wide map + one card per repo
  site/<repo>.html         one map page per repository
  site/data/*.json         the aggregated stats (handy for other tools)
"""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"

LEAFLET = "https://unpkg.com/leaflet@1.9.4/dist"

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e4e4e1;
--accent:#c2410c;--accent-soft:rgba(194,65,12,.18);--warn:#b45309}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1d1d20;--fg:#ececee;
--muted:#9a9aa1;--line:#2c2c31;--accent:#fb923c;--accent-soft:rgba(251,146,60,.22);--warn:#fbbf24}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{padding:28px 16px 8px;max-width:1100px;margin:auto}
header .crumb{font-size:13px;color:var(--muted)}
h1{margin:4px 0 4px;font-size:28px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0}
main{max-width:1100px;margin:auto;padding:8px 16px 48px}
.kpis{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:10px 14px;min-width:120px}
.kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.kpi span{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
#map{height:520px;border-radius:12px;border:1px solid var(--line);background:var(--card)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;margin-top:24px}
.card{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 16px;color:var(--fg)}
.card:hover{border-color:var(--accent);text-decoration:none}
.card h3{margin:0 0 4px;font-size:16px;color:var(--accent)}
.card p{margin:0 0 10px;color:var(--muted);font-size:13px;min-height:2.6em}
.card .meta{font-size:13px;font-variant-numeric:tabular-nums}
.badge{font-size:11px;border:1px solid var(--line);border-radius:999px;padding:1px 7px;
color:var(--muted);margin-left:6px;vertical-align:2px}
.warn{color:var(--warn);font-size:13px}
.cols{display:grid;grid-template-columns:1fr;gap:24px;margin-top:24px}
@media(min-width:800px){.cols{grid-template-columns:1fr 1fr}}
h2{font-size:17px;margin:0 0 10px}
table{width:100%;border-collapse:collapse;font-size:14px}
td{padding:5px 0;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
td.n{text-align:right;width:56px}
td.bar{width:40%;padding-left:10px}
td.bar i{display:block;height:8px;border-radius:4px;background:var(--accent)}
footer{color:var(--muted);font-size:12px;text-align:center;padding:24px 16px}
.leaflet-popup-content{font:13px/1.4 inherit}
"""

MAP_JS = """
(function(){
  var places = %s;
  var map = L.map('map',{worldCopyJump:true,minZoom:1}).setView([25,10],2);
  var dark = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
  // Esri gray canvas: no API key needed (CARTO basemaps now require one).
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_' + (dark?'Dark':'Light') + '_Gray_Base/MapServer/tile/{z}/{y}/{x}',{
    maxZoom:16,
    attribution:'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors'
  }).addTo(map);
  var accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  var bounds = [];
  places.forEach(function(p){
    var r = 5 + 4*Math.sqrt(p.count);
    var m = L.circleMarker([p.lat,p.lon],{radius:r,color:accent,weight:1.5,
      fillColor:accent,fillOpacity:.45}).addTo(map);
    var txt = '<b>'+escapeHtml(p.label)+'</b><br>'+p.count+' stargazer'+(p.count>1?'s':'');
    if (p.logins) txt += '<br>' + p.logins.map(function(l){
      return '<a href="https://github.com/'+encodeURIComponent(l)+'" target="_blank" rel="noopener">@'+escapeHtml(l)+'</a>';
    }).join(', ');
    m.bindPopup(txt);
    bounds.push([p.lat,p.lon]);
  });
  if (bounds.length > 1) map.fitBounds(bounds,{padding:[30,30],maxZoom:5});
  else if (bounds.length === 1) map.setView(bounds[0],4);
  function escapeHtml(s){return String(s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
})();
"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else "–"


def page(title: str, crumb: str, heading: str, sub: str, body: str, places, org: str, generated: str) -> str:
    map_block = ""
    if places is not None:
        data = json.dumps(places, ensure_ascii=False).replace("</", "<\\/")
        map_block = (
            f'<script src="{LEAFLET}/leaflet.js"></script>'
            f"<script>{MAP_JS % data}</script>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="{LEAFLET}/leaflet.css">
<style>{CSS}</style></head>
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
            f"One map per repository, rebuilt daily from public GitHub profile locations.",
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
