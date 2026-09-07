"""Optional helper: where to get player links from.

The library itself deals with players, but a player link has to come from somewhere.
This module does the minimum for an end-to-end run, using AnimeGO as the example:
search -> episode list -> player list (Aniboom / CVH / Kodik / Sibnet) -> streams.

The site markup changes from time to time — when search stops working, the regexes
here are what needs fixing; the core of the library does not depend on any of it.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ..errors import ExtractionError, NotFound, ServiceError
from ..http import DEFAULT_USER_AGENT, HttpClient
from ..models import PlayerResult

__all__ = ["AnimeGo", "AnimeItem", "PlayerLink"]

_ITEM_SPLIT = re.compile(r'class="ani-grid__item ')
_ITEM_LINK = re.compile(r'href="(/anime/([a-z0-9\-]+)-(\d+))"', re.IGNORECASE)
_ITEM_TITLE = re.compile(r'<a\s+title="([^"]+)"\s+href="/anime/[^"]+"')
_ITEM_IMAGE = re.compile(r'<img[^>]+src="([^"]+)"')
_ITEM_RATING = re.compile(r'class="rating-badge[^"]*">\s*([\d.]+)\s*<')
_ITEM_ORIGINAL = re.compile(r'text-line-clamp"[^>]*>\s*([^<>]{2,120}?)\s*</div>')
_BUTTON = re.compile(r"<button\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r'([a-zA-Z0-9\-]+)="([^"]*)"')
_EPISODE = re.compile(r'data-episode="(\d+)"[^>]*data-episode-number="(\d+)"', re.IGNORECASE)
_EPISODE_REVERSED = re.compile(r'data-episode-number="(\d+)"[^>]*data-episode="(\d+)"', re.IGNORECASE)
_CVH_ID = re.compile(r"/cdn-iframe/(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class AnimeItem:
    """An anime that was found."""

    id: str
    slug: str
    title: str
    url: str
    original_title: Optional[str] = None
    poster: Optional[str] = None
    rating: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class PlayerLink:
    """A link to one particular player for one particular dub."""

    player: str
    """The player name as the site spells it: ``AniBoom``, ``CVH``, ``Kodik``, ``Sibnet``."""
    label: str
    """Name of the dub."""
    embed: str
    """The link to hand to :func:`anime_dl_core.extract`."""
    translation_id: Optional[str] = None
    cvh_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class AnimeGo:
    """A small AnimeGO parser: search, and getting player links.

    Example::

        from anime_dl_core.sources import AnimeGo
        import anime_dl_core

        site = AnimeGo()
        anime = site.search("Магическая битва")[0]
        links = site.players(anime.id, episode=1)
        aniboom = next(link for link in links if link.player == "AniBoom")
        result = anime_dl_core.extract(aniboom.embed)
    """

    def __init__(
        self,
        *,
        mirror: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout: float = 20.0,
        user_agent: str = DEFAULT_USER_AGENT,
        client: Optional[HttpClient] = None,
    ) -> None:
        """:param mirror: mirror domain, for when animego.org is blocked (``animego.me``, say)."""
        self.base_url = f"https://{mirror}" if mirror else "https://animego.org"
        self._client = client or HttpClient(proxy=proxy, timeout=timeout, user_agent=user_agent)
        self._own_client = client is None
        self._episodes_cache: Dict[str, Dict[int, str]] = {}

    # -- search ----------------------------------------------------------
    def search(self, query: str, *, limit: int = 20) -> List[AnimeItem]:
        """Search anime by name."""
        resp = self._client.get(f"{self.base_url}/search/anime?q={quote(query)}")
        if resp.status in (403, 503):
            raise ServiceError(
                f"AnimeGO answered {resp.status} — Cloudflare protection has probably kicked in. "
                "Try a proxy or a mirror.",
                status=resp.status,
                url=resp.url,
            )
        resp.raise_for_status()

        items: List[AnimeItem] = []
        for chunk in _ITEM_SPLIT.split(resp.text)[1:]:
            link = _ITEM_LINK.search(chunk)
            title = _ITEM_TITLE.search(chunk)
            if not link or not title:
                continue
            original = _ITEM_ORIGINAL.search(chunk)
            image = _ITEM_IMAGE.search(chunk)
            rating = _ITEM_RATING.search(chunk)
            items.append(
                AnimeItem(
                    id=link.group(3),
                    slug=link.group(2),
                    title=html.unescape(title.group(1)),
                    url=self.base_url + link.group(1),
                    original_title=html.unescape(original.group(1)) if original else None,
                    poster=image.group(1) if image else None,
                    rating=rating.group(1) if rating else None,
                )
            )
            if len(items) >= limit:
                break
        if not items:
            # "ничего не найдено" is AnimeGO's own wording on an empty result page.
            if "ничего не найдено" in resp.text.lower():
                raise NotFound(f"AnimeGO: nothing was found for {query!r}")
            raise NotFound(
                f"AnimeGO returned no cards at all for {query!r}. "
                "That happens when the site filters the query (some titles are hidden) "
                "or when the result markup changed — then fix the regexes in sources/animego.py."
            )
        return items

    @staticmethod
    def anime_id(url: str) -> str:
        """``https://animego.org/anime/naruto-70`` -> ``70``."""
        match = re.search(r"-(\d+)/?$", url.strip())
        if not match:
            raise ExtractionError(f"The url {url!r} carries no AnimeGO anime id")
        return match.group(1)

    # -- players ----------------------------------------------------------
    def episodes(self, anime_id: str) -> Dict[int, str]:
        """``{episode number: player url for that episode}``."""
        anime_id = str(anime_id)
        if anime_id in self._episodes_cache:
            return self._episodes_cache[anime_id]
        content = self._player_html(f"{self.base_url}/player/{anime_id}")
        episodes: Dict[int, str] = {}
        for episode_id, number in _EPISODE.findall(content):
            episodes[int(number)] = f"{self.base_url}/player/videos/{episode_id}"
        for number, episode_id in _EPISODE_REVERSED.findall(content):
            episodes.setdefault(int(number), f"{self.base_url}/player/videos/{episode_id}")
        self._episodes_cache[anime_id] = episodes
        return episodes

    def players(self, anime_id: str, episode: int = 1) -> List[PlayerLink]:
        """The list of players and dubs for one episode."""
        anime_id = str(anime_id)
        if episode == 1:
            url = f"{self.base_url}/player/{anime_id}"
        else:
            episodes = self.episodes(anime_id)
            if episode not in episodes:
                raise NotFound(
                    f"Anime {anime_id} has no episode {episode}. Available: {sorted(episodes)[:1]}"
                    f"..{sorted(episodes)[-1:]}"
                )
            url = episodes[episode]

        content = self._player_html(url)
        links: List[PlayerLink] = []
        for tag in _BUTTON.findall(content):
            attrs = dict(_ATTR.findall(tag))
            embed = attrs.get("data-player")
            label = attrs.get("data-translation-title")
            if not embed or not label:
                continue
            if embed.startswith("//"):
                embed = "https:" + embed
            cvh = _CVH_ID.search(embed)
            links.append(
                PlayerLink(
                    player=attrs.get("data-provider-title") or "unknown",
                    # " (ошибка)" is the marker AnimeGO appends to a broken player.
                    label=html.unescape(label).replace(" (ошибка)", "").strip(),
                    embed=html.unescape(embed),
                    translation_id=attrs.get("data-ptranslation"),
                    cvh_id=cvh.group(1) if cvh else None,
                )
            )
        if not links:
            raise NotFound(f"AnimeGO served no players at all for anime {anime_id}, episode {episode}")
        return links

    def resolve(self, link: "PlayerLink | str", **kwargs: Any) -> PlayerResult:
        """Get the streams straight away: accepts a :class:`PlayerLink` or an embed url."""
        from ..registry import extract

        embed = link.embed if isinstance(link, PlayerLink) else str(link)
        return extract(embed, **kwargs)

    # -- internals ---------------------------------------------------------
    def _player_html(self, url: str) -> str:
        resp = self._client.get(
            url, headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.base_url + "/"}
        )
        if resp.status in (403, 503):
            raise ServiceError(
                f"AnimeGO answered {resp.status} when asked for a player — probably Cloudflare.",
                status=resp.status,
                url=url,
            )
        if resp.status == 404:
            raise NotFound(f"Player not found: {url}")
        resp.raise_for_status()
        try:
            data = json.loads(resp.text)
        except ValueError as exc:
            raise ExtractionError(f"The AnimeGO player response is not json ({url}): {exc}") from exc
        content = (data.get("data") or {}).get("content")
        if not content:
            raise ExtractionError(f"The AnimeGO player response carries no html content: {url}")
        return html.unescape(content)

    # -- lifecycle -----------------------------------------------------------
    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def __enter__(self) -> "AnimeGo":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
