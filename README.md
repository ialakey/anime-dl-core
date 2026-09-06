# anime-dl-core

**English** · [Русский](README.ru.md)

[![CI](https://github.com/ialakey/anime-dl-core/actions/workflows/build.yml/badge.svg)](https://github.com/ialakey/anime-dl-core/actions/workflows/build.yml)
[![PyPI](https://img.shields.io/pypi/v/anime-dl-core?cacheSeconds=3600)](https://pypi.org/project/anime-dl-core/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Python library that turns an anime player embed link into **direct video URLs**:
Aniboom, CVH (CdnVideoHub), Kodik, Sibnet, Animedia, AniLibria, VK Video and
SovetRomantica.

The library does one thing: players. You give it an embed URL, you get back a
list of streams (HLS / DASH / MP4) with resolutions and the headers without
which the CDN will not serve the file. Everything else — search, catalogues,
ratings — is deliberately out of scope; small optional helpers live in
[`anime_dl_core.sources`](#finding-a-player-link).

```python
import anime_dl_core as ap

result = ap.extract("https://aniboom.one/embed/9G1MJ6NMV8z?episode=1&translation=30")

print(result.qualities)                     # [360, 480, 720, 1080]
stream = result.best(kind="hls")            # the 1080p stream
print(stream.url)                           # https://.../media_6.m3u8
print(stream.headers)                       # {'Referer': 'https://aniboom.one/', ...}
print(stream.ffmpeg_command("ep1.mp4"))     # ready-to-paste download command
```

## Contents

- [Supported players](#supported-players)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Data model](#data-model)
- [Player by player](#player-by-player)
- [Finding a player link](#finding-a-player-link)
- [Alloha: catalogue and iframe](#alloha-catalogue-and-iframe)
- [Async](#async)
- [Command line](#command-line)
- [Proxies, headers, timeouts](#proxies-headers-timeouts)
- [Writing your own player](#writing-your-own-player)
- [Errors](#errors)
- [Tests](#tests)
- [How it works inside](#how-it-works-inside)
- [Limitations](#limitations)

## Supported players

| Player | Name in the library | Accepted input | Returns | Verified live |
|---|---|---|---|---|
| Aniboom | `aniboom` | `https://aniboom.one/embed/<id>` or the bare `<id>` | HLS (master + per quality), DASH | ✅ |
| CVH (CdnVideoHub) | `cvh` | `/cdn-iframe/<id>/<studio>/<season>/<episode>` or a numeric `<id>` | HLS, DASH, MP4 144p–1080p | ✅ |
| Kodik | `kodik` | `https://kodikplayer.com/seria\|serial\|video/<id>/<hash>/720p` | HLS and MP4 per quality + opening/ending timecodes | ✅ |
| Sibnet | `sibnet` | `https://video.sibnet.ru/shell.php?videoid=<id>` or `<id>` | MP4 | ✅ |
| Animedia | `animedia` | `https://aser.pro/vod/<id>` or the bare `<id>` | HLS (master + per quality) | ✅ |
| AniLibria (AniLiberty) | `anilibria` | release alias (`bleach`), `bleach/3` or an episode URL | HLS 480/720/1080 + timecodes | ✅ |
| VK Video | `vk` | embed, video URL or `oid_id` | MP4 144p–2160p, HLS (master + qualities), DASH | ✅ |
| SovetRomantica | `sovetromantica` | `/embed/episode_<id>_<episode>-<dubbed\|subtitles>` or the slug | HLS + timecodes, poster, thumbnails, next episode | ⚠️ site offline |

"Verified live" means the player really returned working links during
development, and a live test (`pytest -m live`) keeps it that way.

**SovetRomantica**: parsing is verified against real embed pages, but the team's
own site is currently down — the `sovetromantica.com` domain changed hands and
serves unrelated content, the CDN (`scu*.sovetromantica.com`) is switched off,
and [the team is raising money to relaunch](https://boosty.to/sovetromantica).
Examples and live tests therefore use a real page from the Wayback Machine; once
the site is back, point the player at the new domain:
`SovetRomanticaPlayer(base_url="https://new-domain")`. Their current releases are
published on VK and are handled by the `vk` player.

## Installation

```bash
pip install anime-dl-core                # plain install (requests only)
pip install "anime-dl-core[async]"       # + async mode (aiohttp)
pip install "anime-dl-core[socks]"       # + socks5 proxy support
```

From source, for development and the test suite:

```bash
git clone https://github.com/ialakey/anime-dl-core.git
cd anime-dl-core
pip install -e ".[async,dev]"
```

There is exactly one required dependency — `requests`. HTML is parsed with
regular expressions, so neither `bs4` nor `lxml` is needed.

Python 3.9+.

The same wheel and sdist are attached to every
[release](https://github.com/ialakey/anime-dl-core/releases), together with the
SHA-256 of each file and the commit they were built from.

## Quick start

```python
import anime_dl_core as ap

# 1. The player is detected from the URL
result = ap.extract("https://kodikplayer.com/seria/1304528/932d5da818729ec5ccc9be7968ee3717/720p")

result.player          # 'kodik'
result.qualities       # [360, 480, 720]
result.translation     # '2x2'
result.skip_segments   # [SkipSegment(start=30, end=110, kind='opening'), ...]

# 2. Picking a stream
result.best()                       # highest quality
result.best(kind="mp4")             # direct files only
result.best(max_quality=480)        # nothing above 480p
result.master()                     # HLS master playlist (the player picks the quality)
result.filter("hls", quality=720)   # every matching stream

# 3. Downloading
stream = result.best(kind="mp4")
stream.url                          # direct link
stream.headers                      # Referer/User-Agent — required!
stream.ffmpeg_args("ep1.mp4")       # argument list for subprocess
stream.ffmpeg_command("ep1.mp4")    # the same as a single string

# 4. Everything as json
import json; print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
```

If you hit the same player several times, go through the player object so the
HTTP session is reused:

```python
with ap.AnilibriaPlayer() as player:
    for number in range(1, 13):
        print(player.extract("bleach", episode=number).best(max_quality=720).url)
```

## Data model

### `PlayerResult`

| Field | Type | Description |
|---|---|---|
| `player` | `str` | player name |
| `source_url` | `str` | what was parsed |
| `streams` | `list[Stream]` | streams that were found |
| `title` | `str \| None` | title, when the player exposes one |
| `poster` | `str \| None` | cover image |
| `duration` | `int \| None` | duration in seconds |
| `translation` | `str \| None` | dub / voice-over |
| `skip_segments` | `list[SkipSegment]` | opening / ending |
| `extra` | `dict` | everything player-specific |

Methods: `best()`, `filter()`, `master()`, `qualities`, `to_dict()`.
The object iterates over its streams and is falsy when there are none.

`best(kind=None, max_quality=None, allow_master=True)` returns the highest
quality stream; on a tie it prefers `mp4` (easiest to download), then `hls`,
then `dash`. Master playlists (quality unknown) rank last and are only chosen
when nothing else is available — `allow_master=False` excludes them entirely.

### `Stream`

| Field | Description |
|---|---|
| `url` | direct link |
| `kind` | `StreamKind.HLS` / `DASH` / `MP4` |
| `quality` | picture height (`720`), or `None` for a master playlist |
| `headers` | headers that are mandatory while downloading |
| `label` | caption (`'720p'`, `'master'`, a dub name) |
| `extra` | bitrate, codecs, the original response key, and so on |

Methods: `ffmpeg_args(output)`, `ffmpeg_command(output)`, `to_dict()`, plus the
`is_master` property.

> **The headers are not decoration.** Sibnet, Kodik and Aniboom answer with 403
> without the right `Referer`. Always pass `stream.headers` to your downloader:
> ```python
> requests.get(stream.url, headers=stream.headers, stream=True)
> ```
> For yt-dlp use `--referer`; for ffmpeg, `stream.ffmpeg_args(...)` already
> inserts `-headers`.

### `SkipSegment`

`start`, `end` (seconds from the start of the file), `kind`
(`'opening'` / `'ending'`) and the `duration` property.

## Player by player

### Aniboom

```python
from anime_dl_core import AniboomPlayer

with AniboomPlayer() as player:
    result = player.extract(
        "https://aniboom.one/embed/9G1MJ6NMV8z?episode=1&translation=30",
        referer="https://animego.org/",   # the default
        resolve_qualities=True,           # +1 request: expand master.m3u8 into qualities
    )
    print(result.qualities)               # [360, 480, 720, 1080]
    print(result.master().url)            # the master.m3u8
    print(result.filter("dash"))          # the MPD manifest
```

Also useful: `AniboomPlayer.embed_url(video_id, episode=…, translation=…)` and
`AniboomPlayer.video_id(url)`. `result.extra` carries `video_id`, `max_quality`,
`thumbnails` (the vtt sprite sheet) and `rating`.

### CVH (CdnVideoHub)

```python
from anime_dl_core import CvhPlayer

with CvhPlayer() as player:
    # every episode and dub
    for episode in player.playlist("51019"):
        print(episode.season, episode.episode, episode.studio, episode.voice_type)

    # a specific episode; the dub name is matched loosely
    result = player.extract("51019", season=1, episode=3, studio="AniLibria")

    # given an iframe URL, season / episode / studio are taken from it
    result = player.extract("https://animego.me/cdn-iframe/51019/AnilibriaTV/1/3")
```

Video is served by the Odnoklassniki CDN, so besides HLS/DASH you get direct mp4
files from 144p to 1080p. The publisher parameters are configurable:
`CvhPlayer(pub="747", aggr="mali")` (the defaults are the ones AnimeGO uses).

### Kodik

```python
from anime_dl_core import KodikPlayer

with KodikPlayer() as player:
    result = player.extract(
        "https://kodikplayer.com/seria/1304528/932d5da818729ec5ccc9be7968ee3717/720p",
        # for /serial/... links you can pass the episode and season:
        # season=1, episode=5,
        include_mp4=True,     # add direct mp4 links (on by default)
    )
    print(result.best(kind="mp4").url)   # .../720.mp4
    print(result.skip_segments)          # opening and ending
```

**No Kodik API token is required** — the library works from the embed link an
aggregator site hands out. Those links are time-limited (note the `:2026090707`
stamp in the path), so fetch them right before downloading.

If Kodik has rate-limited your IP the links come through a `/s/m/` proxy host;
`result.extra["warnings"]` then carries a warning, and the `proxy=` parameter
fixes it.

### Sibnet

```python
from anime_dl_core import SibnetPlayer

with SibnetPlayer() as player:
    result = player.extract("2589828")             # the bare id works too
    result = player.extract(
        "https://video.sibnet.ru/shell.php?videoid=2589828",
        resolve=True,   # follow the redirect to the signed CDN address right away
    )
```

Without `resolve=True` you get the stable `video.sibnet.ru/v/<hash>/<id>.mp4`
link, which redirects to the CDN itself — that is the more reliable option,
because the signed address is short-lived and bound to your IP.

### Animedia

```python
from anime_dl_core import AnimediaPlayer

with AnimediaPlayer() as player:
    result = player.extract("https://aser.pro/vod/20182")   # or just 20182
    print(result.qualities)          # [360, 720]
    print(result.best().url)         # .../hls/720/index.m3u8
    print(result.extra)              # {'vod_id': '20182', 'slug': '...', 'episode': 1}
```

Player links live on the title page at amd.online; the
[`sources.Animedia`](#finding-a-player-link) helper collects them for you.

> The old `online.animedia.tv/embed/<id>/<season>/<episode>` links that some
> aggregators still serve do not work: the domain answers with an endless
> redirect to itself. The current player address is `aser.pro/vod/<id>`.

### AniLibria (AniLiberty)

```python
from anime_dl_core import AnilibriaPlayer

with AnilibriaPlayer() as player:
    print(player.search("Bleach")[:1])                 # find the release alias
    print(len(player.episodes("bleach")))              # 354
    result = player.extract("bleach", episode=2)       # or "bleach/2", or an episode URL
    print(result.title, result.qualities, result.skip_segments)
```

This is not an embed player but the open `anilibria.top/api/v1` API (no token
needed). A mirror can be set with
`AnilibriaPlayer(api_base="https://aniliberty.top/api/v1")`.

### VK Video

```python
from anime_dl_core import VkPlayer

with VkPlayer() as player:
    # an anime episode in the SovetRomantica VK community
    result = player.extract("https://vk.com/video_ext.php?oid=-33905270&id=456239024")

    print(result.title)         # [субтитры | 08] Гримгар из пепла и фантазий ...
    print(result.qualities)     # [144, 240, 360, 480, 720]
    print(result.duration)      # 1440
    print(result.best(kind="mp4").url)
```

Every link shape is understood, no manual normalisation needed:

```python
player.extract("https://vk.com/video_ext.php?oid=-33905270&id=456239024&hash=...")
player.extract("https://vkvideo.ru/video-33905270_456239024")
player.extract("-33905270_456239024")
VkPlayer.embed_url(-33905270, 456239024, access_key="abc")   # build an embed by hand
```

Notes:

* `resolve_qualities=True` (default) expands the HLS master playlist into
  separate qualities, the same way Aniboom does;
* "link only" videos need the `hash` from the embed code; private, deleted and
  geo-blocked videos raise `ContentBlocked` with an explanation;
* live streams are parsed too — they only carry HLS, and
  `result.extra["is_live"]` marks them.

Both page formats are supported: the current one
(`apiPrefetchCache` → `video.get` → `files`) and the legacy `var playerParams`
with `url720`-style keys that some mirrors still serve.

### SovetRomantica

The team's site is currently offline (see the [table above](#supported-players)),
so the example uses a real embed page from the Wayback Machine:

```python
from anime_dl_core import SovetRomanticaPlayer

archived = ("https://web.archive.org/web/20240905174049id_/"
            "https://sovetromantica.com/embed/episode_1073_1-dubbed")

with SovetRomanticaPlayer(base_url="https://web.archive.org") as player:
    result = player.extract(archived)

result.title            # 'Gekkan Shoujo Nozaki-kun - Озвучка - Эпизод 1'
result.translation      # 'Озвучка SovetRomantica'
result.best().url       # 'https://scu2.sovetromantica.com/.../episode_1.m3u8'
result.skip_segments    # [SkipSegment(174, 262, 'opening'), SkipSegment(1316, 1398, 'ending')]
result.extra["next_episode"]  # link to the next episode
result.extra["thumbnails"]    # vtt thumbnails for the timeline
```

Once the site is back (or if you have a mirror):

```python
with SovetRomanticaPlayer(base_url="https://new-domain") as player:
    result = player.extract("episode_1073_1-dubbed")   # the slug is enough
```

`base_url` also allows the player to visit any host, which is what mirrors, the
Wayback Machine and local copies need. If the page does not look like an embed —
and that is exactly what the hijacked domain returns today — you get
`NoStreamsFound` with an explanation.

Runnable script with both examples: `examples/06_vk_sovetromantica.py`.

## Finding a player link

A small AnimeGO helper ships with the library — just enough for an end-to-end
scenario:

```python
from anime_dl_core.sources import AnimeGo
import anime_dl_core as ap

with AnimeGo() as site:                    # AnimeGo(mirror="animego.me", proxy=...)
    anime = site.search("Магическая битва")[0]
    print(anime.id, anime.title, anime.original_title, anime.url)

    print(site.episodes(anime.id))         # {1: 'https://animego.org/player/videos/...', ...}

    for link in site.players(anime.id, episode=2):
        print(link.player, link.label, link.embed)
        # CVH      JAM CLUB     https://animego.me/cdn-iframe/40748/Jam Club/1/2
        # AniBoom  JAM CLUB     https://aniboom.one/embed/9G1MJKRXV8z?episode=2...
        # Kodik    JAM CLUB     https://kodikplayer.com/seria/723706/...

    aniboom = next(link for link in site.players(anime.id, episode=2) if link.player == "AniBoom")
    result = site.resolve(aniboom)         # same as ap.extract(aniboom.embed)
```

Runnable script: `examples/02_animego_pipeline.py`.

The second helper is the **Animedia** site (amd.online):

```python
from anime_dl_core.sources import Animedia
import anime_dl_core as ap

with Animedia() as site:                       # Animedia(base_url="https://new-domain")
    anime = site.search("Боруто")[0]
    print(site.info(anime.url).title)          # Боруто: Новое поколение Наруто

    episodes = site.episodes(anime.url)        # {1: 'https://aser.pro/vod/1067', ...}
    print(len(episodes))                       # 293

    print(site.players(anime.url))             # {'animedia': [...], 'kodik': [...]}

    result = ap.extract(episodes[1])           # direct video links
```

Both sites are Russian-language, so the search queries are in Russian too. The
helpers are auxiliary and depend on site markup; the core of the library does
not, and player links can come from anywhere.

## Alloha: catalogue and iframe

Alloha (`api.alloha.tv`) is not a player in this library's sense but a
**source**: given a Kinopoisk / IMDb / TMDb id or a title, it returns the
description, the dubs, seasons with episodes and a ready iframe link.

```python
from anime_dl_core.sources import Alloha

with Alloha() as alloha:                             # Alloha(token="your token")
    anime = alloha.find(name="Атака титанов")        # or find(kp=749374), find(imdb="tt2560140")
    anime.name, anime.year, anime.category           # ('Атака титанов', 2013, 'сериал')
    anime.seasons                                    # {1: [1..25], 2: [...], 3: [...], 4: [...]}
    [t.name for t in anime.translations]             # ['DEEP', 'Субтитры', 'Anilibria', ...]

    # each episode has its own set of dubs
    voices = alloha.translations_for(anime, season=1, episode=1)
    alloha.iframe(anime, season=1, episode=1, translation=voices[0].name)
    # 'https://.../?token_movie=...&translation=10&season=1&episode=1&token=...'
```

**Alloha does not expose direct video links.** Its player fetches them over a
WebSocket from a heavily obfuscated bundle — they are in neither the HTML nor the
open HTTP API. So Alloha returns an iframe URL: embed it in a page or open it in
a browser/webview. If you need the files themselves, a headless browser is the
only way; plain HTML parsing will not get you there.

The API has a public token (`sources.alloha.PUBLIC_TOKEN`) which is used by
default. If it stops working, pass your own: `Alloha(token="...")`.

Runnable script with Animedia and Alloha: `examples/07_animedia_alloha.py`.

## Async

```bash
pip install "anime-dl-core[async]"
```

```python
import asyncio
import anime_dl_core as ap

async def main():
    # different players in parallel
    results = await asyncio.gather(
        ap.extract_async("https://aniboom.one/embed/9G1MJ6NMV8z"),
        ap.extract_async("https://video.sibnet.ru/shell.php?videoid=2589828"),
    )

    # one player, many episodes — a single session for all of them
    async with ap.CvhPlayer() as player:
        streams = await asyncio.gather(
            *(player.aextract("51019", episode=n, studio="AniLibria") for n in range(1, 5))
        )

asyncio.run(main())
```

Every player has an async twin: `aextract()`, `aplaylist()`, `arelease()`,
`afetch()`. With `async with` nothing has to be closed by hand; otherwise call
`await player.aclose()`.

## Command line

```bash
anime-dl-core --list                       # which players are supported
anime-dl-core https://aniboom.one/embed/9G1MJ6NMV8z
anime-dl-core 51019 --player cvh --episode 2 --studio AniLibria
anime-dl-core bleach --player anilibria --episode 1 --best --max-quality 720
anime-dl-core <url> --json                 # machine-readable output
anime-dl-core <url> --ffmpeg ep1.mp4       # ready-made ffmpeg command
anime-dl-core <url> --kind mp4 --proxy socks5://127.0.0.1:9050
anime-dl-core "https://vk.com/video_ext.php?oid=-33905270&id=456239024" --best --kind mp4
anime-dl-core -33905270_456239024 --json   # VK also takes the bare id
```

Without installing: `python -m anime_dl_core <url>`.

Sample output:

```
Плеер: kodik
Озвучка: 2x2
Пропуск: opening 30-110s, ending 1375-1445s
Потоки (6):
  [hls    360p] https://cloud.solodcdn.com/.../360.mp4:hls:manifest.m3u8
  [mp4    360p] https://cloud.solodcdn.com/.../360.mp4
  ...
Заголовки для скачивания:
  Referer: https://kodikplayer.com/
  User-Agent: Mozilla/5.0 ...
```

The CLI output, docstrings and error messages are in Russian, matching the sites
the library talks to.

## Proxies, headers, timeouts

The same parameters work in `extract()` and in any player's constructor:

```python
ap.extract(url, proxy="socks5://user:pass@host:1080", timeout=30)
ap.extract(url, user_agent="Mozilla/5.0 ...", headers={"Accept-Language": "ru-RU"})

with ap.KodikPlayer(proxy="http://127.0.0.1:8080", timeout=15) as player:
    ...
```

socks5 needs the `[socks]` extra. You can also pass a ready client:

```python
from anime_dl_core import HttpClient
client = HttpClient(proxy="http://127.0.0.1:8080", timeout=10)
result = ap.AniboomPlayer(client).extract(url)
```

`proxy`, `timeout`, `user_agent`, `headers` and `client` always go to the HTTP
client; everything else (`episode`, `season`, `studio`, `referer`, `resolve`,
`resolve_qualities`, `include_mp4`) goes to the player.

## Writing your own player

```python
from anime_dl_core import BasePlayer, PlayerResult, Stream, StreamKind, register
from anime_dl_core.utils import search

@register
class MyPlayer(BasePlayer):
    name = "myplayer"
    title = "My Player"
    domains = ("myplayer.example",)
    playback_headers = {"Referer": "https://myplayer.example/"}

    def extract(self, url, **kwargs):
        page = self.client.get(url).raise_for_status()
        playlist = search(r'file:"([^"]+\.m3u8)"', page.text, what="m3u8 link")
        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=[Stream(playlist, StreamKind.HLS, None, dict(self.playback_headers))],
        )

ap.extract("https://myplayer.example/embed/1")   # works already
```

Full example: `examples/05_custom_player.py`.

## Errors

Every exception inherits from `AnimeDlCoreError`:

| Exception | Raised when |
|---|---|
| `UnsupportedUrl` | the URL matches no player |
| `NetworkError` | timeout, dropped connection, unreachable proxy |
| `ServiceError` | the server answered with something unexpected (has `.status`, `.url`) |
| `ExtractionError` | a response arrived but could not be parsed — the player changed its markup |
| `NoStreamsFound` | the page parsed fine but carries no video links |
| `DecryptionError` | a Kodik link could not be decrypted |
| `ContentBlocked` | geo block, age restriction, rights holder |
| `NotFound` | no such episode / dub / release |

```python
try:
    result = ap.extract(url)
except ap.ContentBlocked:
    result = ap.extract(url, proxy="socks5://...")
except ap.AnimeDlCoreError as error:
    print("failed:", error)
```

## Tests

```bash
pip install -e ".[dev]"     # from a source checkout

pytest                                      # 86 offline tests, no network
ANIME_DL_CORE_LIVE=1 pytest -m live         # 18 live tests (bash)
$env:ANIME_DL_CORE_LIVE=1; pytest -m live   # the same in PowerShell
```

Offline tests run the parsers against real player responses saved in
`tests/fixtures/` — including a genuine encrypted Kodik response, so decryption
is exercised for real. Live tests hit the internet and may fail when a
particular title is pulled from a site; that is not a library regression, just
update the constants at the top of `tests/test_live.py`.

## How it works inside

```
src/anime_dl_core/
    __init__.py       public API
    registry.py       player registry, extract() / extract_async()
    base.py           BasePlayer: clients, URL matching, lifecycle
    models.py         Stream, PlayerResult, SkipSegment, StreamKind
    http.py           HttpClient (requests) and AsyncHttpClient (aiohttp), one Response
    utils.py          html/js parsing, m3u8, Kodik link decryption
    errors.py         exception hierarchy
    cli.py            command line
    players/          one file per player
    sources/          optional helpers (AnimeGO, Animedia, Alloha)
```

Parsing is decoupled from fetching: the sync and async methods perform the same
steps and call the same parsing functions, so they behave identically.

How the players work, briefly:

- **Aniboom** — the `<video data-parameters="...">` tag holds html-escaped json
  with the MPD and M3U8 links. The master playlist is additionally expanded into
  separate qualities.
- **CVH** — an open API: `/playlist?pub=&aggr=&id=` lists every episode and dub,
  `/video/<vkId>` returns the streams (Odnoklassniki CDN, keys such as
  `mpegHighUrl` = 720p, `mpegFullHdUrl` = 1080p).
- **Kodik** — three steps: the embed page carries `urlParams` with one-off
  signatures and `vInfo` with the id/hash; the player script hides the endpoint
  (`/ftor`) behind `atob()`; a POST with the signatures returns links encoded as
  base64 with a Caesar shift, and the shift is brute-forced and cached.
  One important detail: the `ref` parameter must be **url-decoded** — with an
  empty value the server answers 500.
- **Sibnet** — a relative mp4 link inside `player.src([...])`; the file is only
  served with a `Referer`.
- **AniLibria** — the API returns ready hls_480/720/1080 links plus opening and
  ending timecodes.
- **Animedia** — the `aser.pro/vod/<id>` page boils down to one useful line,
  `new Playerjs({file: "...index.m3u8"})`; every `file` format Playerjs
  understands is supported (a single link, `[720]url1,[360]url2`, a json
  playlist).
- **VK Video** — `video_ext.php` puts an `apiPrefetchCache` object into
  `window.cur` with a prefetched `video.get` response; its `files` hold
  `mp4_144`…`mp4_2160`, `hls_ondemand` and `dash_ondemand`. The legacy
  `var playerParams` format is the fallback.
- **SovetRomantica** — the player config at the end of the page: `var config={...}`
  with `file`/`poster`/`title`/`thumbnails` (not valid json — it contains js
  variables, so the fields are extracted one by one) and `var skips=[...]`, which
  yields the opening and the ending.

## Limitations

- Players change without warning. When something breaks, the error is specific
  (`ExtractionError` naming what was not found), and the fix is a regex in the
  corresponding `players/*.py`.
- Video links are short-lived and often bound to your IP, so caching them for
  long is pointless — fetch them right before downloading.
- Some services are unavailable from certain countries; use `proxy=`.
- The library downloads nothing by itself and bypasses no paywalls: it reads the
  same data an ordinary web player reads in a browser. What you do with it is on
  you — respect copyright and the terms of the sites you use.

## Release process

Releases are cut by CI from a `v*` tag: GitHub release with artifacts and their
SHA-256, then the upload to PyPI. The steps, and the one-time PyPI setup, are in
[`docs/releasing.md`](docs/releasing.md). Version history:
[`CHANGELOG.md`](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).
