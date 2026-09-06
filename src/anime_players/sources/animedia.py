"""Помощник для сайта Animedia (amd.online, бывший animedia.tv).

Даёт то, чего не хватает плееру: поиск тайтла, список серий и ссылки на плееры.
Сам сайт отдаёт две вещи — свой плеер ``aser.pro/vod/<id>`` (разбирает
:class:`~anime_players.players.animedia.AnimediaPlayer`) и iframe Kodik
(разбирает :class:`~anime_players.players.kodik.KodikPlayer`).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..errors import NotFound, ServiceError
from ..http import DEFAULT_USER_AGENT, HttpClient
from ..models import PlayerResult

__all__ = ["Animedia", "AnimediaItem"]

_SEARCH_LINK = re.compile(r'href="(https://[^"]+/(\d+)-[a-z0-9\-]+\.html)"', re.IGNORECASE)
_TITLE = re.compile(r"<h1[^>]*>([^<]+)</h1>", re.IGNORECASE)
_EPISODE_LINK = re.compile(r'data-vid="(\d+)"\s+data-vlnk="([^"]+)"', re.IGNORECASE)
_KODIK_IFRAME = re.compile(r'(?:src|data-src)="((?://|https://)kodik[^"]+)"', re.IGNORECASE)
_POSTER = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.IGNORECASE)


@dataclass(frozen=True)
class AnimediaItem:
    """Найденный тайтл на amd.online."""

    id: str
    title: str
    url: str
    poster: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class Animedia:
    """Мини-парсер сайта Animedia.

    Пример::

        from anime_players.sources import Animedia
        import anime_players as ap

        with Animedia() as site:
            anime = site.search("Боруто")[0]
            episodes = site.episodes(anime.url)          # {1: 'https://aser.pro/vod/1067', ...}
            result = ap.extract(episodes[1])             # прямые ссылки на видео
    """

    def __init__(
        self,
        *,
        base_url: str = "https://amd.online",
        proxy: Optional[str] = None,
        timeout: float = 25.0,
        user_agent: str = DEFAULT_USER_AGENT,
        client: Optional[HttpClient] = None,
    ) -> None:
        """:param base_url: домен сайта (меняется, когда Animedia переезжает)."""
        self.base_url = base_url.rstrip("/")
        self._client = client or HttpClient(proxy=proxy, timeout=timeout, user_agent=user_agent)
        self._own_client = client is None

    # -- поиск -----------------------------------------------------------
    def search(self, query: str, *, limit: int = 20) -> List[AnimediaItem]:
        """Поиск тайтла по названию."""
        resp = self._client.get(
            f"{self.base_url}/index.php",
            params={"do": "search", "subaction": "search", "story": query},
            headers={"Referer": self.base_url + "/"},
        )
        if resp.status in (403, 503):
            raise ServiceError(
                f"Animedia вернула {resp.status} — возможна защита от ботов.",
                status=resp.status,
                url=resp.url,
            )
        resp.raise_for_status()

        items: List[AnimediaItem] = []
        seen = set()
        for url, item_id in _SEARCH_LINK.findall(resp.text):
            if item_id in seen:
                continue
            seen.add(item_id)
            items.append(AnimediaItem(id=item_id, title=_title_from_url(url), url=url))
            if len(items) >= limit:
                break
        if not items:
            raise NotFound(f"Animedia: по запросу {query!r} ничего не найдено")
        return items

    # -- страница тайтла --------------------------------------------------
    def info(self, page_url: str) -> AnimediaItem:
        """Название и постер тайтла."""
        text = self._page(page_url)
        title = _TITLE.search(text)
        poster = _POSTER.search(text)
        return AnimediaItem(
            id=_id_from_url(page_url),
            title=html.unescape(title.group(1)).strip() if title else _title_from_url(page_url),
            url=page_url,
            poster=poster.group(1) if poster else None,
        )

    def episodes(self, page_url: str) -> Dict[int, str]:
        """``{номер серии: ссылка на плеер aser.pro}``."""
        text = self._page(page_url)
        episodes: Dict[int, str] = {}
        for number, link in _EPISODE_LINK.findall(text):
            if link.startswith("//"):
                link = "https:" + link
            episodes.setdefault(int(number), html.unescape(link))
        if not episodes:
            raise NotFound(f"На странице {page_url} не найдено ни одной серии")
        return dict(sorted(episodes.items()))

    def players(self, page_url: str) -> Dict[str, List[str]]:
        """Все плееры страницы: ``{"animedia": [...], "kodik": [...]}``."""
        text = self._page(page_url)
        animedia = []
        seen = set()
        for _, link in _EPISODE_LINK.findall(text):
            link = "https:" + link if link.startswith("//") else html.unescape(link)
            if link not in seen:
                seen.add(link)
                animedia.append(link)
        kodik = []
        for link in _KODIK_IFRAME.findall(text):
            link = "https:" + link if link.startswith("//") else link
            if link not in kodik:
                kodik.append(link)
        return {"animedia": animedia, "kodik": kodik}

    def resolve(self, url: str, **kwargs: Any) -> PlayerResult:
        """Сразу получить потоки по ссылке на плеер."""
        from ..registry import extract

        return extract(url, **kwargs)

    # -- внутреннее -------------------------------------------------------
    def _page(self, url: str) -> str:
        resp = self._client.get(url, headers={"Referer": self.base_url + "/"})
        if resp.status == 404:
            raise NotFound(f"Страница не найдена: {url}")
        return resp.raise_for_status().text

    # -- жизненный цикл ---------------------------------------------------
    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def __enter__(self) -> "Animedia":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def _id_from_url(url: str) -> str:
    match = re.search(r"/(\d+)-", url)
    return match.group(1) if match else ""


def _title_from_url(url: str) -> str:
    """Запасное название из слага, если h1 недоступен."""
    match = re.search(r"/\d+-([a-z0-9\-]+)\.html", url)
    return match.group(1).replace("-", " ").capitalize() if match else url
