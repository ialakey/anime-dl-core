"""anime-dl-core — direct video links from anime players.

Quick start::

    import anime_dl_core

    result = anime_dl_core.extract("https://aniboom.one/embed/9G1MJ6NMV8z?episode=1")
    stream = result.best(kind="hls")
    print(stream.url)
    print(stream.headers)          # these headers are required when downloading
    print(stream.ffmpeg_command("episode.mp4"))

Supported: Aniboom, CVH (CdnVideoHub), Kodik, Sibnet, AniLibria,
VK Video and SovetRomantica. Full documentation lives in README.md.
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
    # facade
    "extract",
    "extract_async",
    "get_player",
    "get_player_class",
    "all_players",
    "player_names",
    "describe_players",
    "register",
    "PLAYERS",
    # models
    "PlayerResult",
    "Stream",
    "StreamKind",
    "SkipSegment",
    # players
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
    # errors
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
