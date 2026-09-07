"""The player registry and the :func:`extract` / :func:`extract_async` facades."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple, Type

from .base import BasePlayer
from .errors import UnsupportedUrl
from .http import DEFAULT_USER_AGENT
from .models import PlayerResult
from .players.animedia import AnimediaPlayer
from .players.aniboom import AniboomPlayer
from .players.anilibria import AnilibriaPlayer
from .players.cvh import CvhPlayer
from .players.kodik import KodikPlayer
from .players.sibnet import SibnetPlayer
from .players.sovetromantica import SovetRomanticaPlayer
from .players.vk import VkPlayer

__all__ = [
    "PLAYERS",
    "register",
    "all_players",
    "player_names",
    "get_player_class",
    "get_player",
    "extract",
    "extract_async",
]

#: Every known player. Order matters: the first one that matches is the one used.
PLAYERS: List[Type[BasePlayer]] = [
    AniboomPlayer,
    CvhPlayer,
    KodikPlayer,
    SibnetPlayer,
    AnimediaPlayer,
    AnilibriaPlayer,
    VkPlayer,
    SovetRomanticaPlayer,
]

# Arguments that belong to the http client rather than to a specific player.
_CLIENT_KEYS = ("proxy", "timeout", "user_agent", "headers", "client", "async_client")


def register(player: Type[BasePlayer], *, first: bool = False) -> Type[BasePlayer]:
    """Registers your own player (can be used as a decorator).

    >>> @register
    ... class MyPlayer(BasePlayer):
    ...     name = "my"
    ...     domains = ("example.com",)
    """
    if first:
        PLAYERS.insert(0, player)
    else:
        PLAYERS.append(player)
    return player


def all_players() -> Tuple[Type[BasePlayer], ...]:
    """Every registered player, as a tuple."""
    return tuple(PLAYERS)


def player_names() -> List[str]:
    """Names of every player."""
    return [player.name for player in PLAYERS]


def get_player_class(url_or_name: str) -> Type[BasePlayer]:
    """The player class for a url or for a name (``"kodik"``).

    :raises UnsupportedUrl: when no player matches.
    """
    value = str(url_or_name).strip()
    for player in PLAYERS:
        if player.name == value.lower():
            return player
    for player in PLAYERS:
        if player.matches(value):
            return player
    raise UnsupportedUrl(
        f"No player matched {value!r}. Known players: {', '.join(player_names())}"
    )


def get_player(url_or_name: str, **kwargs: Any) -> BasePlayer:
    """A ready player instance for a url (or for a player name)."""
    client_kwargs = {key: kwargs[key] for key in _CLIENT_KEYS if key in kwargs}
    return get_player_class(url_or_name)(**client_kwargs)


def _split_kwargs(kwargs: Mapping[str, Any]) -> "tuple[Dict[str, Any], Dict[str, Any]]":
    client_kwargs = {key: value for key, value in kwargs.items() if key in _CLIENT_KEYS}
    extract_kwargs = {key: value for key, value in kwargs.items() if key not in _CLIENT_KEYS}
    return client_kwargs, extract_kwargs


def extract(url: str, **kwargs: Any) -> PlayerResult:
    """Detects the player from the url and returns the video links.

    ``proxy``, ``timeout``, ``user_agent``, ``headers`` and ``client`` go to the
    http client; everything else (``episode``, ``season``, ``studio``,
    ``referer``, ...) goes to that player's ``extract`` method.

    >>> extract("https://video.sibnet.ru/shell.php?videoid=2589828").best().url
    'https://video.sibnet.ru/v/.../2589828.mp4'
    """
    client_kwargs, extract_kwargs = _split_kwargs(kwargs)
    player = get_player_class(url)(**client_kwargs)
    try:
        return player.extract(url, **extract_kwargs)
    finally:
        player.close()


async def extract_async(url: str, **kwargs: Any) -> PlayerResult:
    """Async counterpart of :func:`extract` (needs ``pip install anime-dl-core[async]``)."""
    client_kwargs, extract_kwargs = _split_kwargs(kwargs)
    player = get_player_class(url)(**client_kwargs)
    try:
        return await player.aextract(url, **extract_kwargs)
    finally:
        await player.aclose()


def describe_players() -> List[Dict[str, Any]]:
    """A short summary of the players — used by the CLI (``--list``)."""
    return [
        {
            "name": player.name,
            "title": player.title,
            "domains": list(player.domains),
            "verified": player.verified,
            "note": player.note,
        }
        for player in PLAYERS
    ]


# The default is exported here too — handy when building your own client.
DEFAULT_USER_AGENT = DEFAULT_USER_AGENT
