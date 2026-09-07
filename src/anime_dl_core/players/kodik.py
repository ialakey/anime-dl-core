"""The Kodik player (kodikplayer.com, kodik.info).

How it works:

1. The embed page serves ``urlParams`` — json with signatures (``d_sign``, ``pd_sign``,
   ``ref_sign``) bound to a domain and a moment in time, plus ``vInfo`` with the video id/hash/type.
2. The player script holds the endpoint address (``url:atob("L2Z0b3I=")`` → ``/ftor``).
3. POSTing the signatures to that endpoint returns per-quality links, encrypted as
   base64 with a Caesar shift — the shift is brute-forced.

Important: the signatures are single-use and short-lived, so the page fetch and the
POST have to happen back to back, and the links must be used right away (they expire too).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlencode, urlparse, urlunparse, parse_qsl

from ..base import BasePlayer, compile_patterns
from ..errors import ExtractionError, NoStreamsFound, ServiceError
from ..models import PlayerResult, SkipSegment, Stream, StreamKind
from ..utils import decode_kodik_url, force_https, search

__all__ = ["KodikPlayer"]

_URL_PARAMS = re.compile(r"urlParams\s*=\s*'(\{.*?\})'", re.DOTALL)
_URL_PARAMS_DQ = re.compile(r'urlParams\s*=\s*"(\{.*?\})"', re.DOTALL)
_V_INFO = re.compile(r"\.(type|hash|id)\s*=\s*['\"]([^'\"]+)['\"]")
_PLAYER_SCRIPT = re.compile(r'["\'](/assets/js/app\.player[^"\']+\.js)["\']')
_ANY_SCRIPT = re.compile(r'<script[^>]+src=["\'](/assets/js/[^"\']+\.js)["\']')
_AJAX_URL = re.compile(r'url:\s*atob\(["\']([^"\']+)["\']\)')
_SKIP_BUTTON = re.compile(r'parseSkipButton\(\s*["\']([^"\']*)["\']')
_TRANSLATION_TITLE = re.compile(r'translationTitle\s*=\s*"([^"]*)"')
_TRANSLATION_ID = re.compile(r"translationId\s*=\s*(\d+)")
_MANIFEST_SUFFIX = ":hls:manifest.m3u8"


class KodikPlayer(BasePlayer):
    """The Kodik player.

    Getting video links needs **no** Kodik API token — the embed url the aggregator
    site hands out is enough::

        with KodikPlayer() as player:
            result = player.extract(
                "https://kodikplayer.com/seria/1304528/932d5da818729ec5ccc9be7968ee3717/720p"
            )
            print(result.qualities)          # [360, 480, 720]
            print(result.best(kind="mp4"))   # the highest-quality direct mp4
    """

    name = "kodik"
    title = "Kodik"
    domains = ("kodikplayer.com", "kodik.info", "kodik.biz", "kodik.cc", "aniqit.com")
    url_patterns = compile_patterns(r"kodik[a-z]*\.[a-z]+/(?:seria|serial|video|episode)/")
    default_referer = "https://animego.org/"
    playback_headers = {"Referer": "https://kodikplayer.com/"}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._post_path_cache: Dict[str, str] = {}
        self._shift: Optional[int] = None

    # -- public interface ------------------------------------------------
    def extract(
        self,
        url: str,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        referer: Optional[str] = None,
        include_mp4: bool = True,
        **_: Any,
    ) -> PlayerResult:
        """Parses a Kodik embed and returns the per-quality links.

        :param url: embed url (``https://kodikplayer.com/seria/<id>/<hash>/720p``).
        :param season: season number for ``/serial/...`` urls (optional).
        :param episode: episode number for ``/serial/...`` urls (optional).
        :param referer: the site the player is supposedly opened from.
        :param include_mp4: also add direct mp4 links (derived from the hls manifest).
        """
        url = self._normalize(url, season=season, episode=episode)
        page = self.client.get(url, headers={"Referer": referer or self.default_referer})
        page.raise_for_status()
        info = self._parse_page(page.text, url)

        script_url = self._absolute(url, info["script_path"])
        post_path = self._post_path_cache.get(script_url)
        if post_path is None:
            script = self.client.get(script_url, headers={"Referer": url})
            post_path = self._parse_post_path(script.raise_for_status().text, script_url)
            self._post_path_cache[script_url] = post_path

        answer = self.client.post(
            self._absolute(url, post_path),
            data=self._post_params(info),
            headers=self._post_headers(url),
        )
        return self._build_result(answer, url, info, include_mp4)

    async def aextract(
        self,
        url: str,
        *,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        referer: Optional[str] = None,
        include_mp4: bool = True,
        **_: Any,
    ) -> PlayerResult:
        url = self._normalize(url, season=season, episode=episode)
        page = await self.async_client.get(url, headers={"Referer": referer or self.default_referer})
        page.raise_for_status()
        info = self._parse_page(page.text, url)

        script_url = self._absolute(url, info["script_path"])
        post_path = self._post_path_cache.get(script_url)
        if post_path is None:
            script = await self.async_client.get(script_url, headers={"Referer": url})
            post_path = self._parse_post_path(script.raise_for_status().text, script_url)
            self._post_path_cache[script_url] = post_path

        answer = await self.async_client.post(
            self._absolute(url, post_path),
            data=self._post_params(info),
            headers=self._post_headers(url),
        )
        return self._build_result(answer, url, info, include_mp4)

    # -- page parsing ------------------------------------------------------
    def _normalize(self, url: str, *, season: Optional[int], episode: Optional[int]) -> str:
        url = force_https(str(url).strip())
        if not url.startswith("http"):
            url = "https://" + url.lstrip("/")
        self.ensure_matches(url)
        if season is None and episode is None:
            return url
        parts = urlparse(url)
        query = dict(parse_qsl(parts.query))
        if season is not None:
            query["season"] = str(season)
        if episode is not None:
            query["episode"] = str(episode)
        return urlunparse(parts._replace(query=urlencode(query)))

    @staticmethod
    def _parse_page(text: str, url: str) -> Dict[str, Any]:
        raw_params = search(_URL_PARAMS, text, what="urlParams on the Kodik page", default=None)
        if raw_params is None:
            raw_params = search(_URL_PARAMS_DQ, text, what="urlParams on the Kodik page")
        try:
            url_params = json.loads(raw_params)
        except ValueError as exc:
            raise ExtractionError(f"Kodik urlParams do not parse as json: {exc}") from exc

        video: Dict[str, str] = {}
        for key, value in _V_INFO.findall(text):
            video.setdefault(key, value)
        missing = {"type", "hash", "id"} - set(video)
        if missing:
            raise ExtractionError(
                f"The Kodik page carries no video data ({', '.join(sorted(missing))}): {url}"
            )

        script_path = search(_PLAYER_SCRIPT, text, what="the Kodik player script", default=None) or search(
            _ANY_SCRIPT, text, what="the Kodik player script"
        )

        return {
            "url_params": url_params,
            "video": video,
            "script_path": script_path,
            "skip": _parse_skip_button(search(_SKIP_BUTTON, text, what="the timecodes", default="")),
            "translation": search(_TRANSLATION_TITLE, text, what="the dub", default=None),
            "translation_id": search(_TRANSLATION_ID, text, what="the dub id", default=None),
        }

    @staticmethod
    def _parse_post_path(script: str, script_url: str) -> str:
        encoded = search(_AJAX_URL, script, what="the Kodik endpoint address", default=None)
        if encoded is None:
            raise ExtractionError(
                f"The Kodik player script has no atob() call carrying the endpoint address: {script_url}"
            )
        import base64

        try:
            path = base64.b64decode(encoded).decode()
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError(f"The Kodik endpoint address does not decode from base64: {exc}") from exc
        if not path.startswith("/"):
            raise ExtractionError(f"The Kodik endpoint address looks unexpected: {path!r}")
        return path

    @staticmethod
    def _post_params(info: Dict[str, Any]) -> Dict[str, str]:
        params = info["url_params"]
        video = info["video"]
        missing = {"d", "d_sign", "pd", "pd_sign", "ref_sign"} - set(params)
        if missing:
            raise ExtractionError(f"Kodik urlParams are missing fields: {', '.join(sorted(missing))}")
        return {
            "hash": video["hash"],
            "id": video["id"],
            "type": video["type"],
            "d": params["d"],
            "d_sign": params["d_sign"],
            "pd": params["pd"],
            "pd_sign": params["pd_sign"],
            # ref is mandatory and must be decoded — an empty value makes the server answer 500
            "ref": unquote(params.get("ref", "")),
            "ref_sign": params["ref_sign"],
            "bad_user": "true",
            "cdn_is_working": "true",
        }

    def _post_headers(self, url: str) -> Dict[str, str]:
        parts = urlparse(url)
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": url,
            "Origin": f"{parts.scheme}://{parts.netloc}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

    @staticmethod
    def _absolute(base_url: str, path: str) -> str:
        parts = urlparse(base_url)
        return f"{parts.scheme}://{parts.netloc}{path}"

    # -- assembling the result ---------------------------------------------
    def _build_result(self, answer: Any, url: str, info: Dict[str, Any], include_mp4: bool) -> PlayerResult:
        if not answer.ok:
            raise ServiceError(
                f"Kodik answered the link request with status {answer.status}. "
                "That usually means the urlParams signatures went stale or the IP is blocked.",
                status=answer.status,
                url=answer.url,
            )
        data = answer.json()
        if isinstance(data, dict) and data.get("error"):
            raise ServiceError(f"Kodik returned an error: {data['error']}")

        links = (data or {}).get("links") or {}
        if not links:
            raise NoStreamsFound(f"Kodik returned no links for {url}")

        headers = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]
        streams: List[Stream] = []
        for quality_key, variants in sorted(links.items(), key=lambda kv: _as_int(kv[0])):
            for variant in variants or []:
                src = variant.get("src") if isinstance(variant, dict) else None
                if not src:
                    continue
                link, self._shift = self._decode(src)
                link = force_https(link)
                quality = _as_int(quality_key)
                streams.append(
                    Stream(link, StreamKind.HLS, quality, headers, f"{quality}p",
                           extra={"type": variant.get("type") if isinstance(variant, dict) else None})
                )
                if include_mp4 and link.endswith(_MANIFEST_SUFFIX):
                    streams.append(
                        Stream(link[: -len(_MANIFEST_SUFFIX)], StreamKind.MP4, quality, headers, f"{quality}p")
                    )
                break  # Kodik always lists exactly one entry per quality

        if not streams:
            raise NoStreamsFound(f"Kodik returned an empty list of links for {url}")

        if any("/s/m/" in stream.url for stream in streams):
            data.setdefault("warnings", []).append(
                "Got a proxy link (/s/m/) — Kodik has most likely rate-limited your IP. "
                "Try the proxy parameter."
            )

        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=streams,
            translation=info.get("translation"),
            skip_segments=info.get("skip") or [],
            extra={
                "video_id": info["video"]["id"],
                "video_hash": info["video"]["hash"],
                "video_type": info["video"]["type"],
                "translation_id": info.get("translation_id"),
                "default_quality": data.get("default"),
                "domain": data.get("domain"),
                "caesar_shift": self._shift,
                "warnings": data.get("warnings", []),
            },
        )

    def _decode(self, src: str) -> Tuple[str, int]:
        if _MANIFEST_SUFFIX in src or src.startswith("http") or src.startswith("//"):
            return src, self._shift if self._shift is not None else 0
        return decode_kodik_url(src, known_shift=self._shift)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_skip_button(value: str) -> List[SkipSegment]:
    """``"0:30-1:50,22:55-24:05"`` -> a list of segments in seconds."""
    segments: List[SkipSegment] = []
    for index, chunk in enumerate(filter(None, (value or "").split(","))):
        if "-" not in chunk:
            continue
        start_raw, _, end_raw = chunk.partition("-")
        start, end = _timecode(start_raw), _timecode(end_raw)
        if start is None or end is None:
            continue
        segments.append(SkipSegment(start, end, "opening" if index == 0 else "ending"))
    return segments


def _timecode(value: str) -> Optional[int]:
    """``"22:55"`` / ``"1:02:03"`` -> seconds."""
    parts = value.strip().split(":")
    if not all(part.strip().isdigit() for part in parts) or not parts:
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return seconds
