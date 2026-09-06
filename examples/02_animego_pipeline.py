"""End to end: anime name -> episode -> dub -> direct link.

Player links come from AnimeGO (the anime_dl_core.sources.AnimeGo helper);
parsing them is the library's own job.

Run it with:
    python examples/02_animego_pipeline.py "Магическая битва" 2
"""

from __future__ import annotations

import sys

import anime_dl_core as ap
from anime_dl_core.sources import AnimeGo

# Player preference, best quality/stability first
PREFERRED = ("aniboom", "kodik", "cvh", "sibnet")


def main() -> None:
    title = sys.argv[1] if len(sys.argv) > 1 else "Магическая битва"
    episode = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    with AnimeGo() as site:
        anime = site.search(title)[0]
        print(f"Found: {anime.title} ({anime.original_title}) — {anime.url}")

        episodes = site.episodes(anime.id)
        print(f"Episodes on the site: {len(episodes)}")

        links = site.players(anime.id, episode=episode)
        print(f"\nPlayers for episode {episode}:")
        for link in links:
            print(f"  {link.player:<10} {link.label}")

        # take the first player from the preference list
        chosen = None
        for name in PREFERRED:
            chosen = next((link for link in links if link.player.lower() == name), None)
            if chosen:
                break
        if chosen is None:
            chosen = links[0]

        print(f"\nGoing with {chosen.player} / {chosen.label}")
        result = ap.extract(chosen.embed)

    best = result.best()
    print(f"Qualities: {result.qualities}")
    print(f"Link:      {best.url}")
    print(f"Headers:   {best.headers}")


if __name__ == "__main__":
    main()
