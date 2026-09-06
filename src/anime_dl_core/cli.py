"""Command line: ``anime-dl-core <url>`` or ``python -m anime_dl_core <url>``."""

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
        description="Extracts direct video links from anime players "
        "(Aniboom, CVH, Kodik, Sibnet, AniLibria, VK, SovetRomantica).",
        epilog="Examples:\n"
        "  anime-dl-core https://aniboom.one/embed/9G1MJ6NMV8z\n"
        "  anime-dl-core 51019 --player cvh --episode 2 --studio AniLibria\n"
        "  anime-dl-core bleach --player anilibria --episode 1 --best\n"
        "  anime-dl-core <url> --ffmpeg episode.mp4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", nargs="?", help="player url (or an id/alias for cvh, anilibria, sibnet)")
    parser.add_argument("--player", help="force a player by name")
    parser.add_argument("--list", action="store_true", help="list the supported players and exit")
    parser.add_argument("--json", action="store_true", help="print the result as json")
    parser.add_argument("--best", action="store_true", help="print only the best-quality link")
    parser.add_argument("--kind", choices=["hls", "dash", "mp4"], help="restrict the stream kind")
    parser.add_argument("--max-quality", type=int, help="highest quality to accept (720, for instance)")
    parser.add_argument("--ffmpeg", metavar="FILE", help="print the ffmpeg command that downloads it")
    parser.add_argument("--episode", type=int, help="episode number (cvh, anilibria, kodik)")
    parser.add_argument("--season", type=int, help="season number (cvh, kodik)")
    parser.add_argument("--studio", help="dub studio (cvh)")
    parser.add_argument("--referer", help="Referer to request the player with")
    parser.add_argument("--resolve", action="store_true", help="follow redirects (sibnet)")
    parser.add_argument("--proxy", help="http/socks5 proxy")
    parser.add_argument("--timeout", type=float, default=20.0, help="request timeout in seconds (default 20)")
    parser.add_argument("--version", action="version", version=f"anime-dl-core {__version__}")
    return parser


def _print_players() -> None:
    has_unverified = False
    for player in describe_players():
        mark = " " if player["verified"] else "*"
        has_unverified = has_unverified or not player["verified"]
        print(f"{mark} {player['name']:<15} {player['title']:<22} {', '.join(player['domains'])}")
        if player.get("note"):
            print(f"{'':<18}note: {player['note']}")
    if has_unverified:
        print("\n* — the player is implemented but was never checked against a live example (see README).")


def _format(result: PlayerResult) -> str:
    lines: List[str] = [f"Player: {result.player}"]
    if result.title:
        lines.append(f"Title: {result.title}")
    if result.translation:
        lines.append(f"Translation: {result.translation}")
    if result.duration:
        lines.append(f"Duration: {result.duration // 60}:{result.duration % 60:02d}")
    if result.skip_segments:
        segments = ", ".join(
            f"{segment.kind or 'skip'} {segment.start}-{segment.end}s" for segment in result.skip_segments
        )
        lines.append(f"Skip: {segments}")
    lines.append(f"Streams ({len(result.streams)}):")
    for stream in result.streams:
        quality = f"{stream.quality}p" if stream.quality else "auto"
        lines.append(f"  [{stream.kind.value:<4} {quality:>5}] {stream.url}")
    if result.streams and result.streams[0].headers:
        lines.append("Headers required for downloading:")
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
        parser.error("a player url is required (or --list)")

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


def run() -> None:  # pragma: no cover - console-script wrapper
    try:
        sys.exit(main())
    except AnimeDlCoreError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    run()
