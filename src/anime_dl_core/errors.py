"""Library exceptions.

Everything raised here derives from :class:`AnimeDlCoreError`, so calling code
only has to catch that one.
"""

from __future__ import annotations

__all__ = [
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


class AnimeDlCoreError(Exception):
    """Base class for every error this library raises."""


class UnsupportedUrl(AnimeDlCoreError):
    """The URL does not match any known player."""


class NetworkError(AnimeDlCoreError):
    """Network failure: timeout, DNS, dropped connection, proxy error."""


class ServiceError(AnimeDlCoreError):
    """The player's server answered unexpectedly (status != 200, wrong content type)."""

    def __init__(self, message: str, *, status: "int | None" = None, url: "str | None" = None) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class ExtractionError(AnimeDlCoreError):
    """The response arrived but could not be parsed — the player probably changed its markup."""


class NoStreamsFound(ExtractionError):
    """The page parsed fine, but it contains no video links at all."""


class DecryptionError(ExtractionError):
    """A link could not be decrypted (relevant for Kodik)."""


class ContentBlocked(AnimeDlCoreError):
    """Content is blocked: geo restriction, age gate, or a rights-holder takedown."""


class NotFound(AnimeDlCoreError):
    """The requested episode, dub, or video does not exist on the player."""
