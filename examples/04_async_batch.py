"""Асинхронный разбор нескольких плееров сразу (нужен aiohttp).

Запуск:
    pip install anime-players[async]
    python examples/04_async_batch.py
"""

from __future__ import annotations

import asyncio

import anime_players as ap

URLS = [
    "https://aniboom.one/embed/9G1MJ6NMV8z?episode=1&translation=30",
    "https://video.sibnet.ru/shell.php?videoid=2589828",
    "https://kodikplayer.com/seria/1304528/932d5da818729ec5ccc9be7968ee3717/720p",
]


async def resolve(url: str) -> None:
    try:
        result = await ap.extract_async(url, timeout=25)
    except ap.AnimePlayersError as error:
        print(f"[{url[:40]}...] ошибка: {error}")
        return
    print(f"[{result.player:<9}] качества={result.qualities or 'auto'} -> {result.best().url[:80]}")


async def main() -> None:
    # Разные плееры разбираются параллельно
    await asyncio.gather(*(resolve(url) for url in URLS))

    # Один плеер, много серий: переиспользуем соединение
    async with ap.AnilibriaPlayer() as player:
        results = await asyncio.gather(
            *(player.aextract("bleach", episode=number) for number in (1, 2, 3))
        )
    for result in results:
        print(f"[anilibria] {result.title}: {result.best(max_quality=720).url[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
