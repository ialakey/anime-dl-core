"""VK Video и SovetRomantica на живых примерах.

Запуск:
    python examples/06_vk_sovetromantica.py            # оба примера
    python examples/06_vk_sovetromantica.py vk         # только VK
    python examples/06_vk_sovetromantica.py sr <ссылка на embed SovetRomantica>

Что показывают примеры:

* **VK Video** — рабочая серия аниме из сообщества SovetRomantica ВКонтакте:
  прямые mp4 от 144p до 720p, HLS/DASH, обложка и длительность.
* **SovetRomantica** — собственный сайт команды сейчас не работает (домен
  ``sovetromantica.com`` перешёл другому владельцу, CDN отключён), поэтому
  разбор показан на настоящей странице embed из веб-архива. Когда сайт вернётся
  или если у вас есть зеркало — передайте ``base_url`` и всё заработает
  как обычно.
"""

from __future__ import annotations

import sys

import anime_players as ap

# Серия «Гримгар из пепла и фантазий» с субтитрами SovetRomantica, ВКонтакте
VK_EPISODE = "https://vk.com/video_ext.php?oid=-33905270&id=456239024"

# Настоящая страница embed SovetRomantica, сохранённая веб-архивом
SR_ARCHIVED = (
    "https://web.archive.org/web/20240905174049id_/"
    "https://sovetromantica.com/embed/episode_1073_1-dubbed"
)


def show(result: ap.PlayerResult) -> None:
    print(f"  Плеер:       {result.player}")
    print(f"  Название:    {result.title}")
    print(f"  Озвучка:     {result.translation or '—'}")
    if result.duration:
        print(f"  Длительность:{result.duration // 60}:{result.duration % 60:02d}")
    print(f"  Качества:    {result.qualities or 'только мастер-плейлист'}")
    for segment in result.skip_segments:
        print(f"  Пропуск:     {segment.kind}: {segment.start}-{segment.end} сек")
    for stream in result.streams[:6]:
        print(f"    {stream}")
    if len(result.streams) > 6:
        print(f"    ... и ещё {len(result.streams) - 6}")


def demo_vk() -> None:
    print("=== VK Video ===")

    with ap.VkPlayer() as player:
        # Ссылка на embed, обычная ссылка на видео и просто "oid_id" — всё подходит
        result = player.extract(VK_EPISODE)
        show(result)

        best = result.best(kind="mp4")
        print(f"\n  Лучший mp4 ({best.quality}p): {best.url[:90]}...")
        print(f"  Заголовки:   {best.headers['Referer']}")

        # Проверяем, что ссылка живая: скачиваем мастер-плейлист
        master = result.master()
        if master is not None:
            content = player.fetch(master)
            print(f"  Мастер-плейлист получен: {content.splitlines()[0]} ({len(content)} байт)")

        print("\n  Скачать:", best.ffmpeg_command("grimgar_08.mp4")[:110], "...")

    print("\n  Приватное/удалённое видео даёт понятную ошибку:")
    try:
        ap.extract("https://vk.com/video_ext.php?oid=-1&id=1&hash=deadbeef")
    except ap.ContentBlocked as error:
        print(f"    ContentBlocked: {str(error)[:100]}...")


def demo_sovetromantica(url: str | None = None) -> None:
    print("\n=== SovetRomantica ===")

    if url:
        # Свой домен/зеркало: base_url разрешает плееру ходить на любой хост
        base = "/".join(url.split("/")[:3])
        with ap.SovetRomanticaPlayer(base_url=base) as player:
            show(player.extract(url))
        return

    print("  Сайт команды сейчас офлайн, поэтому берём страницу из веб-архива.")
    with ap.SovetRomanticaPlayer(base_url="https://web.archive.org", timeout=60) as player:
        try:
            result = player.extract(SR_ARCHIVED)
        except ap.AnimePlayersError as error:
            print(f"  Не получилось: {error}")
            return
    show(result)
    print(f"  Следующая серия: {result.extra['next_episode']}")
    print(f"  Превью для таймлайна: {result.extra['thumbnails']}")
    print(
        "\n  Сами файлы (scu*.sovetromantica.com) сейчас недоступны — CDN выключен.\n"
        "  Когда сайт вернётся, используйте:\n"
        '      with ap.SovetRomanticaPlayer(base_url="https://новый-домен") as player:\n'
        '          result = player.extract("episode_1073_1-dubbed")\n'
        "  А свежие релизы команды сейчас лежат ВКонтакте — их разбирает VkPlayer (пример выше)."
    )


def main() -> None:
    what = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if what in ("all", "vk"):
        demo_vk()
    if what in ("all", "sr", "sovetromantica"):
        demo_sovetromantica(sys.argv[2] if len(sys.argv) > 2 else None)


if __name__ == "__main__":
    main()
