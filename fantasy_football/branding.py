"""
Shared visual identity for every rendered graphic (power rankings, FAAB
report, predictions, season trend chart): the color palette and the
optional league logo.

Color palette -- Mississippi State maroon/white with black accents:
  MAROON is the official MSU brand maroon (#5D1725), used as the header/
  accent color. BLACK is the card background. WHITE is text and the
  highlight color for the #1 rank. A couple of pure-grayscale steps are
  added for text hierarchy (subtext, gridlines) -- those aren't a new
  "brand" hue, just value/lightness variation within black-white, needed
  so secondary text stays legible against black.

Movement/status colors (win-streak green, loss-streak red, etc.) are
deliberately kept separate from this palette -- they're a functional
signal (good/bad), not part of the team's visual identity, matching the
dataviz skill's rule that status colors are reserved and distinct from a
brand/categorical palette.

Logo: optional, via LOGO_PATH in .env (kept out of the repo -- see
config.py). If set, `load_logo()` returns an RGBA image with a
best-effort transparency mask (treats near-white pixels as background,
since most exported logos -- like a badge cut out in an image editor --
come on a white canvas rather than already transparent). If unset, or the
file is missing/unreadable, every caller here falls back to the plain
palette with no logo -- nothing breaks for someone who never sets it.
"""
import os
from typing import Optional

from PIL import Image

from . import config

# --- palette -----------------------------------------------------------
MAROON = (93, 23, 37)          # official MSU brand maroon (#5D1725)
MAROON_LIGHT = (140, 45, 64)   # lighter tint, used for bars/fills on black
BLACK = (13, 13, 13)           # near-black card background
ROW_A = (24, 24, 24)
ROW_B = (32, 32, 32)
WHITE = (255, 255, 255)
GRAY_SUBTEXT = (178, 178, 178)
GRAY_TRACK = (54, 54, 54)      # unfilled bar track

# status colors (unrelated to brand identity -- see module docstring)
STATUS_GOOD = (86, 200, 120)
STATUS_BAD = (220, 90, 90)
STATUS_NEUTRAL = (150, 150, 150)

_NEAR_WHITE_THRESHOLD = 235  # pixels this light or lighter become transparent


def load_logo() -> Optional[Image.Image]:
    """Returns an RGBA PIL Image for config.LOGO_PATH, or None if unset /
    missing / unreadable. Auto-derives an alpha mask from near-white
    pixels if the source has no real transparency, so a plain logo
    exported on a white background still composites cleanly onto a dark
    card instead of showing a white box."""
    path = config.LOGO_PATH
    if not path or not os.path.isfile(path):
        return None
    try:
        img = Image.open(path).convert("RGBA")
    except Exception:
        return None

    # if the source already has real transparency (any alpha < 255 present),
    # trust it as-is rather than second-guessing with the white-background heuristic
    alphas = img.getchannel("A")
    if alphas.getextrema()[0] < 255:
        return img

    r, g, b, a = img.split()
    # build alpha from "how far from white" each pixel is
    import PIL.ImageChops as ImageChops
    darkness = ImageChops.invert(Image.merge("RGB", (r, g, b)).convert("L"))
    new_alpha = darkness.point(lambda v: 255 if v > (255 - _NEAR_WHITE_THRESHOLD) else 0)
    img.putalpha(new_alpha)
    return img


def paste_badge(base: Image.Image, logo: Image.Image, size: int = 76, margin: int = 18, position: str = "top-right"):
    """Composites `logo` as a crisp corner badge onto `base` (mutates
    `base` in place). Scales to fit within `size`x`size` preserving aspect
    ratio."""
    if logo is None:
        return
    logo_fit = logo.copy()
    logo_fit.thumbnail((size, size), Image.LANCZOS)
    bw, bh = base.size
    lw, lh = logo_fit.size
    if position == "top-right":
        x, y = bw - margin - lw, margin
    elif position == "top-left":
        x, y = margin, margin
    else:
        x, y = bw - margin - lw, margin
    base.paste(logo_fit, (x, y), logo_fit)


def flat_tint(logo: Image.Image, opacity: float = 0.14, tint=WHITE, max_size=None) -> Optional[Image.Image]:
    """Returns a standalone RGBA image: `logo`'s silhouette recolored to a
    single flat `tint` at reduced `opacity`. Tinting every opaque pixel to
    one color keeps a multi-tone source logo from fighting the background
    at low opacity -- only its silhouette needs to read here. Used both for
    the PIL card watermark (paste_watermark) and the matplotlib season
    chart's figure-background watermark."""
    if logo is None:
        return None
    alpha = logo.getchannel("A")
    flat = Image.new("RGBA", logo.size, tint + (0,))
    flat.putalpha(alpha.point(lambda v: int(v * opacity)))
    if max_size:
        flat.thumbnail(max_size, Image.LANCZOS)
    return flat


def paste_watermark(base: Image.Image, logo: Image.Image, box, opacity: float = 0.14, tint=WHITE):
    """Composites a large, faint, flat-tinted watermark of `logo` centered
    within `box` = (x0, y0, x1, y1) on `base` (mutates in place)."""
    if logo is None:
        return
    x0, y0, x1, y1 = box
    box_w, box_h = x1 - x0, y1 - y0
    if box_w <= 0 or box_h <= 0:
        return

    flat = flat_tint(logo, opacity=opacity, tint=tint, max_size=(box_w, box_h))
    fw, fh = flat.size
    px = x0 + (box_w - fw) // 2
    py = y0 + (box_h - fh) // 2
    base.alpha_composite(flat.convert("RGBA"), (px, py)) if base.mode == "RGBA" else base.paste(flat, (px, py), flat)
