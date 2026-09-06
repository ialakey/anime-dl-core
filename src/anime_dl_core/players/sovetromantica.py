"""Плеер SovetRomantica (страницы вида ``/embed/episode_<id>_<серия>-<dubbed|subtitles>``).

Как устроен: в конце embed-страницы лежит js-конфиг плеера::

    var nextEpisode='https://sovetromantica.com/embed/episode_1073_2-dubbed';
    var skips = [ { 'start': 174.79, 'end': 184.79, 'skip_to': 262.92 }, ... ];
    var config={
        "id":"sovetromantica_player",
        "file":"https://scu2.sovetromantica.com/anime/.../episode_1.m3u8",
        "poster":"https://scu2.sovetromantica.com/anime/.../episode_1_dub.jpg",
        "thumbnails":"https://scu2.sovetromantica.com/anime/.../episode_1.vtt",
        "title":"Gekkan Shoujo Nozaki-kun - Озвучка - Эпизод 1",
        "points": points
    };

Конфиг — не валидный json (в нём есть js-переменные), поэтому поля достаются
по отдельности регулярками. Из ``skips`` получаются опенинг и эндинг.

.. warning::
   Собственный сайт SovetRomantica с 2025 года не работает: домен
   ``sovetromantica.com`` перешёл другому владельцу и отдаёт чужой контент, а
   CDN (``scu*.sovetromantica.com``) не резолвится. Команда собирает деньги на
   перезапуск. Поэтому:

   * разбор проверен на настоящих страницах из веб-архива (см. живые тесты);
   * когда сайт вернётся (или если у вас есть зеркало), укажите домен:
     ``SovetRomanticaPlayer(base_url="https://новый-домен")`` — тогда плеер
     примет ссылку на любой хост;
   * свежие релизы SovetRomantica сейчас лежат в их сообществе ВКонтакте и
     разбираются плеером :class:`~anime_dl_core.players.vk.VkPlayer`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..base import BasePlayer, compile_patterns
from ..errors import NoStreamsFound
from ..models import PlayerResult, SkipSegment, Stream, StreamKind
from ..utils import parse_master_playlist, search, url_host

__all__ = ["SovetRomanticaPlayer"]

_CONFIG_FIELD = '"{}"\\s*:\\s*"([^"]+)"'
_ANY_M3U8 = re.compile(r'(https?://[^"\'\s\\]+\.m3u8[^"\'\s\\]*)', re.IGNORECASE)
_SOURCE_TAG = re.compile(r'<source[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_SKIPS_BLOCK = re.compile(r"var\s+skips\s*=\s*\[(.*?)\]\s*;", re.DOTALL)
_SKIP_ITEM = re.compile(
    r"['\"]start['\"]\s*:\s*([\d.]+).*?['\"]end['\"]\s*:\s*([\d.]+)"
    r"(?:.*?['\"]skip_to['\"]\s*:\s*([\d.]+))?",
    re.DOTALL,
)
_NEXT_EPISODE = re.compile(r"var\s+nextEpisode\s*=\s*['\"]([^'\"]*)['\"]")
_EPISODE_SLUG = re.compile(r"/embed/(episode_[A-Za-z0-9_\-]+)", re.IGNORECASE)


class SovetRomanticaPlayer(BasePlayer):
    """Плеер SovetRomantica.

    Пример (сайт лежит, поэтому берём настоящую страницу из веб-архива)::

        from anime_dl_core import SovetRomanticaPlayer

        archive = "https://web.archive.org/web/20240905174049id_/"
        with SovetRomanticaPlayer(base_url="https://web.archive.org") as player:
            result = player.extract(archive + "https://sovetromantica.com/embed/episode_1073_1-dubbed")
            print(result.title)              # Gekkan Shoujo Nozaki-kun - Озвучка - Эпизод 1
            print(result.best().url)         # https://scu2.sovetromantica.com/.../episode_1.m3u8
            print(result.skip_segments)      # опенинг и эндинг

    Когда сайт вернётся::

        with SovetRomanticaPlayer(base_url="https://новый-домен") as player:
            result = player.extract("episode_1073_1-dubbed")
    """

    name = "sovetromantica"
    title = "SovetRomantica"
    domains = ("sovetromantica.com",)
    url_patterns = compile_patterns(r"sovetromantica\.[a-z]+/embed/")
    verified = True
    note = (
        "сайт офлайн (домен перешёл другому владельцу); разбор проверен на страницах "
        "из веб-архива, для зеркала укажите base_url"
    )
    base_url = "https://sovetromantica.com"
    playback_headers = {"Referer": "https://sovetromantica.com/"}

    def __init__(self, *args: Any, base_url: Optional[str] = None, **kwargs: Any) -> None:
        """
        :param base_url: адрес сайта, если он переехал или это зеркало/веб-архив.
            Если параметр задан, плеер принимает ссылку на любой хост.
        """
        super().__init__(*args, **kwargs)
        self.custom_base = bool(base_url)
        if base_url:
            self.base_url = base_url.rstrip("/")
            self.playback_headers = {"Referer": self.base_url + "/"}

    # -- публичный интерфейс ------------------------------------------------
    def embed_url(self, episode_slug: str) -> str:
        """``episode_1073_1-dubbed`` -> полная ссылка на embed."""
        return f"{self.base_url}/embed/{episode_slug}"

    @staticmethod
    def episode_slug(url: str) -> Optional[str]:
        """Слаг эпизода из ссылки (``episode_1073_1-dubbed``)."""
        return search(_EPISODE_SLUG, str(url), what="слаг эпизода", default=None)

    def extract(self, url: str, *, resolve_qualities: bool = False, **_: Any) -> PlayerResult:
        """Возвращает HLS-поток эпизода.

        :param url: ссылка на embed или слаг вида ``episode_1073_1-dubbed``.
        :param resolve_qualities: развернуть мастер-плейлист по качествам
            (дополнительный запрос; молча пропускается, если CDN недоступен).
        """
        url = self._normalize(url)
        page = self.client.get(url, headers={"Referer": self.base_url + "/"})
        result = self._build_result(page.raise_for_status().text, url)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = self.client.get(master.url, headers=master.headers)
                if content.ok and "#EXT-X-STREAM-INF" in content.text:
                    result.streams.extend(self._variant_streams(content.text, master))
        return result

    async def aextract(self, url: str, *, resolve_qualities: bool = False, **_: Any) -> PlayerResult:
        url = self._normalize(url)
        page = await self.async_client.get(url, headers={"Referer": self.base_url + "/"})
        result = self._build_result(page.raise_for_status().text, url)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = await self.async_client.get(master.url, headers=master.headers)
                if content.ok and "#EXT-X-STREAM-INF" in content.text:
                    result.streams.extend(self._variant_streams(content.text, master))
        return result

    # -- внутреннее ---------------------------------------------------------
    def _normalize(self, url: str) -> str:
        url = str(url).strip()
        if url.startswith("episode_"):
            return self.embed_url(url)
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("http"):
            return self.embed_url(url.lstrip("/").replace("embed/", ""))
        # со своим base_url разрешаем любой хост: зеркало, локальный сервер, веб-архив
        if self.custom_base or url_host(url) == url_host(self.base_url):
            return url
        return self.ensure_matches(url)

    def _variant_streams(self, master_content: str, master: Stream) -> List[Stream]:
        return [
            Stream(
                variant["url"],
                StreamKind.HLS,
                variant["height"],
                master.headers,
                f"{variant['height']}p" if variant["height"] else None,
                extra={"bandwidth": variant["bandwidth"], "codecs": variant["codecs"]},
            )
            for variant in parse_master_playlist(master_content, master.url)
        ]

    def _build_result(self, text: str, url: str) -> PlayerResult:
        playlist = self._field(text, "file")
        if not playlist:
            playlist = search(_ANY_M3U8, text, what="ссылку на m3u8", default=None)
        if not playlist:
            source = search(_SOURCE_TAG, text, what="тег <source>", default=None)
            playlist = source if source and ".m3u8" in source else None
        if not playlist:
            raise NoStreamsFound(
                f"На странице не найден плейлист SovetRomantica: {url}. "
                "Проверьте, что это действительно страница embed: домен sovetromantica.com "
                "сейчас принадлежит другому владельцу и отдаёт посторонний сайт. "
                "Для зеркала или архива используйте SovetRomanticaPlayer(base_url=...)."
            )

        playlist = playlist.replace("\\/", "/")
        headers: Dict[str, str] = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]

        title = self._field(text, "title")
        slug = self.episode_slug(url)
        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=[Stream(playlist, StreamKind.HLS, None, headers, "master")],
            title=title,
            poster=self._field(text, "poster"),
            translation=_translation_from_slug(slug) or _translation_from_title(title),
            skip_segments=_parse_skips(text),
            extra={
                "episode": slug,
                "thumbnails": self._field(text, "thumbnails"),
                "next_episode": search(_NEXT_EPISODE, text, what="следующий эпизод", default=None) or None,
            },
        )

    @staticmethod
    def _field(text: str, name: str) -> Optional[str]:
        value = search(_CONFIG_FIELD.format(name), text, what=f"поле {name}", default=None)
        return value.replace("\\/", "/") if value else None


def _parse_skips(text: str) -> List[SkipSegment]:
    """``var skips = [ {'start': 174.7, 'end': 184.7, 'skip_to': 262.9}, ... ]``.

    ``start``–``end`` — когда показывать кнопку, ``skip_to`` — куда она перематывает,
    то есть пропускаемый фрагмент это ``start``–``skip_to``.
    """
    block = search(_SKIPS_BLOCK, text, what="таймкоды", default=None)
    if not block:
        return []
    segments: List[SkipSegment] = []
    for index, item in enumerate(_SKIP_ITEM.finditer(block)):
        start = float(item.group(1))
        end = float(item.group(3) or item.group(2))
        segments.append(SkipSegment(int(start), int(end), "opening" if index == 0 else "ending"))
    if len(segments) == 2 and segments[0].start > segments[1].start:
        segments = [
            SkipSegment(segments[1].start, segments[1].end, "opening"),
            SkipSegment(segments[0].start, segments[0].end, "ending"),
        ]
    return segments


def _translation_from_slug(slug: Optional[str]) -> Optional[str]:
    if not slug:
        return None
    if slug.endswith("-dubbed"):
        return "Озвучка SovetRomantica"
    if slug.endswith("-subtitles"):
        return "Субтитры SovetRomantica"
    return None


def _translation_from_title(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    if "Озвучка" in title:
        return "Озвучка SovetRomantica"
    if "Субтитры" in title:
        return "Субтитры SovetRomantica"
    return None
