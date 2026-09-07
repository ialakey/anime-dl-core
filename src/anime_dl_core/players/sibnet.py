"""The Sibnet player (video.sibnet.ru).

How it works: the ``shell.php?videoid=<id>`` page carries a relative mp4 link in
the player js (``player.src([{src: "/v/<hash>/<id>.mp4"}])``).
The file is only served with a ``Referer: https://video.sibnet.ru/`` header, and
the link itself redirects to a signed CDN address.
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
    """The Sibnet player.

    Example::

        with SibnetPlayer() as player:
            result = player.extract("https://video.sibnet.ru/shell.php?videoid=2589828")
            stream = result.best()
            print(stream.url, stream.headers)   # the Referer is mandatory!
    """

    name = "sibnet"
    title = "Sibnet"
    domains = ("sibnet.ru", "video.sibnet.ru")
    url_patterns = compile_patterns(r"sibnet\.ru/(?:shell\.php|video)")
    base_url = "https://video.sibnet.ru"
    playback_headers = {"Referer": "https://video.sibnet.ru/"}

    @classmethod
    def embed_url(cls, video_id: Any) -> str:
        """Player url for a numeric video id."""
        return f"{cls.base_url}/shell.php?videoid={video_id}"

    @staticmethod
    def video_id(url: str) -> Optional[str]:
        """The numeric video id taken from a url."""
        return search(_ID_RE, str(url), what="the Sibnet video id", default=None)

    def extract(self, url: str, *, resolve: bool = False, **_: Any) -> PlayerResult:
        """Returns the direct mp4 link.

        :param url: a player url, or just the numeric video id.
        :param resolve: follow the redirect up front and return the signed CDN address.
            That link is short-lived and bound to your IP, so by default the stable
            ``video.sibnet.ru/v/...`` address is returned instead.
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

    # -- internals ---------------------------------------------------------
    def _normalize(self, url: str) -> str:
        url = str(url).strip()
        if url.isdigit():
            return self.embed_url(url)
        if url.startswith("//"):
            url = "https:" + url
        return self.ensure_matches(url)

    def _build_result(self, text: str, url: str) -> PlayerResult:
        src = search(_SRC_RE, text, what="the file link in the Sibnet player", default=None)
        if not src:
            src = search(_FALLBACK_SRC_RE, text, what="the file link in the Sibnet player", default=None)
        if not src:
            raise NoStreamsFound(
                f"No video link was found on the Sibnet page: {url}. "
                "The video may have been removed or blocked."
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
            title=search(_TITLE_RE, text, what="the title", default=None),
            poster=search(_POSTER_RE, text, what="the poster", default=None),
            extra={"video_id": self.video_id(url)},
        )


def _with_url(stream: Stream, url: str) -> Stream:
    extra = dict(stream.extra)
    extra["original_url"] = stream.url
    return Stream(url, stream.kind, stream.quality, stream.headers, stream.label, extra)
