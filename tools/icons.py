"""Draws the Hush toolbar icons (on/off) at every size Chrome asks for."""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "src" / "icons"
S = 512  # draw large, downsample for crisp edges

PALETTES = {
    "on": {"tile": "#10272B", "mark": "#F3B23C"},
    "off": {"tile": "#3A4547", "mark": "#9AA6A4"},
}


def draw(tile: str, mark: str) -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=S * 0.24, fill=tile)
    # A solid disc with a bar cut through it: the "quiet" sign.
    pad = S * 0.18
    d.ellipse((pad, pad, S - pad, S - pad), fill=mark)
    bar_h = S * 0.12
    d.rounded_rectangle(
        (S * 0.30, S / 2 - bar_h / 2, S * 0.70, S / 2 + bar_h / 2),
        radius=bar_h / 2,
        fill=tile,
    )
    return img


OUT.mkdir(parents=True, exist_ok=True)
for name, p in PALETTES.items():
    big = draw(p["tile"], p["mark"])
    for size in (16, 32, 48, 128):
        big.resize((size, size), Image.LANCZOS).save(OUT / f"{name}-{size}.png")
print("icons written to", OUT)
