"""Тесты командной строки (сеть не используется — extract подменяется)."""

from __future__ import annotations

import json

import pytest

from anime_players import PlayerResult, SkipSegment, Stream, StreamKind, cli


@pytest.fixture
def fake_extract(monkeypatch):
    calls = {}

    def _extract(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        headers = {"Referer": "https://kodikplayer.com/"}
        return PlayerResult(
            player="kodik",
            source_url=url,
            streams=[
                Stream("https://cdn/360.mp4", StreamKind.MP4, 360, headers),
                Stream("https://cdn/720.mp4", StreamKind.MP4, 720, headers),
                Stream("https://cdn/720.m3u8", StreamKind.HLS, 720, headers),
            ],
            translation="AniLibria",
            skip_segments=[SkipSegment(30, 110, "opening")],
        )

    monkeypatch.setattr(cli, "extract", _extract)
    return calls


def test_list_players(capsys):
    assert cli.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "aniboom" in out and "kodik" in out and "vk" in out
    # у плееров с особенностями показывается примечание
    assert "примечание:" in out and "сайт офлайн" in out


def test_default_output(capsys, fake_extract):
    assert cli.main(["https://kodikplayer.com/seria/1/2/720p"]) == 0
    out = capsys.readouterr().out
    assert "Плеер: kodik" in out
    assert "Озвучка: AniLibria" in out
    assert "opening 30-110s" in out
    assert "Referer: https://kodikplayer.com/" in out


def test_best_and_kind(capsys, fake_extract):
    assert cli.main(["https://kodikplayer.com/seria/1/2/720p", "--best", "--kind", "mp4"]) == 0
    assert capsys.readouterr().out.strip() == "https://cdn/720.mp4"


def test_max_quality(capsys, fake_extract):
    assert cli.main(["https://kodikplayer.com/seria/1/2/720p", "--best", "--max-quality", "360"]) == 0
    assert capsys.readouterr().out.strip() == "https://cdn/360.mp4"


def test_json_output(capsys, fake_extract):
    assert cli.main(["https://kodikplayer.com/seria/1/2/720p", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["player"] == "kodik"
    assert len(data["streams"]) == 3


def test_ffmpeg_output(capsys, fake_extract):
    assert cli.main(["https://kodikplayer.com/seria/1/2/720p", "--ffmpeg", "ep.mp4"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("ffmpeg ") and "ep.mp4" in out


def test_player_options_are_forwarded(fake_extract):
    cli.main(["51019", "--episode", "3", "--season", "2", "--studio", "AniLibria", "--proxy", "http://p:1"])
    assert fake_extract["url"] == "51019"
    assert fake_extract["kwargs"]["episode"] == 3
    assert fake_extract["kwargs"]["season"] == 2
    assert fake_extract["kwargs"]["studio"] == "AniLibria"
    assert fake_extract["kwargs"]["proxy"] == "http://p:1"


def test_url_required(capsys):
    with pytest.raises(SystemExit):
        cli.main([])
