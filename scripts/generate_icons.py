"""Generate resources/icon.ico and resources/icon.icns from logo/viewYUV.png.

Both formats are just containers around the same PNG at multiple sizes,
so Pillow can write them on any OS -- no need to run this on a Mac to
get a valid .icns. Re-run whenever logo/viewYUV.png changes.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE_LOGO = ROOT / "logo" / "viewYUV.png"
RESOURCES = ROOT / "resources"

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def _to_square(im: Image.Image, size: int = 1024) -> Image.Image:
    """Pad a (possibly non-square) logo onto a transparent square canvas.

    Resizing a non-square source straight into square icon slots would
    stretch/squish it -- fit-and-center instead so the logo keeps its
    aspect ratio at every icon size.
    """
    im = im.copy()
    im.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    return canvas


def main() -> None:
    RESOURCES.mkdir(exist_ok=True)
    im = _to_square(Image.open(SOURCE_LOGO).convert("RGBA"))

    ico_path = RESOURCES / "icon.ico"
    im.save(ico_path, sizes=[(s, s) for s in ICO_SIZES])
    print(f"wrote {ico_path}")

    icns_path = RESOURCES / "icon.icns"
    im.save(icns_path, sizes=[(s, s) for s in ICNS_SIZES])
    print(f"wrote {icns_path}")


if __name__ == "__main__":
    main()
