"""Плеер Animedia — ``aser.pro/vod/<id>`` (сайт amd.online, бывший animedia.tv).

Как устроен: страница плеера почти пустая, весь смысл в одной строке::

    var player = new Playerjs({
        id: "videoplayer20182",
        file: "https://aser.pro/content/stream/<slug>/<NNN>_<vod_id>/hls/index.m3u8"
    });

``file`` — это либо ссылка на мастер-плейлист HLS, либо запись Playerjs с
несколькими качествами (``[720]url1,[360]url2``), либо json-плейлист.
Поддерживаются все три варианта.

.. note::
   Старые embed-ссылки ``online.animedia.tv/embed/<id>/<сезон>/<серия>``
   (их до сих пор отдают некоторые агрегаторы) не работают: домен отвечает
   бесконечным редиректом на самого себя. Рабочие ссылки на плеер лежат на
   странице тайтла amd.online — их удобно доставать помощником
   :class:`anime_dl_core.sources.Animedia`.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..base import BasePlayer, compile_patterns
from ..errors import NoStreamsFound
from ..models import PlayerResult, Stream, StreamKind
from ..utils import absolute_url, parse_master_playlist, quality_from_label, search

__all__ = ["AnimediaPlayer"]

_PLAYERJS_FILE = re.compile(r"""file\s*:\s*(['"])(.*?)\1""", re.DOTALL)
_VOD_ID = re.compile(r"/vod/(\d+)")
#: ``.../content/stream/<slug>/<номер>_<vod_id>/hls/index.m3u8``
_STREAM_PATH = re.compile(r"/content/stream/([^/]+)/(\d+)_(\d+)/", re.IGNORECASE)
#: запись Playerjs с несколькими качествами: ``[720]https://...,[360]https://...``
_LABELLED = re.compile(r"\[([^\]]+)\]([^,]+)")


class AnimediaPlayer(BasePlayer):
    """Плеер Animedia (aser.pro).

    Пример::

        from anime_dl_core import AnimediaPlayer

        with AnimediaPlayer() as player:
            result = player.extract("https://aser.pro/vod/20182")   # можно и просто 20182
            print(result.qualities)      # [360, 720]
            print(result.best().url)
    """

    name = "animedia"
    title = "Animedia (aser.pro)"
    domains = ("aser.pro", "animedia.tv", "amd.online")
    url_patterns = compile_patterns(r"aser\.pro/vod/\d+", r"animedia\.[a-z]+/embed/")
    note = "старые ссылки online.animedia.tv/embed/... не работают, актуальные — aser.pro/vod/<id>"
    base_url = "https://aser.pro"
    site_url = "https://amd.online"
    playback_headers = {"Referer": "https://aser.pro/"}

    # -- публичный интерфейс ------------------------------------------------
    @classmethod
    def embed_url(cls, vod_id: Any) -> str:
        """Ссылка на плеер по числовому id."""
        return f"{cls.base_url}/vod/{vod_id}"

    @staticmethod
    def vod_id(url: str) -> Optional[str]:
        """Числовой id плеера из ссылки."""
        return search(_VOD_ID, str(url), what="id видео Animedia", default=None)

    def extract(
        self,
        url: str,
        *,
        referer: Optional[str] = None,
        resolve_qualities: bool = True,
        **_: Any,
    ) -> PlayerResult:
        """Возвращает потоки серии.

        :param url: ссылка ``https://aser.pro/vod/<id>`` или просто ``<id>``.
        :param referer: Referer запроса (по умолчанию сайт amd.online).
        :param resolve_qualities: развернуть мастер-плейлист HLS по качествам.
        """
        url = self._normalize(url)
        page = self.client.get(url, headers={"Referer": referer or self.site_url + "/"})
        result = self._build_result(page.raise_for_status().text, url)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = self.client.get(master.url, headers=master.headers)
                if content.ok and "#EXT-X-STREAM-INF" in content.text:
                    result.streams.extend(self._variant_streams(content.text, master))
        return result

    async def aextract(
        self,
        url: str,
        *,
        referer: Optional[str] = None,
        resolve_qualities: bool = True,
        **_: Any,
    ) -> PlayerResult:
        url = self._normalize(url)
        page = await self.async_client.get(url, headers={"Referer": referer or self.site_url + "/"})
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
        if url.isdigit():
            return self.embed_url(url)
        if url.startswith("//"):
            url = "https:" + url
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
        raw = search(_PLAYERJS_FILE, text, group=2, what="параметр file плеера Playerjs", default=None)
        if not raw:
            raise NoStreamsFound(
                f"На странице Animedia не найден параметр file плеера: {url}. "
                "Проверьте ссылку: рабочий адрес выглядит как https://aser.pro/vod/<id>."
            )

        headers: Dict[str, str] = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]
        streams = _streams_from_playerjs(raw.replace("\\/", "/"), url, headers)
        if not streams:
            raise NoStreamsFound(f"Playerjs на странице Animedia не отдал ни одной ссылки: {url}")

        path = _STREAM_PATH.search(streams[0].url)
        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=streams,
            extra={
                "vod_id": self.vod_id(url),
                "slug": path.group(1) if path else None,
                "episode": int(path.group(2)) if path else None,
            },
        )


def _streams_from_playerjs(value: str, base_url: str, headers: Dict[str, str]) -> List[Stream]:
    """Разбирает значение ``file`` во всех форматах, которые понимает Playerjs."""
    value = value.strip()

    # 1. json-плейлист: [{"title": "1 серия", "file": "..."}, ...]
    if value.startswith("["):
        try:
            items = json.loads(value)
        except ValueError:
            items = None
        if isinstance(items, list):
            streams: List[Stream] = []
            for item in items:
                if isinstance(item, dict) and item.get("file"):
                    streams.extend(
                        _streams_from_playerjs(str(item["file"]), base_url, headers)
                    )
            if streams:
                return streams

    # 2. несколько качеств: [720]url1,[360]url2
    labelled = _LABELLED.findall(value)
    if labelled:
        streams = []
        for label, link in labelled:
            link = absolute_url(base_url, link.strip())
            streams.append(Stream(link, _kind(link), quality_from_label(label), headers, label.strip()))
        streams.sort(key=lambda stream: stream.quality or 0)
        return streams

    # 3. обычная ссылка
    link = absolute_url(base_url, value)
    if not link.startswith("http"):
        return []
    return [Stream(link, _kind(link), None, headers, "master" if link.endswith(".m3u8") else None)]


def _kind(url: str) -> StreamKind:
    if ".m3u8" in url:
        return StreamKind.HLS
    if ".mpd" in url:
        return StreamKind.DASH
    return StreamKind.MP4
