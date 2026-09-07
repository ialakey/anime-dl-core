"""The base player class: shared setup, url matching, lifecycle."""

from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, Mapping, Optional, Pattern, Tuple

from .errors import UnsupportedUrl
from .http import DEFAULT_USER_AGENT, AsyncHttpClient, HttpClient
from .models import PlayerResult, Stream
from .utils import url_host

__all__ = ["BasePlayer"]


class BasePlayer:
    """Common ancestor of every player.

    Subclasses must set :attr:`name` and implement :meth:`extract` /
    :meth:`aextract`. Everything else — the client, proxies, timeouts, closing
    sessions — comes from here.

    A player can be used as a context manager::

        with KodikPlayer(proxy="socks5://127.0.0.1:9050") as player:
            result = player.extract(embed_url)
    """

    #: Short player name (used in PlayerResult.player and in the CLI).
    name: ClassVar[str] = ""
    #: Human-readable name.
    title: ClassVar[str] = ""
    #: Domains this player serves.
    domains: ClassVar[Tuple[str, ...]] = ()
    #: Extra patterns for links that cannot be recognised by domain alone.
    url_patterns: ClassVar[Tuple[Pattern[str], ...]] = ()
    #: Whether the player was checked against a live example during development (see README).
    verified: ClassVar[bool] = True
    #: A short note about the player's quirks (shown by the CLI --list).
    note: ClassVar[Optional[str]] = None
    #: Headers required when downloading the video files themselves.
    playback_headers: ClassVar[Dict[str, str]] = {}

    def __init__(
        self,
        client: Optional[HttpClient] = None,
        *,
        proxy: Optional[str] = None,
        timeout: float = 20.0,
        user_agent: str = DEFAULT_USER_AGENT,
        headers: Optional[Mapping[str, str]] = None,
        async_client: Optional[AsyncHttpClient] = None,
    ) -> None:
        """
        :param client: an existing sync client (proxy and timeout are then taken from it).
        :param proxy: http/socks5 proxy for every request this player makes.
        :param timeout: request timeout in seconds.
        :param user_agent: User-Agent for every request.
        :param headers: extra headers added to every request.
        :param async_client: an existing async client for :meth:`aextract`.
        """
        self._client_options: Dict[str, Any] = {
            "proxy": proxy,
            "timeout": timeout,
            "user_agent": user_agent,
            "headers": dict(headers) if headers else None,
        }
        self._client = client
        self._own_client = client is None
        self._async_client = async_client
        self._own_async_client = async_client is None

    # -- clients -------------------------------------------------------
    @property
    def client(self) -> HttpClient:
        """Synchronous http client (created on first use)."""
        if self._client is None:
            self._client = HttpClient(**self._client_options)
        return self._client

    @property
    def async_client(self) -> AsyncHttpClient:
        """Asynchronous http client (created on first use)."""
        if self._async_client is None:
            self._async_client = AsyncHttpClient(**self._client_options)
        return self._async_client

    # -- url matching --------------------------------------------------
    @classmethod
    def matches(cls, url: str) -> bool:
        """Whether this player serves that url."""
        if not url:
            return False
        host = url_host(url)
        for domain in cls.domains:
            if host == domain or host.endswith("." + domain):
                return True
        return any(pattern.search(url) for pattern in cls.url_patterns)

    @classmethod
    def ensure_matches(cls, url: str) -> str:
        if not cls.matches(url):
            raise UnsupportedUrl(f"The url {url!r} does not look like the {cls.name!r} player")
        return url

    # -- main interface ------------------------------------------------
    def extract(self, url: str, **kwargs: Any) -> PlayerResult:
        """Parse the url and return the streams that were found."""
        raise NotImplementedError

    async def aextract(self, url: str, **kwargs: Any) -> PlayerResult:
        """Async counterpart of :meth:`extract`."""
        raise NotImplementedError(f"The {self.name} player has no async mode")

    # -- conveniences for callers ---------------------------------------
    def fetch(self, stream: Stream) -> str:
        """Downloads a playlist/manifest with the headers it needs."""
        return self.client.get(stream.url, headers=stream.headers).raise_for_status().text

    async def afetch(self, stream: Stream) -> str:
        resp = await self.async_client.get(stream.url, headers=stream.headers)
        return resp.raise_for_status().text

    # -- lifecycle -------------------------------------------------------
    def close(self) -> None:
        if self._client is not None and self._own_client:
            self._client.close()
            self._client = None

    async def aclose(self) -> None:
        if self._async_client is not None and self._own_async_client:
            await self._async_client.close()
            self._async_client = None
        self.close()

    def __enter__(self) -> "BasePlayer":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    async def __aenter__(self) -> "BasePlayer":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} name={self.name!r}>"


def compile_patterns(*patterns: str) -> Tuple[Pattern[str], ...]:
    """Helper for subclasses: compile the regexes for url_patterns."""
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)
