# -*- coding: utf-8 -*-
"""Genere le logo/pfp DEMOS (embleme classique) en PNG haute resolution."""
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SCALE = 2
S = 1024 * SCALE
CX = S // 2

def sc(v):
    return int(round(v * SCALE))

def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))

INK_IN = (28, 34, 46)
INK_OUT = (13, 16, 22)
GOLD = (201, 162, 75)
GOLD_L = (232, 202, 122)
GOLD_DIM = (165, 136, 78)
CREAM = (240, 228, 200)

FONT_DIR = Path("C:/Windows/Fonts")
f_demos = ImageFont.truetype(str(FONT_DIR / "georgiab.ttf"), sc(96))
f_sub = ImageFont.truetype(str(FONT_DIR / "arial.ttf"), sc(25))

img = Image.new("RGBA", (S, S), INK_OUT + (255,))
d = ImageDraw.Draw(img)

# --- Fond : degrade radial profond (centre plus clair) ---
steps = 720
Rg = sc(760)
for i in range(steps):
    t = i / steps
    r = Rg * (1 - t)
    col = lerp(INK_OUT, INK_IN, t)
    d.ellipse([CX - r, CX - r, CX + r, CX + r], fill=col + (255,))

def ring(radius, width, color):
    r = sc(radius)
    d.ellipse([CX - r, CX - r, CX + r, CX + r], outline=color + (255,),
              width=sc(width))

# --- Anneaux exterieurs ---
ring(498, 3, GOLD)
ring(450, 1.5, GOLD_DIM)

# --- Ceinture facon pellicule (points dores) ---
dots, rdot = 76, sc(4)
for k in range(dots):
    a = 2 * math.pi * k / dots
    px = CX + sc(474) * math.cos(a)
    py = CX + sc(474) * math.sin(a)
    d.ellipse([px - rdot, py - rdot, px + rdot, py + rdot], fill=GOLD + (255,))

# --- Bouton lecture cercle (haut, double anneau) ---
PCY = sc(352)
d.ellipse([CX - sc(108), PCY - sc(108), CX + sc(108), PCY + sc(108)],
          outline=GOLD_DIM + (255,), width=sc(2))
d.ellipse([CX - sc(96), PCY - sc(96), CX + sc(96), PCY + sc(96)],
          outline=GOLD + (255,), width=sc(7))
tri = [(CX - sc(30), PCY - sc(52)), (CX - sc(30), PCY + sc(52)),
       (CX + sc(64), PCY)]
d.polygon(tri, fill=CREAM + (255,))

# --- Typographie : DEMOS (suivi de lettres) ---
def tracked(text, font, baseline_y, spacing, fill):
    widths = [d.textlength(ch, font=font) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = CX - total / 2
    for ch, w in zip(text, widths):
        d.text((x, baseline_y), ch, font=font, fill=fill + (255,), anchor="ls")
        x += w + spacing

tracked("DEMOS", f_demos, sc(512), sc(16), GOLD_L)
tracked("HISTOIRE · PHILOSOPHIE · RÉCITS", f_sub, sc(560), sc(2), GOLD_DIM)

# --- Filet ornemental sous le sous-titre ---
d.line([CX - sc(150), sc(596), CX + sc(150), sc(596)], fill=GOLD + (255,),
       width=sc(1))
diam = sc(7)
d.polygon([(CX, sc(596) - diam), (CX + diam, sc(596)), (CX, sc(596) + diam),
           (CX - diam, sc(596))], fill=GOLD + (255,))

# --- Deux brins de laurier (style medaille) ---
def leaf(angle_deg, color, w=34, h=13):
    tmp = Image.new("RGBA", (sc(w), sc(h)), (0, 0, 0, 0))
    ld = ImageDraw.Draw(tmp)
    ld.ellipse([sc(2), sc(1), sc(w) - sc(2), sc(h) - sc(1)], fill=color + (255,))
    return tmp.rotate(angle_deg, expand=True, resample=Image.BICUBIC)

def place_leaf(x, y, rot, col, w=34, h=13):
    lf = leaf(rot, col, w, h)
    img.alpha_composite(lf, (sc(x) - lf.width // 2, sc(y) - lf.height // 2))

def sprig(sign):
    stem = [(CX, sc(720)), (CX + sign * sc(30), sc(696)),
            (CX + sign * sc(54), sc(668)), (CX + sign * sc(72), sc(638))]
    d.line(stem, fill=GOLD + (255,), width=sc(2), joint="curve")
    base_rot = 52 if sign > 0 else 128
    pos = [(34, 702), (56, 680), (74, 654), (84, 626)]
    for i, (dx, y) in enumerate(pos):
        col = GOLD if i % 2 == 0 else GOLD_L
        place_leaf(CX // SCALE + sign * dx if False else 512 + sign * dx, y,
                   base_rot, col, w=30 - i * 2, h=12)
        place_leaf(512 + sign * (dx - 14), y + 12, base_rot - sign * 26,
                   GOLD_DIM, w=22, h=9)
    place_leaf(512 + sign * 88, 614, 90, GOLD_L, w=26, h=11)

sprig(1)
sprig(-1)
d.ellipse([CX - sc(7), sc(722) - sc(7), CX + sc(7), sc(722) + sc(7)],
          fill=GOLD_L + (255,))

# --- Reduction pour des bords nets ---
out = img.resize((1024, 1024), Image.LANCZOS)
dest = Path(__file__).parent / "demos_logo.png"
out.save(dest)
# Version 512 pour avatar
out.resize((512, 512), Image.LANCZOS).save(Path(__file__).parent / "demos_logo_512.png")
print("OK ->", dest)
