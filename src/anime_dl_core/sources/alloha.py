"""Alloha (api.alloha.tv) — the catalogue and links to its embeddable player.

Alloha does not hand out direct video links; it serves video through its own iframe player.
The open API takes an id (Kinopoisk / IMDb / TMDb / a name) and returns the title
description, the list of dubs, the seasons with their episodes, and a ready iframe
link for every "episode + dub" combination.

.. important::
   Alloha never returns direct video links (m3u8/mp4): the player itself receives
   them over a WebSocket from a heavily obfuscated bundle, and the address appears
   nowhere in the html. That is why Alloha is a source (``sources``) rather than a
   player (``players``): the result is an iframe link you can embed or open in a
   browser/webview. If you specifically need the files, you need a headless browser —
   plain http parsing will not get you there.

Token: the API has a public token, used by default. Should it stop working, pass
your own: ``Alloha(token="...")``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..errors import NotFound, ServiceError
from ..http import DEFAULT_USER_AGENT, HttpClient

__all__ = ["Alloha", "AllohaItem", "AllohaTranslation", "PUBLIC_TOKEN"]

#: The public Alloha token that circulates in open projects.
PUBLIC_TOKEN = "04941a9a3ca3ac16e2b4327347bbc1"

#: Alloha categories (the ``category`` field). Kept in Russian: these are the API's
#: own values and they are what this client has always returned.
CATEGORIES = {1: "фильм", 2: "мультфильм", 3: "мультсериал", 4: "сериал", 5: "аниме"}


@dataclass(frozen=True)
class AllohaTranslation:
    """A dub together with its player link."""

    id: str
    name: str
    iframe: str
    quality: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class AllohaItem:
    """A title in the Alloha catalogue."""

    name: str
    original_name: Optional[str]
    year: Optional[int]
    category: Optional[str]
    id_kp: Optional[int]
    id_imdb: Optional[str]
    id_tmdb: Optional[int]
    poster: Optional[str]
    description: Optional[str]
    rating_kp: Optional[float]
    quality: Optional[str]
    iframe: Optional[str]
    translations: List[AllohaTranslation] = field(default_factory=list)
    seasons: Dict[int, List[int]] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_series(self) -> bool:
        return bool(self.seasons)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            key: value
            for key, value in self.__dict__.items()
            if key not in ("translations", "raw")
        }
        data["translations"] = [translation.to_dict() for translation in self.translations]
        return data


class Alloha:
    """Client for the open Alloha API.

    Example::

        from anime_dl_core.sources import Alloha

        with Alloha() as alloha:
            anime = alloha.find(name="Атака титанов")
            print(anime.name, anime.year, anime.seasons)     # {1: [1..25], 2: [...], ...}

            # every episode has its own set of dubs
            voices = alloha.translations_for(anime, season=1, episode=1)
            print([voice.name for voice in voices])

            # player link for one episode in one dub
            print(alloha.iframe(anime, season=1, episode=1, translation=voices[0].name))
    """

    api_url = "https://api.alloha.tv/"

    def __init__(
        self,
        *,
        token: str = PUBLIC_TOKEN,
        proxy: Optional[str] = None,
        timeout: float = 25.0,
        user_agent: str = DEFAULT_USER_AGENT,
        client: Optional[HttpClient] = None,
    ) -> None:
        """:param token: API token (public by default, see :data:`PUBLIC_TOKEN`)."""
        self.token = token
        self._client = client or HttpClient(proxy=proxy, timeout=timeout, user_agent=user_agent)
        self._own_client = client is None

    # -- requests -----------------------------------------------------------
    def find(
        self,
        *,
        kp: Optional[Any] = None,
        imdb: Optional[str] = None,
        tmdb: Optional[Any] = None,
        name: Optional[str] = None,
    ) -> AllohaItem:
        """Looks a title up by one of the ids, or by name."""
        params: Dict[str, Any] = {"token": self.token}
        for key, value in (("kp", kp), ("imdb", imdb), ("tmdb", tmdb), ("name", name)):
            if value is not None:
                params[key] = value
        if len(params) == 1:
            raise ValueError("Pass one of: kp, imdb, tmdb or name")

        resp = self._client.get(self.api_url, params=params).raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            message = data.get("error_info") or data
            if "token" in str(message).lower():
                raise ServiceError(
                    f"Alloha rejected the token: {message}. Pass your own: Alloha(token=...)"
                )
            raise NotFound(f"Alloha: nothing was found ({message})")

        payload = data.get("data")
        if isinstance(payload, list):
            if not payload:
                raise NotFound("Alloha returned an empty result")
            payload = payload[0]
        return _item_from_api(payload)

    def episodes(self, item: AllohaItem, season: int) -> List[int]:
        """Episode numbers of one season."""
        if season not in item.seasons:
            raise NotFound(f"Season {season} was not found. Available: {sorted(item.seasons)}")
        return item.seasons[season]

    def translations_for(
        self,
        item: AllohaItem,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> List[AllohaTranslation]:
        """The dubs available for a whole title, a season, or one episode.

        A series carries a different set of dubs from episode to episode, so it is
        worth checking what this episode actually has before calling :meth:`iframe`.
        """
        node = self._node(item, season=season, episode=episode)
        translations = _translation_map(node)
        if not translations:
            return list(item.translations)
        return [
            AllohaTranslation(
                id=str(key),
                name=value.get("translation") or value.get("name") or str(key),
                iframe=value.get("iframe", ""),
                quality=value.get("quality"),
            )
            for key, value in translations.items()
        ]

    def iframe(
        self,
        item: AllohaItem,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        translation: Optional[str] = None,
    ) -> str:
        """Player link: for a whole title, for one episode, or for one dub.

        :param translation: dub name (``"DEEP"``) or dub id (``"260"``).
        """
        node = self._node(item, season=season, episode=episode)

        if translation:
            for key, value in _translation_map(node).items():
                name = value.get("translation") or value.get("name") or ""
                if str(key) == str(translation) or name.lower() == str(translation).lower():
                    return value["iframe"]
            available = [
                (value.get("translation") or value.get("name"))
                for value in _translation_map(node).values()
            ]
            raise NotFound(f"Dub {translation!r} was not found. Available: {available}")

        iframe = node.get("iframe") or item.iframe
        if not iframe:
            raise NotFound("Alloha returned no player link for this request")
        return iframe

    def _node(
        self,
        item: AllohaItem,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> Dict[str, Any]:
        """A node of the API response: title -> season -> episode."""
        node: Dict[str, Any] = item.raw
        if not item.is_series:
            return node
        if season is None and episode is None:
            return node
        if season is None:
            season = sorted(item.seasons)[0]
        seasons = node.get("seasons") or {}
        season_node = seasons.get(str(season)) or seasons.get(season)
        if not season_node:
            raise NotFound(f"Season {season} was not found. Available: {sorted(item.seasons)}")
        node = season_node
        if episode is not None:
            episodes = node.get("episodes") or {}
            episode_node = episodes.get(str(episode)) or episodes.get(episode)
            if not episode_node:
                available = item.seasons.get(season, [])
                raise NotFound(
                    f"Episode {episode} was not found in season {season}. "
                    f"Available: {available[:1]}..{available[-1:]}"
                )
            node = episode_node
        return node

    # -- lifecycle -----------------------------------------------------------
    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def __enter__(self) -> "Alloha":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def _translation_map(node: Dict[str, Any]) -> Dict[str, Any]:
    """The ``translation`` field: a dict of dubs on an episode, a comma-joined string on a title."""
    translations = node.get("translation")
    return translations if isinstance(translations, dict) else {}


def _item_from_api(data: Dict[str, Any]) -> AllohaItem:
    translations = [
        AllohaTranslation(
            id=str(key),
            name=value.get("name") or value.get("translation") or str(key),
            iframe=value.get("iframe", ""),
            quality=value.get("quality"),
        )
        for key, value in (data.get("translation_iframe") or {}).items()
    ]

    seasons: Dict[int, List[int]] = {}
    for key, season in (data.get("seasons") or {}).items():
        try:
            number = int(key)
        except (TypeError, ValueError):
            continue
        episodes = sorted(int(episode) for episode in (season.get("episodes") or {}))
        seasons[number] = episodes

    return AllohaItem(
        name=data.get("name") or "",
        original_name=data.get("original_name"),
        year=data.get("year"),
        category=CATEGORIES.get(data.get("category"), None),
        id_kp=data.get("id_kp"),
        id_imdb=data.get("id_imdb"),
        id_tmdb=data.get("id_tmdb"),
        poster=data.get("poster"),
        description=data.get("description"),
        rating_kp=data.get("rating_kp"),
        quality=data.get("quality"),
        iframe=data.get("iframe"),
        translations=translations,
        seasons=dict(sorted(seasons.items())),
        raw=data,
    )
