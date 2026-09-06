"""Плеер Sibnet (video.sibnet.ru).

Как устроен: на странице ``shell.php?videoid=<id>`` в js-коде плеера лежит
относительная ссылка на mp4 (``player.src([{src: "/v/<hash>/<id>.mp4"}])``).
Файл отдаётся только с заголовком ``Referer: https://video.sibnet.ru/``,
а сама ссылка редиректит на подписанный адрес CDN.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..base import BasePlayer, compile_patterns
from ..errors import NoStreamsFound
from ..models import PlayerResult, Stream, StreamKind
from ..utils import absolute_url, search

__all__ = ["SibnetPlayer"]

_SRC_RE = re.compile(r'player\.src\(\s*\[\s*\{\s*src\s*:\s*["\']([^"\']+)["\']', re.IGNORECASE)
_FALLBACK_SRC_RE = re.compile(r'["\'](/v/[^"\']+\.(?:mp4|m3u8))["\']', re.IGNORECASE)
_TITLE_RE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', re.IGNORECASE)
_POSTER_RE = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', re.IGNORECASE)
_ID_RE = re.compile(r"(?:videoid=|/video)(\d+)", re.IGNORECASE)


class SibnetPlayer(BasePlayer):
    """Плеер Sibnet.

    Пример::

        with SibnetPlayer() as player:
            result = player.extract("https://video.sibnet.ru/shell.php?videoid=2589828")
            stream = result.best()
            print(stream.url, stream.headers)   # Referer обязателен!
    """

    name = "sibnet"
    title = "Sibnet"
    domains = ("sibnet.ru", "video.sibnet.ru")
    url_patterns = compile_patterns(r"sibnet\.ru/(?:shell\.php|video)")
    base_url = "https://video.sibnet.ru"
    playback_headers = {"Referer": "https://video.sibnet.ru/"}

    @classmethod
    def embed_url(cls, video_id: Any) -> str:
        """Ссылка на плеер по числовому id видео."""
        return f"{cls.base_url}/shell.php?videoid={video_id}"

    @staticmethod
    def video_id(url: str) -> Optional[str]:
        """Числовой id видео из ссылки."""
        return search(_ID_RE, str(url), what="id видео Sibnet", default=None)

    def extract(self, url: str, *, resolve: bool = False, **_: Any) -> PlayerResult:
        """Возвращает прямую ссылку на mp4.

        :param url: ссылка на плеер или просто числовой id видео.
        :param resolve: заранее пройти по редиректу и вернуть подписанный адрес CDN.
            Такая ссылка живёт недолго и привязана к IP, поэтому по умолчанию
            возвращается стабильный адрес ``video.sibnet.ru/v/...``.
        """
        url = self._normalize(url)
        page = self.client.get(url, headers={"Referer": self.base_url + "/"})
        result = self._build_result(page.raise_for_status().text, url)
        if resolve:
            for index, stream in enumerate(result.streams):
                direct = self.client.resolve_redirect(stream.url, headers=stream.headers)
                result.streams[index] = _with_url(stream, direct)
        return result

    async def aextract(self, url: str, *, resolve: bool = False, **_: Any) -> PlayerResult:
        url = self._normalize(url)
        page = await self.async_client.get(url, headers={"Referer": self.base_url + "/"})
        result = self._build_result(page.raise_for_status().text, url)
        if resolve:
            for index, stream in enumerate(result.streams):
                direct = await self.async_client.resolve_redirect(stream.url, headers=stream.headers)
                result.streams[index] = _with_url(stream, direct)
        return result

    # -- внутреннее -------------------------------------------------------
    def _normalize(self, url: str) -> str:
        url = str(url).strip()
        if url.isdigit():
            return self.embed_url(url)
        if url.startswith("//"):
            url = "https:" + url
        return self.ensure_matches(url)

    def _build_result(self, text: str, url: str) -> PlayerResult:
        src = search(_SRC_RE, text, what="ссылку на файл в плеере Sibnet", default=None)
        if not src:
            src = search(_FALLBACK_SRC_RE, text, what="ссылку на файл в плеере Sibnet", default=None)
        if not src:
            raise NoStreamsFound(
                f"На странице Sibnet не найдено ссылки на видео: {url}. "
                "Видео могло быть удалено или заблокировано."
            )

        headers: Dict[str, str] = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]
        direct = absolute_url(self.base_url + "/", src)
        kind = StreamKind.HLS if direct.endswith(".m3u8") else StreamKind.MP4
        streams: List[Stream] = [Stream(direct, kind, None, headers, "original")]

        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=streams,
            title=search(_TITLE_RE, text, what="название", default=None),
            poster=search(_POSTER_RE, text, what="постер", default=None),
            extra={"video_id": self.video_id(url)},
        )


def _with_url(stream: Stream, url: str) -> Stream:
    extra = dict(stream.extra)
    extra["original_url"] = stream.url
    return Stream(url, stream.kind, stream.quality, stream.headers, stream.label, extra)
