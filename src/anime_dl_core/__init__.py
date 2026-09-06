"""anime-dl-core — получение прямых ссылок на видео из аниме-плееров.

Быстрый старт::

    import anime_dl_core

    result = anime_dl_core.extract("https://aniboom.one/embed/9G1MJ6NMV8z?episode=1")
    stream = result.best(kind="hls")
    print(stream.url)
    print(stream.headers)          # эти заголовки обязательны при скачивании
    print(stream.ffmpeg_command("episode.mp4"))

Поддерживаются: Aniboom, CVH (CdnVideoHub), Kodik, Sibnet, AniLibria,
VK Video и SovetRomantica. Полная документация — в README.md.
"""

from __future__ import annotations

from .base import BasePlayer
from .errors import (
    AnimeDlCoreError,
    ContentBlocked,
    DecryptionError,
    ExtractionError,
    NetworkError,
    NoStreamsFound,
    NotFound,
    ServiceError,
    UnsupportedUrl,
)
from .http import DEFAULT_USER_AGENT, AsyncHttpClient, HttpClient, Response
from .models import PlayerResult, SkipSegment, Stream, StreamKind
from .players import (
    AniboomPlayer,
    AnimediaPlayer,
    AnilibriaPlayer,
    CvhEpisode,
    CvhPlayer,
    KodikPlayer,
    SibnetPlayer,
    SovetRomanticaPlayer,
    VkPlayer,
)
from .registry import (
    PLAYERS,
    all_players,
    describe_players,
    extract,
    extract_async,
    get_player,
    get_player_class,
    player_names,
    register,
)

__version__ = "0.4.1"

__all__ = [
    "__version__",
    # фасад
    "extract",
    "extract_async",
    "get_player",
    "get_player_class",
    "all_players",
    "player_names",
    "describe_players",
    "register",
    "PLAYERS",
    # модели
    "PlayerResult",
    "Stream",
    "StreamKind",
    "SkipSegment",
    # плееры
    "BasePlayer",
    "AniboomPlayer",
    "AnimediaPlayer",
    "AnilibriaPlayer",
    "CvhPlayer",
    "CvhEpisode",
    "KodikPlayer",
    "SibnetPlayer",
    "SovetRomanticaPlayer",
    "VkPlayer",
    # http
    "HttpClient",
    "AsyncHttpClient",
    "Response",
    "DEFAULT_USER_AGENT",
    # ошибки
    "AnimeDlCoreError",
    "UnsupportedUrl",
    "NetworkError",
    "ServiceError",
    "ExtractionError",
    "NoStreamsFound",
    "DecryptionError",
    "ContentBlocked",
    "NotFound",
]
