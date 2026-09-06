"""Тесты помощников: сайт Animedia и API Alloha (на сохранённых ответах)."""

from __future__ import annotations

import pytest
from conftest import fixture

from anime_players import errors
from anime_players.sources import Alloha, Animedia

TITLE_URL = "https://amd.online/14-boruto-novoe-pokolenie-naruto.html"


# -- сайт Animedia -------------------------------------------------------
def test_animedia_episodes(make_client):
    client = make_client({"amd.online/14-": fixture("animedia_title.html")})
    site = Animedia(client=client)

    episodes = site.episodes(TITLE_URL)
    assert list(episodes) == [1, 2, 3, 4, 5]
    assert episodes[1] == "https://aser.pro/vod/1067"


def test_animedia_info(make_client):
    client = make_client({"amd.online/14-": fixture("animedia_title.html")})
    info = Animedia(client=client).info(TITLE_URL)

    assert info.id == "14"
    assert info.title.startswith("Боруто")
    assert info.poster and info.poster.startswith("https://")


def test_animedia_players_include_kodik(make_client):
    client = make_client({"amd.online/14-": fixture("animedia_title.html")})
    players = Animedia(client=client).players(TITLE_URL)

    assert len(players["animedia"]) == 5
    assert players["kodik"] == ["https://kodikplayer.com/serial/3568/b8eca0cc9b8deb601766f0d3dabd1dac/720p"]


def test_animedia_search(make_client):
    page = (
        '<a href="https://amd.online/14-boruto-novoe-pokolenie-naruto.html">Боруто</a>'
        '<a href="https://amd.online/14-boruto-novoe-pokolenie-naruto.html">дубль</a>'
    )
    client = make_client({"index.php": page})
    items = Animedia(client=client).search("Боруто")

    assert len(items) == 1  # дубли схлопываются
    assert items[0].id == "14"
    assert items[0].url.endswith("boruto-novoe-pokolenie-naruto.html")


def test_animedia_search_empty(make_client):
    client = make_client({"index.php": "<html>Поиск не дал результатов</html>"})
    with pytest.raises(errors.NotFound):
        Animedia(client=client).search("несуществующее аниме")


def test_animedia_episodes_missing(make_client):
    client = make_client({"amd.online/14-": "<html><h1>Пусто</h1></html>"})
    with pytest.raises(errors.NotFound):
        Animedia(client=client).episodes(TITLE_URL)


# -- Alloha ---------------------------------------------------------------
def test_alloha_series(make_client):
    client = make_client({"api.alloha.tv": fixture("alloha_series.json")})
    with Alloha(client=client) as alloha:
        item = alloha.find(name="Атака титанов")

    assert item.name == "Атака титанов"
    assert item.category == "сериал"
    assert item.id_kp == 749374
    assert item.is_series
    assert sorted(item.seasons) == [1, 2]
    assert item.translations and all(t.iframe.startswith("http") for t in item.translations)
    assert item.to_dict()["name"] == "Атака титанов"


def test_alloha_iframe_for_episode_and_translation(make_client):
    client = make_client({"api.alloha.tv": fixture("alloha_series.json")})
    alloha = Alloha(client=client)
    item = alloha.find(kp=749374)

    season = sorted(item.seasons)[0]
    episode = item.seasons[season][0]

    common = alloha.iframe(item, season=season, episode=episode)
    assert f"season={season}" in common and f"episode={episode}" in common

    name = list(
        (item.raw["seasons"][str(season)]["episodes"][str(episode)]["translation"]).values()
    )[0]["translation"]
    by_name = alloha.iframe(item, season=season, episode=episode, translation=name)
    assert "translation=" in by_name


def test_alloha_movie_has_no_seasons(make_client):
    client = make_client({"api.alloha.tv": fixture("alloha_movie.json")})
    alloha = Alloha(client=client)
    item = alloha.find(kp=435)

    assert not item.is_series
    assert item.category == "фильм"
    assert item.iframe and item.iframe.startswith("http")
    assert alloha.iframe(item) == item.iframe


def test_alloha_unknown_episode(make_client):
    client = make_client({"api.alloha.tv": fixture("alloha_series.json")})
    alloha = Alloha(client=client)
    item = alloha.find(kp=749374)

    with pytest.raises(errors.NotFound):
        alloha.iframe(item, season=1, episode=999)
    with pytest.raises(errors.NotFound):
        alloha.iframe(item, season=99)
    with pytest.raises(errors.NotFound):
        alloha.iframe(item, season=1, episode=item.seasons[1][0], translation="Нет такой")


def test_alloha_bad_token(make_client):
    client = make_client({"api.alloha.tv": '{"status":"error","error_info":"not valid token"}'})
    with pytest.raises(errors.ServiceError) as info:
        Alloha(client=client, token="bad").find(kp=1)
    assert "токен" in str(info.value)


def test_alloha_requires_query():
    with pytest.raises(ValueError):
        Alloha(client=object()).find()


def test_alloha_translations_per_episode(make_client):
    """У серии набор озвучек свой, отличный от общего списка тайтла."""
    client = make_client({"api.alloha.tv": fixture("alloha_series.json")})
    alloha = Alloha(client=client)
    item = alloha.find(kp=749374)

    season = sorted(item.seasons)[0]
    episode = item.seasons[season][0]
    voices = alloha.translations_for(item, season=season, episode=episode)

    assert voices and all(voice.iframe.startswith("http") for voice in voices)
    # выбранная озвучка действительно даёт ссылку
    assert "translation=" in alloha.iframe(
        item, season=season, episode=episode, translation=voices[0].name
    )
    # у фильма/тайтла без сезона отдаём общий список
    assert alloha.translations_for(item)


def test_alloha_episodes_helper(make_client):
    client = make_client({"api.alloha.tv": fixture("alloha_series.json")})
    alloha = Alloha(client=client)
    item = alloha.find(kp=749374)

    assert alloha.episodes(item, sorted(item.seasons)[0])
    with pytest.raises(errors.NotFound):
        alloha.episodes(item, 99)
