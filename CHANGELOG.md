# Changelog

**English** · [Русский](CHANGELOG.ru.md)

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[semantic versioning](https://semver.org/).

## [0.4.1] — 2026-09-06

No library changes: the code of 0.4.1 is identical to 0.4.0. The release exists
because everything around it moved.

### Changed

- **Uploads to PyPI now go through Trusted Publishing** (OIDC). The
  `PYPI_API_TOKEN` secret is gone — there is no long-lived credential to leak or
  rotate any more, and PyPI accepts a short-lived token issued to this
  repository and this workflow only. As a side effect the release carries
  [attestations](https://docs.pypi.org/attestations/) (PEP 740): a proof that
  the files were built by this workflow from this commit.
- A manual run of the publish workflow passes `skip-existing`, so it can be used
  to check the credentials without cutting a release; tag runs stay strict.
- The rolling `latest` pre-release drops stale assets instead of accumulating
  them — after a version bump it used to hold two builds at once.
- The PyPI badge URL carries `cacheSeconds`, which makes GitHub's image proxy
  re-fetch it; it was serving the "not found" image cached from before the first
  upload.

## [0.4.0] — 2026-09-06

### Breaking changes

The library is renamed to match the repository and the PyPI package. The old
names are gone with no compatibility shims — nothing was ever published under
them.

| Before | After |
|---|---|
| `pip install anime-players` | `pip install anime-dl-core` |
| `import anime_players` | `import anime_dl_core` |
| the `anime-players` command | the `anime-dl-core` command |
| `python -m anime_players` | `python -m anime_dl_core` |
| `AnimePlayersError` | `AnimeDlCoreError` |
| `ANIME_PLAYERS_LIVE=1 pytest -m live` | `ANIME_DL_CORE_LIVE=1 pytest -m live` |

### Added

- **Published on PyPI**: `pip install anime-dl-core`. Uploading is done by a
  separate workflow, `.github/workflows/publish-pypi.yml`, on a `v*` tag —
  through PyPI Trusted Publishing (OIDC, no secrets) or through a
  `PYPI_API_TOKEN` secret when one is set. Until publishing is enabled the step
  does not fail; it prints what to do instead.
- Release instructions in [`docs/releasing.md`](docs/releasing.md).
- An English `CHANGELOG.md` and a Russian `CHANGELOG.ru.md` that link to each
  other, the same way the two READMEs do.

### Infrastructure

- The [ialakey/anime-dl-core](https://github.com/ialakey/anime-dl-core)
  repository: two READMEs (English and Russian) with a language switch, a
  description and topics.
- CI (`build.yml`): the offline suite on Python 3.9 / 3.12 / 3.13, an
  sdist + wheel build, an install of the built wheel into a clean environment,
  and the SHA-256 of every file plus the build commit in the release notes. A
  push to `main` refreshes the rolling `latest` pre-release, a `v*` tag creates
  a versioned release.

## [0.3.0] — 2026-09-06

### Added

- **The Animedia player** (`aser.pro/vod/<id>`), verified live: the HLS master
  playlist is expanded into qualities, and every format the Playerjs `file`
  parameter can take is supported (a single link, `[720]url1,[360]url2`, a json
  playlist).
- **The `sources.Animedia` helper** for the amd.online site (formerly
  animedia.tv): title search, name and poster, the episode list
  (`{number: player link}`) and every player on the page, Kodik iframes
  included.
- **The `sources.Alloha` helper** — the open api.alloha.tv API: lookup by
  Kinopoisk / IMDb / TMDb id or by title, description, dubs, seasons with
  episodes and iframe links (including per episode and per dub), plus
  `translations_for()` for the dubs of one specific episode.
- The `examples/07_animedia_alloha.py` example, 22 offline tests (86 in total)
  and 4 live tests (18 in total).

### Notes

- **Alloha exposes no direct video links**: its player fetches them over a
  WebSocket from an obfuscated bundle, and they are in neither the HTML nor the
  open API. That is why Alloha is a source (`sources`) rather than a player — it
  returns an iframe URL. Getting the files themselves requires a headless
  browser.
- The old Animedia links `online.animedia.tv/embed/...` that some aggregators
  still hand out do not work: the domain answers with an endless redirect to
  itself. The working links are `aser.pro/vod/<id>`, taken from the amd.online
  title page.

## [0.2.0] — 2026-09-06

### Changed

- **VK Video is now fully supported and verified live.** Parsing was rewritten
  for the current `video_ext.php` format: the data comes from `window.cur` →
  `apiPrefetchCache` → the `video.get` response (`files` with `mp4_144`…
  `mp4_2160`, `hls_ondemand`, `dash_ondemand`, `hls_fmp4`). The legacy
  `var playerParams` format stays as a fallback.
- **VK: every link shape.** Embeds, `vkvideo.ru/video-123_456`, `vk.ru/...`, a
  link with `hash` and the bare `-123_456` (in the CLI too).
- **VK: the HLS master playlist is expanded into qualities**
  (`resolve_qualities`); title, duration, poster and a live flag were added, and
  private or deleted videos raise `ContentBlocked` with an explanation.
- **SovetRomantica: parsing rewritten for the real markup** of the embed page
  (`var config={...}` + `var skips=[...]`): playlist, poster, vtt thumbnails,
  title, dub type, the link to the next episode and the opening/ending
  timecodes.
- **SovetRomantica: the `base_url` parameter** — a mirror, a new domain or the
  Wayback Machine; with it the player accepts a link to any host. The error is
  explicit when the address turns out not to be an embed (which is exactly what
  the hijacked `sovetromantica.com` domain returns today, its CDN being off
  while the team raises money to relaunch).
- Players gained a `note` field, shown by `anime-dl-core --list`.

### Added

- The `examples/06_vk_sovetromantica.py` example covering both players.
- 11 offline tests on real saved VK and SovetRomantica pages (64 in total) and
  6 live tests (14 in total), including a check that a VK stream really
  downloads.

## [0.1.0] — 2026-09-06

The first release.

### Added

- Players: **Aniboom**, **CVH (CdnVideoHub)**, **Kodik**, **Sibnet**,
  **AniLibria (AniLiberty)** — all verified against live links;
  **VK Video** and **SovetRomantica** — implemented but not verified live.
- A single `extract(url)` facade that detects the player from the URL, and a
  registry that accepts custom players (`register`).
- The `PlayerResult` / `Stream` / `SkipSegment` / `StreamKind` models: stream
  selection (`best`, `filter`, `master`), download headers, ffmpeg command
  generation and json serialisation.
- Async mode (`extract_async`, `aextract`) on aiohttp — the `[async]` extra.
- Support for http/socks5 proxies, custom headers and timeouts.
- The `anime-dl-core` command line (`--json`, `--best`, `--kind`,
  `--max-quality`, `--ffmpeg`, `--episode`, `--season`, `--studio`, `--proxy`,
  `--list`).
- The optional `sources.AnimeGo` helper: anime search, the episode list and
  player links.
- Tests: 53 offline tests on saved player responses and 8 live tests
  (`pytest -m live`), plus the examples in `examples/`.

### Implementation notes

- Kodik: the `ref` parameter of the `/ftor` request is sent **url-decoded** —
  with an empty value the server answers 500 (which is how older
  implementations broke).
- Kodik: the Caesar shift is brute-forced and cached on the player object, and
  the endpoint (`atob(...)`) is located with a regex rather than by an offset
  into the script.
- CVH: the Odnoklassniki CDN response keys (`mpegHighUrl`, `mpegFullHdUrl`, ...)
  are mapped to picture heights; the older `url720` style is understood too.
- Aniboom: the HLS master playlist is expanded into separate quality streams.
- Parsing does not depend on `bs4`/`lxml` — `requests` is the only required
  dependency.
