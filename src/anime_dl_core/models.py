"""The data models every player in the library returns."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional

__all__ = ["StreamKind", "Stream", "SkipSegment", "PlayerResult"]


class StreamKind(str, Enum):
    """Kind of stream."""

    HLS = "hls"
    """m3u8 — either a master playlist or a playlist for one quality."""
    DASH = "dash"
    """mpd — an MPEG-DASH manifest."""
    MP4 = "mp4"
    """A direct link to a file (mp4/webm)."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# Preference order when everything else is equal: a plain file is the easiest to
# download, a master playlist is the easiest to play.
_KIND_ORDER = {StreamKind.MP4: 2, StreamKind.HLS: 1, StreamKind.DASH: 0}


@dataclass(frozen=True)
class SkipSegment:
    """A stretch the player suggests skipping (opening/ending).

    Times are in seconds from the start of the file.
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
    """A single video link.

    :param url: Direct link to a playlist, a manifest, or a file.
    :param kind: Stream kind (:class:`StreamKind`).
    :param quality: Picture height in pixels (720, 1080, ...), or ``None`` when
        the quality is unknown (an HLS master playlist, for instance).
    :param headers: Headers that must be sent when downloading or playing the
        stream (usually ``Referer`` and ``User-Agent``).
    :param label: Human-readable caption (the dub, ``"master"``, ``"AniLibria"``, ...).
    :param extra: Anything specific to one particular player. ``extra["audio_url"]``
        is the separate HLS audio rendition of a video-only variant; :meth:`ffmpeg_args`
        pulls it in as a second input.
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
        """An HLS master playlist (the player picks the quality itself)."""
        return self.kind is StreamKind.HLS and self.quality is None

    @property
    def audio_url(self) -> Optional[str]:
        """The separate audio rendition of a video-only HLS variant, if any."""
        value = self.extra.get("audio_url") if self.extra else None
        return str(value) if value else None

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
        """A ready ffmpeg command (as a list) that downloads this stream.

        >>> stream.ffmpeg_args("episode.mp4")
        ['ffmpeg', '-headers', 'Referer: ...', '-i', 'https://...', '-c', 'copy', 'episode.mp4']
        """
        args: List[str] = ["ffmpeg"]
        header_args: List[str] = []
        if self.headers:
            joined = "".join(f"{k}: {v}\r\n" for k, v in self.headers.items())
            header_args = ["-headers", joined]
        args += header_args + ["-i", self.url]
        audio = self.audio_url
        if audio:
            # a video-only variant: bring its audio rendition in as a second input
            args += header_args + ["-i", audio, "-map", "0:v:0", "-map", "1:a:0"]
        args += ["-c", "copy"]
        args += list(extra_args)
        args.append(output)
        return args

    def ffmpeg_command(self, output: str, *, extra_args: Iterable[str] = ()) -> str:
        """Same as :meth:`ffmpeg_args`, but as one line you can paste into a terminal."""
        return " ".join(shlex.quote(a) for a in self.ffmpeg_args(output, extra_args=extra_args))


@dataclass
class PlayerResult:
    """What parsing a player produced.

    :param player: Player name (``"aniboom"``, ``"kodik"``, ...).
    :param source_url: The URL that was parsed.
    :param streams: Every stream that was found.
    :param skip_segments: Opening/ending, when the player exposes them.
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
        """Sorted list of the available qualities (``None`` dropped)."""
        return sorted({s.quality for s in self.streams if s.quality})

    def filter(
        self,
        kind: "StreamKind | str | None" = None,
        *,
        quality: Optional[int] = None,
        max_quality: Optional[int] = None,
    ) -> List[Stream]:
        """Streams matching the conditions, in the same order as :attr:`streams`."""
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
        """The best stream: highest quality, ties broken by mp4 > hls > dash.

        Streams of unknown quality (master playlists) rank last and are picked
        only when there is nothing else. ``allow_master=False`` drops them
        entirely.

        :raises NoStreamsFound: when nothing matches the conditions.
        """
        from .errors import NoStreamsFound

        candidates = self.filter(kind, max_quality=max_quality)
        if not allow_master:
            candidates = [s for s in candidates if not s.is_master]
        if not candidates:
            raise NoStreamsFound(
                f"No matching streams (player={self.player}, kind={kind}, max_quality={max_quality})"
            )
        return max(
            candidates,
            key=lambda s: (s.quality is not None, s.quality or 0, _KIND_ORDER[s.kind]),
        )

    def master(self) -> Optional[Stream]:
        """The HLS master playlist, if there is one (handy to hand to an external player)."""
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
