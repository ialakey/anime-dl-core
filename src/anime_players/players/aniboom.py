"""Плеер Aniboom (aniboom.one) — основной плеер AnimeGO.

Как устроен: страница embed содержит тег ``<video id="video" data-parameters="...">``,
в атрибуте лежит html-экранированный json со ссылками на MPD (DASH) и M3U8 (HLS),
постером, длительностью и максимальным качеством.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..base import BasePlayer, compile_patterns
from ..errors import ContentBlocked, ExtractionError, NoStreamsFound
from ..http import Response
from ..models import PlayerResult, Stream, StreamKind
from ..utils import json_from_attribute, parse_master_playlist, search, to_int

__all__ = ["AniboomPlayer"]

_VIDEO_TAG = re.compile(r'<video[^>]*\bdata-parameters="([^"]+)"', re.IGNORECASE)
_ID_FROM_URL = re.compile(r"/embed/([A-Za-z0-9_-]+)")


class AniboomPlayer(BasePlayer):
    """Плеер Aniboom.

    Пример::

        from anime_players import AniboomPlayer

        with AniboomPlayer() as player:
            result = player.extract("https://aniboom.one/embed/9G1MJ6NMV8z?episode=1&translation=30")
            print(result.best(kind="hls"))
    """

    name = "aniboom"
    title = "Aniboom"
    domains = ("aniboom.one", "aniboom.tv")
    url_patterns = compile_patterns(r"aniboom\.[a-z]+/embed/")
    embed_base = "https://aniboom.one/embed/"
    #: Referer по умолчанию — без него aniboom отдаёт заглушку.
    default_referer = "https://animego.org/"
    playback_headers = {"Referer": "https://aniboom.one/", "Origin": "https://aniboom.one"}

    # -- публичный интерфейс -------------------------------------------
    @classmethod
    def embed_url(cls, video_id: str, *, episode: Optional[int] = None, translation: Optional[int] = None) -> str:
        """Собирает ссылку на embed по id видео."""
        url = f"{cls.embed_base}{video_id}"
        params = []
        if episode is not None:
            params.append(f"episode={episode}")
        if translation is not None:
            params.append(f"translation={translation}")
        return url + ("?" + "&".join(params) if params else "")

    @staticmethod
    def video_id(url: str) -> str:
        """Достаёт id видео из ссылки на embed."""
        return search(_ID_FROM_URL, url, what="id видео в ссылке Aniboom")

    def extract(
        self,
        url: str,
        *,
        referer: Optional[str] = None,
        resolve_qualities: bool = True,
        **_: Any,
    ) -> PlayerResult:
        """Разбирает embed-страницу Aniboom.

        :param url: ссылка вида ``https://aniboom.one/embed/<id>`` (можно с параметрами
            ``?episode=&translation=``) либо просто ``<id>``.
        :param referer: сайт, с которого якобы открыт плеер (по умолчанию animego.org).
        :param resolve_qualities: скачать мастер-плейлист HLS и добавить потоки
            по каждому качеству отдельно (одиин дополнительный запрос).
        """
        url = self._normalize(url)
        resp = self.client.get(url, headers={"Referer": referer or self.default_referer})
        data = self._parse_page(resp, url)
        result = self._build_result(url, data)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = self.client.get(master.url, headers=master.headers)
                if content.ok:
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
        resp = await self.async_client.get(url, headers={"Referer": referer or self.default_referer})
        data = self._parse_page(resp, url)
        result = self._build_result(url, data)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = await self.async_client.get(master.url, headers=master.headers)
                if content.ok:
                    result.streams.extend(self._variant_streams(content.text, master))
        return result

    # -- разбор ---------------------------------------------------------
    def _normalize(self, url: str) -> str:
        if "/" not in url:  # передали только id видео
            return self.embed_url(url)
        return self.ensure_matches(url)

    @staticmethod
    def _parse_page(resp: Response, url: str) -> Dict[str, Any]:
        resp.raise_for_status()
        raw = search(_VIDEO_TAG, resp.text, what="тег <video data-parameters> на странице Aniboom", default=None)
        if raw is None:
            if "не доступно" in resp.text or "video-error" in resp.text:
                raise ContentBlocked(f"Aniboom не отдаёт видео (гео-блокировка или удалено): {url}")
            raise ExtractionError(
                f"На странице Aniboom нет тега <video data-parameters=...>: {url}. "
                "Возможно, изменилась разметка плеера."
            )
        return json_from_attribute(raw)

    def _headers(self) -> Dict[str, str]:
        headers = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]
        return headers

    @staticmethod
    def _src(value: Any) -> Optional[str]:
        """Значения hls/dash приходят как json-строка ``{"src": "...", "type": "..."}``."""
        if not value:
            return None
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return value if value.startswith("http") else None
        if isinstance(value, dict):
            return value.get("src")
        return None

    def _build_result(self, url: str, data: Dict[str, Any]) -> PlayerResult:
        headers = self._headers()
        streams: List[Stream] = []

        for key, kind in (("hls", StreamKind.HLS), ("dash", StreamKind.DASH),
                          ("fallbackHls", StreamKind.HLS), ("fallbackDash", StreamKind.DASH)):
            src = self._src(data.get(key))
            if src:
                streams.append(
                    Stream(
                        url=src,
                        kind=kind,
                        quality=None,
                        headers=headers,
                        label="fallback" if key.startswith("fallback") else "master",
                        extra={"source": key},
                    )
                )

        if not streams:
            raise NoStreamsFound(f"Aniboom не вернул ни hls, ни dash для {url}. Данные плеера: {data}")

        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=streams,
            poster=data.get("poster"),
            duration=to_int(data.get("duration")),
            extra={
                "video_id": data.get("id"),
                "max_quality": to_int(data.get("qualityVideo")),
                "thumbnails": data.get("thumbnails"),
                "rating": data.get("rating"),
                "domain": data.get("domain"),
                "country": data.get("country"),
            },
        )

    def _variant_streams(self, master_content: str, master: Stream) -> List[Stream]:
        """Разворачивает мастер-плейлист в отдельные потоки по качествам."""
        streams = []
        for variant in parse_master_playlist(master_content, master.url):
            streams.append(
                Stream(
                    url=variant["url"],
                    kind=StreamKind.HLS,
                    quality=variant["height"],
                    headers=master.headers,
                    label=f"{variant['height']}p" if variant["height"] else None,
                    extra={"bandwidth": variant["bandwidth"], "codecs": variant["codecs"]},
                )
            )
        return streams
