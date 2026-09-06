"""Самый простой сценарий: ссылка на плеер -> ссылки на видео.

Запуск:
    python examples/01_basic.py [ссылка на плеер]
"""

from __future__ import annotations

import sys

import anime_dl_core as ap

DEFAULT_URL = "https://video.sibnet.ru/shell.php?videoid=2589828"


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    # extract сам определяет плеер по домену ссылки
    result = ap.extract(url)

    print(f"Плеер:      {result.player}")
    print(f"Название:   {result.title or '—'}")
    print(f"Озвучка:    {result.translation or '—'}")
    qualities = result.qualities or "неизвестны (мастер-плейлист или один файл)"
    print(f"Качества:   {qualities}")
    for segment in result.skip_segments:
        print(f"Пропуск:    {segment.kind}: {segment.start}-{segment.end} сек")

    print("\nВсе найденные потоки:")
    for stream in result.streams:
        print(f"  {stream}")

    best = result.best()
    print(f"\nЛучший поток: {best.url}")
    print("Заголовки, без которых видео не отдадут:")
    for key, value in best.headers.items():
        print(f"  {key}: {value}")

    print("\nСкачать через ffmpeg:")
    print(" ", best.ffmpeg_command("episode.mp4"))


if __name__ == "__main__":
    main()
