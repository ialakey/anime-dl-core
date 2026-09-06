"""Живые тесты — ходят в интернет.

Запуск::

    ANIME_PLAYERS_LIVE=1 pytest -m live          # bash
    $env:ANIME_PLAYERS_LIVE=1; pytest -m live    # PowerShell

Ссылки в тестах со временем протухают (аниме удаляют, id меняются). Если тест
упал с NotFound — обновите константы ниже, это не поломка библиотеки.
"""

from __future__ import annotations

import pytest

import anime_players as ap
from anime_players.sources import AnimeGo

pytestmark = pytest.mark.live

ANIME_TITLE = "Магическая битва"
SIBNET_ID = "2589828"
ANILIBRIA_ALIAS = "bleach"


@pytest.fixture(scope="module")
def animego():
    with AnimeGo() as site:
        yield site


@pytest.fixture(scope="module")
def player_links(animego):
    anime = animego.search(ANIME_TITLE)[0]
    return animego.players(anime.id, episode=1)


def _first(links, name):
    link = next((item for item in links if item.player.lower() == name), None)
    if link is None:
        pytest.skip(f"AnimeGO сейчас не отдаёт плеер {name} для {ANIME_TITLE!r}")
    return link


def test_animego_search_and_players(animego, player_links):
    assert player_links
    assert all(link.embed.startswith("http") for link in player_links)


def test_aniboom_live(player_links):
    result = ap.extract(_first(player_links, "aniboom").embed)
    assert result.player == "aniboom"
    assert result.qualities, "мастер-плейлист должен разворачиваться в качества"
    assert result.best(kind="hls").url.endswith(".m3u8")


def test_cvh_live(player_links):
    link = _first(player_links, "cvh")
    result = ap.extract(link.embed)
    assert result.player == "cvh"
    assert result.streams
    assert result.duration


def test_kodik_live(player_links):
    result = ap.extract(_first(player_links, "kodik").embed)
    assert result.player == "kodik"
    assert result.qualities
    assert result.best(kind="mp4").url.endswith(".mp4")


def test_sibnet_live():
    result = ap.extract(f"https://video.sibnet.ru/shell.php?videoid={SIBNET_ID}")
    assert result.best().url.startswith("https://video.sibnet.ru/v/")


def test_anilibria_live():
    with ap.AnilibriaPlayer() as player:
        result = player.extract(ANILIBRIA_ALIAS, episode=1)
    assert result.qualities == [480, 720, 1080]
    assert result.title


@pytest.mark.asyncio
async def test_async_live(player_links):
    result = await ap.extract_async(_first(player_links, "aniboom").embed)
    assert result.streams


def test_streams_are_downloadable(player_links):
    """Проверяем, что по ссылке реально отдаётся плейлист (с нужными заголовками)."""
    result = ap.extract(_first(player_links, "aniboom").embed, resolve_qualities=False)
    with ap.AniboomPlayer() as player:
        content = player.fetch(result.master())
    assert content.startswith("#EXTM3U")


# -- VK Video -----------------------------------------------------------
#: Серия аниме в сообществе SovetRomantica ВКонтакте (открытое видео)
VK_ANIME = "https://vk.com/video_ext.php?oid=-33905270&id=456239024"


def test_vk_live():
    result = ap.extract(VK_ANIME)
    assert result.player == "vk"
    assert result.qualities, "ожидались mp4 разных качеств"
    assert result.title and result.duration
    assert result.best(kind="mp4").url.startswith("http")


def test_vk_accepts_plain_video_id():
    result = ap.extract("-33905270_456239024", resolve_qualities=False)
    assert result.streams


def test_vk_stream_is_downloadable():
    result = ap.extract(VK_ANIME, resolve_qualities=False)
    with ap.VkPlayer() as player:
        content = player.fetch(result.master())
    assert content.startswith("#EXTM3U")


def test_vk_unavailable_video_raises():
    with pytest.raises(ap.ContentBlocked):
        ap.extract("https://vk.com/video_ext.php?oid=-1&id=1&hash=deadbeef")


# -- SovetRomantica -----------------------------------------------------
# Свой сайт SovetRomantica сейчас не работает (домен перешёл другому владельцу),
# поэтому разбор проверяется на настоящей странице из веб-архива.
SR_ARCHIVE = (
    "https://web.archive.org/web/20240905174049id_/"
    "https://sovetromantica.com/embed/episode_1073_1-dubbed"
)


def test_sovetromantica_live_from_archive():
    with ap.SovetRomanticaPlayer(base_url="https://web.archive.org", timeout=60) as player:
        try:
            result = player.extract(SR_ARCHIVE)
        except (ap.ServiceError, ap.NetworkError) as error:
            pytest.skip(f"веб-архив недоступен: {error}")

    assert result.player == "sovetromantica"
    assert result.title == "Gekkan Shoujo Nozaki-kun - Озвучка - Эпизод 1"
    assert result.best().url.endswith(".m3u8")
    assert [segment.kind for segment in result.skip_segments] == ["opening", "ending"]


def test_sovetromantica_domain_is_taken_over():
    """Пока сайт не вернулся, обычная ссылка приводит к понятной ошибке."""
    with ap.SovetRomanticaPlayer(timeout=30) as player:
        with pytest.raises(ap.AnimePlayersError):
            player.extract("episode_1073_1-dubbed")


# -- Animedia -----------------------------------------------------------
ANIMEDIA_TITLE = "Боруто"


def test_animedia_live():
    from anime_players.sources import Animedia

    with Animedia() as site:
        anime = site.search(ANIMEDIA_TITLE)[0]
        episodes = site.episodes(anime.url)
        assert episodes and 1 in episodes

        result = ap.extract(episodes[1])

    assert result.player == "animedia"
    assert result.qualities, "мастер-плейлист должен разворачиваться в качества"
    assert result.best().url.endswith(".m3u8")


def test_animedia_stream_is_downloadable():
    with ap.AnimediaPlayer() as player:
        result = player.extract("https://aser.pro/vod/20182", resolve_qualities=False)
        content = player.fetch(result.master())
    assert content.startswith("#EXTM3U")


# -- Alloha -------------------------------------------------------------
def test_alloha_live():
    """Alloha отдаёт каталог и ссылки на свой iframe (прямых файлов у неё нет)."""
    from anime_players.sources import Alloha

    with Alloha() as alloha:
        item = alloha.find(name="Атака титанов")
        assert item.is_series and item.seasons
        season = sorted(item.seasons)[0]
        iframe = alloha.iframe(item, season=season, episode=item.seasons[season][0])

    assert iframe.startswith("http") and "token_movie=" in iframe


def test_alloha_by_kinopoisk_id():
    from anime_players.sources import Alloha

    with Alloha() as alloha:
        item = alloha.find(kp=435)
    assert item.name and item.iframe
