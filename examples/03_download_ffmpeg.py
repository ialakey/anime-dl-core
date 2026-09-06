"""Скачивание серии через ffmpeg (ffmpeg должен быть установлен и доступен в PATH).

Запуск:
    python examples/03_download_ffmpeg.py <ссылка на плеер> [файл.mp4] [качество]

Пример:
    python examples/03_download_ffmpeg.py https://aniboom.one/embed/9G1MJ6NMV8z ep1.mp4 720
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import anime_players as ap


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    url = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "episode.mp4"
    max_quality = int(sys.argv[3]) if len(sys.argv) > 3 else None

    result = ap.extract(url)
    # allow_master=False — берём поток конкретного качества, а не мастер-плейлист
    try:
        stream = result.best(max_quality=max_quality, allow_master=False)
    except ap.NoStreamsFound:
        stream = result.best(max_quality=max_quality)

    print(f"Плеер: {result.player}, качество: {stream.quality or 'auto'}")
    print(f"Источник: {stream.url}")

    if shutil.which("ffmpeg") is None:
        print("\nffmpeg не найден в PATH. Скопируйте команду и выполните вручную:")
        print(stream.ffmpeg_command(output))
        return 1

    args = stream.ffmpeg_args(output, extra_args=["-bsf:a", "aac_adtstoasc", "-y"])
    print("\nЗапускаем:", " ".join(args[:4]), "...")
    completed = subprocess.run(args)
    if completed.returncode == 0:
        print(f"Готово: {output}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
