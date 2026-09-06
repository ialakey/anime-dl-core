"""Вспомогательные функции: разбор html/js, m3u8 и дешифровка ссылок Kodik."""

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
    what: str = "нужный фрагмент",
    flags: int = 0,
    default: Any = ...,
) -> Any:
    """re.search + понятная ошибка, если не нашли.

    Если передан ``default``, вместо исключения вернётся он.
    """
    match = re.search(pattern, text, flags) if isinstance(pattern, str) else pattern.search(text)
    if match is None:
        if default is not ...:
            return default
        raise ExtractionError(
            f"Не удалось найти {what} — скорее всего, плеер изменил разметку страницы."
        )
    return match.group(group)


def json_from_attribute(value: str) -> Dict[str, Any]:
    """Разбирает json, лежащий в html-атрибуте (с &quot; и прочими сущностями)."""
    try:
        return json.loads(html.unescape(value))
    except ValueError as exc:
        raise ExtractionError(f"Не удалось разобрать json из атрибута страницы: {exc}") from exc


_STREAM_INF = re.compile(r"#EXT-X-STREAM-INF:([^\n]+)\n\s*([^\s#][^\n]*)")


def parse_master_playlist(content: str, base_url: str) -> List[Dict[str, Any]]:
    """Разбирает мастер-плейлист HLS на варианты качества.

    Возвращает список словарей ``{"url", "height", "width", "bandwidth", "codecs"}``,
    отсортированный по возрастанию качества.
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
    """Превращает относительную ссылку в абсолютную относительно base_url."""
    if url.startswith("//"):
        scheme = urlparse(base_url).scheme or "https"
        return f"{scheme}:{url}"
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(base_url, url)


def force_https(url: str) -> str:
    """``//host/path`` -> ``https://host/path``; остальное не трогает."""
    if url.startswith("//"):
        return "https:" + url
    return url


def query_param(url: str, key: str) -> Optional[str]:
    """Значение GET-параметра из ссылки (или None)."""
    values = parse_qs(urlparse(url).query).get(key)
    return values[0] if values else None


def url_host(url: str) -> str:
    """Хост ссылки без ``www.`` и порта, в нижнем регистре."""
    netloc = urlparse(url if "//" in url else "//" + url).netloc.lower()
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[1]
    if ":" in netloc:
        netloc = netloc.split(":", 1)[0]
    return netloc[4:] if netloc.startswith("www.") else netloc


_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def caesar_shift(text: str, shift: int) -> str:
    """Шифр Цезаря по латинице с сохранением регистра (остальные символы не трогаются)."""
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
    """Расшифровывает ссылку из ответа Kodik.

    Kodik отдаёт ссылку как base64, дополнительно сдвинутый шифром Цезаря.
    Сдвиг периодически меняется, поэтому он подбирается перебором (26 вариантов),
    а найденное значение можно переиспользовать через ``known_shift``.

    :returns: кортеж ``(ссылка, использованный сдвиг)``.
    :raises DecryptionError: если ни один сдвиг не дал корректной ссылки.
    """
    shifts = ([known_shift] if known_shift is not None else []) + list(range(26))
    for shift in shifts:
        try:
            decoded = _b64_padded(caesar_shift(value, shift)).decode("utf-8")
        except Exception:  # noqa: BLE001 - любой мусор просто означает "не тот сдвиг"
            continue
        if decoded.startswith("//") or decoded.startswith("http"):
            return decoded, shift
    raise DecryptionError(
        "Не удалось расшифровать ссылку Kodik — возможно, изменился алгоритм шифрования."
    )


_QUALITY_RE = re.compile(r"(\d{3,4})\s*[pр]?", re.IGNORECASE)


def quality_from_label(label: str) -> Optional[int]:
    """Достаёт число качества из подписи вида ``720p`` / ``1080`` / ``hd720``."""
    match = _QUALITY_RE.search(label or "")
    if not match:
        return None
    value = int(match.group(1))
    return value if 100 <= value <= 4320 else None


def to_int(value: Any) -> Optional[int]:
    """Приводит значение к int, если это возможно (плееры шлют и числа, и строки)."""
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
