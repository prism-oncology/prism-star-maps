# stargazer-map
Weekly, automatically updated maps of where the stargazers of a GitHub user's or organisation's repositories are, published with GitHub Pages. Fork it to get maps for your own repositories.

Each public repository gets its own map, and an overview page combines all of them. Locations come from the free-text "location" field on stargazers' GitHub profiles and are geocoded with [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/).

## Make your own

Fork this repository into the account or organisation whose stars you want to map. The maps cover every public repository the fork's owner has, except forks.

1. **Create a token.** Create a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) with these settings (see [Token](#token) for why):
   - Resource owner: your account or organisation
   - Repository access: all repositories
   - Permissions: the default read-only metadata permission

   Organisations may need to approve the token.
2. **Add it as a secret.** In your fork, go to *Settings → Secrets and variables → Actions → New repository secret*. Name it `STARGAZERS_TOKEN` and paste the token.
3. **Enable GitHub Pages.** Go to *Settings → Pages* and set *Source* to **GitHub Actions**.
4. **Enable Actions.** Open the *Actions* tab and enable workflows. GitHub turns off scheduled workflows in forks until you do this.
5. **Run it once.** Go to *Actions → Update star maps → Run workflow*. After that, it runs every Monday at 04:17 UTC.

The site is published at `https://<owner>.github.io/<fork-name>/`.

The first run replaces the upstream data in `data/`. `data/geocode-cache.json` keeps locations that have already been geocoded, so they aren't looked up again. Nominatim allows about one request per second, so each run geocodes at most 800 new locations. If you have more stargazers than that, the maps fill in over several runs.

### Options

Set these in the `env:` block of `.github/workflows/update-maps.yml`:

| Variable | Default | Effect |
|---|---|---|
| `INCLUDE_FORKS` | `false` | Include repositories that are forks |
| `INCLUDE_ARCHIVED` | `true` | Include archived repositories |
| `INCLUDE_LOGINS` | `false` | Show stargazers' usernames in map popups and in the published JSON |
| `MAX_GEOCODE` | `800` | Maximum number of new locations geocoded per run |

## Token

GitHub only lets admins and collaborators of a repository list its stargazers, so the workflow's built-in `GITHUB_TOKEN` is not enough. The token in `STARGAZERS_TOKEN` must belong to someone with admin or collaborator access to the repositories you want to map. If a repository can't be read, its page shows a warning and keeps the data from the last successful run.

## Run locally

Requires Python 3.12+ and the [GitHub CLI](https://cli.github.com/), signed in with `gh auth login`.

```sh
python star-map/fetch_stargazers.py              # writes data/; ORG=<owner> to map someone else
python star-map/site_builder/build_site.py        # writes site/
python -m http.server -d site
```
