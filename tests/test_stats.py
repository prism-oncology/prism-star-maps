import json

from stargazer_map.geocode import normalise_location
from stargazer_map.github import parse_github_url
from stargazer_map.stats import aggregate

PARIS = {"lat": 48.857, "lon": 2.352, "label": "Paris, France", "country": "France",
         "country_code": "FR"}  # fmt: skip
LYON = {"lat": 45.758, "lon": 4.835, "label": "Lyon, France", "country": "France",
        "country_code": "FR"}  # fmt: skip


def test_normalise_location():
    assert normalise_location("  Paris,  France 🇫🇷 ") == "paris, france"
    assert normalise_location("🌍") is None
    assert normalise_location("") is None
    assert normalise_location(None) is None


def test_parse_github_url():
    for url in (
        "https://github.com/me/repo.git",
        "https://github.com/me/repo",
        "git@github.com:me/repo.git\n",
    ):
        assert parse_github_url(url) == "me/repo"
    assert parse_github_url("https://gitlab.com/me/repo") is None


def test_aggregate():
    cache = {"paris": PARIS, "lyon": LYON, "nowhere": None}
    users = {"a": "paris", "b": "paris", "c": "lyon", "d": "nowhere", "e": None}
    stats = aggregate(users, cache)
    assert stats["stargazers"] == 5
    assert stats["with_location"] == 4
    assert stats["located"] == 3
    assert [(p["label"], p["count"]) for p in stats["places"]] == [
        ("Paris, France", 2),
        ("Lyon, France", 1),
    ]
    assert stats["countries"] == [{"code": "FR", "name": "France", "count": 3}]
    assert "logins" not in stats["places"][0]


def test_aggregate_logins():
    stats = aggregate({"a": "paris", "b": "paris"}, {"paris": PARIS}, include_logins=True)
    assert stats["places"][0]["logins"] == ["a", "b"]


def test_fetch(tmp_path, monkeypatch):
    from stargazer_map import geocode, github, stats

    repos = [
        {"name": "tool", "url": "u1", "description": "d", "stargazerCount": 3,
         "isFork": False, "isArchived": False, "primaryLanguage": {"name": "Python"}},
        {"name": "secret", "url": "u2", "description": None, "stargazerCount": 1,
         "isFork": False, "isArchived": True, "primaryLanguage": None},
        {"name": "empty", "url": "u3", "description": None, "stargazerCount": 0,
         "isFork": False, "isArchived": False, "primaryLanguage": None},
    ]  # fmt: skip
    stargazers = {
        "tool": [
            {"login": "a", "location": "Paris"},
            {"login": "b", "location": "Lyon 🦁"},
            {"login": "c", "location": None},
        ]
    }

    def list_stargazers(owner, repo):
        if repo not in stargazers:
            raise PermissionError("FORBIDDEN")
        return stargazers[repo]

    lookups = []

    def nominatim(query, user_agent):
        lookups.append(query)
        return {"paris": PARIS, "lyon": LYON}[query]

    monkeypatch.setattr(github, "list_repos", lambda *a: repos)
    monkeypatch.setattr(github, "list_stargazers", list_stargazers)
    monkeypatch.setattr(geocode, "nominatim", nominatim)

    data = tmp_path / "data"
    (data / "stats").mkdir(parents=True)
    # Previous stats for an unreadable repo are kept; stats for deleted repos are dropped.
    old = {"stargazers": 1, "located": 1, "places": [], "countries": [],
           "generated_at": "2026-01-01T00:00:00+00:00"}  # fmt: skip
    (data / "stats" / "secret.json").write_text(json.dumps(old))
    (data / "stats" / "gone.json").write_text("{}")

    summary = stats.fetch("me", data, repository="me/stargazer-map")

    assert sorted(lookups) == ["lyon", "paris"]
    assert summary["repository"] == "me/stargazer-map"
    assert summary["overall"] == {"stargazers": 3, "with_location": 2, "located": 2,
                                  "countries": 1}  # fmt: skip
    files = sorted(p.name for p in (data / "stats").iterdir())
    assert files == ["_all.json", "empty.json", "secret.json", "tool.json"]
    secret = json.loads((data / "stats" / "secret.json").read_text())
    assert secret["error"] and secret["stale_since"] == old["generated_at"]
    assert json.loads((data / "geocode-cache.json").read_text()) == {"lyon": LYON, "paris": PARIS}

    # Second run: everything is cached, nothing is geocoded again.
    lookups.clear()
    stats.fetch("me", data)
    assert lookups == []


def test_fetch_fails_when_token_cannot_read_any_repo(tmp_path, monkeypatch):
    import pytest

    from stargazer_map import github, stats

    repos = [
        {"name": n, "url": "u", "description": None, "stargazerCount": c,
         "isFork": False, "isArchived": False, "primaryLanguage": None}
        for n, c in (("starred", 2), ("empty", 0))
    ]  # fmt: skip

    def refuse(owner, repo):
        raise PermissionError("Resource not accessible by personal access token")

    monkeypatch.setattr(github, "list_repos", lambda *a: repos)
    monkeypatch.setattr(github, "list_stargazers", refuse)
    with pytest.raises(RuntimeError, match="Resource not accessible"):
        stats.fetch("me", tmp_path / "data")
    assert not (tmp_path / "data" / "summary.json").exists()
