"""
Genera los iconos de la app (PWA, Windows .ico y macOS .icns) a partir del
logotipo "ac2". Ejecutar:  python scripts/make_icons.py   (requiere Pillow)
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
NAVY = (7, 16, 30, 255)
BLUE = (1, 176, 245, 255)
WHITE = (255, 255, 255, 255)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def draw_icon(size: int, rounded: bool = True, padding: float = 0.0) -> Image.Image:
    scale = 4  # supermuestreo para bordes suaves
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.225), fill=NAVY)
    else:
        d.rectangle((0, 0, s, s), fill=NAVY)

    inner = s * (1 - padding * 2)
    f = font(int(inner * 0.42))
    parts = [("ac", WHITE), ("2", BLUE)]
    widths = [d.textlength(t, font=f) for t, _ in parts]
    total = sum(widths) - inner * 0.02
    x = (s - total) / 2
    ascent, descent = f.getmetrics()
    y = (s - ascent) / 2 - descent * 0.15 - s * 0.045
    for (text, color), w in zip(parts, widths):
        d.text((x, y), text, font=f, fill=color)
        x += w - inner * 0.02
    # subrayado de marca
    bar_w, bar_h = inner * 0.36, inner * 0.045
    d.rounded_rectangle(((s - bar_w) / 2, s * 0.72, (s + bar_w) / 2, s * 0.72 + bar_h), radius=int(bar_h / 2), fill=BLUE)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    web = ROOT / "web" / "icons"
    assets = ROOT / "app" / "assets"
    web.mkdir(parents=True, exist_ok=True)
    assets.mkdir(parents=True, exist_ok=True)

    draw_icon(192).save(web / "icon-192.png")
    draw_icon(512).save(web / "icon-512.png")
    draw_icon(512, rounded=False, padding=0.1).save(web / "icon-maskable-512.png")
    draw_icon(180, rounded=False).convert("RGB").save(web / "apple-touch-icon.png")  # iOS redondea solo

    big = draw_icon(1024)
    big.save(assets / "icon-1024.png")
    big.save(assets / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    big.save(assets / "icon.icns")
    print("Iconos generados en web/icons y app/assets")


if __name__ == "__main__":
    main()
