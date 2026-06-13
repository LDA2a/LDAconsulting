"""Genere une miniature YouTube 1280x720 pour 'Le langage de Dieu'."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
BASE = HERE / "thumb_base.png"
OUT_PNG = HERE / "output" / "miniature_youtube.png"
OUT_JPG = HERE / "output" / "miniature_youtube.jpg"
W, H = 1280, 720

FONTS = {
    "title": [r"C:\Windows\Fonts\georgiab.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
    "ital":  [r"C:\Windows\Fonts\georgiai.ttf", r"C:\Windows\Fonts\ariali.ttf"],
}


def font(kind, size):
    for p in FONTS[kind]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def centered(draw, text, fnt, cy, fill, stroke=0, stroke_fill=(0, 0, 0),
             shadow=None):
    bb = draw.textbbox((0, 0), text, font=fnt, stroke_width=stroke)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    x = (W - tw) / 2 - bb[0]
    y = cy - th / 2 - bb[1]
    if shadow:
        dx, dy, scol = shadow
        draw.text((x + dx, y + dy), text, font=fnt, fill=scol,
                  stroke_width=stroke, stroke_fill=scol)
    draw.text((x, y), text, font=fnt, fill=fill,
              stroke_width=stroke, stroke_fill=stroke_fill)


img = Image.open(BASE).convert("RGB").resize((W, H))

# 1) Assombrissement global doux pour faire ressortir le texte
overlay = Image.new("RGB", (W, H), (0, 0, 0))
img = Image.blend(img, overlay, 0.32)

# 2) Vignette + degrade bas (alpha) pour ancrer le titre
grad = Image.new("L", (1, H), 0)
for y in range(H):
    t = y / H
    grad.putpixel((0, y), int(150 * (t ** 1.6)))   # plus sombre vers le bas
grad = grad.resize((W, H))
dark = Image.new("RGB", (W, H), (0, 0, 0))
img = Image.composite(dark, img, grad)

draw = ImageDraw.Draw(img)

# 3) Kicker en haut
kick = font("ital", 40)
centered(draw, "un voyage au coeur du silence qui parle", kick, 92,
         fill=(235, 222, 190), shadow=(2, 2, (0, 0, 0)))

# 4) Titre principal (2 lignes)
ftitle = font("title", 150)
centered(draw, "LE LANGAGE", ftitle, 330, fill=(255, 255, 255),
         stroke=3, stroke_fill=(20, 12, 0), shadow=(4, 5, (0, 0, 0)))
centered(draw, "DE DIEU", ftitle, 480, fill=(255, 255, 255),
         stroke=3, stroke_fill=(20, 12, 0), shadow=(4, 5, (0, 0, 0)))

# 5) Filet dore + tagline
cy_line = 575
draw.line([(W / 2 - 170, cy_line), (W / 2 + 170, cy_line)],
          fill=(220, 180, 110), width=3)
ftag = font("ital", 50)
centered(draw, "Et si Dieu te parlait... sans un seul mot ?", ftag, 632,
         fill=(245, 230, 200), shadow=(2, 2, (0, 0, 0)))

img.save(OUT_PNG)
img.save(OUT_JPG, quality=90)
print(f"Miniature -> {OUT_JPG}")
