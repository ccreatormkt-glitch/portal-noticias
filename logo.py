"""Logo do PB Minuto: cronômetro com 'PB' + palavra MINUTO.

  python logo.py   -> gera brand/logo_horizontal.png, brand/logo_escuro.png e brand/avatar.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import BRAND_COLOR

ROOT = Path(__file__).parent
FONT_DIR = ROOT / "fonts"
NAVY = (9, 20, 44)
ACCENT = tuple(int(BRAND_COLOR.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))  # cor da marca
WHITE = (255, 255, 255)
SS = 4  # superamostragem para bordas suaves


def _f(weight, size):
    return ImageFont.truetype(str(FONT_DIR / f"Inter-{weight}.otf"), size)


def symbol(size: int, fundo=None) -> Image.Image:
    """Monograma: quadrado vermelho de cantos suaves com PB em branco."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.2), fill=ACCENT)
    d.text((s / 2, s / 2 + s * 0.03), "PB", font=_f("Black", int(s * 0.52)), fill=WHITE, anchor="mm")
    return img.resize((size, size), Image.LANCZOS)


def lockup(height: int, escuro=True) -> Image.Image:
    """Monograma + MINUTO (branco no fundo escuro, grafite no claro)."""
    cor = WHITE if escuro else (17, 24, 39)
    f = _f("Bold", int(height * 0.44))
    gap = int(height * 0.24)
    w = height + gap + int(f.getlength("MINUTO")) + 6
    img = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    img.alpha_composite(symbol(height), (0, 0))
    ImageDraw.Draw(img).text((height + gap, height / 2 + height * 0.03), "MINUTO", font=f, fill=cor, anchor="lm")
    return img


def avatar(size=1080) -> Image.Image:
    """Foto do perfil: fundo vermelho, PB grande e MINUTO pequeno (centralizado para o corte redondo)."""
    img = Image.new("RGBA", (size, size), ACCENT + (255,))
    d = ImageDraw.Draw(img)
    d.text((size / 2, size * 0.47), "PB", font=_f("Black", int(size * 0.40)), fill=WHITE, anchor="mm")
    d.text((size / 2, size * 0.70), "MINUTO", font=_f("Bold", int(size * 0.10)), fill=WHITE, anchor="mm")
    return img


if __name__ == "__main__":
    out = ROOT / "brand"
    out.mkdir(exist_ok=True)
    avatar().convert("RGB").save(out / "avatar.png")
    lk = lockup(240, escuro=True)
    bg = Image.new("RGBA", (lk.width + 160, lk.height + 160), NAVY + (255,))
    bg.alpha_composite(lk, (80, 80))
    bg.save(out / "logo_escuro.png")
    lk2 = lockup(240, escuro=False)
    bg2 = Image.new("RGBA", (lk2.width + 160, lk2.height + 160), (255, 255, 255, 255))
    bg2.alpha_composite(lk2, (80, 80))
    bg2.save(out / "logo_claro.png")
    print("logos em", out)
