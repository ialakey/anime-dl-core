"""Animedia и Alloha.

Запуск:
    python examples/07_animedia_alloha.py              # оба примера
    python examples/07_animedia_alloha.py animedia [название] [номер серии]
    python examples/07_animedia_alloha.py alloha [название]

* **Animedia** — полноценный плеер: сайт amd.online (бывший animedia.tv) отдаёт
  ссылки вида ``aser.pro/vod/<id>``, из них достаются HLS-потоки по качествам.
* **Alloha** — каталог и ссылки на встраиваемый плеер. Прямых ссылок на видео
  Alloha не отдаёт (плеер получает их по WebSocket из обфусцированного бандла),
  поэтому она реализована как источник: по id Кинопоиска/IMDb/TMDb или названию
  возвращает описание, озвучки, сезоны с сериями и готовый iframe.
"""

from __future__ import annotations

import sys

import anime_players as ap
from anime_players.sources import Alloha, Animedia


def demo_animedia(query: str = "Боруто", episode: int = 1) -> None:
    print("=== Animedia (amd.online + aser.pro) ===")

    with Animedia() as site:
        anime = site.search(query)[0]
        info = site.info(anime.url)
        print(f"  Тайтл:    {info.title}")
        print(f"  Страница: {info.url}")

        episodes = site.episodes(anime.url)
        print(f"  Серий:    {len(episodes)} (с {min(episodes)} по {max(episodes)})")

        players = site.players(anime.url)
        print(f"  Плееры:   animedia — {len(players['animedia'])}, kodik — {len(players['kodik'])}")

        if episode not in episodes:
            episode = min(episodes)
        print(f"\n  Серия {episode}: {episodes[episode]}")
        result = ap.extract(episodes[episode])

    print(f"  Качества: {result.qualities}")
    for stream in result.streams:
        print(f"    {stream}")

    best = result.best()
    print(f"\n  Лучшее качество: {best.quality}p")
    print(f"  Заголовки:       {best.headers['Referer']}")
    print("  Скачать:", best.ffmpeg_command("episode.mp4")[:110], "...")

    # ссылка живая: скачиваем плейлист
    with ap.AnimediaPlayer() as player:
        content = player.fetch(best)
    print(f"  Плейлист получен: {content.splitlines()[0]} ({len(content)} байт)")


def demo_alloha(query: str = "Атака титанов") -> None:
    print("\n=== Alloha (api.alloha.tv) ===")

    with Alloha() as alloha:                      # Alloha(token="свой токен")
        item = alloha.find(name=query)            # или find(kp=..., imdb=..., tmdb=...)
        print(f"  Тайтл:     {item.name} ({item.original_name}), {item.year}")
        print(f"  Категория: {item.category} | Кинопоиск: {item.id_kp} | IMDb: {item.id_imdb}")
        print(f"  Рейтинг:   {item.rating_kp} | Качество: {item.quality}")
        print(f"  Озвучки:   {', '.join(t.name for t in item.translations)}")

        if item.is_series:
            print(f"  Сезоны:    {{сезон: серий}} = { {s: len(e) for s, e in item.seasons.items()} }")
            season = sorted(item.seasons)[0]
            episode = item.seasons[season][0]
            print(f"\n  Плеер серии {season}x{episode}:")
            print("   ", alloha.iframe(item, season=season, episode=episode))
            # у конкретной серии набор озвучек свой, берём его
            available = alloha.translations_for(item, season=season, episode=episode)
            first = available[0].name
            print(f"  Озвучки этой серии: {', '.join(t.name for t in available)}")
            print(f"  Плеер в озвучке «{first}»:")
            print("   ", alloha.iframe(item, season=season, episode=episode, translation=first))
        else:
            print(f"\n  Плеер: {alloha.iframe(item)}")

    print(
        "\n  Это ссылки на iframe — их вставляют на страницу или открывают в браузере.\n"
        "  Прямых m3u8/mp4 Alloha не отдаёт: плеер забирает их по WebSocket из\n"
        "  обфусцированного бандла, обычным http-разбором их не достать."
    )


def main() -> None:
    what = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if what in ("all", "animedia"):
        demo_animedia(
            sys.argv[2] if len(sys.argv) > 2 and what == "animedia" else "Боруто",
            int(sys.argv[3]) if len(sys.argv) > 3 else 1,
        )
    if what in ("all", "alloha"):
        demo_alloha(sys.argv[2] if len(sys.argv) > 2 and what == "alloha" else "Атака титанов")


if __name__ == "__main__":
    main()
