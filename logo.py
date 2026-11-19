"""Logo do PB Minuto na identidade vermelho e branco (fonte Inter, a da 1ª postagem).

  python logo.py   -> gera brand/avatar.png (foto do perfil), brand/logo_vermelho.png e brand/logo_branco.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import BRAND_COLOR

ROOT = Path(__file__).parent
FONT_DIR = ROOT / "fonts"
VERMELHO = tuple(int(BRAND_COLOR.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
WHITE = (255, 255, 255)
SS = 4  # superamostragem para bordas suaves


def _f(size, peso="Black"):
    """Inter, a fonte da 1ª postagem (padrão de toda a marca)."""
    return ImageFont.truetype(str(FONT_DIR / f"Inter-{peso}.otf"), size)


def symbol(size: int, invertido=False) -> Image.Image:
    """Monograma: quadrado de cantos suaves com PB (branco com PB vermelho, ou o inverso)."""
    s = size * SS
    fundo, letra = (VERMELHO, WHITE) if invertido else (WHITE, VERMELHO)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=fundo)
    d.text((s / 2, s / 2 + s * 0.02), "PB", font=_f(int(s * 0.50)), fill=letra, anchor="mm")
    return img.resize((size, size), Image.LANCZOS)


def lockup(height: int, fundo_vermelho=True) -> Image.Image:
    """Monograma + MINUTO. No fundo vermelho: quadrado branco e MINUTO branco."""
    cor = WHITE if fundo_vermelho else VERMELHO
    f = _f(int(height * 0.46), "Bold")
    gap = int(height * 0.22)
    w = height + gap + int(f.getlength("MINUTO")) + 6
    img = Image.new("RGBA", (w, height), (0, 0, 0, 0))
    img.alpha_composite(symbol(height, invertido=not fundo_vermelho), (0, 0))
    ImageDraw.Draw(img).text((height + gap, height / 2 + height * 0.02), "MINUTO", font=f, fill=cor, anchor="lm")
    return img


def avatar(size=1080) -> Image.Image:
    """Foto do perfil: fundo vermelho, PB grande e MINUTO em branco (centralizado para o corte redondo)."""
    img = Image.new("RGBA", (size, size), VERMELHO + (255,))
    d = ImageDraw.Draw(img)
    d.text((size / 2, size * 0.45), "PB", font=_f(int(size * 0.42)), fill=WHITE, anchor="mm")
    d.text((size / 2, size * 0.69), "MINUTO", font=_f(int(size * 0.11), "Bold"), fill=WHITE, anchor="mm")
    return img


if __name__ == "__main__":
    out = ROOT / "brand"
    out.mkdir(exist_ok=True)
    avatar().convert("RGB").save(out / "avatar.png")
    for nome, verm in (("logo_vermelho.png", True), ("logo_branco.png", False)):
        lk = lockup(240, fundo_vermelho=verm)
        bg = Image.new("RGBA", (lk.width + 160, lk.height + 160), (VERMELHO if verm else WHITE) + (255,))
        bg.alpha_composite(lk, (80, 80))
        bg.save(out / nome)
    print("logos em", out)
