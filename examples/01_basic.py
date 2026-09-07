"""The simplest run: a player url in, video links out.

Run it with:
    python examples/01_basic.py [player url]
"""

from __future__ import annotations

import sys

import anime_dl_core as ap

DEFAULT_URL = "https://video.sibnet.ru/shell.php?videoid=2589828"


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL

    # extract works the player out from the url's domain on its own
    result = ap.extract(url)

    print(f"Player:      {result.player}")
    print(f"Title:       {result.title or '—'}")
    print(f"Translation: {result.translation or '—'}")
    qualities = result.qualities or "unknown (a master playlist, or a single file)"
    print(f"Qualities:   {qualities}")
    for segment in result.skip_segments:
        print(f"Skip:        {segment.kind}: {segment.start}-{segment.end} s")

    print("\nEvery stream that was found:")
    for stream in result.streams:
        print(f"  {stream}")

    best = result.best()
    print(f"\nBest stream: {best.url}")
    print("Headers without which the video will not be served:")
    for key, value in best.headers.items():
        print(f"  {key}: {value}")

    print("\nDownload it with ffmpeg:")
    print(" ", best.ffmpeg_command("episode.mp4"))


if __name__ == "__main__":
    main()
