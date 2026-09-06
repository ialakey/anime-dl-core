"""Сквозной сценарий: название аниме -> серия -> озвучка -> прямая ссылка.

Ссылки на плееры берутся с AnimeGO (помощник anime_dl_core.sources.AnimeGo),
а разбирает их уже сама библиотека.

Запуск:
    python examples/02_animego_pipeline.py "Магическая битва" 2
"""

from __future__ import annotations

import sys

import anime_dl_core as ap
from anime_dl_core.sources import AnimeGo

# Порядок предпочтения плееров: чем раньше, тем лучше качество/стабильность
PREFERRED = ("aniboom", "kodik", "cvh", "sibnet")


def main() -> None:
    title = sys.argv[1] if len(sys.argv) > 1 else "Магическая битва"
    episode = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    with AnimeGo() as site:
        anime = site.search(title)[0]
        print(f"Нашли: {anime.title} ({anime.original_title}) — {anime.url}")

        episodes = site.episodes(anime.id)
        print(f"Серий на сайте: {len(episodes)}")

        links = site.players(anime.id, episode=episode)
        print(f"\nПлееры для серии {episode}:")
        for link in links:
            print(f"  {link.player:<10} {link.label}")

        # выбираем первый плеер из списка предпочтений
        chosen = None
        for name in PREFERRED:
            chosen = next((link for link in links if link.player.lower() == name), None)
            if chosen:
                break
        if chosen is None:
            chosen = links[0]

        print(f"\nБерём {chosen.player} / {chosen.label}")
        result = ap.extract(chosen.embed)

    best = result.best()
    print(f"Качества: {result.qualities}")
    print(f"Ссылка:   {best.url}")
    print(f"Заголовки: {best.headers}")


if __name__ == "__main__":
    main()
