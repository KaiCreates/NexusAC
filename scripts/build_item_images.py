"""Build small web thumbnails from an ox_inventory-style image directory.

Usage: python scripts/build_item_images.py "C:/path/to/images"
The source artwork is never modified. Pillow is needed only when rebuilding.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "app" / "static" / "item-images"


def build_one(path: Path) -> str | None:
    name = path.stem.lower()
    if name in ("", ".", "..") or any(ord(char) < 32 for char in name):
        print(f"Skipping unsafe filename: {path.name}")
        return None
    output = DEST / f"{name}.webp"
    if output.exists() and output.stat().st_mtime >= path.stat().st_mtime:
        return name
    with Image.open(path) as original:
        has_alpha = original.mode in ("RGBA", "LA") or "transparency" in original.info
        image = ImageOps.exif_transpose(original).convert("RGBA" if has_alpha else "RGB")
        image.thumbnail((128, 128), Image.Resampling.LANCZOS)
        image.save(output, "WEBP", quality=84, method=3)
    return name


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python scripts/build_item_images.py "path/to/images"')

    source = Path(sys.argv[1])
    if not source.is_dir():
        raise SystemExit(f"Image directory not found: {source}")

    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        names = [name for name in pool.map(build_one, sorted(source.rglob("*.png"))) if name]

    (DEST / "manifest.js").write_text(
        "window.NEXUS_ITEM_IMAGES = new Set(" + json.dumps(names, separators=(",", ":")) + ");\n",
        encoding="utf-8",
    )
    print(f"Built {len(names)} item thumbnails in {DEST}")


if __name__ == "__main__":
    main()
