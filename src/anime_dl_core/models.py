"""Модели данных, которые возвращают все плееры библиотеки."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

__all__ = ["StreamKind", "Stream", "SkipSegment", "PlayerResult"]


class StreamKind(str, Enum):
    """Тип потока."""

    HLS = "hls"
    """m3u8 — мастер-плейлист или плейлист конкретного качества."""
    DASH = "dash"
    """mpd — MPEG-DASH манифест."""
    MP4 = "mp4"
    """Прямая ссылка на файл (mp4/webm)."""

    def __str__(self) -> str:  # pragma: no cover - тривиально
        return self.value


# Порядок предпочтения при прочих равных: прямой файл проще всего скачать,
# мастер-плейлист удобнее всего проигрывать.
_KIND_ORDER = {StreamKind.MP4: 2, StreamKind.HLS: 1, StreamKind.DASH: 0}


@dataclass(frozen=True)
class SkipSegment:
    """Фрагмент, который плеер предлагает пропустить (опенинг/эндинг).

    Время указано в секундах от начала файла.
    """

    start: int
    end: int
    kind: Optional[str] = None  # "opening" | "ending" | None

    @property
    def duration(self) -> int:
        return max(0, self.end - self.start)

    def to_dict(self) -> Dict[str, Any]:
        return {"start": self.start, "end": self.end, "kind": self.kind}


@dataclass(frozen=True)
class Stream:
    """Одна ссылка на видео.

    :param url: Прямая ссылка на плейлист/манифест/файл.
    :param kind: Тип потока (:class:`StreamKind`).
    :param quality: Высота картинки в пикселях (720, 1080, ...) или ``None``,
        если качество неизвестно (например, для мастер-плейлиста HLS).
    :param headers: Заголовки, которые обязательно нужно отправлять при
        скачивании/проигрывании (обычно ``Referer`` и ``User-Agent``).
    :param label: Человекочитаемая подпись (озвучка, "master", "AniLibria", ...).
    :param extra: Всё, что специфично для конкретного плеера.
    """

    url: str
    kind: StreamKind
    quality: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)
    label: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        q = f"{self.quality}p" if self.quality else "auto"
        return f"[{self.kind.value} {q}] {self.url}"

    @property
    def is_master(self) -> bool:
        """Мастер-плейлист HLS (качество внутри выбирает плеер)."""
        return self.kind is StreamKind.HLS and self.quality is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "kind": self.kind.value,
            "quality": self.quality,
            "headers": dict(self.headers),
            "label": self.label,
            "extra": self.extra,
        }

    def ffmpeg_args(self, output: str, *, extra_args: Iterable[str] = ()) -> List[str]:
        """Готовая команда ffmpeg (списком) для скачивания этого потока.

        >>> stream.ffmpeg_args("episode.mp4")
        ['ffmpeg', '-headers', 'Referer: ...', '-i', 'https://...', '-c', 'copy', 'episode.mp4']
        """
        args: List[str] = ["ffmpeg"]
        if self.headers:
            joined = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
            args += ["-headers", joined]
        args += ["-i", self.url, "-c", "copy"]
        args += list(extra_args)
        args.append(output)
        return args

    def ffmpeg_command(self, output: str, *, extra_args: Iterable[str] = ()) -> str:
        """То же, что :meth:`ffmpeg_args`, но одной строкой для копипаста в терминал."""
        return " ".join(shlex.quote(a) for a in self.ffmpeg_args(output, extra_args=extra_args))


@dataclass
class PlayerResult:
    """Результат разбора плеера.

    :param player: Имя плеера (``"aniboom"``, ``"kodik"``, ...).
    :param source_url: Ссылка, которую разбирали.
    :param streams: Все найденные потоки.
    :param skip_segments: Опенинг/эндинг, если плеер их отдаёт.
    """

    player: str
    source_url: str
    streams: List[Stream] = field(default_factory=list)
    title: Optional[str] = None
    poster: Optional[str] = None
    duration: Optional[int] = None
    translation: Optional[str] = None
    skip_segments: List[SkipSegment] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.streams)

    def __iter__(self):
        return iter(self.streams)

    def __len__(self) -> int:
        return len(self.streams)

    @property
    def qualities(self) -> List[int]:
        """Отсортированный список доступных качеств (без ``None``)."""
        return sorted({s.quality for s in self.streams if s.quality})

    def filter(
        self,
        kind: "StreamKind | str | None" = None,
        *,
        quality: Optional[int] = None,
        max_quality: Optional[int] = None,
    ) -> List[Stream]:
        """Потоки, подходящие под условия (в том же порядке, что и в :attr:`streams`)."""
        if isinstance(kind, str):
            kind = StreamKind(kind)
        res = self.streams
        if kind is not None:
            res = [s for s in res if s.kind is kind]
        if quality is not None:
            res = [s for s in res if s.quality == quality]
        if max_quality is not None:
            res = [s for s in res if s.quality is None or s.quality <= max_quality]
        return list(res)

    def best(
        self,
        kind: "StreamKind | str | None" = None,
        *,
        max_quality: Optional[int] = None,
        allow_master: bool = True,
    ) -> Stream:
        """Лучший поток: максимальное качество, при равенстве — mp4 > hls > dash.

        Потоки с неизвестным качеством (мастер-плейлисты) считаются худшими и
        выбираются, только если других нет. ``allow_master=False`` исключает их
        совсем.

        :raises NoStreamsFound: если под условия ничего не подошло.
        """
        from .errors import NoStreamsFound

        candidates = self.filter(kind, max_quality=max_quality)
        if not allow_master:
            candidates = [s for s in candidates if not s.is_master]
        if not candidates:
            raise NoStreamsFound(
                f"Нет подходящих потоков (player={self.player}, kind={kind}, max_quality={max_quality})"
            )
        return max(
            candidates,
            key=lambda s: (s.quality is not None, s.quality or 0, _KIND_ORDER[s.kind]),
        )

    def master(self) -> Optional[Stream]:
        """Мастер-плейлист HLS, если он есть (удобно отдавать во внешний плеер)."""
        for s in self.streams:
            if s.is_master:
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "player": self.player,
            "source_url": self.source_url,
            "title": self.title,
            "poster": self.poster,
            "duration": self.duration,
            "translation": self.translation,
            "skip_segments": [s.to_dict() for s in self.skip_segments],
            "streams": [s.to_dict() for s in self.streams],
            "extra": self.extra,
        }
