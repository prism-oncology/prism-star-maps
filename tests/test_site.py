import json

from stargazer_map.site import build


def write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def test_build(tmp_path):
    data = tmp_path / "data"
    (data / "stats").mkdir(parents=True)
    write(
        data / "summary.json",
        {
            "org": "me",
            "repository": "me/stargazer-map",
            "generated_at": "2026-10-09T00:00:00+00:00",
            "repos": [
                {
                    "repo": "tool",
                    "url": "https://github.com/me/tool",
                    "description": "A tool",
                    "language": "Python",
                    "archived": False,
                    "star_count": 2,
                    "stargazers": 2,
                    "located": 1,
                    "error": None,
                    "countries": 1,
                },
            ],
        },
    )
    stats = {
        "stargazers": 2,
        "located": 1,
        "places": [{"lat": 1, "lon": 2, "label": "Evil </script>", "count": 1}],
        "countries": [{"code": "FR", "name": "France", "count": 1}],
    }
    write(data / "stats" / "tool.json", stats)
    write(data / "stats" / "_all.json", stats)

    site = build(data, tmp_path / "site")

    files = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    assert {"index.html", "tool.html", ".nojekyll", "assets/style.css", "assets/map.js",
            "data/summary.json", "data/tool.json", "data/_all.json"} <= files  # fmt: skip
    index = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="https://github.com/me/stargazer-map">source' in index
    assert 'href="tool.html"' in index
    # A place label must not be able to close the embedded JSON script.
    assert "Evil <\\/script>" in (site / "tool.html").read_text(encoding="utf-8")
