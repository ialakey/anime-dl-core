"""Реестр плееров и функции-фасады :func:`extract` / :func:`extract_async`."""

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

#: Все известные плееры. Порядок важен: первый подошедший и будет использован.
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

# Параметры, которые относятся к http-клиенту, а не к конкретному плееру.
_CLIENT_KEYS = ("proxy", "timeout", "user_agent", "headers", "client", "async_client")


def register(player: Type[BasePlayer], *, first: bool = False) -> Type[BasePlayer]:
    """Добавляет свой плеер в реестр (можно использовать как декоратор).

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
    """Кортеж всех зарегистрированных плееров."""
    return tuple(PLAYERS)


def player_names() -> List[str]:
    """Имена всех плееров."""
    return [player.name for player in PLAYERS]


def get_player_class(url_or_name: str) -> Type[BasePlayer]:
    """Класс плеера по ссылке или по имени (``"kodik"``).

    :raises UnsupportedUrl: если подходящего плеера нет.
    """
    value = str(url_or_name).strip()
    for player in PLAYERS:
        if player.name == value.lower():
            return player
    for player in PLAYERS:
        if player.matches(value):
            return player
    raise UnsupportedUrl(
        f"Не нашлось плеера для {value!r}. Известные плееры: {', '.join(player_names())}"
    )


def get_player(url_or_name: str, **kwargs: Any) -> BasePlayer:
    """Готовый экземпляр плеера для ссылки (или по имени плеера)."""
    client_kwargs = {key: kwargs[key] for key in _CLIENT_KEYS if key in kwargs}
    return get_player_class(url_or_name)(**client_kwargs)


def _split_kwargs(kwargs: Mapping[str, Any]) -> "tuple[Dict[str, Any], Dict[str, Any]]":
    client_kwargs = {key: value for key, value in kwargs.items() if key in _CLIENT_KEYS}
    extract_kwargs = {key: value for key, value in kwargs.items() if key not in _CLIENT_KEYS}
    return client_kwargs, extract_kwargs


def extract(url: str, **kwargs: Any) -> PlayerResult:
    """Определяет плеер по ссылке и возвращает ссылки на видео.

    Параметры ``proxy``, ``timeout``, ``user_agent``, ``headers``, ``client``
    уходят в http-клиент, всё остальное (``episode``, ``season``, ``studio``,
    ``referer``, ...) — в метод ``extract`` конкретного плеера.

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
    """Асинхронный вариант :func:`extract` (нужен ``pip install anime-dl-core[async]``)."""
    client_kwargs, extract_kwargs = _split_kwargs(kwargs)
    player = get_player_class(url)(**client_kwargs)
    try:
        return await player.aextract(url, **extract_kwargs)
    finally:
        await player.aclose()


def describe_players() -> List[Dict[str, Any]]:
    """Краткая справка по плеерам — используется в CLI (``--list``)."""
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


# Значение по умолчанию доступно и отсюда — удобно для своих клиентов.
DEFAULT_USER_AGENT = DEFAULT_USER_AGENT
