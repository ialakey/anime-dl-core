"""Базовый класс плеера: общая инициализация, сопоставление ссылок, жизненный цикл."""

from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, Mapping, Optional, Pattern, Tuple

from .errors import UnsupportedUrl
from .http import DEFAULT_USER_AGENT, AsyncHttpClient, HttpClient
from .models import PlayerResult, Stream
from .utils import url_host

__all__ = ["BasePlayer"]


class BasePlayer:
    """Общий предок всех плееров.

    Наследники обязаны задать :attr:`name` и реализовать :meth:`extract` /
    :meth:`aextract`. Всё остальное (клиент, прокси, таймауты, закрытие сессий)
    берётся отсюда.

    Плеер можно использовать как контекстный менеджер::

        with KodikPlayer(proxy="socks5://127.0.0.1:9050") as player:
            result = player.extract(embed_url)
    """

    #: Короткое имя плеера (используется в PlayerResult.player и в CLI).
    name: ClassVar[str] = ""
    #: Человекочитаемое название.
    title: ClassVar[str] = ""
    #: Домены, которые обслуживает плеер.
    domains: ClassVar[Tuple[str, ...]] = ()
    #: Дополнительные регулярки для ссылок, которые не опознать по домену.
    url_patterns: ClassVar[Tuple[Pattern[str], ...]] = ()
    #: Проверялся ли плеер на живом примере при разработке (см. README).
    verified: ClassVar[bool] = True
    #: Короткая заметка об особенностях плеера (показывается в CLI --list).
    note: ClassVar[Optional[str]] = None
    #: Заголовки, которые нужны при скачивании самих видеофайлов.
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
        :param client: готовый синхронный клиент (тогда прокси/таймаут берутся из него).
        :param proxy: http/socks5 прокси для всех запросов плеера.
        :param timeout: таймаут запроса в секундах.
        :param user_agent: User-Agent для всех запросов.
        :param headers: дополнительные заголовки ко всем запросам.
        :param async_client: готовый асинхронный клиент для :meth:`aextract`.
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

    # -- клиенты -------------------------------------------------------
    @property
    def client(self) -> HttpClient:
        """Синхронный http-клиент (создаётся при первом обращении)."""
        if self._client is None:
            self._client = HttpClient(**self._client_options)
        return self._client

    @property
    def async_client(self) -> AsyncHttpClient:
        """Асинхронный http-клиент (создаётся при первом обращении)."""
        if self._async_client is None:
            self._async_client = AsyncHttpClient(**self._client_options)
        return self._async_client

    # -- сопоставление ссылок -----------------------------------------
    @classmethod
    def matches(cls, url: str) -> bool:
        """Обслуживает ли этот плеер такую ссылку."""
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
            raise UnsupportedUrl(f"Ссылка {url!r} не похожа на плеер {cls.name!r}")
        return url

    # -- основной интерфейс -------------------------------------------
    def extract(self, url: str, **kwargs: Any) -> PlayerResult:
        """Разобрать ссылку и вернуть найденные потоки."""
        raise NotImplementedError

    async def aextract(self, url: str, **kwargs: Any) -> PlayerResult:
        """Асинхронный вариант :meth:`extract`."""
        raise NotImplementedError(f"Плеер {self.name} не поддерживает асинхронный режим")

    # -- утилиты для пользователя -------------------------------------
    def fetch(self, stream: Stream) -> str:
        """Скачивает содержимое плейлиста/манифеста с нужными заголовками."""
        return self.client.get(stream.url, headers=stream.headers).raise_for_status().text

    async def afetch(self, stream: Stream) -> str:
        resp = await self.async_client.get(stream.url, headers=stream.headers)
        return resp.raise_for_status().text

    # -- жизненный цикл ------------------------------------------------
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

    def __repr__(self) -> str:  # pragma: no cover - отладочное
        return f"<{type(self).__name__} name={self.name!r}>"


def compile_patterns(*patterns: str) -> Tuple[Pattern[str], ...]:
    """Хелпер для наследников: скомпилировать регулярки для url_patterns."""
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)
