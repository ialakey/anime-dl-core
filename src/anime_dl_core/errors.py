"""Исключения библиотеки.

Все исключения наследуются от :class:`AnimeDlCoreError`, поэтому в вызывающем
коде достаточно перехватывать его одного.
"""

from __future__ import annotations

__all__ = [
    "AnimeDlCoreError",
    "UnsupportedUrl",
    "NetworkError",
    "ServiceError",
    "ExtractionError",
    "NoStreamsFound",
    "DecryptionError",
    "ContentBlocked",
    "NotFound",
]


class AnimeDlCoreError(Exception):
    """Базовое исключение библиотеки."""


class UnsupportedUrl(AnimeDlCoreError):
    """Ссылка не подходит ни под один известный плеер."""


class NetworkError(AnimeDlCoreError):
    """Сетевая ошибка: таймаут, DNS, обрыв соединения, ошибка прокси."""


class ServiceError(AnimeDlCoreError):
    """Сервер плеера вернул неожиданный ответ (код != 200, не тот content-type)."""

    def __init__(self, message: str, *, status: "int | None" = None, url: "str | None" = None) -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class ExtractionError(AnimeDlCoreError):
    """Ответ получен, но разобрать его не удалось — вероятно, плеер изменил разметку."""


class NoStreamsFound(ExtractionError):
    """Страница разобрана, но ни одной ссылки на видео в ней нет."""


class DecryptionError(ExtractionError):
    """Не удалось расшифровать ссылку (актуально для Kodik)."""


class ContentBlocked(AnimeDlCoreError):
    """Контент заблокирован: гео-блокировка, возрастное ограничение, правообладатель."""


class NotFound(AnimeDlCoreError):
    """Запрошенный эпизод/озвучка/видео отсутствует у плеера."""
