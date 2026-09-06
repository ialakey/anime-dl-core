"""Помощники для получения ссылок на плееры с сайтов-агрегаторов."""

from .alloha import Alloha, AllohaItem, AllohaTranslation
from .animedia import Animedia, AnimediaItem
from .animego import AnimeGo, AnimeItem, PlayerLink

__all__ = [
    "AnimeGo",
    "AnimeItem",
    "PlayerLink",
    "Animedia",
    "AnimediaItem",
    "Alloha",
    "AllohaItem",
    "AllohaTranslation",
]
