"""Как добавить свой плеер, не трогая код библиотеки.

Достаточно унаследоваться от BasePlayer, задать домены и реализовать extract().
После register() ссылка на новый плеер работает через общий anime_dl_core.extract().

Запуск:
    python examples/05_custom_player.py
"""

from __future__ import annotations

import re
from typing import Any

import anime_dl_core as ap
from anime_dl_core import BasePlayer, PlayerResult, Stream, StreamKind, register
from anime_dl_core.utils import search

FILE_RE = re.compile(r'file\s*:\s*"([^"]+\.m3u8)"')


@register
class MyPlayer(BasePlayer):
    """Плеер вымышленного сайта myplayer.example."""

    name = "myplayer"
    title = "My Player"
    domains = ("myplayer.example",)
    playback_headers = {"Referer": "https://myplayer.example/"}

    def extract(self, url: str, **kwargs: Any) -> PlayerResult:
        page = self.client.get(url, headers={"Referer": "https://myplayer.example/"})
        playlist = search(FILE_RE, page.raise_for_status().text, what="ссылку на m3u8")

        headers = dict(self.playback_headers)
        headers["User-Agent"] = self._client_options["user_agent"]
        return PlayerResult(
            player=self.name,
            source_url=url,
            streams=[Stream(playlist, StreamKind.HLS, None, headers, "master")],
        )


def main() -> None:
    print("Плееры в реестре:", ap.player_names())
    player = ap.get_player_class("https://myplayer.example/embed/1")
    print("Ссылка ушла в:", player.name)

    # Проверим разбор на подставном ответе, без сети
    class FakeClient:
        def get(self, url: str, **kwargs: Any):
            from anime_dl_core.http import Response

            return Response(200, 'var cfg = {file:"https://cdn.example/master.m3u8"};', url)

        def close(self) -> None:
            pass

    result = MyPlayer(FakeClient()).extract("https://myplayer.example/embed/1")
    print("Результат:", result.best())


if __name__ == "__main__":
    main()
