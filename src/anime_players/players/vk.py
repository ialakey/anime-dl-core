"""Плеер VK Video (vk.com / vkvideo.ru / vk.ru).

Как устроен (актуально на сентябрь 2026): страница ``video_ext.php`` кладёт в
``window.cur`` объект ``apiPrefetchCache`` — предзагруженные ответы внутреннего
API. Нужный ответ — метод ``video.get``: в нём есть ``files`` со ссылками
(``mp4_144`` … ``mp4_2160``, ``hls_ondemand``, ``dash_ondemand``), название,
длительность и обложка.

Старый формат (``var playerParams = {...}`` с ключами ``url720``) тоже
поддерживается — он ещё встречается на части зеркал и мобильных страниц.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..base import BasePlayer, compile_patterns
from ..errors import ContentBlocked, ExtractionError, NoStreamsFound
from ..models import PlayerResult, Stream, StreamKind
from ..utils import absolute_url, parse_master_playlist, to_int

__all__ = ["VkPlayer"]

_PREFETCH_KEY = '"apiPrefetchCache"'
_PLAYER_PARAMS = re.compile(r"var\s+playerParams\s*=\s*(\{.*?\})\s*;", re.DOTALL)
_MP4_KEY = re.compile(r"^(?:mp4_|url)(\d{3,4})$")
_HLS_KEYS = ("hls_ondemand", "hls", "hls_fmp4", "hls_live_playback", "live_playback_hls")
_DASH_KEYS = ("dash_ondemand", "dash_sep", "dash_webm", "dash", "dash_live_playback")
#: ``video-123_456``, ``video-123_456_ab12cd``, ``-123_456``
_VIDEO_ID = re.compile(r"(?:video)?(-?\d+)_(\d+)(?:_([0-9a-f]+))?", re.IGNORECASE)


class VkPlayer(BasePlayer):
    """Плеер VK Video.

    Принимает и ссылку на embed, и обычную ссылку на видео, и просто пару
    ``owner_id_video_id``::

        with VkPlayer() as player:
            result = player.extract("https://vk.com/video_ext.php?oid=-116782009&id=456239250")
            result = player.extract("https://vkvideo.ru/video-116782009_456239250")
            result = player.extract("-116782009_456239250")

            print(result.title, result.qualities)
            print(result.best(kind="mp4").url)

    Часть видео (приватные, «только для друзей», удалённые) анонимно недоступна —
    тогда бросается :class:`~anime_players.errors.ContentBlocked`. Для видео,
    закрытых по ссылке, нужен параметр ``hash`` из кода вставки — передайте его
    в ссылке или через :meth:`embed_url`.
    """

    name = "vk"
    title = "VK Video"
    domains = ("vk.com", "vkvideo.ru", "vk.ru", "userapi.com", "m.vk.com", "m.vk.ru")
    url_patterns = compile_patterns(
        r"video_ext\.php", r"/video-?\d+_\d+", r"^-?\d+_\d+(?:_[0-9a-f]+)?$"
    )
    embed_base = "https://vk.com/video_ext.php"
    playback_headers = {"Referer": "https://vk.com/", "Origin": "https://vk.com"}

    # -- сборка ссылок ---------------------------------------------------
    @classmethod
    def embed_url(
        cls,
        owner_id: Any,
        video_id: Any,
        *,
        access_key: Optional[str] = None,
        hd: int = 2,
    ) -> str:
        """Ссылка на embed по ``oid``/``id`` (и ``hash``, если видео по ссылке)."""
        url = f"{cls.embed_base}?oid={owner_id}&id={video_id}&hd={hd}"
        return url + (f"&hash={access_key}" if access_key else "")

    @staticmethod
    def video_ids(url: str) -> Tuple[str, str, Optional[str]]:
        """``(owner_id, video_id, access_key)`` из любой формы ссылки VK."""
        url = str(url).strip()
        if "video_ext.php" in url:
            from ..utils import query_param

            owner, video = query_param(url, "oid"), query_param(url, "id")
            if owner and video:
                return owner, video, query_param(url, "hash")
        match = _VIDEO_ID.search(url)
        if not match:
            raise ExtractionError(
                f"Не удалось понять ссылку VK: {url!r}. Ожидалось video_ext.php?oid=&id=, "
                "ссылка вида /video-123_456 или строка '-123_456'."
            )
        return match.group(1), match.group(2), match.group(3)

    # -- основной интерфейс ----------------------------------------------
    def extract(
        self,
        url: str,
        *,
        referer: Optional[str] = None,
        resolve_qualities: bool = True,
        **_: Any,
    ) -> PlayerResult:
        """Возвращает mp4/HLS/DASH ссылки видео VK.

        :param url: embed, обычная ссылка на видео или ``owner_id_video_id``.
        :param referer: Referer запроса (по умолчанию ``https://vk.com/``).
        :param resolve_qualities: развернуть мастер-плейлист HLS в отдельные
            качества (один дополнительный запрос).
        """
        embed = self._normalize(url)
        page = self.client.get(embed, headers={"Referer": referer or "https://vk.com/"})
        result = self._build_result(page.raise_for_status().text, embed)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = self.client.get(master.url, headers=master.headers)
                if content.ok:
                    result.streams.extend(self._variant_streams(content.text, master))
        return result

    async def aextract(
        self,
        url: str,
        *,
        referer: Optional[str] = None,
        resolve_qualities: bool = True,
        **_: Any,
    ) -> PlayerResult:
        embed = self._normalize(url)
        page = await self.async_client.get(embed, headers={"Referer": referer or "https://vk.com/"})
        result = self._build_result(page.raise_for_status().text, embed)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = await self.async_client.get(master.url, headers=master.headers)
                if content.ok:
                    result.streams.extend(self._variant_streams(content.text, master))
        return result

    # -- внутреннее -------------------------------------------------------
    def _normalize(self, url: str) -> str:
        url = str(url).strip()
        if url.startswith("//"):
            url = "https:" + url
        if "video_ext.php" in url:
            return url
        owner, video, access_key = self.video_ids(url)
        return self.embed_url(owner, video, access_key=access_key)

    def _variant_streams(self, master_content: str, master: Stream) -> List[Stream]:
        streams = []
        for variant in parse_master_playlist(master_content, master.url):
            streams.append(
                Stream(
                    absolute_url(master.url, variant["url"]),
                    StreamKind.HLS,
                    variant["height"],
                    master.headers,
                    f"{variant['height']}p" if variant["height"] else None,
                    extra={"bandwidth": variant["bandwidth"], "codecs": variant["codecs"]},
                )
            )
        return streams

    # -- разбор страницы ---------------------------------------------------
    @staticmethod
    def _parse_prefetch(text: str) -> Optional[Dict[str, Any]]:
        """Ищет ответ метода ``video.get`` в ``apiPrefetchCache``."""
        index = text.find(_PREFETCH_KEY)
        if index < 0:
            return None
        start = text.find("[", index)
        if start < 0:
            return None
        try:
            entries, _ = json.JSONDecoder().raw_decode(text[start:])
        except ValueError:
            return None
        for entry in entries or []:
            if entry.get("method") != "video.get":
                continue
            items = ((entry.get("response") or {}).get("items")) or []
            if items:
                return items[0]
        return None

    @staticmethod
    def _parse_player_params(text: str) -> Optional[Dict[str, Any]]:
        """Старый формат страницы: ``var playerParams = {...}``."""
        raw = _PLAYER_PARAMS.search(text)
        if not raw:
            return None
        try:
            params = json.loads(raw.group(1))
        except ValueError:
            return None
        source = params.get("params")
        source = source[0] if isinstance(source, list) and source else params
        if not isinstance(source, dict):
            return None
        # приводим к виду нового формата
        files = {key: value for key, value in source.items() if isinstance(value, str)}
        return {
            "files": files,
            "title": source.get("md_title") or source.get("title"),
            "duration": source.get("duration"),
            "image": [{"url": source.get("jpg") or source.get("thumb"), "width": 0}]
            if source.get("jpg") or source.get("thumb")
            else [],
            "owner_id": source.get("oid"),
            "id": source.get("vid"),
        }

    def _build_result(self, text: str, url: str) -> PlayerResult:
        item = self._parse_prefetch(text) or self._parse_player_params(text)
        if item is None:
            raise ContentBlocked(
                f"VK не отдал данные видео для {url}. Обычно это значит, что видео приватное, "
                "удалено, доступно только по ссылке (нужен параметр hash из кода вставки) "
                "или закрыто в вашем регионе."
            )

        files = item.get("files") or {}
        headers = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]

        streams: List[Stream] = []
        for key, value in files.items():
            if not isinstance(value, str) or not value.startswith("http"):
                continue
            quality = _MP4_KEY.match(key)
            if quality:
                height = int(quality.group(1))
                streams.append(
                    Stream(value, StreamKind.MP4, height, headers, f"{height}p", extra={"key": key})
                )
            elif key in _HLS_KEYS:
                streams.append(Stream(value, StreamKind.HLS, None, headers, "master", extra={"key": key}))
            elif key in _DASH_KEYS:
                streams.append(Stream(value, StreamKind.DASH, None, headers, key, extra={"key": key}))
        streams.sort(key=lambda stream: stream.quality or 0)

        if not streams:
            raise NoStreamsFound(
                f"VK вернул описание видео, но без ссылок на файлы: {url}. "
                f"Доступные ключи: {sorted(files)}"
            )

        images = [image for image in (item.get("image") or []) if image.get("url")]
        poster = max(images, key=lambda image: image.get("width") or 0)["url"] if images else None

        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=streams,
            title=item.get("title"),
            poster=poster,
            duration=to_int(item.get("duration")),
            extra={
                "owner_id": item.get("owner_id"),
                "video_id": item.get("id"),
                "is_live": bool(item.get("live")) or ("hls" in files and "hls_ondemand" not in files),
                "failover_host": files.get("failover_host"),
                "share_url": item.get("share_url"),
                "views": item.get("views"),
            },
        )
