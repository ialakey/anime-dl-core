"""Animedia and Alloha.

Run it with:
    python examples/07_animedia_alloha.py              # both examples
    python examples/07_animedia_alloha.py animedia [title] [episode number]
    python examples/07_animedia_alloha.py alloha [title]

* **Animedia** — a full player: the amd.online site (formerly animedia.tv) serves
  ``aser.pro/vod/<id>`` links, and per-quality HLS streams come out of those.
* **Alloha** — a catalogue plus links to an embeddable player. Alloha never
  returns direct video links (its player fetches them over a WebSocket from an
  obfuscated bundle), so it is a source: given a Kinopoisk/IMDb/TMDb id or a name
  it returns the description, the dubs, the seasons with their episodes, and a
  ready iframe.
"""

from __future__ import annotations

import sys

import anime_dl_core as ap
from anime_dl_core.sources import Alloha, Animedia


def demo_animedia(query: str = "Боруто", episode: int = 1) -> None:
    print("=== Animedia (amd.online + aser.pro) ===")

    with Animedia() as site:
        anime = site.search(query)[0]
        info = site.info(anime.url)
        print(f"  Title:    {info.title}")
        print(f"  Page:     {info.url}")

        episodes = site.episodes(anime.url)
        print(f"  Episodes: {len(episodes)} ({min(episodes)} through {max(episodes)})")

        players = site.players(anime.url)
        print(f"  Players:  animedia — {len(players['animedia'])}, kodik — {len(players['kodik'])}")

        if episode not in episodes:
            episode = min(episodes)
        print(f"\n  Episode {episode}: {episodes[episode]}")
        result = ap.extract(episodes[episode])

    print(f"  Qualities: {result.qualities}")
    for stream in result.streams:
        print(f"    {stream}")

    best = result.best()
    print(f"\n  Best quality: {best.quality}p")
    print(f"  Headers:      {best.headers['Referer']}")
    print("  Download:", best.ffmpeg_command("episode.mp4")[:110], "...")

    # the link is alive: fetch the playlist
    with ap.AnimediaPlayer() as player:
        content = player.fetch(best)
    print(f"  Playlist fetched: {content.splitlines()[0]} ({len(content)} bytes)")


def demo_alloha(query: str = "Атака титанов") -> None:
    print("\n=== Alloha (api.alloha.tv) ===")

    with Alloha() as alloha:                      # Alloha(token="your token")
        item = alloha.find(name=query)            # or find(kp=..., imdb=..., tmdb=...)
        print(f"  Title:     {item.name} ({item.original_name}), {item.year}")
        print(f"  Category:  {item.category} | Kinopoisk: {item.id_kp} | IMDb: {item.id_imdb}")
        print(f"  Rating:    {item.rating_kp} | Quality: {item.quality}")
        print(f"  Dubs:      {', '.join(t.name for t in item.translations)}")

        if item.is_series:
            print(f"  Seasons:   {{season: episodes}} = { {s: len(e) for s, e in item.seasons.items()} }")
            season = sorted(item.seasons)[0]
            episode = item.seasons[season][0]
            print(f"\n  Player for episode {season}x{episode}:")
            print("   ", alloha.iframe(item, season=season, episode=episode))
            # one episode carries its own set of dubs, so ask for that set
            available = alloha.translations_for(item, season=season, episode=episode)
            first = available[0].name
            print(f"  Dubs for this episode: {', '.join(t.name for t in available)}")
            print(f"  Player in the «{first}» dub:")
            print("   ", alloha.iframe(item, season=season, episode=episode, translation=first))
        else:
            print(f"\n  Player: {alloha.iframe(item)}")

    print(
        "\n  These are iframe links — embed them in a page or open them in a browser.\n"
        "  Alloha serves no direct m3u8/mp4: its player pulls those over a WebSocket\n"
        "  from an obfuscated bundle, and plain http parsing will not reach them."
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
