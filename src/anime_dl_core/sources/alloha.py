"""Alloha (api.alloha.tv) — каталог и ссылки на встраиваемый плеер.

Alloha раздаёт видео не прямыми ссылками, а через собственный iframe-плеер.
Открытое API отдаёт по id (Кинопоиск / IMDb / TMDb / название) описание тайтла,
список озвучек, сезоны с сериями и готовые ссылки на iframe для каждой
комбинации «серия + озвучка».

.. important::
   Прямых ссылок на видео (m3u8/mp4) Alloha не отдаёт: сам плеер получает их по
   WebSocket из сильно обфусцированного бандла, и адрес нигде в html не лежит.
   Поэтому Alloha реализована как источник (``sources``), а не как плеер
   (``players``): результат — ссылка на iframe, которую можно вставить к себе
   или открыть в браузере/webview. Если нужны именно файлы — понадобится
   headless-браузер, обычным http-разбором их не достать.

Токен: у API есть публичный токен (используется по умолчанию). Если он
перестанет работать, передайте свой: ``Alloha(token="...")``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..errors import NotFound, ServiceError
from ..http import DEFAULT_USER_AGENT, HttpClient

__all__ = ["Alloha", "AllohaItem", "AllohaTranslation", "PUBLIC_TOKEN"]

#: Публичный токен Alloha, который ходит по открытым проектам.
PUBLIC_TOKEN = "04941a9a3ca3ac16e2b4327347bbc1"

#: Категории Alloha (поле ``category``).
CATEGORIES = {1: "фильм", 2: "мультфильм", 3: "мультсериал", 4: "сериал", 5: "аниме"}


@dataclass(frozen=True)
class AllohaTranslation:
    """Озвучка со ссылкой на плеер."""

    id: str
    name: str
    iframe: str
    quality: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class AllohaItem:
    """Тайтл в базе Alloha."""

    name: str
    original_name: Optional[str]
    year: Optional[int]
    category: Optional[str]
    id_kp: Optional[int]
    id_imdb: Optional[str]
    id_tmdb: Optional[int]
    poster: Optional[str]
    description: Optional[str]
    rating_kp: Optional[float]
    quality: Optional[str]
    iframe: Optional[str]
    translations: List[AllohaTranslation] = field(default_factory=list)
    seasons: Dict[int, List[int]] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_series(self) -> bool:
        return bool(self.seasons)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            key: value
            for key, value in self.__dict__.items()
            if key not in ("translations", "raw")
        }
        data["translations"] = [translation.to_dict() for translation in self.translations]
        return data


class Alloha:
    """Клиент открытого API Alloha.

    Пример::

        from anime_dl_core.sources import Alloha

        with Alloha() as alloha:
            anime = alloha.find(name="Атака титанов")
            print(anime.name, anime.year, anime.seasons)     # {1: [1..25], 2: [...], ...}

            # у каждой серии свой набор озвучек
            voices = alloha.translations_for(anime, season=1, episode=1)
            print([voice.name for voice in voices])

            # ссылка на плеер конкретной серии в конкретной озвучке
            print(alloha.iframe(anime, season=1, episode=1, translation=voices[0].name))
    """

    api_url = "https://api.alloha.tv/"

    def __init__(
        self,
        *,
        token: str = PUBLIC_TOKEN,
        proxy: Optional[str] = None,
        timeout: float = 25.0,
        user_agent: str = DEFAULT_USER_AGENT,
        client: Optional[HttpClient] = None,
    ) -> None:
        """:param token: токен API (по умолчанию публичный, см. :data:`PUBLIC_TOKEN`)."""
        self.token = token
        self._client = client or HttpClient(proxy=proxy, timeout=timeout, user_agent=user_agent)
        self._own_client = client is None

    # -- запросы ----------------------------------------------------------
    def find(
        self,
        *,
        kp: Optional[Any] = None,
        imdb: Optional[str] = None,
        tmdb: Optional[Any] = None,
        name: Optional[str] = None,
    ) -> AllohaItem:
        """Ищет тайтл по одному из идентификаторов или по названию."""
        params: Dict[str, Any] = {"token": self.token}
        for key, value in (("kp", kp), ("imdb", imdb), ("tmdb", tmdb), ("name", name)):
            if value is not None:
                params[key] = value
        if len(params) == 1:
            raise ValueError("Укажите один из параметров: kp, imdb, tmdb или name")

        resp = self._client.get(self.api_url, params=params).raise_for_status()
        data = resp.json()
        if data.get("status") != "success":
            message = data.get("error_info") or data
            if "token" in str(message).lower():
                raise ServiceError(
                    f"Alloha не приняла токен: {message}. Передайте свой: Alloha(token=...)"
                )
            raise NotFound(f"Alloha: ничего не найдено ({message})")

        payload = data.get("data")
        if isinstance(payload, list):
            if not payload:
                raise NotFound("Alloha вернула пустой результат")
            payload = payload[0]
        return _item_from_api(payload)

    def episodes(self, item: AllohaItem, season: int) -> List[int]:
        """Номера серий сезона."""
        if season not in item.seasons:
            raise NotFound(f"Сезон {season} не найден. Доступные: {sorted(item.seasons)}")
        return item.seasons[season]

    def translations_for(
        self,
        item: AllohaItem,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> List[AllohaTranslation]:
        """Озвучки, доступные для тайтла целиком, сезона или конкретной серии.

        У сериала набор озвучек отличается от серии к серии, поэтому перед
        :meth:`iframe` удобно посмотреть, что есть именно у этой серии.
        """
        node = self._node(item, season=season, episode=episode)
        translations = _translation_map(node)
        if not translations:
            return list(item.translations)
        return [
            AllohaTranslation(
                id=str(key),
                name=value.get("translation") or value.get("name") or str(key),
                iframe=value.get("iframe", ""),
                quality=value.get("quality"),
            )
            for key, value in translations.items()
        ]

    def iframe(
        self,
        item: AllohaItem,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        translation: Optional[str] = None,
    ) -> str:
        """Ссылка на плеер: тайтла целиком, конкретной серии или конкретной озвучки.

        :param translation: имя озвучки (``"DEEP"``) или её id (``"260"``).
        """
        node = self._node(item, season=season, episode=episode)

        if translation:
            for key, value in _translation_map(node).items():
                name = value.get("translation") or value.get("name") or ""
                if str(key) == str(translation) or name.lower() == str(translation).lower():
                    return value["iframe"]
            available = [
                (value.get("translation") or value.get("name"))
                for value in _translation_map(node).values()
            ]
            raise NotFound(f"Озвучка {translation!r} не найдена. Доступные: {available}")

        iframe = node.get("iframe") or item.iframe
        if not iframe:
            raise NotFound("Alloha не вернула ссылку на плеер для этого запроса")
        return iframe

    def _node(
        self,
        item: AllohaItem,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Узел ответа API: тайтл -> сезон -> серия."""
        node: Dict[str, Any] = item.raw
        if not item.is_series:
            return node
        if season is None and episode is None:
            return node
        if season is None:
            season = sorted(item.seasons)[0]
        seasons = node.get("seasons") or {}
        season_node = seasons.get(str(season)) or seasons.get(season)
        if not season_node:
            raise NotFound(f"Сезон {season} не найден. Доступные: {sorted(item.seasons)}")
        node = season_node
        if episode is not None:
            episodes = node.get("episodes") or {}
            episode_node = episodes.get(str(episode)) or episodes.get(episode)
            if not episode_node:
                available = item.seasons.get(season, [])
                raise NotFound(
                    f"Серия {episode} не найдена в сезоне {season}. "
                    f"Доступные: {available[:1]}..{available[-1:]}"
                )
            node = episode_node
        return node

    # -- жизненный цикл ---------------------------------------------------
    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def __enter__(self) -> "Alloha":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def _translation_map(node: Dict[str, Any]) -> Dict[str, Any]:
    """Поле ``translation``: у серии это словарь озвучек, у тайтла — строка с перечислением."""
    translations = node.get("translation")
    return translations if isinstance(translations, dict) else {}


def _item_from_api(data: Dict[str, Any]) -> AllohaItem:
    translations = [
        AllohaTranslation(
            id=str(key),
            name=value.get("name") or value.get("translation") or str(key),
            iframe=value.get("iframe", ""),
            quality=value.get("quality"),
        )
        for key, value in (data.get("translation_iframe") or {}).items()
    ]

    seasons: Dict[int, List[int]] = {}
    for key, season in (data.get("seasons") or {}).items():
        try:
            number = int(key)
        except (TypeError, ValueError):
            continue
        episodes = sorted(int(episode) for episode in (season.get("episodes") or {}))
        seasons[number] = episodes

    return AllohaItem(
        name=data.get("name") or "",
        original_name=data.get("original_name"),
        year=data.get("year"),
        category=CATEGORIES.get(data.get("category"), None),
        id_kp=data.get("id_kp"),
        id_imdb=data.get("id_imdb"),
        id_tmdb=data.get("id_tmdb"),
        poster=data.get("poster"),
        description=data.get("description"),
        rating_kp=data.get("rating_kp"),
        quality=data.get("quality"),
        iframe=data.get("iframe"),
        translations=translations,
        seasons=dict(sorted(seasons.items())),
        raw=data,
    )
