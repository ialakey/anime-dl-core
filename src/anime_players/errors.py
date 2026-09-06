"""Исключения библиотеки.

Все исключения наследуются от :class:`AnimePlayersError`, поэтому в вызывающем
коде достаточно перехватывать его одного.
"""

from __future__ import annotations

__all__ = [
    "AnimePlayersError",
    "UnsupportedUrl",
    "NetworkError",
    "ServiceError",
    "ExtractionError",
    "NoStreamsFound",
    "DecryptionError",
    "ContentBlocked",
    "NotFound",
]


class AnimePlayersError(Exception):
    """Базовое исключение библиотеки."""


class UnsupportedUrl(AnimePlayersError):
    """Ссылка не подходит ни под один известный плеер."""


class NetworkError(AnimePlayersError):
    """Сетевая ошибка: таймаут, DNS, обрыв соединения, ошибка прокси."""


class ServiceError(AnimePlayersError):
    """Сервер плеера вернул неожиданный ответ (код != 200, не тот content-type)."""

    def __init__(self, message: str, *, status: "int | None" = None, url: "str | None" = None) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class ExtractionError(AnimePlayersError):
    """Ответ получен, но разобрать его не удалось — вероятно, плеер изменил разметку."""


class NoStreamsFound(ExtractionError):
    """Страница разобрана, но ни одной ссылки на видео в ней нет."""


class DecryptionError(ExtractionError):
    """Не удалось расшифровать ссылку (актуально для Kodik)."""


class ContentBlocked(AnimePlayersError):
    """Контент заблокирован: гео-блокировка, возрастное ограничение, правообладатель."""


class NotFound(AnimePlayersError):
    """Запрошенный эпизод/озвучка/видео отсутствует у плеера."""
