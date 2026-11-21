"""Marca do PB Minuto refeita com os parâmetros de design do g1 (layout.py).

Letra: Inter Display (regra do PB Minuto: só Inter em tudo, ver layout.py). Do g1 vêm o contraste
de pesos do cabeçalho (nome forte + texto leve), o espaço entre letras dos títulos, o canto de 12 sobre 48 e a proporção da logo na barra
vermelha. O desenho é do PB Minuto: monograma PB num quadrado branco + MINUTO.

  python logo.py   -> gera brand/avatar.png (foto do perfil), brand/logo_vermelho.png,
                      brand/logo_branco.png e brand/barra.png (barra do topo)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import layout as L

ROOT = Path(__file__).parent
FONT_DIR = ROOT / "fonts"
VERMELHO = L.MARCA["vermelho"]
VERMELHO_2 = L.MARCA["vermelho_2"]
WHITE = L.MARCA["branco"]
SS = 4  # superamostragem para bordas suaves

RAIO = L.G1["raio"] / L.G1["barra"]["logo"]   # canto 12 numa logo de 48 = 25% da altura
TRACK_PB = L.em("destaque")                    # PB tão justo quanto a manchete do g1 (-0,045 em)
PESO_PB, PESO_NOME = 800, 700                  # monograma extra-negrito, nome negrito
TRACK_NOME = 0.02                              # caixa-alta pede um pouco de ar


def _f(size, peso=800):
    return ImageFont.truetype(str(FONT_DIR / L.FONTE_LOGO[peso]), size)


def _texto(d, xy, texto, f, fill, track, anchor):
    """Texto com espaço entre letras (em "em"), centrado/ancorado como o Pillow faria."""
    larg = f.getlength(texto) + track * f.size * (len(texto) - 1)
    x, y = xy
    if anchor[0] == "m":
        x -= larg / 2
    for i, ch in enumerate(texto):
        d.text((x + f.getlength(texto[:i]) + track * f.size * i, y), ch, font=f, fill=fill,
               anchor="l" + anchor[1])
    return larg


def symbol(size: int, invertido=False) -> Image.Image:
    """Monograma: quadrado branco de canto 25% com PB vermelho (ou o inverso)."""
    s = size * SS
    fundo, letra = (VERMELHO, WHITE) if invertido else (WHITE, VERMELHO)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * RAIO), fill=fundo)
    _texto(d, (s / 2, s / 2 + s * 0.015), "PB", _f(int(s * 0.56), PESO_PB), letra, TRACK_PB, "mm")
    return img.resize((size, size), Image.LANCZOS)


def lockup(height: int, fundo_vermelho=True) -> Image.Image:
    """Monograma + MINUTO na altura das maiúsculas do PB. No vermelho: quadrado e nome brancos."""
    cor = WHITE if fundo_vermelho else VERMELHO
    f = _f(int(height * 0.50), PESO_NOME)
    gap = int(height * 0.24)
    larg_nome = f.getlength("MINUTO") + TRACK_NOME * f.size * 5
    w = height + gap + int(larg_nome) + 4
    img = Image.new("RGBA", (w * SS, height * SS), (0, 0, 0, 0))
    img.alpha_composite(symbol(height * SS, invertido=not fundo_vermelho), (0, 0))
    d = ImageDraw.Draw(img)
    f_ss = _f(int(height * 0.50) * SS, PESO_NOME)
    _texto(d, ((height + gap) * SS, height * SS / 2 + height * SS * 0.015), "MINUTO", f_ss, cor,
           TRACK_NOME, "lm")
    return img.resize((w, height), Image.LANCZOS)


def barra(largura: int, altura: int, logo_h: int, centro_y: int, borda: int = 0) -> Image.Image:
    """Barra vermelha do topo (cabeçalho no padrão do g1) com a logo centralizada."""
    img = Image.new("RGBA", (largura, altura), VERMELHO + (255,))
    if borda:
        ImageDraw.Draw(img).rectangle((0, altura - borda, largura, altura), fill=VERMELHO_2)
    lk = lockup(logo_h, fundo_vermelho=True)
    img.alpha_composite(lk, ((largura - lk.width) // 2, centro_y - logo_h // 2))
    return img


def avatar(size=1080) -> Image.Image:
    """Foto do perfil: fundo vermelho, monograma PB grande e MINUTO (centrado para o corte redondo)."""
    img = Image.new("RGBA", (size, size), VERMELHO + (255,))
    d = ImageDraw.Draw(img)
    s = int(size * 0.40)
    img.alpha_composite(symbol(s), ((size - s) // 2, int(size * 0.20)))
    f = _f(int(size * 0.105), PESO_NOME)
    _texto(d, (size / 2, size * 0.735), "MINUTO", f, WHITE, TRACK_NOME, "mm")
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
    b = L.barra(L.FORMATOS["reels"])
    barra(1080, b["fim"], b["logo"], b["centro"], b["borda"]).save(out / "barra.png")
    print("logos em", out)
