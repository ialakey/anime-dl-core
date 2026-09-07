"""Helpers: html/js parsing, m3u8 parsing, and Kodik link decryption."""

from __future__ import annotations

import base64
import html
import json
import re
from typing import Any, Dict, List, Optional, Pattern, Tuple, Union
from urllib.parse import parse_qs, urljoin, urlparse

from .errors import DecryptionError, ExtractionError

__all__ = [
    "search",
    "json_from_attribute",
    "parse_master_playlist",
    "absolute_url",
    "force_https",
    "query_param",
    "url_host",
    "caesar_shift",
    "decode_kodik_url",
    "quality_from_label",
    "to_int",
]


def search(
    pattern: Union[str, Pattern[str]],
    text: str,
    *,
    group: int = 1,
    what: str = "the fragment we needed",
    flags: int = 0,
    default: Any = ...,
) -> Any:
    """re.search plus a readable error when nothing matched.

    When ``default`` is given it is returned instead of raising.
    """
    match = re.search(pattern, text, flags) if isinstance(pattern, str) else pattern.search(text)
    if match is None:
        if default is not ...:
            return default
        raise ExtractionError(
            f"Could not find {what} — the player has most likely changed its markup."
        )
    return match.group(group)


def json_from_attribute(value: str) -> Dict[str, Any]:
    """Parses json stored in an html attribute (with &quot; and other entities)."""
    try:
        return json.loads(html.unescape(value))
    except ValueError as exc:
        raise ExtractionError(f"Could not parse the json held in a page attribute: {exc}") from exc


_STREAM_INF = re.compile(r"#EXT-X-STREAM-INF:([^\n]+)\n\s*([^\s#][^\n]*)")


def parse_master_playlist(content: str, base_url: str) -> List[Dict[str, Any]]:
    """Splits an HLS master playlist into its quality variants.

    Returns a list of ``{"url", "height", "width", "bandwidth", "codecs"}`` dicts,
    sorted from the lowest quality up.
    """
    variants: List[Dict[str, Any]] = []
    for attrs, uri in _STREAM_INF.findall(content):
        info: Dict[str, Any] = {"url": absolute_url(base_url, uri.strip())}
        resolution = re.search(r"RESOLUTION=(\d+)x(\d+)", attrs)
        if resolution:
            info["width"] = int(resolution.group(1))
            info["height"] = int(resolution.group(2))
        else:
            info["width"] = None
            info["height"] = None
        bandwidth = re.search(r"[^-]BANDWIDTH=(\d+)", " " + attrs)
        info["bandwidth"] = int(bandwidth.group(1)) if bandwidth else None
        codecs = re.search(r'CODECS="([^"]+)"', attrs)
        info["codecs"] = codecs.group(1) if codecs else None
        variants.append(info)
    variants.sort(key=lambda v: (v["height"] or 0, v["bandwidth"] or 0))
    return variants


def absolute_url(base_url: str, url: str) -> str:
    """Turns a relative link into an absolute one against base_url."""
    if url.startswith("//"):
        scheme = urlparse(base_url).scheme or "https"
        return f"{scheme}:{url}"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(base_url, url)


def force_https(url: str) -> str:
    """``//host/path`` -> ``https://host/path``; anything else is left alone."""
    if url.startswith("//"):
        return "https:" + url
    return url


def query_param(url: str, key: str) -> Optional[str]:
    """Value of a GET parameter from a url (or None)."""
    values = parse_qs(urlparse(url).query).get(key)
    return values[0] if values else None


def url_host(url: str) -> str:
    """Host of a url, lowercased, without ``www.`` and without the port."""
    netloc = urlparse(url if "//" in url else "//" + url).netloc.lower()
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if ":" in netloc:
        netloc = netloc.split(":", 1)[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def caesar_shift(text: str, shift: int) -> str:
    """Caesar cipher over the latin alphabet, case preserved (other characters untouched)."""
    out = []
    for char in text:
        upper = char.upper()
        index = _ALPHABET.find(upper)
        if index == -1:
            out.append(char)
            continue
        shifted = _ALPHABET[(index + shift) % 26]
        out.append(shifted.lower() if char.islower() else shifted)
    return "".join(out)


def _b64_padded(value: str) -> bytes:
    return base64.b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def decode_kodik_url(value: str, *, known_shift: Optional[int] = None) -> Tuple[str, int]:
    """Decrypts the link Kodik returns.

    Kodik hands out the link as base64 that has additionally been Caesar-shifted.
    The shift changes from time to time, so it is brute-forced (26 options) and
    the value that worked can be reused through ``known_shift``.

    :returns: a ``(link, shift used)`` tuple.
    :raises DecryptionError: when no shift produced a valid link.
    """
    shifts = ([known_shift] if known_shift is not None else []) + list(range(26))
    for shift in shifts:
        try:
            decoded = _b64_padded(caesar_shift(value, shift)).decode("utf-8")
        except Exception:  # noqa: BLE001 - any garbage simply means "wrong shift"
            continue
        if decoded.startswith("//") or decoded.startswith("http"):
            return decoded, shift
    raise DecryptionError(
        "Could not decrypt the Kodik link — the encryption may have changed."
    )


# Quality labels on these sites use both the latin "p" and the cyrillic "р".
_QUALITY_RE = re.compile(r"(\d{3,4})\s*[pр]?", re.IGNORECASE)


def quality_from_label(label: str) -> Optional[int]:
    """Pulls the quality number out of a label like ``720p`` / ``1080`` / ``hd720``."""
    match = _QUALITY_RE.search(label or "")
    if not match:
        return None
    value = int(match.group(1))
    return value if 100 <= value <= 4320 else None


def to_int(value: Any) -> Optional[int]:
    """Coerces a value to int when possible (players send both numbers and strings)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        value = value.strip()
        if value.isdigit():
            return int(value)
        try:
            return int(float(value))
        except ValueError:
            return None
    return None
