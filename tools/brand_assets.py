#!/usr/bin/env python3
"""Build web-sized brand assets from the master PNGs in brand/AiWazz-Brand-Kit/ (needs Pillow).

Output: design/assets/ (committed, shared by dashboard + landing)
  logo-{color,for-dark}-{w}.webp            full logo with tagline   (use at ≥ 160 px CSS width)
  logo-nt-{color,for-dark}-{w}.webp         logo without tagline     (use at ≥ 120 px CSS width)
  icon-{w}.webp                             A-Play icon, transparent (≥ 16 px)
  favicon/*                                 03_Favicon set, unchanged (goes to each site root)
  og-image.png                              05_Social-Media/og-image-light-1200x630.png, unchanged
The masters are never modified: no recolouring, effects or cropping (brand guidelines p.9).
Usage: python3 tools/brand_assets.py
"""
import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "brand" / "AiWazz-Brand-Kit"
OUT = ROOT / "design" / "assets"

SOURCES = {
    "logo-color": KIT / "01_Logo/Full-Color/AiWazz-logo-color-transparent-2048px.png",
    "logo-for-dark": KIT / "01_Logo/On-Dark/AiWazz-logo-for-dark-transparent-2048px.png",
    "logo-nt-color": KIT / "01_Logo/No-Tagline/AiWazz-logo-no-tagline-color-4096px.png",
    "logo-nt-for-dark": KIT / "01_Logo/No-Tagline/AiWazz-logo-no-tagline-for-dark-4096px.png",
    "icon": KIT / "02_Icon/AiWazz-icon-transparent-1024px.png",
}
WIDTHS = {"icon": [64, 128, 256]}
DEFAULT_WIDTHS = [320, 640, 960]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, src in SOURCES.items():
        im = Image.open(src).convert("RGBA")
        for w in WIDTHS.get(name, DEFAULT_WIDTHS):
            h = round(im.height * w / im.width)
            dest = OUT / f"{name}-{w}.webp"
            im.resize((w, h), Image.Resampling.LANCZOS).save(dest, "WEBP", quality=90, method=6)
            print(f"{dest.relative_to(ROOT)}  {w}x{h}  {dest.stat().st_size // 1024} KB")

    fav = OUT / "favicon"
    fav.mkdir(exist_ok=True)
    for f in (KIT / "03_Favicon").iterdir():
        if f.name != "HTML-snippet.txt":
            shutil.copy2(f, fav / f.name)
    shutil.copy2(KIT / "05_Social-Media/og-image-light-1200x630.png", OUT / "og-image.png")
    print(f"favicon set: {len(list(fav.iterdir()))} files; og-image.png copied")


if __name__ == "__main__":
    main()
