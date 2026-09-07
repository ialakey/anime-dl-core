"""The AniLibria / AniLiberty player (anilibria.top).

Strictly speaking this is not an embed player but an open API: given a release
alias it returns the list of episodes with ready HLS links in 480/720/1080 and
the opening/ending timecodes. No token needed.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from ..base import BasePlayer, compile_patterns
from ..errors import NoStreamsFound, NotFound
from ..models import PlayerResult, SkipSegment, Stream, StreamKind
from ..utils import to_int

__all__ = ["AnilibriaPlayer"]

_RELEASE_RE = re.compile(r"/release/([A-Za-z0-9_-]+)", re.IGNORECASE)
_EPISODE_RE = re.compile(r"/episodes?/(\d+)", re.IGNORECASE)
_HLS_KEY_RE = re.compile(r"^hls_(\d{3,4})$")


class AnilibriaPlayer(BasePlayer):
    """The AniLibria (aniliberty) player.

    Example::

        with AnilibriaPlayer() as player:
            result = player.extract("bleach", episode=1)
            print(result.title, result.qualities)
            print(result.skip_segments)     # opening/ending
    """

    name = "anilibria"
    title = "AniLibria (AniLiberty)"
    domains = ("anilibria.top", "aniliberty.top", "anilibria.tv")
    url_patterns = compile_patterns(r"anilib(?:ria|erty)\.[a-z]+/anime/releases/release/")
    api_base = "https://anilibria.top/api/v1"
    site_base = "https://anilibria.top"

    def __init__(self, *args: Any, api_base: Optional[str] = None, **kwargs: Any) -> None:
        """:param api_base: API address, for when the main domain is unreachable (a mirror)."""
        super().__init__(*args, **kwargs)
        if api_base:
            self.api_base = api_base.rstrip("/")

    # -- API ---------------------------------------------------------------
    def release(self, alias: str) -> Dict[str, Any]:
        """Full release data by alias or id."""
        resp = self.client.get(f"{self.api_base}/anime/releases/{alias}", headers={"Accept": "application/json"})
        return self._check_release(resp.raise_for_status().json(), alias)

    async def arelease(self, alias: str) -> Dict[str, Any]:
        resp = await self.async_client.get(
            f"{self.api_base}/anime/releases/{alias}", headers={"Accept": "application/json"}
        )
        return self._check_release(resp.raise_for_status().json(), alias)

    def episodes(self, alias: str) -> List[Dict[str, Any]]:
        """The release's episode list, exactly as the API returns it."""
        return self.release(alias).get("episodes") or []

    def search(self, query: str, *, limit: int = 10) -> List[Dict[str, Any]]:
        """Search releases by name (handy for finding an alias)."""
        resp = self.client.get(
            f"{self.api_base}/app/search/releases",
            params={"query": query, "limit": limit},
            headers={"Accept": "application/json"},
        )
        data = resp.raise_for_status().json()
        items = data.get("data") if isinstance(data, dict) else data
        return list(items or [])[:limit]

    # -- main interface -----------------------------------------------------
    def extract(self, url: str, *, episode: Optional[int] = None, **_: Any) -> PlayerResult:
        """Links for one episode.

        :param url: a ``https://anilibria.top/anime/releases/release/<alias>/episodes/<n>`` url,
            a release alias (``"bleach"``), or a ``"bleach/3"`` string.
        :param episode: episode number, when the url does not carry one (first by default).
        """
        alias, episode_number = self._parse(url, episode)
        release = self.release(alias)
        return self._build_result(release, alias, episode_number, str(url))

    async def aextract(self, url: str, *, episode: Optional[int] = None, **_: Any) -> PlayerResult:
        alias, episode_number = self._parse(url, episode)
        release = await self.arelease(alias)
        return self._build_result(release, alias, episode_number, str(url))

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _parse(url: str, episode: Optional[int]) -> "tuple[str, Optional[int]]":
        url = str(url).strip()
        if url.startswith("http"):
            alias_match = _RELEASE_RE.search(url)
            if not alias_match:
                raise NotFound(f"The url {url!r} carries no AniLibria release alias")
            alias = alias_match.group(1)
            episode_match = _EPISODE_RE.search(url)
            if episode is None and episode_match:
                episode = int(episode_match.group(1))
            return alias, episode
        if "/" in url:
            alias, _, tail = url.partition("/")
            if episode is None and tail.strip().isdigit():
                episode = int(tail.strip())
            return alias, episode
        return url, episode

    @staticmethod
    def _check_release(data: Any, alias: str) -> Dict[str, Any]:
        if not isinstance(data, dict) or not data.get("id"):
            raise NotFound(f"Release {alias!r} was not found on AniLibria")
        if data.get("is_blocked_by_geo"):
            from ..errors import ContentBlocked

            raise ContentBlocked(f"Release {alias!r} is blocked in your region (use a proxy)")
        return data

    @staticmethod
    def _select_episode(episodes: Sequence[Dict[str, Any]], number: Optional[int]) -> Dict[str, Any]:
        if not episodes:
            raise NotFound("The release has no episodes at all")
        if number is None:
            return episodes[0]
        for item in episodes:
            if int(item.get("ordinal") or 0) == number:
                return item
        available = [int(item.get("ordinal") or 0) for item in episodes]
        raise NotFound(f"Episode {number} was not found. Available: {available[:1]}..{available[-1:]}")

    def _build_result(
        self, release: Dict[str, Any], alias: str, number: Optional[int], source_url: str
    ) -> PlayerResult:
        episode = self._select_episode(release.get("episodes") or [], number)
        headers = {"User-Agent": self._client_options["user_agent"]}

        streams: List[Stream] = []
        for key, value in episode.items():
            match = _HLS_KEY_RE.match(key)
            if match and isinstance(value, str) and value.startswith("http"):
                quality = int(match.group(1))
                streams.append(Stream(value, StreamKind.HLS, quality, headers, f"{quality}p"))
        streams.sort(key=lambda s: s.quality or 0)

        if not streams:
            raise NoStreamsFound(f"AniLibria returned no links for episode {number} of release {alias!r}")

        skip: List[SkipSegment] = []
        for kind in ("opening", "ending"):
            block = episode.get(kind) or {}
            start, stop = block.get("start"), block.get("stop")
            if isinstance(start, (int, float)) and isinstance(stop, (int, float)):
                skip.append(SkipSegment(int(start), int(stop), kind))

        names = release.get("name") or {}
        episode_name = episode.get("name")
        title = names.get("main") or names.get("english") or alias
        if episode.get("ordinal"):
            title = f"{title} — episode {int(episode['ordinal'])}"
        if episode_name:
            title = f"{title}: {episode_name}"

        poster = ((release.get("poster") or {}).get("src")) or None
        if poster and poster.startswith("/"):
            poster = self.site_base + poster

        duration = episode.get("duration") or release.get("average_duration_of_episode")
        return PlayerResult(
            player=self.name,
            source_url=source_url,
            streams=streams,
            title=title,
            poster=poster,
            duration=to_int(duration),
            skip_segments=skip,
            extra={
                "alias": release.get("alias", alias),
                "release_id": release.get("id"),
                "episode_id": episode.get("id"),
                "ordinal": episode.get("ordinal"),
                "episodes_total": release.get("episodes_total"),
                "is_ongoing": release.get("is_ongoing"),
            },
        )
