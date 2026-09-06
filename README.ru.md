# anime-dl-core

[English](README.md) · **Русский**

[![CI](https://github.com/ialakey/anime-dl-core/actions/workflows/build.yml/badge.svg)](https://github.com/ialakey/anime-dl-core/actions/workflows/build.yml)
[![PyPI](https://img.shields.io/pypi/v/anime-dl-core)](https://pypi.org/project/anime-dl-core/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Python-библиотека для получения **прямых ссылок на видео** из аниме-плееров рунета:
Aniboom, CVH (CdnVideoHub), Kodik, Sibnet, Animedia, AniLibria, VK Video, SovetRomantica.

Библиотека занимается именно плеерами: на вход — ссылка на embed, на выходе —
список потоков (HLS / DASH / MP4) с качествами и заголовками, без которых CDN
не отдаст файл. Всё остальное (поиск, каталог, оценки) сознательно вынесено за
скобки — для этого есть отдельный необязательный помощник
[`anime_dl_core.sources.AnimeGo`](#где-взять-ссылку-на-плеер).

```python
import anime_dl_core as ap

result = ap.extract("https://aniboom.one/embed/9G1MJ6NMV8z?episode=1&translation=30")

print(result.qualities)                     # [360, 480, 720, 1080]
stream = result.best(kind="hls")            # поток 1080p
print(stream.url)                           # https://.../media_6.m3u8
print(stream.headers)                       # {'Referer': 'https://aniboom.one/', ...}
print(stream.ffmpeg_command("ep1.mp4"))     # готовая команда для скачивания
```

## Содержание

- [Поддерживаемые плееры](#поддерживаемые-плееры)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Модель данных](#модель-данных)
- [Плееры по отдельности](#плееры-по-отдельности)
- [Где взять ссылку на плеер](#где-взять-ссылку-на-плеер)
- [Alloha: каталог и iframe](#alloha-каталог-и-iframe)
- [Асинхронный режим](#асинхронный-режим)
- [Командная строка](#командная-строка)
- [Прокси, заголовки, таймауты](#прокси-заголовки-таймауты)
- [Свой плеер](#свой-плеер)
- [Ошибки](#ошибки)
- [Тесты](#тесты)
- [Как это устроено внутри](#как-это-устроено-внутри)
- [Ограничения](#ограничения)

## Поддерживаемые плееры

| Плеер | Имя в библиотеке | Что принимает на вход | Что отдаёт | Проверен вживую |
|---|---|---|---|---|
| Aniboom | `aniboom` | `https://aniboom.one/embed/<id>` или сам `<id>` | HLS (master + по качествам), DASH | ✅ |
| CVH (CdnVideoHub) | `cvh` | `/cdn-iframe/<id>/<студия>/<сезон>/<серия>` или числовой `<id>` | HLS, DASH, MP4 144p–1080p | ✅ |
| Kodik | `kodik` | `https://kodikplayer.com/seria|serial|video/<id>/<hash>/720p` | HLS и MP4 по качествам + таймкоды опенинга/эндинга | ✅ |
| Sibnet | `sibnet` | `https://video.sibnet.ru/shell.php?videoid=<id>` или `<id>` | MP4 | ✅ |
| Animedia | `animedia` | `https://aser.pro/vod/<id>` или сам `<id>` | HLS (master + по качествам) | ✅ |
| AniLibria (AniLiberty) | `anilibria` | алиас релиза (`bleach`), `bleach/3` или ссылка на серию | HLS 480/720/1080 + таймкоды | ✅ |
| VK Video | `vk` | embed, ссылка на видео или `oid_id` | MP4 144p–2160p, HLS (master + качества), DASH | ✅ |
| SovetRomantica | `sovetromantica` | `/embed/episode_<id>_<серия>-<dubbed\|subtitles>` или слаг | HLS + таймкоды, постер, превью, следующая серия | ⚠️ сайт офлайн |

«Проверен вживую» — плеер реально отдавал рабочие ссылки, и это закреплено живым
тестом (`pytest -m live`).

**SovetRomantica**: разбор проверен на настоящих страницах embed, но сам сайт
команды сейчас не работает — домен `sovetromantica.com` перешёл другому владельцу
и отдаёт посторонний контент, CDN (`scu*.sovetromantica.com`) отключён,
[команда собирает деньги на перезапуск](https://boosty.to/sovetromantica).
Поэтому в примерах и живых тестах используется настоящая страница из веб-архива,
а когда сайт вернётся — достаточно указать домен:
`SovetRomanticaPlayer(base_url="https://новый-домен")`. Свежие релизы команды
сейчас выкладываются ВКонтакте и разбираются плеером `vk`.

## Установка

```bash
pip install anime-dl-core                # обычная установка (только requests)
pip install "anime-dl-core[async]"       # + асинхронный режим (aiohttp)
pip install "anime-dl-core[socks]"       # + поддержка socks5-прокси
```

Из исходников — для разработки и тестов:

```bash
git clone https://github.com/ialakey/anime-dl-core.git
cd anime-dl-core
pip install -e ".[async,dev]"
```

Зависимость всего одна — `requests`. HTML разбирается регулярными выражениями,
поэтому ни `bs4`, ни `lxml` не нужны.

Python 3.9+.

Те же wheel и sdist приложены к каждому
[релизу](https://github.com/ialakey/anime-dl-core/releases) вместе с SHA-256
каждого файла и коммитом, из которого они собраны.

## Быстрый старт

```python
import anime_dl_core as ap

# 1. Плеер определяется по ссылке автоматически
result = ap.extract("https://kodikplayer.com/seria/1304528/932d5da818729ec5ccc9be7968ee3717/720p")

result.player          # 'kodik'
result.qualities       # [360, 480, 720]
result.translation     # '2x2'
result.skip_segments   # [SkipSegment(start=30, end=110, kind='opening'), ...]

# 2. Выбор потока
result.best()                       # максимальное качество
result.best(kind="mp4")             # только прямые файлы
result.best(max_quality=480)        # не выше 480p
result.master()                     # мастер-плейлист HLS (качество выберет плеер)
result.filter("hls", quality=720)   # список подходящих потоков

# 3. Скачивание
stream = result.best(kind="mp4")
stream.url                          # прямая ссылка
stream.headers                      # Referer/User-Agent — обязательны!
stream.ffmpeg_args("ep1.mp4")       # список аргументов для subprocess
stream.ffmpeg_command("ep1.mp4")    # то же одной строкой

# 4. Всё сразу в json
import json; print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
```

Если нужно несколько раз обратиться к одному плееру — работайте через объект
плеера, тогда переиспользуется http-сессия:

```python
with ap.AnilibriaPlayer() as player:
    for number in range(1, 13):
        print(player.extract("bleach", episode=number).best(max_quality=720).url)
```

## Модель данных

### `PlayerResult`

| Поле | Тип | Описание |
|---|---|---|
| `player` | `str` | имя плеера |
| `source_url` | `str` | что разбирали |
| `streams` | `list[Stream]` | найденные потоки |
| `title` | `str \| None` | название, если плеер его отдаёт |
| `poster` | `str \| None` | обложка |
| `duration` | `int \| None` | длительность в секундах |
| `translation` | `str \| None` | озвучка |
| `skip_segments` | `list[SkipSegment]` | опенинг/эндинг |
| `extra` | `dict` | всё специфичное для плеера |

Методы: `best()`, `filter()`, `master()`, `qualities`, `to_dict()`.
Объект итерируется по потокам и приводится к `bool` (`False`, если потоков нет).

`best(kind=None, max_quality=None, allow_master=True)` берёт поток с максимальным
качеством; при равном качестве предпочитает `mp4` (его проще скачать), затем
`hls`, затем `dash`. Мастер-плейлисты (качество неизвестно) считаются худшими и
выбираются только если других вариантов нет — `allow_master=False` исключает их
совсем.

### `Stream`

| Поле | Описание |
|---|---|
| `url` | прямая ссылка |
| `kind` | `StreamKind.HLS` / `DASH` / `MP4` |
| `quality` | высота картинки (`720`) или `None` для мастер-плейлиста |
| `headers` | заголовки, обязательные при скачивании |
| `label` | подпись (`'720p'`, `'master'`, название озвучки) |
| `extra` | битрейт, кодеки, исходный ключ ответа и т.п. |

Методы: `ffmpeg_args(output)`, `ffmpeg_command(output)`, `to_dict()`,
свойство `is_master`.

> **Заголовки — не украшение.** Sibnet, Kodik и Aniboom отдают 403 без нужного
> `Referer`. Всегда передавайте `stream.headers` в свой загрузчик:
> ```python
> requests.get(stream.url, headers=stream.headers, stream=True)
> ```
> Для yt-dlp: `yt-dlp --referer "$(...)"`, для ffmpeg — `stream.ffmpeg_args(...)`
> уже подставляет `-headers`.

### `SkipSegment`

`start`, `end` (секунды от начала файла), `kind` (`'opening'` / `'ending'`),
свойство `duration`.

## Плееры по отдельности

### Aniboom

```python
from anime_dl_core import AniboomPlayer

with AniboomPlayer() as player:
    result = player.extract(
        "https://aniboom.one/embed/9G1MJ6NMV8z?episode=1&translation=30",
        referer="https://animego.org/",   # по умолчанию именно он
        resolve_qualities=True,           # +1 запрос: развернуть master.m3u8 по качествам
    )
    print(result.qualities)               # [360, 480, 720, 1080]
    print(result.master().url)            # общий master.m3u8
    print(result.filter("dash"))          # MPD-манифест
```

Полезное: `AniboomPlayer.embed_url(video_id, episode=…, translation=…)` и
`AniboomPlayer.video_id(url)`. В `result.extra` лежат `video_id`, `max_quality`,
`thumbnails` (vtt-спрайты для превью), `rating`.

### CVH (CdnVideoHub)

```python
from anime_dl_core import CvhPlayer

with CvhPlayer() as player:
    # полный список серий и озвучек
    for episode in player.playlist("51019"):
        print(episode.season, episode.episode, episode.studio, episode.voice_type)

    # конкретная серия; название озвучки сопоставляется нестрого
    result = player.extract("51019", season=1, episode=3, studio="AniLibria")

    # если ссылка из iframe — сезон/серия/студия берутся прямо из неё
    result = player.extract("https://animego.me/cdn-iframe/51019/AnilibriaTV/1/3")
```

Видео раздаёт CDN Одноклассников, поэтому кроме HLS/DASH приходят прямые mp4 от
144p до 1080p. Параметры издателя настраиваются: `CvhPlayer(pub="747", aggr="mali")`
(значения по умолчанию — те, что использует AnimeGO).

### Kodik

```python
from anime_dl_core import KodikPlayer

with KodikPlayer() as player:
    result = player.extract(
        "https://kodikplayer.com/seria/1304528/932d5da818729ec5ccc9be7968ee3717/720p",
        # для ссылок вида /serial/... можно указать серию и сезон:
        # season=1, episode=5,
        include_mp4=True,     # добавить прямые mp4 (по умолчанию да)
    )
    print(result.best(kind="mp4").url)   # .../720.mp4
    print(result.skip_segments)          # опенинг и эндинг
```

**Токен API Kodik не нужен** — библиотека работает по ссылке на embed, которую
отдаёт сайт-агрегатор. Ссылки действуют ограниченное время (в пути есть метка
`:2026090707`), поэтому получать их нужно непосредственно перед скачиванием.

Если Kodik заблокировал ваш IP, ссылки приходят через прокси-хост `/s/m/` —
в этом случае в `result.extra["warnings"]` появится предупреждение, а лечится это
параметром `proxy=`.

### Sibnet

```python
from anime_dl_core import SibnetPlayer

with SibnetPlayer() as player:
    result = player.extract("2589828")             # можно просто id
    result = player.extract(
        "https://video.sibnet.ru/shell.php?videoid=2589828",
        resolve=True,   # сразу развернуть редирект на подписанный адрес CDN
    )
```

Без `resolve=True` возвращается стабильная ссылка `video.sibnet.ru/v/<hash>/<id>.mp4`,
которая сама редиректит на CDN — так надёжнее, потому что подписанный адрес
живёт недолго и привязан к IP.

### Animedia

```python
from anime_dl_core import AnimediaPlayer

with AnimediaPlayer() as player:
    result = player.extract("https://aser.pro/vod/20182")   # можно и просто 20182
    print(result.qualities)          # [360, 720]
    print(result.best().url)         # .../hls/720/index.m3u8
    print(result.extra)              # {'vod_id': '20182', 'slug': '...', 'episode': 1}
```

Ссылки на плеер лежат на странице тайтла amd.online — их удобно доставать
помощником [`sources.Animedia`](#где-взять-ссылку-на-плеер).

> Старые embed-ссылки `online.animedia.tv/embed/<id>/<сезон>/<серия>`, которые до
> сих пор отдают некоторые агрегаторы, не работают: домен отвечает бесконечным
> редиректом на самого себя. Актуальный адрес плеера — `aser.pro/vod/<id>`.

### AniLibria (AniLiberty)

```python
from anime_dl_core import AnilibriaPlayer

with AnilibriaPlayer() as player:
    print(player.search("Блич")[:1])                   # найти алиас релиза
    print(len(player.episodes("bleach")))              # 354
    result = player.extract("bleach", episode=2)       # или "bleach/2", или ссылку на серию
    print(result.title, result.qualities, result.skip_segments)
```

Это не embed-плеер, а открытое API `anilibria.top/api/v1` (токен не нужен).
Зеркало задаётся параметром `AnilibriaPlayer(api_base="https://aniliberty.top/api/v1")`.

### VK Video

```python
from anime_dl_core import VkPlayer

with VkPlayer() as player:
    # серия аниме в сообществе SovetRomantica ВКонтакте
    result = player.extract("https://vk.com/video_ext.php?oid=-33905270&id=456239024")

    print(result.title)         # [субтитры | 08] Гримгар из пепла и фантазий ...
    print(result.qualities)     # [144, 240, 360, 480, 720]
    print(result.duration)      # 1440
    print(result.best(kind="mp4").url)
```

Понимает все формы ссылок — их не нужно приводить руками:

```python
player.extract("https://vk.com/video_ext.php?oid=-33905270&id=456239024&hash=...")
player.extract("https://vkvideo.ru/video-33905270_456239024")
player.extract("-33905270_456239024")
VkPlayer.embed_url(-33905270, 456239024, access_key="abc")   # собрать embed вручную
```

Полезное:

* `resolve_qualities=True` (по умолчанию) — мастер-плейлист HLS разворачивается
  в отдельные качества, как у Aniboom;
* видео «только по ссылке» требует параметр `hash` из кода вставки; приватные,
  удалённые и закрытые по гео видео дают `ContentBlocked` с пояснением;
* трансляции тоже разбираются — у них только HLS, флаг `result.extra["is_live"]`.

Разбор работает и со старым форматом страницы (`var playerParams` с ключами
`url720`), который ещё встречается на зеркалах, и с актуальным
(`apiPrefetchCache` → `video.get` → `files`).

### SovetRomantica

Сайт команды сейчас офлайн (см. [таблицу выше](#поддерживаемые-плееры)), поэтому
пример — на настоящей странице embed из веб-архива:

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
result.extra["next_episode"]  # ссылка на следующую серию
result.extra["thumbnails"]    # vtt-превью для таймлайна
```

Когда сайт вернётся (или если у вас есть зеркало):

```python
with SovetRomanticaPlayer(base_url="https://новый-домен") as player:
    result = player.extract("episode_1073_1-dubbed")   # можно просто слаг
```

`base_url` заодно разрешает плееру ходить на любой хост — это нужно для зеркал,
веб-архива и локальных копий. Если страница не похожа на embed (а именно так
сейчас отвечает захваченный домен), будет `NoStreamsFound` с объяснением.

Готовый скрипт с обоими примерами: `examples/06_vk_sovetromantica.py`.

## Где взять ссылку на плеер

В комплекте есть маленький помощник для AnimeGO — он умеет ровно столько,
сколько нужно для сквозного сценария:

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
    result = site.resolve(aniboom)         # то же, что ap.extract(aniboom.embed)
```

Готовый скрипт: `examples/02_animego_pipeline.py`.

Второй помощник — сайт **Animedia** (amd.online):

```python
from anime_dl_core.sources import Animedia
import anime_dl_core as ap

with Animedia() as site:                       # Animedia(base_url="https://новый-домен")
    anime = site.search("Боруто")[0]
    print(site.info(anime.url).title)          # Боруто: Новое поколение Наруто

    episodes = site.episodes(anime.url)        # {1: 'https://aser.pro/vod/1067', ...}
    print(len(episodes))                       # 293

    print(site.players(anime.url))             # {'animedia': [...], 'kodik': [...]}

    result = ap.extract(episodes[1])           # прямые ссылки на видео
```

Помощники — вспомогательные и зависят от вёрстки сайтов; ядро библиотеки от них
не зависит, и ссылки на плееры можно брать откуда угодно.

## Alloha: каталог и iframe

Alloha (`api.alloha.tv`) — не плеер в терминах этой библиотеки, а **источник**:
по id Кинопоиска / IMDb / TMDb или по названию она отдаёт описание тайтла,
озвучки, сезоны с сериями и готовую ссылку на свой iframe.

```python
from anime_dl_core.sources import Alloha

with Alloha() as alloha:                       # Alloha(token="свой токен")
    anime = alloha.find(name="Атака титанов")  # или find(kp=749374), find(imdb="tt2560140")
    anime.name, anime.year, anime.category     # ('Атака титанов', 2013, 'сериал')
    anime.seasons                              # {1: [1..25], 2: [...], 3: [...], 4: [...]}
    [t.name for t in anime.translations]       # ['DEEP', 'Субтитры', 'Anilibria', ...]

    # у каждой серии свой набор озвучек
    voices = alloha.translations_for(anime, season=1, episode=1)
    alloha.iframe(anime, season=1, episode=1, translation=voices[0].name)
    # 'https://.../?token_movie=...&translation=10&season=1&episode=1&token=...'
```

**Прямых ссылок на видео Alloha не отдаёт.** Её плеер получает их по WebSocket
из сильно обфусцированного бандла — ни в html, ни в открытом http-API их нет.
Поэтому Alloha возвращает ссылку на iframe: её вставляют на страницу или
открывают в браузере/webview. Если нужны именно файлы, потребуется
headless-браузер — обычным разбором html это не решается.

У API есть публичный токен (`sources.alloha.PUBLIC_TOKEN`), он используется по
умолчанию. Если перестанет работать — передайте свой: `Alloha(token="...")`.

Готовый скрипт с Animedia и Alloha: `examples/07_animedia_alloha.py`.

## Асинхронный режим

```bash
pip install "anime-dl-core[async]"
```

```python
import asyncio
import anime_dl_core as ap

async def main():
    # разные плееры параллельно
    results = await asyncio.gather(
        ap.extract_async("https://aniboom.one/embed/9G1MJ6NMV8z"),
        ap.extract_async("https://video.sibnet.ru/shell.php?videoid=2589828"),
    )

    # один плеер, много серий — одна сессия на всех
    async with ap.CvhPlayer() as player:
        streams = await asyncio.gather(
            *(player.aextract("51019", episode=n, studio="AniLibria") for n in range(1, 5))
        )

asyncio.run(main())
```

У каждого плеера есть асинхронный близнец: `aextract()`, `aplaylist()`,
`arelease()`, `afetch()`. Закрывать вручную не нужно, если используете
`async with`; иначе вызовите `await player.aclose()`.

## Командная строка

```bash
anime-dl-core --list                       # какие плееры поддерживаются
anime-dl-core https://aniboom.one/embed/9G1MJ6NMV8z
anime-dl-core 51019 --player cvh --episode 2 --studio AniLibria
anime-dl-core bleach --player anilibria --episode 1 --best --max-quality 720
anime-dl-core <ссылка> --json              # машинно-читаемый вывод
anime-dl-core <ссылка> --ffmpeg ep1.mp4    # готовая команда ffmpeg
anime-dl-core <ссылка> --kind mp4 --proxy socks5://127.0.0.1:9050
anime-dl-core "https://vk.com/video_ext.php?oid=-33905270&id=456239024" --best --kind mp4
anime-dl-core -33905270_456239024 --json          # VK понимает и голый id
```

Без установки: `python -m anime_dl_core <ссылка>`.

Пример вывода:

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

## Прокси, заголовки, таймауты

Одинаково работают и в `extract()`, и в конструкторе любого плеера:

```python
ap.extract(url, proxy="socks5://user:pass@host:1080", timeout=30)
ap.extract(url, user_agent="Mozilla/5.0 ...", headers={"Accept-Language": "ru-RU"})

with ap.KodikPlayer(proxy="http://127.0.0.1:8080", timeout=15) as player:
    ...
```

Для socks5 нужен extras `[socks]`. Можно передать и готовый клиент:

```python
from anime_dl_core import HttpClient
client = HttpClient(proxy="http://127.0.0.1:8080", timeout=10)
result = ap.AniboomPlayer(client).extract(url)
```

Параметры `proxy`, `timeout`, `user_agent`, `headers`, `client` всегда уходят в
http-клиент, а всё остальное (`episode`, `season`, `studio`, `referer`,
`resolve`, `resolve_qualities`, `include_mp4`) — в конкретный плеер.

## Свой плеер

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
        playlist = search(r'file:"([^"]+\.m3u8)"', page.text, what="ссылку на m3u8")
        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=[Stream(playlist, StreamKind.HLS, None, dict(self.playback_headers))],
        )

ap.extract("https://myplayer.example/embed/1")   # уже работает
```

Полный пример: `examples/05_custom_player.py`.

## Ошибки

Все исключения наследуются от `AnimeDlCoreError`:

| Исключение | Когда |
|---|---|
| `UnsupportedUrl` | ссылка не подходит ни одному плееру |
| `NetworkError` | таймаут, обрыв, недоступный прокси |
| `ServiceError` | сервер ответил не тем (есть `.status`, `.url`) |
| `ExtractionError` | ответ пришёл, но разобрать не удалось — плеер поменял разметку |
| `NoStreamsFound` | страница разобрана, ссылок на видео нет |
| `DecryptionError` | не удалось расшифровать ссылку Kodik |
| `ContentBlocked` | гео-блок, возрастное ограничение, правообладатель |
| `NotFound` | нет такой серии/озвучки/релиза |

```python
try:
    result = ap.extract(url)
except ap.ContentBlocked:
    result = ap.extract(url, proxy="socks5://...")
except ap.AnimeDlCoreError as error:
    print("не получилось:", error)
```

## Тесты

```bash
pip install -e ".[dev]"     # из клона репозитория

pytest                                   # 86 тестов на сохранённых ответах, без сети
ANIME_DL_CORE_LIVE=1 pytest -m live      # 18 живых тестов (bash)
$env:ANIME_DL_CORE_LIVE=1; pytest -m live   # то же в PowerShell
```

Офлайн-тесты гоняют разбор на реальных ответах плееров, сохранённых в
`tests/fixtures/` (в том числе настоящий зашифрованный ответ Kodik — расшифровка
проверяется по-настоящему). Живые тесты ходят в интернет и могут падать, если
конкретное аниме убрали с сайта — это не поломка библиотеки, поправьте константы
в начале `tests/test_live.py`.

## Как это устроено внутри

```
src/anime_dl_core/
    __init__.py       публичный API
    registry.py       реестр плееров, extract() / extract_async()
    base.py           BasePlayer: клиенты, сопоставление ссылок, жизненный цикл
    models.py         Stream, PlayerResult, SkipSegment, StreamKind
    http.py           HttpClient (requests) и AsyncHttpClient (aiohttp) с общим Response
    utils.py          разбор html/js, m3u8, дешифровка ссылок Kodik
    errors.py         иерархия исключений
    cli.py            командная строка
    players/          по файлу на плеер
    sources/          необязательные помощники (AnimeGO, Animedia, Alloha)
```

Разбор каждого плеера отделён от способа запроса: синхронный и асинхронный
методы делают одинаковые шаги и вызывают одни и те же функции разбора, поэтому
поведение у них совпадает.

Коротко о механике плееров:

- **Aniboom** — в теге `<video data-parameters="...">` лежит html-экранированный
  json со ссылками на MPD и M3U8. Мастер-плейлист дополнительно разворачивается
  в отдельные качества.
- **CVH** — открытое API: `/playlist?pub=&aggr=&id=` отдаёт все серии и озвучки,
  `/video/<vkId>` — ссылки на потоки (CDN Одноклассников, ключи вида
  `mpegHighUrl` = 720p, `mpegFullHdUrl` = 1080p).
- **Kodik** — три шага: страница embed отдаёт `urlParams` с одноразовыми
  подписями и `vInfo` с id/hash; в скрипте плеера через `atob()` спрятан адрес
  ручки (`/ftor`); POST с подписями возвращает ссылки, зашифрованные base64 со
  сдвигом (шифр Цезаря), сдвиг подбирается перебором и кэшируется.
  Важная деталь: параметр `ref` должен быть **раскодированным** — с пустым
  значением сервер отвечает 500.
- **Sibnet** — относительная ссылка на mp4 в `player.src([...])`, файл отдаётся
  только с `Referer`.
- **AniLibria** — API отдаёт готовые hls_480/720/1080 и таймкоды опенинга/эндинга.
- **Animedia** — страница `aser.pro/vod/<id>` состоит из одной полезной строки
  `new Playerjs({file: "...index.m3u8"})`; разбираются все форматы `file`, которые
  понимает Playerjs (одна ссылка, `[720]url1,[360]url2`, json-плейлист).
- **VK Video** — страница `video_ext.php` кладёт в `window.cur` объект
  `apiPrefetchCache` с предзагруженным ответом метода `video.get`; в нём `files`
  со ссылками `mp4_144`…`mp4_2160`, `hls_ondemand`, `dash_ondemand`. Старый
  формат `var playerParams` разбирается как запасной вариант.
- **SovetRomantica** — js-конфиг плеера в конце страницы: `var config={...}` с
  полями `file`/`poster`/`title`/`thumbnails` (это не валидный json — внутри есть
  js-переменные, поэтому поля достаются по отдельности) и `var skips=[...]`,
  откуда получаются опенинг и эндинг.

## Ограничения

- Плееры меняются без предупреждения. Если что-то перестало работать, ошибка
  будет говорящей (`ExtractionError` с указанием, что именно не нашлось), а
  чинить нужно регулярки в соответствующем файле `players/*.py`.
- Ссылки на видео живут ограниченное время и часто привязаны к IP, поэтому их
  бессмысленно кэшировать надолго — получайте перед скачиванием.
- Часть сервисов недоступна из некоторых стран — используйте `proxy=`.
- Библиотека ничего не скачивает сама и не обходит платные ограничения: она лишь
  читает те же данные, что и обычный веб-плеер в браузере. Ответственность за
  использование лежит на вас; уважайте авторские права и правила сайтов.

## Как выпускается релиз

Релизы собирает CI по тегу `v*`: релиз на GitHub с артефактами и их SHA-256,
затем загрузка на PyPI. Порядок действий и разовая настройка PyPI —
в [`docs/releasing.md`](docs/releasing.md). История версий:
[`CHANGELOG.ru.md`](CHANGELOG.ru.md).

## Лицензия

MIT — см. [LICENSE](LICENSE).
