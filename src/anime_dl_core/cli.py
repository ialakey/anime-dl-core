"""Командная строка: ``anime-dl-core <ссылка>`` или ``python -m anime_dl_core <ссылка>``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .errors import AnimeDlCoreError
from .models import PlayerResult
from .registry import describe_players, extract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-dl-core",
        description="Достаёт прямые ссылки на видео из аниме-плееров "
        "(Aniboom, CVH, Kodik, Sibnet, AniLibria, VK, SovetRomantica).",
        epilog="Примеры:\n"
        "  anime-dl-core https://aniboom.one/embed/9G1MJ6NMV8z\n"
        "  anime-dl-core 51019 --player cvh --episode 2 --studio AniLibria\n"
        "  anime-dl-core bleach --player anilibria --episode 1 --best\n"
        "  anime-dl-core <ссылка> --ffmpeg episode.mp4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="ссылка на плеер (или id/алиас для cvh, anilibria, sibnet)")
    parser.add_argument("--player", help="принудительно выбрать плеер по имени")
    parser.add_argument("--list", action="store_true", help="показать поддерживаемые плееры и выйти")
    parser.add_argument("--json", action="store_true", help="вывести результат в json")
    parser.add_argument("--best", action="store_true", help="вывести только ссылку лучшего качества")
    parser.add_argument("--kind", choices=["hls", "dash", "mp4"], help="ограничить тип потока")
    parser.add_argument("--max-quality", type=int, help="максимальное качество (например 720)")
    parser.add_argument("--ffmpeg", metavar="FILE", help="показать команду ffmpeg для скачивания")
    parser.add_argument("--episode", type=int, help="номер серии (cvh, anilibria, kodik)")
    parser.add_argument("--season", type=int, help="номер сезона (cvh, kodik)")
    parser.add_argument("--studio", help="озвучка (cvh)")
    parser.add_argument("--referer", help="Referer, с которым запрашивать плеер")
    parser.add_argument("--resolve", action="store_true", help="разворачивать редиректы (sibnet)")
    parser.add_argument("--proxy", help="http/socks5 прокси")
    parser.add_argument("--timeout", type=float, default=20.0, help="таймаут запроса, сек (по умолчанию 20)")
    parser.add_argument("--version", action="version", version=f"anime-dl-core {__version__}")
    return parser


def _print_players() -> None:
    has_unverified = False
    for player in describe_players():
        mark = " " if player["verified"] else "*"
        has_unverified = has_unverified or not player["verified"]
        print(f"{mark} {player['name']:<15} {player['title']:<22} {', '.join(player['domains'])}")
        if player.get("note"):
            print(f"{'':<18}примечание: {player['note']}")
    if has_unverified:
        print("\n* — плеер реализован, но не проверялся на живом примере (см. README).")


def _format(result: PlayerResult) -> str:
    lines: List[str] = [f"Плеер: {result.player}"]
    if result.title:
        lines.append(f"Название: {result.title}")
    if result.translation:
        lines.append(f"Озвучка: {result.translation}")
    if result.duration:
        lines.append(f"Длительность: {result.duration // 60}:{result.duration % 60:02d}")
    if result.skip_segments:
        segments = ", ".join(
            f"{segment.kind or 'skip'} {segment.start}-{segment.end}s" for segment in result.skip_segments
        )
        lines.append(f"Пропуск: {segments}")
    lines.append(f"Потоки ({len(result.streams)}):")
    for stream in result.streams:
        quality = f"{stream.quality}p" if stream.quality else "auto"
        lines.append(f"  [{stream.kind.value:<4} {quality:>5}] {stream.url}")
    if result.streams and result.streams[0].headers:
        lines.append("Заголовки для скачивания:")
        for key, value in result.streams[0].headers.items():
            lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        _print_players()
        return 0
    if not args.url:
        parser.error("нужно указать ссылку на плеер (или --list)")

    options: Dict[str, Any] = {"proxy": args.proxy, "timeout": args.timeout}
    for key in ("episode", "season", "studio", "referer"):
        value = getattr(args, key)
        if value is not None:
            options[key] = value
    if args.resolve:
        options["resolve"] = True

    target = args.url
    if args.player:
        from .registry import get_player_class

        player_class = get_player_class(args.player)
        client_options = {"proxy": args.proxy, "timeout": args.timeout}
        extract_options = {k: v for k, v in options.items() if k not in client_options}
        player = player_class(**client_options)
        try:
            result = player.extract(target, **extract_options)
        finally:
            player.close()
    else:
        result = extract(target, **options)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.ffmpeg or args.best:
        stream = result.best(args.kind, max_quality=args.max_quality)
        print(stream.ffmpeg_command(args.ffmpeg) if args.ffmpeg else stream.url)
        return 0

    if args.kind or args.max_quality:
        result.streams = result.filter(args.kind, max_quality=args.max_quality)
    print(_format(result))
    return 0


def run() -> None:  # pragma: no cover - обёртка для точки входа
    try:
        sys.exit(main())
    except AnimeDlCoreError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    run()
