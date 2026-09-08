"""Tests for the models, the utilities and the player registry."""

from __future__ import annotations

import pytest
from conftest import fixture

from anime_dl_core import (
    AniboomPlayer,
    BasePlayer,
    KodikPlayer,
    PlayerResult,
    SkipSegment,
    Stream,
    StreamKind,
    errors,
    get_player_class,
    player_names,
    registry,
    supports,
)
from anime_dl_core.utils import (
    absolute_url,
    caesar_shift,
    decode_kodik_url,
    parse_master_playlist,
    quality_from_label,
    query_param,
    url_host,
)


def _result() -> PlayerResult:
    headers = {"Referer": "https://example.com/"}
    return PlayerResult(
        player="test",
        source_url="https://example.com/embed/1",
        streams=[
            Stream("https://cdn/master.m3u8", StreamKind.HLS, None, headers, "master"),
            Stream("https://cdn/360.mp4", StreamKind.MP4, 360, headers),
            Stream("https://cdn/720.mp4", StreamKind.MP4, 720, headers),
            Stream("https://cdn/720.m3u8", StreamKind.HLS, 720, headers),
        ],
        skip_segments=[SkipSegment(0, 90, "opening")],
    )


# -- models ---------------------------------------------------------------
def test_best_prefers_highest_quality():
    result = _result()
    assert result.best().quality == 720
    assert result.best().kind is StreamKind.MP4  # at equal quality mp4 is the handier one
    assert result.best(kind="hls").url == "https://cdn/720.m3u8"
    assert result.best(max_quality=360).quality == 360


def test_master_and_filters():
    result = _result()
    assert result.master().url.endswith("master.m3u8")
    assert result.qualities == [360, 720]
    assert len(result.filter("mp4")) == 2
    assert len(result.filter(quality=720)) == 2
    assert len(result) == 4 and bool(result) is True


def test_best_without_master():
    result = PlayerResult(
        player="test",
        source_url="u",
        streams=[Stream("https://cdn/master.m3u8", StreamKind.HLS)],
    )
    assert result.best().is_master
    with pytest.raises(errors.NoStreamsFound):
        result.best(allow_master=False)


def test_ffmpeg_command_includes_headers():
    stream = _result().best()
    args = stream.ffmpeg_args("out.mp4")
    assert args[0] == "ffmpeg" and args[-1] == "out.mp4"
    assert "-headers" in args
    assert "Referer: https://example.com/" in args[args.index("-headers") + 1]
    assert "out.mp4" in stream.ffmpeg_command("out.mp4")


def test_to_dict_is_json_ready():
    data = _result().to_dict()
    assert data["player"] == "test"
    assert data["streams"][0]["kind"] == "hls"
    assert data["skip_segments"][0] == {"start": 0, "end": 90, "kind": "opening"}


def test_skip_segment_duration():
    assert SkipSegment(30, 110).duration == 80


# -- utilities ------------------------------------------------------------
def test_parse_master_playlist_sorted_by_quality():
    variants = parse_master_playlist(fixture("aniboom_master.m3u8"), "https://cdn/qk/id/master.m3u8")
    assert [v["height"] for v in variants] == [360, 480, 720, 1080]
    assert variants[0]["url"].startswith("https://cdn/qk/id/")
    assert variants[-1]["bandwidth"] > variants[0]["bandwidth"]


def test_caesar_and_kodik_decoding():
    assert caesar_shift("abcZ", 1) == "bcdA"
    assert caesar_shift(caesar_shift("Hello, мир!", 7), -7) == "Hello, мир!"

    # a real encrypted link out of a /ftor response
    import json

    links = json.loads(fixture("kodik_ftor.json"))["links"]
    encrypted = links["720"][0]["src"]
    url, shift = decode_kodik_url(encrypted)
    assert url.startswith("//") or url.startswith("http")
    assert url.endswith(":hls:manifest.m3u8")
    # the shift that worked can be reused
    assert decode_kodik_url(encrypted, known_shift=shift)[0] == url


def test_decode_kodik_url_failure():
    with pytest.raises(errors.DecryptionError):
        decode_kodik_url("!!!")


def test_url_helpers():
    assert url_host("https://WWW.Aniboom.one:443/embed/x") == "aniboom.one"
    assert absolute_url("https://a/b/c.m3u8", "media_1.m3u8") == "https://a/b/media_1.m3u8"
    assert absolute_url("https://a/b", "//cdn/x.mp4") == "https://cdn/x.mp4"
    assert query_param("https://x/?videoid=42&a=1", "videoid") == "42"
    assert quality_from_label("hd720") == 720
    assert quality_from_label("master") is None


# -- registry --------------------------------------------------------------
@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://aniboom.one/embed/QK8d1LbNX6l", "aniboom"),
        ("https://animego.me/cdn-iframe/51019/Dream Cast/1/1", "cvh"),
        ("https://kodikplayer.com/seria/1/2/720p", "kodik"),
        ("//kodik.info/serial/1/2/720p", "kodik"),
        ("https://video.sibnet.ru/shell.php?videoid=1", "sibnet"),
        ("https://anilibria.top/anime/releases/release/bleach/episodes/1", "anilibria"),
        ("https://vk.com/video_ext.php?oid=-1&id=2", "vk"),
        ("https://sovetromantica.com/embed/episode_1_1-subtitles", "sovetromantica"),
    ],
)
def test_routing_by_url(url, expected):
    assert get_player_class(url).name == expected


def test_routing_by_name():
    assert get_player_class("kodik") is KodikPlayer
    assert set(player_names()) >= {"aniboom", "cvh", "kodik", "sibnet", "anilibria"}


def test_unknown_url():
    with pytest.raises(errors.UnsupportedUrl):
        get_player_class("https://example.com/video/1")


def test_register_custom_player():
    class DummyPlayer(BasePlayer):
        name = "dummy"
        title = "Dummy"
        domains = ("dummy.test",)

        def extract(self, url, **kwargs):  # pragma: no cover - the logic does not matter here
            return PlayerResult(player=self.name, source_url=url)

    registry.register(DummyPlayer, first=True)
    try:
        assert get_player_class("https://dummy.test/x").name == "dummy"
    finally:
        registry.PLAYERS.remove(DummyPlayer)


def test_extract_splits_client_and_player_options(monkeypatch):
    captured = {}

    def fake_extract(self, url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        captured["timeout"] = self._client_options["timeout"]
        return PlayerResult(player=self.name, source_url=url)

    monkeypatch.setattr(AniboomPlayer, "extract", fake_extract)
    registry.extract("https://aniboom.one/embed/x", timeout=5, referer="https://animego.org/")

    assert captured["timeout"] == 5
    assert captured["kwargs"] == {"referer": "https://animego.org/"}


def test_players_declare_metadata():
    for player in registry.all_players():
        assert player.name and player.title
        assert player.domains or player.url_patterns


# -- the AnimeGO helper -----------------------------------------------------
def test_animego_search_parses_cards():
    from anime_dl_core.http import Response
    from anime_dl_core.sources import AnimeGo

    card = (
        '<div class="ani-grid__item g-col-6">'
        '<div class="rating-badge positive"> 9.0 </div>'
        '<a class="d-block ani-grid__item-picture" href="/anime/magicheskaya-bitva-1635">'
        '<img class="image__img" src="https://img.example/poster.jpg" alt="Магическая битва"></a>'
        '<div class="fw-lighter small mb-1 text-line-clamp"> Jujutsu Kaisen </div>'
        '<div class="ani-grid__item-title h5 text-line-clamp">'
        '<a title="Магическая битва" href="/anime/magicheskaya-bitva-1635">Магическая битва</a>'
        "</div></div>"
    )

    class Client:
        def get(self, url, **kwargs):
            return Response(200, "<html>" + card + "</html>", url)

        def close(self):
            pass

    site = AnimeGo(client=Client())
    items = site.search("Магическая битва")
    assert len(items) == 1
    item = items[0]
    assert (item.id, item.slug, item.title) == ("1635", "magicheskaya-bitva", "Магическая битва")
    assert item.original_title == "Jujutsu Kaisen"
    assert item.rating == "9.0"
    assert item.url.endswith("/anime/magicheskaya-bitva-1635")
    assert AnimeGo.anime_id(item.url) == "1635"


def test_animego_search_reports_empty_result():
    from anime_dl_core.http import Response
    from anime_dl_core.sources import AnimeGo

    class Client:
        def get(self, url, **kwargs):
            return Response(200, "<html>По запросу «дандадан» ничего не найдено.</html>", url)

        def close(self):
            pass

    with pytest.raises(errors.NotFound) as info:
        AnimeGo(client=Client()).search("дандадан")
    assert "nothing was found" in str(info.value)


class TestSupports:
    def test_known_url_gives_player_name(self):
        assert supports("https://video.sibnet.ru/shell.php?videoid=2589828") == "sibnet"
        assert supports("kodik") == "kodik"

    def test_unknown_url_gives_none(self):
        assert supports("https://example.com/player/1") is None
        assert supports("") is None
