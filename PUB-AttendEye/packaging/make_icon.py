"""Generates packaging/attendeye.ico (and a 512px PNG) from the app's logo mark. Run: python packaging/make_icon.py"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
S = 1024  # draw large, downsample for smooth edges


def draw() -> Image.Image:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.22), fill="#0b1f3a")
    u = S / 32
    teal, blue = "#2dd4bf", "#8fb4e8"
    c = S / 2
    d.ellipse((c - 9 * u, c - 9 * u, c + 9 * u, c + 9 * u), outline=teal, width=int(2.4 * u))
    d.ellipse((c - 3.2 * u, c - 3.2 * u, c + 3.2 * u, c + 3.2 * u), fill=teal)
    w = int(2.2 * u)
    L = 7 * u
    for (x, y, sx, sy) in ((4.5, 4.5, 1, 1), (27.5, 4.5, -1, 1), (4.5, 27.5, 1, -1), (27.5, 27.5, -1, -1)):
        x, y = x * u, y * u
        d.line((x, y, x + sx * L, y), fill=blue, width=w)
        d.line((x, y, x, y + sy * L), fill=blue, width=w)
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=blue)
        d.ellipse((x + sx * L - w / 2, y - w / 2, x + sx * L + w / 2, y + w / 2), fill=blue)
        d.ellipse((x - w / 2, y + sy * L - w / 2, x + w / 2, y + sy * L + w / 2), fill=blue)
    return im


if __name__ == "__main__":
    im = draw()
    im.resize((512, 512), Image.LANCZOS).save(OUT / "attendeye.png")
    im.save(OUT / "attendeye.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", OUT / "attendeye.ico")
