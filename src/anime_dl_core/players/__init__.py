"""Player implementations."""

from .animedia import AnimediaPlayer
from .aniboom import AniboomPlayer
from .anilibria import AnilibriaPlayer
from .cvh import CvhEpisode, CvhPlayer
from .kodik import KodikPlayer
from .sibnet import SibnetPlayer
from .sovetromantica import SovetRomanticaPlayer
from .vk import VkPlayer

__all__ = [
    "AniboomPlayer",
    "AnimediaPlayer",
    "AnilibriaPlayer",
    "CvhPlayer",
    "CvhEpisode",
    "KodikPlayer",
    "SibnetPlayer",
    "SovetRomanticaPlayer",
    "VkPlayer",
]
