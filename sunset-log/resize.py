"""Drop new sunset photographs into photos/ at web size.

Usage:
    python resize.py "<folder with new photos>"

Reads every JPEG/HEIC in the given folder, resizes so the long edge is
LONG_EDGE px, and writes photos/<NAME>.jpg next to this script. Files already
present in photos/ are skipped, so re-running is safe.

HEIC support needs `pip install pillow-heif`; plain JPEG needs only pillow.
"""

import sys
from pathlib import Path

from PIL import Image, ImageOps

try:  # optional — only needed for iPhone HEIC originals
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass

LONG_EDGE = 1600
QUALITY = 82
SRC_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".png"}
DEST = Path(__file__).parent / "photos"


def convert(src: Path, dest: Path) -> str:
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)  # honour the phone's rotation flag
        im = im.convert("RGB")
        before = im.size
        im.thumbnail((LONG_EDGE, LONG_EDGE), Image.LANCZOS)
        im.save(dest, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    kb = dest.stat().st_size / 1024
    return f"{src.name}: {before[0]}x{before[1]} -> {im.size[0]}x{im.size[1]}, {kb:.0f} KB"


def main(folder: str) -> int:
    src_dir = Path(folder)
    if not src_dir.is_dir():
        print(f"Not a folder: {src_dir}")
        return 1

    DEST.mkdir(exist_ok=True)
    done = skipped = 0

    for src in sorted(src_dir.iterdir()):
        if src.suffix.lower() not in SRC_EXT:
            continue
        # the dataset refers to photographs as .jpg, so normalise the extension
        dest = DEST / (src.stem + ".jpg")
        if dest.exists():
            print(f"skip  {dest.name} (already in photos/)")
            skipped += 1
            continue
        print("write " + convert(src, dest))
        done += 1

    print(f"\n{done} written, {skipped} skipped, into {DEST}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
