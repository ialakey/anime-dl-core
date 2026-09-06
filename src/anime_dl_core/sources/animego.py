"""Необязательный помощник: где взять ссылки на плееры.

Сама библиотека занимается плеерами, но ссылку на плеер нужно откуда-то получить.
Этот модуль умеет минимум для сквозного сценария на примере AnimeGO:
поиск -> список серий -> список плееров (Aniboom / CVH / Kodik / Sibnet) -> потоки.

Разметка сайта может меняться — если поиск перестал работать, чинить нужно
регулярки здесь, ядро библиотеки от этого не зависит.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ..errors import ExtractionError, NotFound, ServiceError
from ..http import DEFAULT_USER_AGENT, HttpClient
from ..models import PlayerResult

__all__ = ["AnimeGo", "AnimeItem", "PlayerLink"]

_ITEM_SPLIT = re.compile(r'class="ani-grid__item ')
_ITEM_LINK = re.compile(r'href="(/anime/([a-z0-9\-]+)-(\d+))"', re.IGNORECASE)
_ITEM_TITLE = re.compile(r'<a\s+title="([^"]+)"\s+href="/anime/[^"]+"')
_ITEM_IMAGE = re.compile(r'<img[^>]+src="([^"]+)"')
_ITEM_RATING = re.compile(r'class="rating-badge[^"]*">\s*([\d.]+)\s*<')
_ITEM_ORIGINAL = re.compile(r'text-line-clamp"[^>]*>\s*([^<>]{2,120}?)\s*</div>')
_BUTTON = re.compile(r"<button\b[^>]*>", re.IGNORECASE)
_ATTR = re.compile(r'([a-zA-Z0-9\-]+)="([^"]*)"')
_EPISODE = re.compile(r'data-episode="(\d+)"[^>]*data-episode-number="(\d+)"', re.IGNORECASE)
_EPISODE_REVERSED = re.compile(r'data-episode-number="(\d+)"[^>]*data-episode="(\d+)"', re.IGNORECASE)
_CVH_ID = re.compile(r"/cdn-iframe/(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class AnimeItem:
    """Найденное аниме."""

    id: str
    slug: str
    title: str
    url: str
    original_title: Optional[str] = None
    poster: Optional[str] = None
    rating: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class PlayerLink:
    """Ссылка на конкретный плеер для конкретной озвучки."""

    player: str
    """Название плеера на сайте: ``AniBoom``, ``CVH``, ``Kodik``, ``Sibnet``."""
    label: str
    """Название озвучки."""
    embed: str
    """Ссылка, которую нужно передать в :func:`anime_dl_core.extract`."""
    translation_id: Optional[str] = None
    cvh_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class AnimeGo:
    """Мини-парсер AnimeGO: поиск и получение ссылок на плееры.

    Пример::

        from anime_dl_core.sources import AnimeGo
        import anime_dl_core

        site = AnimeGo()
        anime = site.search("Магическая битва")[0]
        links = site.players(anime.id, episode=1)
        aniboom = next(link for link in links if link.player == "AniBoom")
        result = anime_dl_core.extract(aniboom.embed)
    """

    def __init__(
        self,
        *,
        mirror: Optional[str] = None,
        proxy: Optional[str] = None,
        timeout: float = 20.0,
        user_agent: str = DEFAULT_USER_AGENT,
        client: Optional[HttpClient] = None,
    ) -> None:
        """:param mirror: домен зеркала, если animego.org заблокирован (например ``animego.me``)."""
        self.base_url = f"https://{mirror}" if mirror else "https://animego.org"
        self._client = client or HttpClient(proxy=proxy, timeout=timeout, user_agent=user_agent)
        self._own_client = client is None
        self._episodes_cache: Dict[str, Dict[int, str]] = {}

    # -- поиск ---------------------------------------------------------
    def search(self, query: str, *, limit: int = 20) -> List[AnimeItem]:
        """Поиск аниме по названию."""
        resp = self._client.get(f"{self.base_url}/search/anime?q={quote(query)}")
        if resp.status in (403, 503):
            raise ServiceError(
                f"AnimeGO вернул {resp.status} — вероятно, включилась защита Cloudflare. "
                "Попробуйте прокси или зеркало.",
                status=resp.status,
                url=resp.url,
            )
        resp.raise_for_status()

        items: List[AnimeItem] = []
        for chunk in _ITEM_SPLIT.split(resp.text)[1:]:
            link = _ITEM_LINK.search(chunk)
            title = _ITEM_TITLE.search(chunk)
            if not link or not title:
                continue
            original = _ITEM_ORIGINAL.search(chunk)
            image = _ITEM_IMAGE.search(chunk)
            rating = _ITEM_RATING.search(chunk)
            items.append(
                AnimeItem(
                    id=link.group(3),
                    slug=link.group(2),
                    title=html.unescape(title.group(1)),
                    url=self.base_url + link.group(1),
                    original_title=html.unescape(original.group(1)) if original else None,
                    poster=image.group(1) if image else None,
                    rating=rating.group(1) if rating else None,
                )
            )
            if len(items) >= limit:
                break
        if not items:
            if "ничего не найдено" in resp.text.lower():
                raise NotFound(f"AnimeGO: по запросу {query!r} ничего не найдено")
            raise NotFound(
                f"AnimeGO не вернул ни одной карточки по запросу {query!r}. "
                "Так бывает, когда сайт фильтрует запрос (часть тайтлов скрыта) "
                "или изменилась вёрстка выдачи — тогда правьте регулярки в sources/animego.py."
            )
        return items

    @staticmethod
    def anime_id(url: str) -> str:
        """``https://animego.org/anime/naruto-70`` -> ``70``."""
        match = re.search(r"-(\d+)/?$", url.strip())
        if not match:
            raise ExtractionError(f"В ссылке {url!r} нет id аниме AnimeGO")
        return match.group(1)

    # -- плееры ---------------------------------------------------------
    def episodes(self, anime_id: str) -> Dict[int, str]:
        """``{номер серии: ссылка на плеер этой серии}``."""
        anime_id = str(anime_id)
        if anime_id in self._episodes_cache:
            return self._episodes_cache[anime_id]
        content = self._player_html(f"{self.base_url}/player/{anime_id}")
        episodes: Dict[int, str] = {}
        for episode_id, number in _EPISODE.findall(content):
            episodes[int(number)] = f"{self.base_url}/player/videos/{episode_id}"
        for number, episode_id in _EPISODE_REVERSED.findall(content):
            episodes.setdefault(int(number), f"{self.base_url}/player/videos/{episode_id}")
        self._episodes_cache[anime_id] = episodes
        return episodes

    def players(self, anime_id: str, episode: int = 1) -> List[PlayerLink]:
        """Список плееров и озвучек для серии."""
        anime_id = str(anime_id)
        if episode == 1:
            url = f"{self.base_url}/player/{anime_id}"
        else:
            episodes = self.episodes(anime_id)
            if episode not in episodes:
                raise NotFound(
                    f"У аниме {anime_id} нет серии {episode}. Доступные: {sorted(episodes)[:1]}"
                    f"..{sorted(episodes)[-1:]}"
                )
            url = episodes[episode]

        content = self._player_html(url)
        links: List[PlayerLink] = []
        for tag in _BUTTON.findall(content):
            attrs = dict(_ATTR.findall(tag))
            embed = attrs.get("data-player")
            label = attrs.get("data-translation-title")
            if not embed or not label:
                continue
            if embed.startswith("//"):
                embed = "https:" + embed
            cvh = _CVH_ID.search(embed)
            links.append(
                PlayerLink(
                    player=attrs.get("data-provider-title") or "unknown",
                    label=html.unescape(label).replace(" (ошибка)", "").strip(),
                    embed=html.unescape(embed),
                    translation_id=attrs.get("data-ptranslation"),
                    cvh_id=cvh.group(1) if cvh else None,
                )
            )
        if not links:
            raise NotFound(f"AnimeGO не отдал ни одного плеера для аниме {anime_id}, серия {episode}")
        return links

    def resolve(self, link: "PlayerLink | str", **kwargs: Any) -> PlayerResult:
        """Сразу получить потоки: принимает :class:`PlayerLink` или ссылку на embed."""
        from ..registry import extract

        embed = link.embed if isinstance(link, PlayerLink) else str(link)
        return extract(embed, **kwargs)

    # -- внутреннее ------------------------------------------------------
    def _player_html(self, url: str) -> str:
        resp = self._client.get(
            url, headers={"X-Requested-With": "XMLHttpRequest", "Referer": self.base_url + "/"}
        )
        if resp.status in (403, 503):
            raise ServiceError(
                f"AnimeGO вернул {resp.status} при запросе плеера — вероятно, Cloudflare.",
                status=resp.status,
                url=url,
            )
        if resp.status == 404:
            raise NotFound(f"Плеер не найден: {url}")
        resp.raise_for_status()
        try:
            data = json.loads(resp.text)
        except ValueError as exc:
            raise ExtractionError(f"Ответ плеера AnimeGO не является json ({url}): {exc}") from exc
        content = (data.get("data") or {}).get("content")
        if not content:
            raise ExtractionError(f"В ответе плеера AnimeGO нет html-содержимого: {url}")
        return html.unescape(content)

    # -- жизненный цикл ---------------------------------------------------
    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def __enter__(self) -> "AnimeGo":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
