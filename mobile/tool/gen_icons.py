#!/usr/bin/env python3
"""Regenerate all launcher / app / web icons from the brand source art.

Sources live in `mobile/brand_src/` (the brand5 handoff). Run from the `mobile/`
directory: `python3 tool/gen_icons.py`. Requires Pillow. No Flutter SDK needed —
the sizes are computed straight from each platform's icon manifest.
"""
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MOB = os.path.dirname(HERE)
SRC = os.path.join(MOB, "brand_src")
TEAL = (0, 107, 94, 255)  # brand #006B5E

# Full-bleed opaque square: flatten the rounded-corner art onto solid teal so the
# transparent corners fill in seamlessly. iOS/Android apply their own mask; iOS
# also forbids alpha, hence the RGB flatten.
_art = Image.open(os.path.join(SRC, "icon-square-1024.png")).convert("RGBA")
SQUARE = Image.new("RGBA", _art.size, TEAL)
SQUARE.alpha_composite(_art)
SQUARE = SQUARE.convert("RGB")

FG = Image.open(os.path.join(SRC, "android-adaptive-foreground-432.png")).convert("RGBA")


def _write(img, size, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.resize((size, size), Image.LANCZOS).save(path)


def android():
    res = os.path.join(MOB, "android/app/src/main/res")
    legacy = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for dens, px in legacy.items():
        _write(SQUARE, px, f"{res}/mipmap-{dens}/ic_launcher.png")
    adaptive = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
    for dens, px in adaptive.items():
        _write(FG, px, f"{res}/mipmap-{dens}/ic_launcher_foreground.png")


def ios():
    d = os.path.join(MOB, "ios/Runner/Assets.xcassets/AppIcon.appiconset")
    with open(f"{d}/Contents.json") as f:
        contents = json.load(f)
    for fn in {img["filename"] for img in contents["images"]}:
        size = float(fn.replace("Icon-App-", "").split("x")[0])
        scale = int(fn.split("@")[1].split("x")[0])
        _write(SQUARE, round(size * scale), f"{d}/{fn}")


def web():
    w = os.path.join(MOB, "web")
    _write(SQUARE, 64, f"{w}/favicon.png")
    _write(SQUARE, 192, f"{w}/icons/Icon-192.png")
    _write(SQUARE, 512, f"{w}/icons/Icon-512.png")
    # Maskable: inset the glyph to the ~80% safe zone over a full-bleed teal field.
    for px in (192, 512):
        canvas = Image.new("RGBA", (px, px), TEAL)
        inner = round(px * 0.72)
        canvas.alpha_composite(_art.resize((inner, inner), Image.LANCZOS),
                               ((px - inner) // 2, (px - inner) // 2))
        canvas.convert("RGB").save(f"{w}/icons/Icon-maskable-{px}.png")


if __name__ == "__main__":
    android()
    ios()
    web()
    print("icons regenerated from", os.path.relpath(SRC, MOB))
