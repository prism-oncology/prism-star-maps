#!/usr/bin/env python3
"""
Fetch stargazers of every public repo in a GitHub org, geocode their
profile locations and write aggregated per-repo stats to data/stats/.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATS = DATA / "stats"
CACHE_FILE = DATA / "geocode-cache.json"

ORG = os.environ.get("ORG", "prism-oncology")


def env_flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes"}


INCLUDE_FORKS = env_flag("INCLUDE_FORKS", False)
INCLUDE_ARCHIVED = env_flag("INCLUDE_ARCHIVED", True)
INCLUDE_LOGINS = env_flag("INCLUDE_LOGINS", False)
MAX_GEOCODE = int(os.environ.get("MAX_GEOCODE", "800"))

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = f"prism-star-maps/1.0 (https://github.com/{ORG}/prism-star-maps)"

# --------------------------------------------------------------------------
# GitHub (via gh CLI)
# --------------------------------------------------------------------------

REPOS_QUERY = """
query($org: String!, $endCursor: String) {
  repositoryOwner(login: $org) {
    repositories(first: 100, after: $endCursor, privacy: PUBLIC,
                 ownerAffiliations: [OWNER],
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes {
        name description url stargazerCount isFork isArchived
        primaryLanguage { name }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

STARGAZERS_QUERY = """
query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    stargazers(first: 100, after: $endCursor) {
      nodes { login location }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def gh_graphql_paginate(query: str, jq: str, **variables: str) -> list[dict]:
    cmd = ["gh", "api", "graphql", "--paginate", "-f", f"query={query}", "--jq", jq]
    for key, value in variables.items():
        cmd += ["-f", f"{key}={value}"]
    for attempt in range(3):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        err = proc.stderr.strip()
        # Permission problems won't fix themselves; transient ones might.
        if re.search(r"NOT_FOUND|FORBIDDEN|Could not resolve|Resource not accessible|403", err):
            raise PermissionError(err)
        print(f"  gh failed (attempt {attempt + 1}/3): {err[:300]}", file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    raise RuntimeError(err)


def list_repos() -> list[dict]:
    repos = gh_graphql_paginate(
        REPOS_QUERY, ".data.repositoryOwner.repositories.nodes[]", org=ORG
    )
    kept = []
    for r in repos:
        if r["isFork"] and not INCLUDE_FORKS:
            continue
        if r["isArchived"] and not INCLUDE_ARCHIVED:
            continue
        kept.append(r)
    return kept


def list_stargazers(repo: str) -> list[dict]:
    return gh_graphql_paginate(
        STARGAZERS_QUERY,
        ".data.repository.stargazers.nodes[]",
        owner=ORG,
        name=repo,
    )


# --------------------------------------------------------------------------
# Geocoding (OpenStreetMap Nominatim, 1 request/second, cached)
# --------------------------------------------------------------------------

def normalise_location(raw: str | None) -> str | None:
    if not raw:
        return None
    text = re.sub(r"[\U00010000-\U0010FFFF]", " ", raw)  # strip emoji
    text = re.sub(r"\s+", " ", text).strip(" ,.;|-/")
    if len(text) < 2:
        return None
    return text.lower()


def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.write_text(
        json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


_last_call = 0.0


def nominatim(query: str) -> dict | None:
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
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{params}", headers={"User-Agent": USER_AGENT}
    )
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


def geocode_all(locations: set[str], cache: dict) -> None:
    todo = sorted(loc for loc in locations if loc not in cache)
    if len(todo) > MAX_GEOCODE:
        print(f"Geocoding {MAX_GEOCODE} of {len(todo)} new locations (rest next run)")
        todo = todo[:MAX_GEOCODE]
    else:
        print(f"Geocoding {len(todo)} new locations")
    for i, loc in enumerate(todo, 1):
        try:
            cache[loc] = nominatim(loc)
        except Exception as exc:  # network hiccup: retry on the next run
            print(f"  geocode failed for {loc!r}: {exc}", file=sys.stderr)
            continue
        if i % 50 == 0:
            save_cache(cache)
            print(f"  {i}/{len(todo)}")
    save_cache(cache)


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def aggregate(users: dict[str, str | None], cache: dict) -> dict:
    """users: login -> normalised location (or None)."""
    places: dict[tuple, dict] = {}
    countries: Counter = Counter()
    country_names: dict[str, str] = {}
    with_location = located = 0
    for login, loc in sorted(users.items()):
        if loc:
            with_location += 1
        geo = cache.get(loc) if loc else None
        if not geo:
            continue
        located += 1
        key = (geo["lat"], geo["lon"])
        place = places.setdefault(
            key, {"lat": geo["lat"], "lon": geo["lon"], "label": geo["label"], "count": 0}
        )
        place["count"] += 1
        if INCLUDE_LOGINS:
            place.setdefault("logins", []).append(login)
        if geo.get("country_code"):
            countries[geo["country_code"]] += 1
            country_names[geo["country_code"]] = geo.get("country") or geo["country_code"]
    return {
        "stargazers": len(users),
        "with_location": with_location,
        "located": located,
        "places": sorted(places.values(), key=lambda p: -p["count"]),
        "countries": [
            {"code": c, "name": country_names[c], "count": n}
            for c, n in countries.most_common()
        ],
    }


def main() -> int:
    STATS.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    repos = list_repos()
    print(f"{len(repos)} repos in {ORG}")

    per_repo_users: dict[str, dict[str, str | None]] = {}
    errors: dict[str, str] = {}
    for r in repos:
        if r["stargazerCount"] == 0:
            per_repo_users[r["name"]] = {}
            continue
        print(f"- {r['name']} ({r['stargazerCount']} stars)")
        try:
            nodes = list_stargazers(r["name"])
        except PermissionError as exc:
            errors[r["name"]] = (
                "Token cannot list stargazers (needs admin/collaborator access)."
            )
            print(f"  skipped: {str(exc)[:200]}", file=sys.stderr)
            continue
        per_repo_users[r["name"]] = {
            n["login"]: normalise_location(n.get("location")) for n in nodes
        }

    if not per_repo_users:
        print("No stargazer data could be fetched; check the token.", file=sys.stderr)
        return 1

    cache = load_cache()
    all_locations = {
        loc for users in per_repo_users.values() for loc in users.values() if loc
    }
    geocode_all(all_locations, cache)

    summary = {"org": ORG, "generated_at": now, "repos": []}
    union: dict[str, str | None] = {}
    for r in repos:
        name = r["name"]
        users = per_repo_users.get(name)
        stats = {
            "repo": name,
            "url": r["url"],
            "description": r.get("description"),
            "language": (r.get("primaryLanguage") or {}).get("name"),
            "archived": r["isArchived"],
            "star_count": r["stargazerCount"],
            "generated_at": now,
            "error": errors.get(name),
        }
        if users is not None:
            stats.update(aggregate(users, cache))
            union.update(users)
        else:
            # Keep the previous map if this run could not read the repo.
            previous = STATS / f"{name}.json"
            if previous.exists():
                old = json.loads(previous.read_text(encoding="utf-8"))
                for key in ("stargazers", "with_location", "located", "places", "countries"):
                    stats[key] = old.get(key)
                stats["stale_since"] = old.get("stale_since") or old.get("generated_at")
        (STATS / f"{name}.json").write_text(
            json.dumps(stats, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        summary["repos"].append(
            {
                k: stats.get(k)
                for k in (
                    "repo", "url", "description", "language", "archived",
                    "star_count", "stargazers", "located", "error",
                )
            }
            | {"countries": len(stats.get("countries") or [])}
        )

    overall = {
        "repo": "_all",
        "url": f"https://github.com/{ORG}",
        "description": f"Unique stargazers across all {ORG} repositories",
        "generated_at": now,
    } | aggregate(union, cache)
    (STATS / "_all.json").write_text(
        json.dumps(overall, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    summary["overall"] = {
        k: overall[k] for k in ("stargazers", "with_location", "located")
    } | {"countries": len(overall["countries"])}
    (DATA / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    # Drop stats for repos that disappeared from the org.
    keep = {f"{r['name']}.json" for r in repos} | {"_all.json"}
    for f in STATS.glob("*.json"):
        if f.name not in keep:
            f.unlink()

    print(
        f"Done: {overall['stargazers']} unique stargazers, "
        f"{overall['located']} located in {len(overall['countries'])} countries"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
