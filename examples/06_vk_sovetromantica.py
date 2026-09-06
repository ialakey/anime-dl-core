"""VK Video and SovetRomantica on live examples.

Run it with:
    python examples/06_vk_sovetromantica.py            # both examples
    python examples/06_vk_sovetromantica.py vk         # VK only
    python examples/06_vk_sovetromantica.py sr <SovetRomantica embed url>

What the examples show:

* **VK Video** — a working anime episode from the SovetRomantica VK community:
  direct mp4 from 144p to 720p, HLS/DASH, the cover and the duration.
* **SovetRomantica** — the team's own site is down (the ``sovetromantica.com``
  domain changed hands, the CDN is off), so parsing is shown against a real
  embed page from the web archive. Once the site is back, or if you have a
  mirror, pass ``base_url`` and everything works as usual.
"""

from __future__ import annotations

import sys

import anime_dl_core as ap

# "Grimgar of Fantasy and Ash" with SovetRomantica subtitles, on VK
VK_EPISODE = "https://vk.com/video_ext.php?oid=-33905270&id=456239024"

# A real SovetRomantica embed page as saved by the web archive
SR_ARCHIVED = (
    "https://web.archive.org/web/20240905174049id_/"
    "https://sovetromantica.com/embed/episode_1073_1-dubbed"
)


def show(result: ap.PlayerResult) -> None:
    print(f"  Player:      {result.player}")
    print(f"  Title:       {result.title}")
    print(f"  Translation: {result.translation or '—'}")
    if result.duration:
        print(f"  Duration:    {result.duration // 60}:{result.duration % 60:02d}")
    print(f"  Qualities:   {result.qualities or 'master playlist only'}")
    for segment in result.skip_segments:
        print(f"  Skip:        {segment.kind}: {segment.start}-{segment.end} s")
    for stream in result.streams[:6]:
        print(f"    {stream}")
    if len(result.streams) > 6:
        print(f"    ... and {len(result.streams) - 6} more")


def demo_vk() -> None:
    print("=== VK Video ===")

    with ap.VkPlayer() as player:
        # An embed url, an ordinary video url, or plain "oid_id" — all of them work
        result = player.extract(VK_EPISODE)
        show(result)

        best = result.best(kind="mp4")
        print(f"\n  Best mp4 ({best.quality}p): {best.url[:90]}...")
        print(f"  Headers:     {best.headers['Referer']}")

        # Check the link is alive by fetching the master playlist
        master = result.master()
        if master is not None:
            content = player.fetch(master)
            print(f"  Master playlist fetched: {content.splitlines()[0]} ({len(content)} bytes)")

        print("\n  Download:", best.ffmpeg_command("grimgar_08.mp4")[:110], "...")

    print("\n  A private or deleted video fails with a readable error:")
    try:
        ap.extract("https://vk.com/video_ext.php?oid=-1&id=1&hash=deadbeef")
    except ap.ContentBlocked as error:
        print(f"    ContentBlocked: {str(error)[:100]}...")


def demo_sovetromantica(url: str | None = None) -> None:
    print("\n=== SovetRomantica ===")

    if url:
        # Your own domain or a mirror: base_url lets the player call any host
        base = "/".join(url.split("/")[:3])
        with ap.SovetRomanticaPlayer(base_url=base) as player:
            show(player.extract(url))
        return

    print("  The team's site is offline, so this uses a page from the web archive.")
    with ap.SovetRomanticaPlayer(base_url="https://web.archive.org", timeout=60) as player:
        try:
            result = player.extract(SR_ARCHIVED)
        except ap.AnimeDlCoreError as error:
            print(f"  It did not work: {error}")
            return
    show(result)
    print(f"  Next episode: {result.extra['next_episode']}")
    print(f"  Timeline thumbnails: {result.extra['thumbnails']}")
    print(
        "\n  The files themselves (scu*.sovetromantica.com) are unreachable — the CDN is off.\n"
        "  Once the site is back, use:\n"
        '      with ap.SovetRomanticaPlayer(base_url="https://new-domain") as player:\n'
        '          result = player.extract("episode_1073_1-dubbed")\n'
        "  Current releases live on VK, and VkPlayer handles those (see the example above)."
    )


def main() -> None:
    what = sys.argv[1].lower() if len(sys.argv) > 1 else "all"
    if what in ("all", "vk"):
        demo_vk()
    if what in ("all", "sr", "sovetromantica"):
        demo_sovetromantica(sys.argv[2] if len(sys.argv) > 2 else None)


if __name__ == "__main__":
    main()
