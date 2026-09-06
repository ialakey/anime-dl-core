"""The CVH player — CdnVideoHub (plapi.cdnvideohub.com), listed as "CVH" on AnimeGO.

How it works: a media item has a numeric ``cvh_id`` that the site drops into an
iframe (``/cdn-iframe/<cvh_id>/<studio>/<season>/<episode>``). That id fetches the
playlist of every episode and dub through an open API, and the ``vkId`` of one
episode fetches its streams. The video itself is served by Odnoklassniki's CDN (okcdn.ru).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..base import BasePlayer, compile_patterns
from ..errors import ExtractionError, NoStreamsFound, NotFound
from ..models import PlayerResult, Stream, StreamKind
from ..utils import quality_from_label, to_int

__all__ = ["CvhPlayer", "CvhEpisode"]

_IFRAME_RE = re.compile(r"/cdn-iframe/(\d+)(?:/([^/?#]+))?(?:/(\d+))?(?:/(\d+))?", re.IGNORECASE)
_VIDEO_RE = re.compile(r"/player/sv/video/(\d+)", re.IGNORECASE)

#: Maps the keys of a CVH response (Odnoklassniki naming) to picture height.
QUALITY_KEYS = {
    "mpegMobileUrl": 144,
    "mpegTinyUrl": 144,
    "mpegLowestUrl": 240,
    "mpegLowUrl": 360,
    "mpegMediumUrl": 480,
    "mpegHighUrl": 720,
    "mpegFullHdUrl": 1080,
    "mpegQhdUrl": 1440,
    "mpeg2kUrl": 2048,
    "mpeg4kUrl": 2160,
}


@dataclass(frozen=True)
class CvhEpisode:
    """One playlist entry from CVH: an episode in one particular dub."""

    cvh_id: str
    video_id: str
    studio: Optional[str]
    voice_type: Optional[str]
    season: int
    episode: int

    @classmethod
    def from_api(cls, item: Dict[str, Any]) -> "CvhEpisode":
        return cls(
            cvh_id=str(item.get("cvhId", "")),
            video_id=str(item.get("vkId", "")),
            studio=item.get("voiceStudio"),
            voice_type=item.get("voiceType"),
            season=int(item.get("season") or 1),
            episode=int(item.get("episode") or 1),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cvh_id": self.cvh_id,
            "video_id": self.video_id,
            "studio": self.studio,
            "voice_type": self.voice_type,
            "season": self.season,
            "episode": self.episode,
        }


class CvhPlayer(BasePlayer):
    """The CVH (CdnVideoHub) player.

    Example::

        with CvhPlayer() as player:
            for ep in player.playlist("51019"):
                print(ep.season, ep.episode, ep.studio)
            result = player.extract("51019", season=1, episode=1, studio="AniLibria")
            print(result.best())
    """

    name = "cvh"
    title = "CVH (CdnVideoHub)"
    domains = ("cdnvideohub.com", "plapi.cdnvideohub.com")
    url_patterns = compile_patterns(r"/cdn-iframe/\d+")
    api_base = "https://plapi.cdnvideohub.com/api/v1/player/sv"
    default_referer = "https://animego.org/"

    def __init__(self, *args: Any, pub: str = "747", aggr: str = "mali", **kwargs: Any) -> None:
        """
        :param pub: publisher id (``747`` for animego.org).
        :param aggr: aggregator id (``mali`` for animego.org).
        """
        super().__init__(*args, **kwargs)
        self.pub = pub
        self.aggr = aggr

    # -- url parsing -----------------------------------------------------
    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        """Pulls ``cvh_id``/studio/season/episode out of an iframe url.

        Also understands a bare numeric id and a ``/player/sv/video/<vkId>`` url.
        """
        url = str(url).strip()
        if url.isdigit():
            return {"cvh_id": url}
        video = _VIDEO_RE.search(url)
        if video:
            return {"video_id": video.group(1)}
        match = _IFRAME_RE.search(url)
        if not match:
            raise ExtractionError(
                f"Could not make sense of the CVH url: {url!r}. "
                "Expected /cdn-iframe/<id>/<studio>/<season>/<episode> or a numeric id."
            )
        studio = match.group(2)
        return {
            "cvh_id": match.group(1),
            "studio": studio.replace("%20", " ") if studio else None,
            "season": int(match.group(3)) if match.group(3) else None,
            "episode": int(match.group(4)) if match.group(4) else None,
        }

    # -- API ------------------------------------------------------------
    def playlist(self, cvh_id: str) -> List[CvhEpisode]:
        """Every episode and dub of a media item."""
        resp = self.client.get(self._playlist_url(cvh_id), headers=self._api_headers())
        return self._parse_playlist(resp.raise_for_status().json(), cvh_id)

    async def aplaylist(self, cvh_id: str) -> List[CvhEpisode]:
        resp = await self.async_client.get(self._playlist_url(cvh_id), headers=self._api_headers())
        return self._parse_playlist(resp.raise_for_status().json(), cvh_id)

    def extract(
        self,
        url: str,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        studio: Optional[str] = None,
        **_: Any,
    ) -> PlayerResult:
        """Returns the streams of the requested episode.

        :param url: an iframe url, a numeric ``cvh_id``, or a ``/player/sv/video/<id>`` url.
        :param season: season number (ignored when there is only one season).
        :param episode: episode number (the first available one by default).
        :param studio: dub name; matched loosely
            (``"AniLibria"`` will find ``"AnilibriaTV"``).
        """
        parsed = self.parse_url(url)
        season = season if season is not None else parsed.get("season")
        episode = episode if episode is not None else parsed.get("episode")
        studio = studio if studio is not None else parsed.get("studio")

        if parsed.get("video_id"):
            return self.extract_video(parsed["video_id"], source_url=str(url))

        items = self.playlist(parsed["cvh_id"])
        chosen = self.select(items, season=season, episode=episode, studio=studio)
        return self.extract_video(chosen.video_id, source_url=str(url), episode=chosen)

    async def aextract(
        self,
        url: str,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        studio: Optional[str] = None,
        **_: Any,
    ) -> PlayerResult:
        parsed = self.parse_url(url)
        season = season if season is not None else parsed.get("season")
        episode = episode if episode is not None else parsed.get("episode")
        studio = studio if studio is not None else parsed.get("studio")

        if parsed.get("video_id"):
            return await self.aextract_video(parsed["video_id"], source_url=str(url))

        items = await self.aplaylist(parsed["cvh_id"])
        chosen = self.select(items, season=season, episode=episode, studio=studio)
        return await self.aextract_video(chosen.video_id, source_url=str(url), episode=chosen)

    def extract_video(
        self, video_id: str, *, source_url: Optional[str] = None, episode: Optional[CvhEpisode] = None
    ) -> PlayerResult:
        """Streams for the ``vkId`` of one particular video."""
        resp = self.client.get(f"{self.api_base}/video/{video_id}", headers=self._api_headers())
        return self._build_result(resp.raise_for_status().json(), video_id, source_url, episode)

    async def aextract_video(
        self, video_id: str, *, source_url: Optional[str] = None, episode: Optional[CvhEpisode] = None
    ) -> PlayerResult:
        resp = await self.async_client.get(f"{self.api_base}/video/{video_id}", headers=self._api_headers())
        return self._build_result(resp.raise_for_status().json(), video_id, source_url, episode)

    # -- picking an episode ----------------------------------------------
    @staticmethod
    def select(
        items: Sequence[CvhEpisode],
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        studio: Optional[str] = None,
    ) -> CvhEpisode:
        """Picks an episode from the playlist. Raises :class:`NotFound` when there is none."""
        if not items:
            raise NotFound("The CVH playlist is empty")

        seasons = sorted({item.season for item in items})
        if season is None or len(seasons) == 1:
            season = seasons[0] if len(seasons) == 1 else (season or seasons[0])
        pool = [item for item in items if item.season == season]
        if not pool:
            raise NotFound(f"Season {season} was not found. Available seasons: {seasons}")

        episodes = sorted({item.episode for item in pool})
        if episode is None:
            episode = episodes[0]
        pool = [item for item in pool if item.episode == episode]
        if not pool:
            raise NotFound(f"Episode {episode} was not found in season {season}. Available: {episodes}")

        if studio:
            match = _match_studio(studio, pool)
            if match is None:
                raise NotFound(
                    f"Dub {studio!r} was not found. Available: {[item.studio for item in pool]}"
                )
            return match
        return pool[0]

    # -- internals --------------------------------------------------------
    def _playlist_url(self, cvh_id: str) -> str:
        return f"{self.api_base}/playlist?pub={self.pub}&aggr={self.aggr}&id={cvh_id}"

    def _api_headers(self) -> Dict[str, str]:
        return {"Referer": self.default_referer, "Accept": "application/json"}

    @staticmethod
    def _parse_playlist(data: Any, cvh_id: str) -> List[CvhEpisode]:
        items = (data or {}).get("items") or []
        if not items:
            raise NotFound(f"CVH returned an empty playlist for id={cvh_id}")
        return [CvhEpisode.from_api(item) for item in items]

    def _build_result(
        self,
        data: Dict[str, Any],
        video_id: str,
        source_url: Optional[str],
        episode: Optional[CvhEpisode],
    ) -> PlayerResult:
        sources = (data or {}).get("sources") or {}
        headers = {"User-Agent": self._client_options["user_agent"]}
        streams: List[Stream] = []

        if sources.get("hlsUrl"):
            streams.append(Stream(sources["hlsUrl"], StreamKind.HLS, None, headers, "master"))
        dash = sources.get("dashUrl") or sources.get("dashManifestUrl")
        if dash:
            streams.append(Stream(dash, StreamKind.DASH, None, headers, "master"))

        for key, value in sources.items():
            if not isinstance(value, str) or not value.startswith("http"):
                continue
            if key in ("hlsUrl", "dashUrl", "dashManifestUrl"):
                continue
            quality = QUALITY_KEYS.get(key) or quality_from_label(key)
            streams.append(
                Stream(value, StreamKind.MP4, quality, headers, f"{quality}p" if quality else key,
                       extra={"source_key": key})
            )

        if not streams:
            raise NoStreamsFound(f"CVH returned no links for video {video_id}. sources={sources}")

        return PlayerResult(
            player=self.name,
            source_url=source_url or f"{self.api_base}/video/{video_id}",
            streams=streams,
            poster=data.get("thumbUrl"),
            duration=to_int(data.get("duration")),
            translation=episode.studio if episode else None,
            extra={
                "video_id": video_id,
                "episode": episode.to_dict() if episode else None,
                "failover_host": data.get("failoverHost"),
            },
        )


def _match_studio(name: str, items: Iterable[CvhEpisode]) -> Optional[CvhEpisode]:
    """Loose matching of a dub name: exact first, then substring."""
    items = list(items)
    wanted = name.strip().lower()
    for item in items:
        if (item.studio or "").strip().lower() == wanted:
            return item
    for item in items:
        studio = (item.studio or "").strip().lower()
        if studio and (wanted in studio or studio in wanted):
            return item
    return None
