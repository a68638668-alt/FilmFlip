"""Create native macOS and Windows icons from one rendered PNG."""

from pathlib import Path
import sys

from PIL import Image


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: create_icons.py SOURCE.png OUTPUT.icns OUTPUT.ico")

    source_path, icns_path, ico_path = map(Path, sys.argv[1:])
    with Image.open(source_path) as source:
        image = source.convert("RGBA")
        image.save(icns_path, format="ICNS")
        image.save(
            ico_path,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )


if __name__ == "__main__":
    main()
