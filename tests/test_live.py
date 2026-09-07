"""Live tests — these go out to the internet.

Run them with::

    ANIME_DL_CORE_LIVE=1 pytest -m live          # bash
    $env:ANIME_DL_CORE_LIVE=1; pytest -m live    # PowerShell

The links here go stale over time (anime get removed, ids change). A test failing
with NotFound means the constants below need updating, not that the library broke.
"""

from __future__ import annotations

import pytest

import anime_dl_core as ap
from anime_dl_core.sources import AnimeGo

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
        pytest.skip(f"AnimeGO is not serving the {name} player for {ANIME_TITLE!r} right now")
    return link


def test_animego_search_and_players(animego, player_links):
    assert player_links
    assert all(link.embed.startswith("http") for link in player_links)


def test_aniboom_live(player_links):
    result = ap.extract(_first(player_links, "aniboom").embed)
    assert result.player == "aniboom"
    assert result.qualities, "the master playlist should expand into qualities"
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
    """Checks that the link really does serve a playlist (with the required headers)."""
    result = ap.extract(_first(player_links, "aniboom").embed, resolve_qualities=False)
    with ap.AniboomPlayer() as player:
        content = player.fetch(result.master())
    assert content.startswith("#EXTM3U")


# -- VK Video -----------------------------------------------------------
#: An anime episode in the SovetRomantica VK community (a public video)
VK_ANIME = "https://vk.com/video_ext.php?oid=-33905270&id=456239024"


def test_vk_live():
    result = ap.extract(VK_ANIME)
    assert result.player == "vk"
    assert result.qualities, "mp4 in several qualities was expected"
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
# SovetRomantica's own site is down (the domain changed hands), so parsing is
# checked against a real page from the web archive.
SR_ARCHIVE = (
    "https://web.archive.org/web/20240905174049id_/"
    "https://sovetromantica.com/embed/episode_1073_1-dubbed"
)


def test_sovetromantica_live_from_archive():
    with ap.SovetRomanticaPlayer(base_url="https://web.archive.org", timeout=60) as player:
        try:
            result = player.extract(SR_ARCHIVE)
        except (ap.ServiceError, ap.NetworkError) as error:
            pytest.skip(f"the web archive is unreachable: {error}")

    assert result.player == "sovetromantica"
    assert result.title == "Gekkan Shoujo Nozaki-kun - Озвучка - Эпизод 1"
    assert result.best().url.endswith(".m3u8")
    assert [segment.kind for segment in result.skip_segments] == ["opening", "ending"]


def test_sovetromantica_domain_is_taken_over():
    """While the site is down, an ordinary link should fail with a readable error."""
    with ap.SovetRomanticaPlayer(timeout=30) as player:
        with pytest.raises(ap.AnimeDlCoreError):
            player.extract("episode_1073_1-dubbed")


# -- Animedia -----------------------------------------------------------
ANIMEDIA_TITLE = "Боруто"


def test_animedia_live():
    from anime_dl_core.sources import Animedia

    with Animedia() as site:
        anime = site.search(ANIMEDIA_TITLE)[0]
        episodes = site.episodes(anime.url)
        assert episodes and 1 in episodes

        result = ap.extract(episodes[1])

    assert result.player == "animedia"
    assert result.qualities, "the master playlist should expand into qualities"
    assert result.best().url.endswith(".m3u8")


def test_animedia_stream_is_downloadable():
    with ap.AnimediaPlayer() as player:
        result = player.extract("https://aser.pro/vod/20182", resolve_qualities=False)
        content = player.fetch(result.master())
    assert content.startswith("#EXTM3U")


# -- Alloha -------------------------------------------------------------
def test_alloha_live():
    """Alloha serves a catalogue and links to its own iframe (it has no direct files)."""
    from anime_dl_core.sources import Alloha

    with Alloha() as alloha:
        item = alloha.find(name="Атака титанов")
        assert item.is_series and item.seasons
        season = sorted(item.seasons)[0]
        iframe = alloha.iframe(item, season=season, episode=item.seasons[season][0])

    assert iframe.startswith("http") and "token_movie=" in iframe


def test_alloha_by_kinopoisk_id():
    from anime_dl_core.sources import Alloha

    with Alloha() as alloha:
        item = alloha.find(kp=435)
    assert item.name and item.iframe
