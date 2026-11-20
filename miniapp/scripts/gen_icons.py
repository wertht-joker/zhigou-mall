from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "src" / "static"
OUT.mkdir(parents=True, exist_ok=True)

NORMAL = (138, 143, 153, 255)
ACTIVE = (225, 37, 27, 255)
SIZE = 81


def canvas():
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def draw_home(color):
    image, d = canvas()
    d.line([(12, 40), (40, 15), (69, 40)], fill=color, width=6, joint="curve")
    d.rounded_rectangle([21, 38, 60, 68], radius=4, outline=color, width=5)
    d.rounded_rectangle([35, 52, 46, 68], radius=3, outline=color, width=4)
    return image


def draw_cart(color):
    image, d = canvas()
    d.line([(10, 16), (20, 16), (29, 54), (63, 54)], fill=color, width=5, joint="curve")
    d.line([(34, 32), (68, 32), (61, 50), (31, 50)], fill=color, width=5, joint="curve")
    d.ellipse([30, 61, 40, 71], outline=color, width=4)
    d.ellipse([54, 61, 64, 71], outline=color, width=4)
    return image


def draw_orders(color):
    image, d = canvas()
    d.rounded_rectangle([19, 13, 62, 68], radius=6, outline=color, width=5)
    d.line([(29, 29), (52, 29)], fill=color, width=4)
    d.line([(29, 42), (52, 42)], fill=color, width=4)
    d.line([(29, 54), (43, 54)], fill=color, width=4)
    return image


def draw_profile(color):
    image, d = canvas()
    d.ellipse([27, 12, 54, 39], outline=color, width=5)
    d.arc([14, 39, 67, 86], start=190, end=350, fill=color, width=5)
    return image


for name, renderer in {
    "tab-home": draw_home,
    "tab-cart": draw_cart,
    "tab-orders": draw_orders,
    "tab-profile": draw_profile,
}.items():
    renderer(NORMAL).save(OUT / f"{name}.png")
    renderer(ACTIVE).save(OUT / f"{name}-active.png")

print("icons generated:", len(list(OUT.glob("tab-*.png"))))
