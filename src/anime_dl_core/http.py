"""Тонкая обёртка над requests/aiohttp с одинаковым интерфейсом.

Синхронный и асинхронный клиенты возвращают один и тот же :class:`Response`,
поэтому функции разбора страниц в плеерах не зависят от способа запроса.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

import requests

from .errors import NetworkError, ServiceError

__all__ = ["Response", "HttpClient", "AsyncHttpClient", "DEFAULT_USER_AGENT"]

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


@dataclass
class Response:
    """Ответ сервера в минимальном виде."""

    status: int
    text: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> Any:
        try:
            return _json.loads(self.text)
        except ValueError as exc:
            raise ServiceError(
                f"Ожидался JSON, получено что-то другое ({self.url}): {exc}",
                status=self.status,
                url=self.url,
            ) from exc

    def raise_for_status(self) -> "Response":
        if not self.ok:
            raise ServiceError(
                f"Сервер вернул код {self.status} (ожидался 2xx): {self.url}",
                status=self.status,
                url=self.url,
            )
        return self


def _merge_headers(base: Mapping[str, str], extra: Optional[Mapping[str, str]]) -> Dict[str, str]:
    headers = dict(base)
    if extra:
        headers.update({k: v for k, v in extra.items() if v is not None})
    return headers


class HttpClient:
    """Синхронный http-клиент на requests.

    :param proxy: адрес прокси вида http://host:port или socks5://user:pass@host:port
        (для socks нужен ``pip install anime-dl-core[socks]``).
    :param timeout: таймаут одного запроса в секундах.
    :param user_agent: значение заголовка User-Agent.
    :param headers: заголовки, добавляемые ко всем запросам.
    :param session: готовая ``requests.Session`` (тогда закрывать её должен вызывающий код).
    """

    def __init__(
        self,
        *,
        proxy: Optional[str] = None,
        timeout: float = 20.0,
        user_agent: str = DEFAULT_USER_AGENT,
        headers: Optional[Mapping[str, str]] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.timeout = timeout
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self._own_session = session is None
        self.session = session or requests.Session()
        self.session.headers.update(
            _merge_headers(
                {"User-Agent": user_agent, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}, headers
            )
        )

    # -- запросы -------------------------------------------------------
    def get(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, Any]] = None,
        allow_redirects: bool = True,
    ) -> Response:
        return self._request(
            "GET", url, headers=headers, params=params, allow_redirects=allow_redirects
        )

    def post(
        self,
        url: str,
        *,
        data: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Response:
        return self._request("POST", url, headers=headers, data=data)

    def resolve_redirect(self, url: str, *, headers: Optional[Mapping[str, str]] = None) -> str:
        """Возвращает адрес, на который редиректит url (или сам url, если редиректа нет)."""
        resp = self._request("GET", url, headers=headers, allow_redirects=False, stream=True)
        location = resp.headers.get("Location") or resp.headers.get("location")
        if not location:
            return url
        if location.startswith("//"):
            return "https:" + location
        return location

    def _request(self, method: str, url: str, *, stream: bool = False, **kwargs: Any) -> Response:
        try:
            resp = self.session.request(
                method, url, timeout=self.timeout, proxies=self.proxies, stream=stream, **kwargs
            )
        except requests.RequestException as exc:
            raise NetworkError(f"Ошибка соединения при {method} {url}: {exc}") from exc
        try:
            text = "" if stream else resp.text
        finally:
            if stream:
                resp.close()
        return Response(resp.status_code, text, str(resp.url), dict(resp.headers))

    # -- жизненный цикл ------------------------------------------------
    def close(self) -> None:
        if self._own_session:
            self.session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


class AsyncHttpClient:
    """Асинхронный клиент на aiohttp. Требует ``pip install anime-dl-core[async]``."""

    def __init__(
        self,
        *,
        proxy: Optional[str] = None,
        timeout: float = 20.0,
        user_agent: str = DEFAULT_USER_AGENT,
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        try:
            import aiohttp  # noqa: F401
        except ImportError as exc:  # pragma: no cover - зависит от окружения
            raise ImportError(
                "Для асинхронного режима нужен aiohttp: pip install anime-dl-core[async]"
            ) from exc
        self.timeout = timeout
        self.proxy = proxy
        self.headers = _merge_headers(
            {"User-Agent": user_agent, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"}, headers
        )
        self._session = None

    async def _get_session(self):
        import aiohttp

        if self._session is None or self._session.closed:
            connector = None
            if self.proxy and self.proxy.startswith("socks"):
                try:
                    from aiohttp_socks import ProxyConnector
                except ImportError as exc:  # pragma: no cover
                    raise ImportError(
                        "Для socks-прокси в асинхронном режиме нужен aiohttp-socks: "
                        "pip install anime-dl-core[socks]"
                    ) from exc
                connector = ProxyConnector.from_url(self.proxy)
            self._session = aiohttp.ClientSession(
                headers=self.headers,
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    async def get(
        self,
        url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        params: Optional[Mapping[str, Any]] = None,
        allow_redirects: bool = True,
    ) -> Response:
        return await self._request(
            "GET", url, headers=headers, params=params, allow_redirects=allow_redirects
        )

    async def post(
        self,
        url: str,
        *,
        data: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Response:
        return await self._request("POST", url, headers=headers, data=data)

    async def resolve_redirect(
        self, url: str, *, headers: Optional[Mapping[str, str]] = None
    ) -> str:
        resp = await self._request(
            "GET", url, headers=headers, allow_redirects=False, read_body=False
        )
        location = resp.headers.get("Location") or resp.headers.get("location")
        if not location:
            return url
        if location.startswith("//"):
            return "https:" + location
        return location

    async def _request(self, method: str, url: str, *, read_body: bool = True, **kwargs: Any) -> Response:
        import aiohttp

        session = await self._get_session()
        if self.proxy and not self.proxy.startswith("socks"):
            kwargs["proxy"] = self.proxy
        try:
            async with session.request(method, url, **kwargs) as resp:
                text = await resp.text() if read_body else ""
                return Response(resp.status, text, str(resp.url), dict(resp.headers))
        except aiohttp.ClientError as exc:
            raise NetworkError(f"Ошибка соединения при {method} {url}: {exc}") from exc

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def __aenter__(self) -> "AsyncHttpClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()
