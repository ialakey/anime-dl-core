"""The SovetRomantica player (pages like ``/embed/episode_<id>_<episode>-<dubbed|subtitles>``).

How it works: the end of the embed page carries the player's js config::

    var nextEpisode='https://sovetromantica.com/embed/episode_1073_2-dubbed';
    var skips = [ { 'start': 174.79, 'end': 184.79, 'skip_to': 262.92 }, ... ];
    var config={
        "id":"sovetromantica_player",
        "file":"https://scu2.sovetromantica.com/anime/.../episode_1.m3u8",
        "poster":"https://scu2.sovetromantica.com/anime/.../episode_1_dub.jpg",
        "thumbnails":"https://scu2.sovetromantica.com/anime/.../episode_1.vtt",
        "title":"Gekkan Shoujo Nozaki-kun - Озвучка - Эпизод 1",
        "points": points
    };

The config is not valid json (it contains js variables), so the fields are pulled
out one by one with regexes. ``skips`` yields the opening and the ending.

.. warning::
   SovetRomantica's own site has been down since 2025: the ``sovetromantica.com``
   domain changed hands and now serves somebody else's content, and the CDN
   (``scu*.sovetromantica.com``) does not resolve. The team is raising money for
   a relaunch. So:

   * parsing was verified against real pages from the web archive (see the live tests);
   * when the site comes back (or if you have a mirror), point the player at the domain:
     ``SovetRomanticaPlayer(base_url="https://new-domain")`` — it will then accept
     a url on any host;
   * current SovetRomantica releases live in their VK community and are handled
     by :class:`~anime_dl_core.players.vk.VkPlayer`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..base import BasePlayer, compile_patterns
from ..errors import NoStreamsFound
from ..models import PlayerResult, SkipSegment, Stream, StreamKind
from ..utils import parse_master_playlist, search, url_host

__all__ = ["SovetRomanticaPlayer"]

_CONFIG_FIELD = '"{}"\\s*:\\s*"([^"]+)"'
_ANY_M3U8 = re.compile(r'(https?://[^"\'\s\\]+\.m3u8[^"\'\s\\]*)', re.IGNORECASE)
_SOURCE_TAG = re.compile(r'<source[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_SKIPS_BLOCK = re.compile(r"var\s+skips\s*=\s*\[(.*?)\]\s*;", re.DOTALL)
_SKIP_ITEM = re.compile(
    r"['\"]start['\"]\s*:\s*([\d.]+).*?['\"]end['\"]\s*:\s*([\d.]+)"
    r"(?:.*?['\"]skip_to['\"]\s*:\s*([\d.]+))?",
    re.DOTALL,
)
_NEXT_EPISODE = re.compile(r"var\s+nextEpisode\s*=\s*['\"]([^'\"]*)['\"]")
_EPISODE_SLUG = re.compile(r"/embed/(episode_[A-Za-z0-9_\-]+)", re.IGNORECASE)


class SovetRomanticaPlayer(BasePlayer):
    """The SovetRomantica player.

    Example (the site is down, so this uses a real page from the web archive)::

        from anime_dl_core import SovetRomanticaPlayer

        archive = "https://web.archive.org/web/20240905174049id_/"
        with SovetRomanticaPlayer(base_url="https://web.archive.org") as player:
            result = player.extract(archive + "https://sovetromantica.com/embed/episode_1073_1-dubbed")
            print(result.title)              # Gekkan Shoujo Nozaki-kun - Озвучка - Эпизод 1
            print(result.best().url)         # https://scu2.sovetromantica.com/.../episode_1.m3u8
            print(result.skip_segments)      # opening and ending

    Once the site is back::

        with SovetRomanticaPlayer(base_url="https://new-domain") as player:
            result = player.extract("episode_1073_1-dubbed")
    """

    name = "sovetromantica"
    title = "SovetRomantica"
    domains = ("sovetromantica.com",)
    url_patterns = compile_patterns(r"sovetromantica\.[a-z]+/embed/")
    verified = True
    note = (
        "site offline (the domain changed hands); parsing was verified against web-archive "
        "pages, point base_url at a mirror to use one"
    )
    base_url = "https://sovetromantica.com"
    playback_headers = {"Referer": "https://sovetromantica.com/"}

    def __init__(self, *args: Any, base_url: Optional[str] = None, **kwargs: Any) -> None:
        """
        :param base_url: site address, for when it has moved or this is a mirror/web archive.
            When it is set, the player accepts a url on any host.
        """
        super().__init__(*args, **kwargs)
        self.custom_base = bool(base_url)
        if base_url:
            self.base_url = base_url.rstrip("/")
            self.playback_headers = {"Referer": self.base_url + "/"}

    # -- public interface ---------------------------------------------------
    def embed_url(self, episode_slug: str) -> str:
        """``episode_1073_1-dubbed`` -> the full embed url."""
        return f"{self.base_url}/embed/{episode_slug}"

    @staticmethod
    def episode_slug(url: str) -> Optional[str]:
        """The episode slug taken from a url (``episode_1073_1-dubbed``)."""
        return search(_EPISODE_SLUG, str(url), what="the episode slug", default=None)

    def extract(self, url: str, *, resolve_qualities: bool = False, **_: Any) -> PlayerResult:
        """Returns the HLS stream of one episode.

        :param url: an embed url, or a slug like ``episode_1073_1-dubbed``.
        :param resolve_qualities: expand the master playlist into per-quality streams
            (one extra request; skipped silently when the CDN is unreachable).
        """
        url = self._normalize(url)
        page = self.client.get(url, headers={"Referer": self.base_url + "/"})
        result = self._build_result(page.raise_for_status().text, url)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = self.client.get(master.url, headers=master.headers)
                if content.ok and "#EXT-X-STREAM-INF" in content.text:
                    result.streams.extend(self._variant_streams(content.text, master))
        return result

    async def aextract(self, url: str, *, resolve_qualities: bool = False, **_: Any) -> PlayerResult:
        url = self._normalize(url)
        page = await self.async_client.get(url, headers={"Referer": self.base_url + "/"})
        result = self._build_result(page.raise_for_status().text, url)
        if resolve_qualities:
            master = result.master()
            if master is not None:
                content = await self.async_client.get(master.url, headers=master.headers)
                if content.ok and "#EXT-X-STREAM-INF" in content.text:
                    result.streams.extend(self._variant_streams(content.text, master))
        return result

    # -- internals ----------------------------------------------------------
    def _normalize(self, url: str) -> str:
        url = str(url).strip()
        if url.startswith("episode_"):
            return self.embed_url(url)
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("http"):
            return self.embed_url(url.lstrip("/").replace("embed/", ""))
        # with a custom base_url any host is allowed: a mirror, a local server, the web archive
        if self.custom_base or url_host(url) == url_host(self.base_url):
            return url
        return self.ensure_matches(url)

    def _variant_streams(self, master_content: str, master: Stream) -> List[Stream]:
        return [
            Stream(
                variant["url"],
                StreamKind.HLS,
                variant["height"],
                master.headers,
                f"{variant['height']}p" if variant["height"] else None,
                extra={"bandwidth": variant["bandwidth"], "codecs": variant["codecs"]},
            )
            for variant in parse_master_playlist(master_content, master.url)
        ]

    def _build_result(self, text: str, url: str) -> PlayerResult:
        playlist = self._field(text, "file")
        if not playlist:
            playlist = search(_ANY_M3U8, text, what="an m3u8 link", default=None)
        if not playlist:
            source = search(_SOURCE_TAG, text, what="a <source> tag", default=None)
            playlist = source if source and ".m3u8" in source else None
        if not playlist:
            raise NoStreamsFound(
                f"No SovetRomantica playlist was found on the page: {url}. "
                "Check that this really is an embed page: the sovetromantica.com domain "
                "now belongs to someone else and serves an unrelated site. "
                "For a mirror or an archive use SovetRomanticaPlayer(base_url=...)."
            )

        playlist = playlist.replace("\\/", "/")
        headers: Dict[str, str] = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]

        title = self._field(text, "title")
        slug = self.episode_slug(url)
        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=[Stream(playlist, StreamKind.HLS, None, headers, "master")],
            title=title,
            poster=self._field(text, "poster"),
            translation=_translation_from_slug(slug) or _translation_from_title(title),
            skip_segments=_parse_skips(text),
            extra={
                "episode": slug,
                "thumbnails": self._field(text, "thumbnails"),
                "next_episode": search(_NEXT_EPISODE, text, what="the next episode", default=None) or None,
            },
        )

    @staticmethod
    def _field(text: str, name: str) -> Optional[str]:
        value = search(_CONFIG_FIELD.format(name), text, what=f"the {name} field", default=None)
        return value.replace("\\/", "/") if value else None


def _parse_skips(text: str) -> List[SkipSegment]:
    """``var skips = [ {'start': 174.7, 'end': 184.7, 'skip_to': 262.9}, ... ]``.

    ``start``–``end`` is when the button is shown and ``skip_to`` is where it jumps,
    so the stretch actually skipped is ``start``–``skip_to``.
    """
    block = search(_SKIPS_BLOCK, text, what="the timecodes", default=None)
    if not block:
        return []
    segments: List[SkipSegment] = []
    for index, item in enumerate(_SKIP_ITEM.finditer(block)):
        start = float(item.group(1))
        end = float(item.group(3) or item.group(2))
        segments.append(SkipSegment(int(start), int(end), "opening" if index == 0 else "ending"))
    if len(segments) == 2 and segments[0].start > segments[1].start:
        segments = [
            SkipSegment(segments[1].start, segments[1].end, "opening"),
            SkipSegment(segments[0].start, segments[0].end, "ending"),
        ]
    return segments


# The two labels below are SovetRomantica's own wording for a dub and for subtitles.
# They are kept in Russian on purpose: they are matched against the page title and
# are part of what PlayerResult.translation has always returned.
def _translation_from_slug(slug: Optional[str]) -> Optional[str]:
    if not slug:
        return None
    if slug.endswith("-dubbed"):
        return "Озвучка SovetRomantica"
    if slug.endswith("-subtitles"):
        return "Субтитры SovetRomantica"
    return None


def _translation_from_title(title: Optional[str]) -> Optional[str]:
    if not title:
        return None
    if "Озвучка" in title:
        return "Озвучка SovetRomantica"
    if "Субтитры" in title:
        return "Субтитры SovetRomantica"
    return None
