"""
Generates the header image for every email -- a real photo (fetched live
from Lorem Picsum, https://picsum.photos -- free, no API key, backed by
Unsplash's full library, so every send can pull a genuinely different photo
from anywhere in the world, any subject).

Design note: earlier versions of this module tried to render the Hebrew
quote directly on top of the photo (via a bundled font + manual
BiDi/shaping). That added a real Hebrew-font/text-rendering dependency
inside the image pipeline, and in practice it silently failed end-to-end on
at least one real scheduled run (no image arrived in the email at all --
the whole generate call raised and notify.py's outer try/except swallowed
it). The quote is shown perfectly well as plain HTML text right below the
image (see notify.py's build_html_email) -- there is no need to also draw
it into the JPEG. So this module now does ONE simple thing: return a nice
photo. No fonts, no text shaping, far fewer ways to fail.

Network dependency and fallback: fetching a live photo needs internet
access at send time. If the fetch fails for any reason (offline, blocked,
slow, non-200 response) within a short timeout, this falls back to a
procedural gradient + abstract "growth motif" generator instead, so a
flaky network never turns into a missing email -- only a plainer image for
that one send. (notify.py's own caller wraps this whole module in a
try/except besides, so even a total failure here still lets the email send
with no image at all, never blocking the send itself.)
"""

from __future__ import annotations

import colorsys
import io
import random

import numpy as np
import requests
from PIL import Image, ImageDraw

WIDTH = 1200
HEIGHT = 400

PHOTO_FETCH_TIMEOUT = 6  # seconds -- a slow/hanging photo host must never stall a scheduled send

# (start_hue, end_hue) in degrees -- chosen to keep every random combination
# in tasteful, finance-appropriate territory (sunrise/gold/teal/purple/green)
# rather than fully random (often garish) hues. Each generation also jitters
# hue/saturation/lightness within the family, so the actual pool of possible
# images is effectively unbounded. Used only for the no-live-photo fallback.
HUE_FAMILIES = [
    (18, 280),    # sunrise orange -> purple
    (200, 260),   # ocean blue -> indigo
    (140, 45),    # green growth -> gold
    (270, 320),   # purple -> magenta twilight
    (35, 200),    # gold horizon -> teal
    (170, 215),   # teal -> deep blue
    (355, 320),   # warm rose -> magenta
]

MOTIFS = ["bars", "arrow", "summit", "candles", "arc", "dots"]


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple:
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l, s)
    return int(r * 255), int(g * 255), int(b * 255)


def _random_gradient_colors() -> tuple:
    h1, h2 = random.choice(HUE_FAMILIES)
    jitter = random.uniform(-14, 14)
    h1 = (h1 + jitter) % 360
    h2 = (h2 + jitter) % 360
    s = random.uniform(0.45, 0.7)
    l1 = random.uniform(0.20, 0.30)
    l2 = random.uniform(0.42, 0.56)
    return _hsl_to_rgb(h1, s, l1), _hsl_to_rgb(h2, s, l2)


def _gradient_background(c1: tuple, c2: tuple, direction: str) -> Image.Image:
    c1_arr = np.array(c1, dtype=np.float32)
    c2_arr = np.array(c2, dtype=np.float32)

    if direction == "horizontal":
        t = np.linspace(0.0, 1.0, WIDTH, dtype=np.float32)
        row = c1_arr[None, :] + (c2_arr - c1_arr)[None, :] * t[:, None]  # (W, 3)
        arr = np.tile(row[None, :, :], (HEIGHT, 1, 1))
    elif direction == "vertical":
        t = np.linspace(0.0, 1.0, HEIGHT, dtype=np.float32)
        col = c1_arr[None, :] + (c2_arr - c1_arr)[None, :] * t[:, None]  # (H, 3)
        arr = np.tile(col[:, None, :], (1, WIDTH, 1))
    else:  # diagonal
        ty = np.linspace(0.0, 1.0, HEIGHT, dtype=np.float32)
        tx = np.linspace(0.0, 1.0, WIDTH, dtype=np.float32)
        tt = (ty[:, None] + tx[None, :]) / 2.0  # (H, W)
        arr = c1_arr[None, None, :] + (c2_arr - c1_arr)[None, None, :] * tt[:, :, None]

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def _draw_bars(draw: ImageDraw.ImageDraw) -> None:
    n = random.randint(7, 11)
    margin = 60
    gap = 14
    bar_w = (WIDTH - 2 * margin - gap * (n - 1)) / n
    base_y = HEIGHT - 40
    trend = sorted(random.uniform(0.15, 1.0) for _ in range(n))  # generally ascending
    for i, t in enumerate(trend):
        jitter = random.uniform(-0.05, 0.05)
        h = max(20, (t + jitter) * (HEIGHT - 120))
        x0 = margin + i * (bar_w + gap)
        x1 = x0 + bar_w
        y1 = base_y
        y0 = base_y - h
        draw.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=(255, 255, 255, 60))


def _draw_arrow(draw: ImageDraw.ImageDraw) -> None:
    import math

    x0, y0 = 90, HEIGHT - 70
    x1, y1 = WIDTH - 120, 70
    draw.line([x0, y0, x1, y1], fill=(255, 255, 255, 90), width=10)

    # Triangular arrowhead: two points swept +-25deg from the reversed line
    # direction, at a fixed length back from the tip.
    angle = math.atan2(y1 - y0, x1 - x0)
    head_len = 34
    sweep = math.radians(25)
    back_angle_1 = angle + math.pi - sweep
    back_angle_2 = angle + math.pi + sweep
    p1 = (x1 + head_len * math.cos(back_angle_1), y1 + head_len * math.sin(back_angle_1))
    p2 = (x1 + head_len * math.cos(back_angle_2), y1 + head_len * math.sin(back_angle_2))
    draw.polygon([(x1, y1), p1, p2], fill=(255, 255, 255, 90))


def _draw_summit(draw: ImageDraw.ImageDraw) -> None:
    peaks = random.randint(2, 3)
    base_y = HEIGHT - 20
    for i in range(peaks):
        peak_x = WIDTH * random.uniform(0.25, 0.85)
        peak_y = HEIGHT * random.uniform(0.15, 0.45)
        spread = WIDTH * random.uniform(0.28, 0.42)
        opacity = 45 + i * 20
        draw.polygon([
            (peak_x - spread, base_y),
            (peak_x, peak_y),
            (peak_x + spread, base_y),
        ], fill=(255, 255, 255, opacity))


def _draw_candles(draw: ImageDraw.ImageDraw) -> None:
    n = random.randint(14, 20)
    margin = 60
    gap = 10
    body_w = (WIDTH - 2 * margin - gap * (n - 1)) / n
    mid = HEIGHT / 2
    level = mid
    for i in range(n):
        move = random.uniform(-30, 45)  # slight upward drift on average
        new_level = max(60, min(HEIGHT - 60, level - move))
        top = min(level, new_level)
        bottom = max(level, new_level)
        x0 = margin + i * (body_w + gap)
        x1 = x0 + body_w
        wick_x = (x0 + x1) / 2
        draw.line([wick_x, top - 14, wick_x, bottom + 14], fill=(255, 255, 255, 70), width=2)
        draw.rectangle([x0, top, x1, bottom], fill=(255, 255, 255, 80))
        level = new_level


def _draw_arc(draw: ImageDraw.ImageDraw) -> None:
    cx = WIDTH * random.uniform(0.55, 0.8)
    cy = HEIGHT * random.uniform(0.75, 0.95)
    for i, r in enumerate([260, 190, 130]):
        opacity = 35 + i * 15
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, opacity), width=3)
    r = 70
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 90))
    draw.line([0, cy, WIDTH, cy], fill=(255, 255, 255, 40), width=2)


def _draw_dots(draw: ImageDraw.ImageDraw) -> None:
    n = random.randint(6, 9)
    margin = 80
    xs = np.linspace(margin, WIDTH - margin, n)
    trend = sorted(random.uniform(0.15, 0.9) for _ in range(n))
    pts = []
    for x, t in zip(xs, trend):
        jitter = random.uniform(-0.06, 0.06)
        y = HEIGHT - 40 - max(0.0, min(1.0, t + jitter)) * (HEIGHT - 100)
        pts.append((x, y))
    draw.line(pts, fill=(255, 255, 255, 90), width=4)
    for x, y in pts:
        draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(255, 255, 255, 130))


_MOTIF_FUNCS = {
    "bars": _draw_bars,
    "arrow": _draw_arrow,
    "summit": _draw_summit,
    "candles": _draw_candles,
    "arc": _draw_arc,
    "dots": _draw_dots,
}


def _procedural_background() -> Image.Image:
    """
    The original purely-local generator: a randomized two-color gradient plus
    one abstract "growth" motif. Used only as a fallback when a live photo
    can't be fetched (see _fetch_random_photo), so an offline/blocked network
    still produces a nice-looking image instead of none at all.
    """
    c1, c2 = _random_gradient_colors()
    direction = random.choice(["horizontal", "vertical", "diagonal"])
    base = _gradient_background(c1, c2, direction).convert("RGBA")

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    motif = random.choice(MOTIFS)
    _MOTIF_FUNCS[motif](draw)

    return Image.alpha_composite(base, overlay).convert("RGB")


def _fetch_random_photo() -> "Image.Image | None":
    """
    A random real photo from Lorem Picsum (Unsplash-backed, free, no API
    key -- see https://picsum.photos), for "a different beautiful photo from
    anywhere in the world" on every send. Returns None on ANY failure
    (offline, blocked host, timeout, bad response, corrupt image) -- the
    caller falls back to _procedural_background() instead, so a flaky photo
    host can only ever make the image plainer, never break the send.
    """
    try:
        # ?random=<n> busts caching so consecutive sends don't repeat the same photo.
        url = f"https://picsum.photos/{WIDTH}/{HEIGHT}?random={random.randint(1, 10_000_000)}"
        resp = requests.get(url, timeout=PHOTO_FETCH_TIMEOUT)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        if img.size != (WIDTH, HEIGHT):
            img = img.resize((WIDTH, HEIGHT))
        return img
    except Exception:  # noqa: BLE001 - any failure here just falls back to the local generator
        return None


def generate_image_bytes() -> bytes:
    """
    Returns raw JPEG bytes for the email header image: a real random photo
    if one could be fetched, otherwise the procedural gradient fallback.
    No text is drawn onto it -- the quote is a separate HTML block in the
    email body (see notify.py), styled and positioned there instead.
    """
    photo = _fetch_random_photo()
    base = photo if photo is not None else _procedural_background()

    buf = io.BytesIO()
    base.convert("RGB").save(buf, format="JPEG", quality=87)
    return buf.getvalue()
