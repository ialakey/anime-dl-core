"""The Aniboom player (aniboom.one) — the player AnimeGO uses by default.

How it works: the embed page carries a ``<video id="video" data-parameters="...">``
tag whose attribute holds html-escaped json with the MPD (DASH) and M3U8 (HLS)
links, the poster, the duration and the highest quality on offer.
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
    """The Aniboom player.

    Example::

        from anime_dl_core import AniboomPlayer

        with AniboomPlayer() as player:
            result = player.extract("https://aniboom.one/embed/9G1MJ6NMV8z?episode=1&translation=30")
            print(result.best(kind="hls"))
    """

    name = "aniboom"
    title = "Aniboom"
    domains = ("aniboom.one", "aniboom.tv")
    url_patterns = compile_patterns(r"aniboom\.[a-z]+/embed/")
    embed_base = "https://aniboom.one/embed/"
    #: Default Referer — without it aniboom serves a placeholder.
    default_referer = "https://animego.org/"
    playback_headers = {"Referer": "https://aniboom.one/", "Origin": "https://aniboom.one"}

    # -- public interface ----------------------------------------------
    @classmethod
    def embed_url(cls, video_id: str, *, episode: Optional[int] = None, translation: Optional[int] = None) -> str:
        """Builds the embed url from a video id."""
        url = f"{cls.embed_base}{video_id}"
        params = []
        if episode is not None:
            params.append(f"episode={episode}")
        if translation is not None:
            params.append(f"translation={translation}")
        return url + ("?" + "&".join(params) if params else "")

    @staticmethod
    def video_id(url: str) -> str:
        """Pulls the video id out of an embed url."""
        return search(_ID_FROM_URL, url, what="the video id in the Aniboom url")

    def extract(
        self,
        url: str,
        *,
        referer: Optional[str] = None,
        resolve_qualities: bool = True,
        **_: Any,
    ) -> PlayerResult:
        """Parses an Aniboom embed page.

        :param url: a ``https://aniboom.one/embed/<id>`` url (query parameters
            ``?episode=&translation=`` are allowed), or just ``<id>``.
        :param referer: the site the player is supposedly opened from (animego.org by default).
        :param resolve_qualities: fetch the HLS master playlist and add one stream
            per quality (costs one extra request).
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

    # -- parsing ----------------------------------------------------------
    def _normalize(self, url: str) -> str:
        if "/" not in url:  # only a video id was passed
            return self.embed_url(url)
        return self.ensure_matches(url)

    @staticmethod
    def _parse_page(resp: Response, url: str) -> Dict[str, Any]:
        resp.raise_for_status()
        raw = search(_VIDEO_TAG, resp.text, what="the <video data-parameters> tag on the Aniboom page", default=None)
        if raw is None:
            # "не доступно" is the wording Aniboom itself puts on a blocked page.
            if "не доступно" in resp.text or "video-error" in resp.text:
                raise ContentBlocked(f"Aniboom is not serving the video (geo-blocked or removed): {url}")
            raise ExtractionError(
                f"The Aniboom page has no <video data-parameters=...> tag: {url}. "
                "The player markup has probably changed."
            )
        return json_from_attribute(raw)

    def _headers(self) -> Dict[str, str]:
        headers = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]
        return headers

    @staticmethod
    def _src(value: Any) -> Optional[str]:
        """The hls/dash values arrive as a json string ``{"src": "...", "type": "..."}``."""
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
            raise NoStreamsFound(f"Aniboom returned neither hls nor dash for {url}. Player data: {data}")

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
        """Expands a master playlist into one stream per quality."""
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
