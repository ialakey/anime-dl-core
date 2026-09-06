"""Тесты разбора плееров на сохранённых ответах (без сети)."""

from __future__ import annotations

import json

import pytest
from conftest import FakeClient, fixture, fixture_json

from anime_players import (
    AniboomPlayer,
    AnimediaPlayer,
    AnilibriaPlayer,
    CvhPlayer,
    KodikPlayer,
    SibnetPlayer,
    SovetRomanticaPlayer,
    StreamKind,
    VkPlayer,
    errors,
)
from anime_players.http import Response

ANIBOOM_EMBED = "https://aniboom.one/embed/9G1MJ6NMV8z?episode=1&translation=30"
KODIK_EMBED = "https://kodikplayer.com/seria/1304528/932d5da818729ec5ccc9be7968ee3717/720p"
SIBNET_EMBED = "https://video.sibnet.ru/shell.php?videoid=2589828"


# -- Aniboom ------------------------------------------------------------
def test_aniboom_parses_hls_and_dash(make_client):
    client = make_client({"aniboom.one/embed": fixture("aniboom_embed.html")})
    result = AniboomPlayer(client).extract(ANIBOOM_EMBED, resolve_qualities=False)

    assert result.player == "aniboom"
    assert result.master() is not None
    assert result.master().url.endswith("master.m3u8")
    assert [s.kind for s in result.streams].count(StreamKind.DASH) == 1
    assert result.duration == 2971
    assert result.poster and result.poster.startswith("http")
    assert result.extra["max_quality"] == 1080
    # заголовки обязательны для скачивания
    assert result.streams[0].headers["Referer"] == "https://aniboom.one/"


def test_aniboom_expands_master_playlist(make_client):
    client = make_client(
        {
            "aniboom.one/embed": fixture("aniboom_embed.html"),
            "master.m3u8": fixture("aniboom_master.m3u8"),
        }
    )
    result = AniboomPlayer(client).extract(ANIBOOM_EMBED, resolve_qualities=True)

    assert result.qualities == [360, 480, 720, 1080]
    best = result.best(kind="hls")
    assert best.quality == 1080
    assert best.url.startswith("https://")


def test_aniboom_reports_broken_markup(make_client):
    client = make_client({"aniboom.one/embed": "<html><body>ничего интересного</body></html>"})
    with pytest.raises(errors.ExtractionError):
        AniboomPlayer(client).extract(ANIBOOM_EMBED)


def test_aniboom_builds_embed_url():
    url = AniboomPlayer.embed_url("QK8d1LbNX6l", episode=3, translation=30)
    assert url == "https://aniboom.one/embed/QK8d1LbNX6l?episode=3&translation=30"
    assert AniboomPlayer.video_id(url) == "QK8d1LbNX6l"


# -- CVH ----------------------------------------------------------------
def test_cvh_playlist_and_streams(make_client):
    client = make_client(
        {
            "/playlist": fixture("cvh_playlist.json"),
            "/video/": fixture("cvh_video.json"),
        }
    )
    player = CvhPlayer(client)
    episodes = player.playlist("51019")

    assert episodes and episodes[0].season == 1
    assert all(episode.video_id for episode in episodes)

    result = player.extract("https://animego.me/cdn-iframe/51019/AniDub%20Online/1/1")
    assert result.player == "cvh"
    assert result.qualities  # mp4 разных качеств
    assert result.master().kind is StreamKind.HLS
    assert result.duration == 2966
    assert result.translation == "AniDub Online"


def test_cvh_parses_iframe_url():
    parsed = CvhPlayer.parse_url("https://animego.me/cdn-iframe/40748/Jam Club/2/13")
    assert parsed == {"cvh_id": "40748", "studio": "Jam Club", "season": 2, "episode": 13}
    assert CvhPlayer.parse_url("51019")["cvh_id"] == "51019"


def test_cvh_studio_matching_is_fuzzy(make_client):
    client = make_client(
        {"/playlist": fixture("cvh_playlist.json"), "/video/": fixture("cvh_video.json")}
    )
    player = CvhPlayer(client)
    episodes = player.playlist("51019")
    studios = {episode.studio for episode in episodes}

    # точное имя студии не требуется — достаточно подстроки
    partial = next(iter(studios)).split()[0]
    assert CvhPlayer.select(episodes, episode=1, studio=partial) is not None

    with pytest.raises(errors.NotFound):
        CvhPlayer.select(episodes, episode=1, studio="Такой озвучки нет")


def test_cvh_missing_episode(make_client):
    client = make_client({"/playlist": fixture("cvh_playlist.json")})
    player = CvhPlayer(client)
    with pytest.raises(errors.NotFound):
        player.extract("51019", episode=9999)


# -- Kodik --------------------------------------------------------------
def _kodik_client(make_client) -> FakeClient:
    return make_client(
        {
            "kodikplayer.com/seria": fixture("kodik_embed.html"),
            "/assets/js/": fixture("kodik_player_script.js"),
            "/ftor": fixture("kodik_ftor.json"),
        }
    )


def test_kodik_full_flow(make_client):
    client = _kodik_client(make_client)
    result = KodikPlayer(client).extract(KODIK_EMBED)

    assert result.player == "kodik"
    assert result.qualities == [360, 480, 720]
    # ссылки расшифрованы
    for stream in result.streams:
        assert stream.url.startswith("https://")
    assert result.best(kind="mp4").url.endswith("720.mp4")
    assert result.best(kind="hls").url.endswith(":hls:manifest.m3u8")
    assert result.translation == "2x2"
    assert [(s.start, s.end, s.kind) for s in result.skip_segments] == [
        (30, 110, "opening"),
        (1375, 1445, "ending"),
    ]


def test_kodik_sends_decoded_ref(make_client):
    """Пустой ref ломает ручку /ftor (сервер отвечает 500) — проверяем, что он заполнен."""
    client = _kodik_client(make_client)
    KodikPlayer(client).extract(KODIK_EMBED)

    post = client.last_call("POST")
    assert post["url"].endswith("/ftor")
    assert post["data"]["ref"] == "https://animego.org/"
    assert post["data"]["ref_sign"]
    assert post["data"]["hash"] and post["data"]["id"] and post["data"]["type"] == "seria"


def test_kodik_reuses_post_path(make_client):
    client = _kodik_client(make_client)
    player = KodikPlayer(client)
    player.extract(KODIK_EMBED)
    script_calls = [c for c in client.calls if "/assets/js/" in c["url"]]
    player.extract(KODIK_EMBED)
    assert len([c for c in client.calls if "/assets/js/" in c["url"]]) == len(script_calls)


def test_kodik_service_error(make_client):
    client = make_client(
        {
            "kodikplayer.com/seria": fixture("kodik_embed.html"),
            "/assets/js/": fixture("kodik_player_script.js"),
            "/ftor": Response(500, "<html>Error</html>", "https://kodikplayer.com/ftor"),
        }
    )
    with pytest.raises(errors.ServiceError):
        KodikPlayer(client).extract(KODIK_EMBED)


def test_kodik_adds_season_and_episode():
    player = KodikPlayer()
    url = player._normalize(
        "https://kodikplayer.com/serial/123/abc/720p", season=2, episode=5
    )
    assert "season=2" in url and "episode=5" in url


# -- Sibnet -------------------------------------------------------------
def test_sibnet_direct_mp4(make_client):
    client = make_client({"sibnet.ru/shell.php": fixture("sibnet_shell.html")})
    result = SibnetPlayer(client).extract(SIBNET_EMBED)

    assert result.player == "sibnet"
    stream = result.best()
    assert stream.kind is StreamKind.MP4
    assert stream.url.startswith("https://video.sibnet.ru/v/")
    assert stream.headers["Referer"] == "https://video.sibnet.ru/"
    assert result.title


def test_sibnet_resolves_redirect(make_client):
    client = make_client(
        {
            "sibnet.ru/shell.php": fixture("sibnet_shell.html"),
            "video.sibnet.ru/v/": Response(
                302, "", "https://video.sibnet.ru/v/x.mp4", {"Location": "https://dv97.sibnet.ru/25/89/82/x.mp4"}
            ),
        }
    )
    result = SibnetPlayer(client).extract("2589828", resolve=True)
    stream = result.best()
    assert stream.url == "https://dv97.sibnet.ru/25/89/82/x.mp4"
    assert stream.extra["original_url"].startswith("https://video.sibnet.ru/v/")


def test_sibnet_no_video(make_client):
    client = make_client({"sibnet.ru/shell.php": "<html>Видео удалено</html>"})
    with pytest.raises(errors.NoStreamsFound):
        SibnetPlayer(client).extract(SIBNET_EMBED)


# -- AniLibria ----------------------------------------------------------
def test_anilibria_episode(make_client):
    client = make_client({"/anime/releases/": fixture("anilibria_release.json")})
    result = AnilibriaPlayer(client).extract("bleach", episode=1)

    assert result.qualities == [480, 720, 1080]
    assert result.title.startswith("Блич")
    assert result.skip_segments and result.skip_segments[0].kind == "opening"
    assert result.extra["alias"] == "bleach"


def test_anilibria_parses_site_url(make_client):
    client = make_client({"/anime/releases/": fixture("anilibria_release.json")})
    result = AnilibriaPlayer(client).extract(
        "https://anilibria.top/anime/releases/release/bleach/episodes/2"
    )
    assert result.extra["ordinal"] == 2


def test_anilibria_unknown_episode(make_client):
    client = make_client({"/anime/releases/": fixture("anilibria_release.json")})
    with pytest.raises(errors.NotFound):
        AnilibriaPlayer(client).extract("bleach", episode=999)



# -- VK Video -----------------------------------------------------------
VK_EMBED = "https://vk.com/video_ext.php?oid=-33905270&id=456239024"


def _vk_client(make_client) -> FakeClient:
    return make_client(
        {
            "video_ext.php": fixture("vk_video_ext.html"),
            "okcdn.ru": fixture("vk_master.m3u8"),
        }
    )


def test_vk_parses_prefetch_cache(make_client):
    """Актуальный формат страницы: apiPrefetchCache -> video.get -> files."""
    client = _vk_client(make_client)
    result = VkPlayer(client).extract(VK_EMBED, resolve_qualities=False)

    assert result.player == "vk"
    assert result.qualities == [144, 240, 360, 480, 720]
    assert result.duration == 1440
    assert "Гримгар" in result.title
    assert result.poster and result.poster.startswith("http")
    assert result.master() is not None
    assert result.filter("dash")
    assert result.best(kind="mp4").quality == 720
    assert result.streams[0].headers["Referer"] == "https://vk.com/"


def test_vk_expands_master_playlist(make_client):
    client = _vk_client(make_client)
    result = VkPlayer(client).extract(VK_EMBED, resolve_qualities=True)

    hls_qualities = [stream.quality for stream in result.filter("hls") if stream.quality]
    assert hls_qualities  # мастер развернулся в отдельные качества
    assert max(hls_qualities) >= 480


def test_vk_supports_legacy_player_params(make_client):
    """Старый формат (var playerParams) ещё встречается на зеркалах."""
    params = {
        "params": [
            {
                "url240": "https://vk.com/240.mp4",
                "url720": "https://vk.com/720.mp4",
                "hls": "https://vk.com/index.m3u8",
                "dash_sep": "https://vk.com/index.mpd",
                "duration": 1420,
                "md_title": "Серия 1",
            }
        ]
    }
    page = "<html><script>var playerParams = " + json.dumps(params) + ";</script></html>"
    client = make_client({"video_ext.php": page})
    result = VkPlayer(client).extract("https://vk.com/video_ext.php?oid=-1&id=2", resolve_qualities=False)

    assert result.qualities == [240, 720]
    assert result.master().url.endswith(".m3u8")
    assert result.filter("dash")
    assert result.title == "Серия 1"
    assert result.duration == 1420


def test_vk_unavailable_video(make_client):
    client = make_client({"video_ext.php": fixture("vk_unavailable.html")})
    with pytest.raises(errors.ContentBlocked):
        VkPlayer(client).extract("https://vk.com/video_ext.php?oid=-1&id=1")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://vk.com/video_ext.php?oid=-1&id=2&hash=abc", ("-1", "2", "abc")),
        ("https://vkvideo.ru/video-33905270_456239024", ("-33905270", "456239024", None)),
        ("https://vk.ru/video-1_2_ab12cd", ("-1", "2", "ab12cd")),
        ("-33905270_456239024", ("-33905270", "456239024", None)),
    ],
)
def test_vk_understands_url_forms(value, expected):
    assert VkPlayer.video_ids(value) == expected


def test_vk_normalizes_to_embed(make_client):
    client = _vk_client(make_client)
    VkPlayer(client).extract("https://vkvideo.ru/video-33905270_456239024", resolve_qualities=False)
    assert "video_ext.php?oid=-33905270&id=456239024" in client.last_call("GET")["url"]


# -- SovetRomantica -----------------------------------------------------
SR_DUBBED = "https://sovetromantica.com/embed/episode_1073_1-dubbed"


def test_sovetromantica_dubbed(make_client):
    client = make_client({"/embed/": fixture("sovetromantica_dubbed.html")})
    result = SovetRomanticaPlayer(client).extract(SR_DUBBED)

    assert result.player == "sovetromantica"
    stream = result.best()
    assert stream.kind is StreamKind.HLS
    assert stream.url.endswith("episodes/dubbed/episode_1/episode_1.m3u8")
    assert result.title == "Gekkan Shoujo Nozaki-kun - Озвучка - Эпизод 1"
    assert result.translation == "Озвучка SovetRomantica"
    assert result.poster and result.poster.endswith("_dub.jpg")
    assert result.extra["episode"] == "episode_1073_1-dubbed"
    assert result.extra["next_episode"].endswith("episode_1073_2-dubbed")
    assert result.extra["thumbnails"].endswith(".vtt")


def test_sovetromantica_skip_segments(make_client):
    """skips: start..end — окно кнопки, skip_to — куда перематывает."""
    client = make_client({"/embed/": fixture("sovetromantica_dubbed.html")})
    result = SovetRomanticaPlayer(client).extract(SR_DUBBED)

    assert [(s.start, s.end, s.kind) for s in result.skip_segments] == [
        (174, 262, "opening"),
        (1316, 1398, "ending"),
    ]


def test_sovetromantica_subtitles_without_skips(make_client):
    client = make_client({"/embed/": fixture("sovetromantica_subtitles.html")})
    result = SovetRomanticaPlayer(client).extract("episode_1152_1-subtitles")

    assert "JoJo" in result.title
    assert result.translation == "Субтитры SovetRomantica"
    assert result.skip_segments == []
    assert result.best().url.endswith("episodes/subtitles/episode_1/episode_1.m3u8")


def test_sovetromantica_custom_domain(make_client):
    """С base_url плеер принимает зеркало/архив и ходит на указанный домен."""
    client = make_client({"/embed/": fixture("sovetromantica_dubbed.html")})
    player = SovetRomanticaPlayer(client, base_url="https://web.archive.org")
    result = player.extract("https://web.archive.org/web/2024id_/https://sovetromantica.com/embed/episode_1073_1-dubbed")

    assert result.title
    assert result.streams[0].headers["Referer"] == "https://web.archive.org/"
    assert player.embed_url("episode_1_1-dubbed").startswith("https://web.archive.org/embed/")


def test_sovetromantica_explains_dead_domain(make_client):
    """Домен сейчас отдаёт посторонний сайт — ошибка должна это объяснять."""
    client = make_client({"/embed/": "<html><body>Интернет-магазин</body></html>"})
    with pytest.raises(errors.NoStreamsFound) as info:
        SovetRomanticaPlayer(client).extract(SR_DUBBED)
    assert "другому владельцу" in str(info.value)


# -- Animedia (aser.pro) ------------------------------------------------
ANIMEDIA_VOD = "https://aser.pro/vod/20182"


def test_animedia_playerjs_file(make_client):
    client = make_client({"aser.pro/vod/": fixture("animedia_vod.html")})
    result = AnimediaPlayer(client).extract(ANIMEDIA_VOD, resolve_qualities=False)

    assert result.player == "animedia"
    master = result.master()
    assert master is not None and master.url.endswith("/hls/index.m3u8")
    assert master.headers["Referer"] == "https://aser.pro/"
    assert result.extra["vod_id"] == "20182"
    assert result.extra["episode"] == 1
    assert result.extra["slug"] == "raskolotaya_bitvoj_sineva_nebes_5"


def test_animedia_expands_master(make_client):
    client = make_client(
        {
            "aser.pro/vod/": fixture("animedia_vod.html"),
            "/hls/index.m3u8": fixture("animedia_master.m3u8"),
        }
    )
    result = AnimediaPlayer(client).extract(ANIMEDIA_VOD)

    assert result.qualities == [360, 720]
    assert result.best().quality == 720
    assert result.best().url.endswith("/720/index.m3u8")


def test_animedia_accepts_plain_id(make_client):
    client = make_client({"aser.pro/vod/": fixture("animedia_vod.html")})
    AnimediaPlayer(client).extract("20182", resolve_qualities=False)
    assert client.last_call("GET")["url"] == "https://aser.pro/vod/20182"


def test_animedia_multiquality_playerjs(make_client):
    """Playerjs умеет отдавать несколько качеств одной строкой."""
    page = (
        '<script>var player = new Playerjs({id:"v", '
        'file:"[720]https://cdn.example/720.mp4,[480]https://cdn.example/480.mp4"});</script>'
    )
    client = make_client({"aser.pro/vod/": page})
    result = AnimediaPlayer(client).extract(ANIMEDIA_VOD, resolve_qualities=False)

    assert result.qualities == [480, 720]
    assert result.best().kind is StreamKind.MP4


def test_animedia_json_playlist(make_client):
    """И json-плейлист со списком серий."""
    page = (
        '<script>new Playerjs({file:\'[{"title":"1","file":"https://cdn.example/1.m3u8"},'
        '{"title":"2","file":"https://cdn.example/2.m3u8"}]\'});</script>'
    )
    client = make_client({"aser.pro/vod/": page})
    result = AnimediaPlayer(client).extract(ANIMEDIA_VOD, resolve_qualities=False)

    assert len(result.streams) == 2
    assert all(stream.kind is StreamKind.HLS for stream in result.streams)


def test_animedia_without_player(make_client):
    client = make_client({"aser.pro/vod/": "<html><body>Видео удалено</body></html>"})
    with pytest.raises(errors.NoStreamsFound):
        AnimediaPlayer(client).extract(ANIMEDIA_VOD)
