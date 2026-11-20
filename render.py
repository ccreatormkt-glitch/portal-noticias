"""Desenha os cards do portal (1080x1350, formato 4:5 do feed).

Princípios (HIG da Apple aplicados a card editorial):
- Clareza: uma mensagem por lâmina; hierarquia por peso e tamanho, nunca por enfeite.
- Deferência: o conteúdo é o herói; a moldura é discreta.
- Profundidade: camadas suaves (brilho, cartões) em vez de linhas e caixas.
- Consistência: grade de 8 px, mesmas margens, mesmos raios concêntricos em todas as lâminas.

Lâmina 1 (capa): chapéu + manchete + linha fina.
Lâmina 2 (detalhes): resumo + "O que você precisa saber", em cartões sobre fundo claro.
Toda a arte é gerada aqui (ou é ilustração de IA). Nunca usamos foto de outro veículo.
"""
import datetime as dt
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import BRAND_COLOR, FONT_DIR, PORTAL_HANDLE, PORTAL_NAME, TIMEZONE

W, H = 1080, 1350
M = 80                    # margem lateral (grade de 8)
R_CARD, R_CHIP = 40, 999  # raios: cartão / cápsula

# cores
NAVY = (9, 20, 44)
INK = (17, 24, 39)                 # texto principal em fundo claro
INK_2 = (75, 85, 99)               # texto secundário em fundo claro
INK_3 = (142, 142, 147)            # terciário (cinza do sistema)
BG_LIGHT = (242, 242, 247)         # fundo agrupado (systemGray6)
SEP = (229, 229, 234)              # separador
WHITE = (255, 255, 255)
SOFT = (200, 210, 228)             # texto secundário em fundo escuro
ACCENT = tuple(int(BRAND_COLOR.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))  # cor da marca (padrão: vermelho #DC2626)
URGENTE = (220, 38, 38)            # vermelho de urgência (#DC2626, paleta News/Media)

EDITORIA_COR = {
    "CIDADE": (10, 132, 255), "POLÍCIA": (255, 69, 58), "POLÍTICA": (175, 82, 222),
    "SAÚDE": (48, 209, 88), "EMPREGO": (255, 159, 10), "CONCURSO": (255, 159, 10),
    "TRÂNSITO": (255, 159, 10), "CLIMA": (100, 210, 255), "ESPORTE": (48, 209, 88),
    "CULTURA": (255, 55, 95), "ECONOMIA": (52, 199, 89), "EDUCAÇÃO": (94, 92, 230),
    "SERVIÇO": (90, 200, 250), "BRASIL": (142, 142, 147), "PARAÍBA": (10, 132, 255),
}
# versão mais escura da cor, para texto/ícones sobre fundo claro (contraste AA)
EDITORIA_ESCURA = {
    "CIDADE": (0, 95, 204), "POLÍCIA": (196, 30, 30), "POLÍTICA": (122, 46, 168),
    "SAÚDE": (20, 128, 60), "EMPREGO": (178, 98, 0), "CONCURSO": (178, 98, 0),
    "TRÂNSITO": (178, 98, 0), "CLIMA": (0, 112, 160), "ESPORTE": (20, 128, 60),
    "CULTURA": (196, 22, 70), "ECONOMIA": (20, 128, 60), "EDUCAÇÃO": (64, 61, 196),
    "SERVIÇO": (0, 112, 160), "BRASIL": (88, 88, 94), "PARAÍBA": (0, 95, 204),
}

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# textos fixos (revisados: verbo no início, curtos, iguais em todo lugar)
TXT_CTA_CARROSSEL = "Deslize para ler"
TXT_CTA_UNICO = "Detalhes na legenda"
TXT_LISTA = {"noticia": "Principais pontos", "o_que_se_sabe": "O que se sabe",
             "entenda": "Entenda", "servico": "Veja como fazer"}

_fonts = {}


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(str(FONT_DIR / f"Inter-{weight}.otf"), size)
    return _fonts[key]


def hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def cor(card, escura=False):
    tabela = EDITORIA_ESCURA if escura else EDITORIA_COR
    return tabela.get(card.get("chapeu", ""), hex_rgb(BRAND_COLOR))


def clean(text: str) -> str:
    for a, b in {"“": '"', "”": '"', "‘": "'", "’": "'", "…": "...", "–": "-", "—": "-"}.items():
        text = text.replace(a, b)
    return " ".join(text.split())


def wrap(text, f, max_w) -> list:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return balance(lines, f, max_w)


def balance(lines, f, max_w):
    """Evita palavra sozinha na última linha (viúva) puxando uma palavra de cima."""
    if len(lines) >= 2 and len(lines[-1].split()) == 1:
        prev = lines[-2].split()
        if len(prev) > 2:
            cand_last = prev[-1] + " " + lines[-1]
            if f.getlength(cand_last) <= max_w:
                lines[-2], lines[-1] = " ".join(prev[:-1]), cand_last
    return lines


def fit(text, weight, sizes, max_w, max_lines):
    for size in sizes:
        f = font(weight, size)
        lines = wrap(text, f, max_w)
        if len(lines) <= max_lines:
            return f, lines
    f = font(weight, sizes[-1])
    lines = wrap(text, f, max_w)[:max_lines]
    lines[-1] = lines[-1].rstrip(" ,.;:") + "..."
    return f, lines


def primeira_frase(texto: str, limite=120) -> str:
    texto = clean(texto)
    frase = texto.split(". ")[0].rstrip(".")
    return frase + "." if 20 <= len(frase) <= limite else ""


def stamp():
    n = dt.datetime.now(ZoneInfo(TIMEZONE))
    return f"{n.day} {MESES[n.month - 1]}  ·  {n.hour:02d}h{n.minute:02d}"


# ------------------------------------------------------------------ elementos
def logo(img, x, y, altura=72, escuro=True):
    """Cola o logo oficial (cronômetro + MINUTO) gerado por logo.py."""
    import logo as _logo
    key = (altura, escuro)
    if key not in _logo_cache:
        _logo_cache[key] = _logo.lockup(altura, escuro)
    img.alpha_composite(_logo_cache[key], (int(x), int(y)))


_logo_cache = {}

ICONE = {  # editoria -> ícone (Material Icons, licença Apache 2.0)
    "CIDADE": "location_city", "POLÍCIA": "local_police", "POLÍTICA": "account_balance",
    "SAÚDE": "local_hospital", "EMPREGO": "work", "CONCURSO": "assignment", "TRÂNSITO": "traffic",
    "CLIMA": "thunderstorm", "ESPORTE": "sports_soccer", "CULTURA": "theater_comedy",
    "ECONOMIA": "trending_up", "EDUCAÇÃO": "school", "SERVIÇO": "campaign", "BRASIL": "flag",
    "PARAÍBA": "location_city",
}


def icone(nome: str, size: int):
    import json as _json
    if "_cp" not in _icon_cache:
        _icon_cache["_cp"] = {}
        try:
            path = FONT_DIR / "MaterialIcons-Regular.json"
            if path.exists():
                _icon_cache["_cp"] = _json.loads(path.read_text())
        except Exception:
            pass
    cp = _icon_cache["_cp"].get(nome)
    ch = chr(int(cp, 16)) if cp else nome
    f = ImageFont.truetype(str(FONT_DIR / "MaterialIcons-Regular.ttf"), size)
    return f, ch


_icon_cache = {}


def capsula(d, x, y, texto, fundo, frente=WHITE, size=26, peso="Bold", h=56, borda=None):
    f = font(peso, size)
    w = int(f.getlength(texto)) + 48
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=fundo, outline=borda,
                        width=2 if borda else 0)  # fundo=None -> só contorno
    d.text((x + w / 2, y + h / 2 + 1), texto, font=f, fill=frente, anchor="mm")
    return w


def capsula_dir(d, x_dir, y, texto, **kw):
    f = font(kw.get("peso", "Bold"), kw.get("size", 26))
    w = int(f.getlength(texto)) + 48
    capsula(d, x_dir - w, y, texto, **kw)
    return w


def pin(d, x, y, c, bg):
    d.ellipse((x, y, x + 24, y + 24), fill=c)
    d.polygon([(x + 3, y + 17), (x + 21, y + 17), (x + 12, y + 34)], fill=c)
    d.ellipse((x + 8, y + 8, x + 16, y + 16), fill=bg)


def relogio(img, cx, cy, raio, c):
    """Motivo da marca: anéis concêntricos com um ponteiro (o 'minuto')."""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(lay)
    for i, r in enumerate(range(raio, 80, -96)):
        alpha = 34 - i * 5
        if alpha <= 6:
            break
        g.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 255, 255, alpha), width=2)
    for k in range(60):  # marcas dos minutos no anel externo
        a = math.radians(k * 6)
        r1, r2 = raio - (22 if k % 5 == 0 else 10), raio
        g.line((cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a)),
               fill=(255, 255, 255, 40 if k % 5 == 0 else 18), width=3 if k % 5 == 0 else 2)
    m = dt.datetime.now(ZoneInfo(TIMEZONE)).minute
    a = math.radians(m * 6 - 90)
    g.line((cx, cy, cx + (raio - 60) * math.cos(a), cy + (raio - 60) * math.sin(a)), fill=c + (150,), width=8)
    g.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), fill=c + (200,))
    img.alpha_composite(lay)


def fundo_escuro(card, image_path=None):
    c = cor(card)
    if image_path and Path(image_path).exists():
        bg = Image.open(image_path).convert("RGB")
        s = max(W / bg.width, H / bg.height)
        bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
        l, t = (bg.width - W) // 2, (bg.height - H) // 2
        img = bg.crop((l, t, l + W, t + H)).convert("RGBA")
    else:
        img = Image.new("RGBA", (W, H), NAVY + (255,))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        g.ellipse((380, -360, 1440, 700), fill=c + (110,))
        g.ellipse((-560, 520, 420, 1500), fill=(24, 56, 140, 80))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))
        relogio(img, 820, 330, 400, c)
    # véu inferior para legibilidade do texto (gradiente suave)
    veu = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(veu)
    for yy in range(H):
        t = max(0.0, (yy - H * 0.34) / (H * 0.66))
        vd.line([(0, yy), (W, yy)], fill=(5, 12, 28, int(240 * min(1.0, t) ** 1.1)))
    for yy in range(200):
        vd.line([(0, yy), (W, yy)], fill=(5, 12, 28, int(130 * (1 - yy / 200) ** 2)))
    img.alpha_composite(veu)
    return img


# ------------------------------------------------------------------ lâminas
def area_visual(card, alto, image_path=None):
    """Fundo da capa: foto/ilustração se houver; senão, azul-marinho com brilho da cor da marca + ícone."""
    c = ACCENT
    if image_path and Path(image_path).exists():
        bg = Image.open(image_path).convert("RGB")
        s = max(W / bg.width, alto / bg.height)
        bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1), Image.LANCZOS)
        l, t = (bg.width - W) // 2, (bg.height - alto) // 2
        return bg.crop((l, t, l + W, t + alto)).convert("RGBA")
    img = Image.new("RGBA", (W, alto), NAVY + (255,))
    lay = Image.new("RGBA", (W, alto), (0, 0, 0, 0))
    g = ImageDraw.Draw(lay)
    g.ellipse((W * 0.30, -alto * 0.55, W * 1.45, alto * 0.95), fill=c + (130,))
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(120)))
    # linhas diagonais finas (textura editorial)
    tex = Image.new("RGBA", (W, alto), (0, 0, 0, 0))
    td = ImageDraw.Draw(tex)
    for x in range(-alto, W, 28):
        td.line((x, alto, x + alto, 0), fill=(255, 255, 255, 10), width=2)
    img.alpha_composite(tex)
    # ícone grande da editoria no terço superior
    f, ch = icone(ICONE.get(card.get("chapeu", ""), "newspaper"), int(min(W, alto) * 0.62))
    ic = Image.new("RGBA", (W, alto), (0, 0, 0, 0))
    ImageDraw.Draw(ic).text((W * 0.42, alto * 0.10), ch, font=f, fill=(255, 255, 255, 46))
    img.alpha_composite(ic)
    return img


def selo(d, y):
    """Aviso de que a foto é de banco de imagens (não é do acontecimento)."""
    d.text((W - 64, y), "Imagem ilustrativa", font=font("Medium", 22), fill=(205, 212, 224), anchor="rs")


def render_cover_reels(card, out_path, image_path=None, tema=None) -> Path:
    """Arte do Reels (1080x1920), foto em tela cheia: véu escuro no topo (logo) e embaixo
    (manchete), etiqueta vermelha da editoria, manchete branca grande, cidade e hora, e o
    crédito da foto bem pequeno. Tudo que importa fica no miolo visível no feed (4:5) e na grade (3:4)."""
    HH, mx = 1920, 72
    W0 = globals()["W"]
    img = area_visual(card, HH, image_path)
    # véu: leve no topo, forte embaixo (contraste AA para o texto branco)
    veu = Image.new("RGBA", (W0, HH), (0, 0, 0, 0))
    vd = ImageDraw.Draw(veu)
    for y in range(HH):
        a = 0
        if y < 560:
            a = int(160 * (1 - y / 560) ** 1.5)
        if y > 860:
            a = max(a, int(238 * min(1.0, (y - 860) / 700) ** 1.1))
        vd.line((0, y, W0, y), fill=(4, 8, 18, a))
    img.alpha_composite(veu)
    logo(img, mx, 300, altura=66)
    d = ImageDraw.Draw(img)

    # manchete: Inter Black, até 5 linhas, ancorada para terminar perto de y=1540
    for tamanhos in ((80, 76), (72, 68), (64, 60), (56, 52), (50, 46)):
        ft, linhas = fit(clean(card["titulo"]), "Black", tamanhos, W0 - 2 * mx, 6)
        lh = int(ft.size * 1.12)
        cortou = linhas[-1].endswith("...")
        if not cortou and len(linhas) * lh <= 560:
            break  # a manchete inteira cabe: nunca corta com "..." se der para diminuir a letra
    y = 1540 - len(linhas) * lh
    # etiqueta da editoria
    fe = font("Bold", 28)
    rot = card.get("chapeu", "NOTÍCIA")
    d.rounded_rectangle((mx, y - 86, mx + fe.getlength(rot) + 40, y - 32), radius=8, fill=ACCENT)
    d.text((mx + 20, y - 59), rot, font=fe, fill=WHITE, anchor="lm")
    for ln in linhas:
        d.text((mx, y), ln, font=ft, fill=WHITE)
        y += lh
    # cidade · data/hora (· imagem ilustrativa)
    n = dt.datetime.now(ZoneInfo(TIMEZONE))
    cidade = card.get("cidade") if card.get("cidade") not in (None, "", "Brasil") else "Paraíba"
    meta = f"{cidade}  ·  {n.day} {MESES[n.month - 1]}, {n.hour:02d}h{n.minute:02d}"
    if card.get("_ilustrativa"):
        meta += "  ·  Imagem ilustrativa"
    d.text((mx, y + 18), meta, font=font("Medium", 30), fill=SOFT)
    # crédito da foto, bem pequeno
    if card.get("_credito"):
        fc = font("Medium", 18)
        cred = clean(card["_credito"])
        while fc.getlength(cred) > W0 - 2 * mx and len(cred) > 10:
            cred = cred[:-2]
        d.text((W0 - mx, 1626), cred, font=fc, fill=(190, 196, 208), anchor="rs")
    return _save(img, out_path)


def render_cover(card, out_path, source_line="", image_path=None, carousel=False,
                 topo_logo=60, base_texto=None) -> Path:
    """Capa no padrão de portal: imagem em tela cheia, logo pequeno no topo,
    rótulo (editoria · cidade) + manchete em branco no canto inferior esquerdo."""
    img = area_visual(card, H, image_path)

    # escurecimento: leve no topo (logo) e forte embaixo (manchete) — legibilidade AA
    veu = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(veu)
    for yy in range(topo_logo + 180):
        vd.line([(0, yy), (W, yy)], fill=(0, 0, 0, int(110 * (1 - yy / (topo_logo + 180)) ** 1.6)))
    fim = min(H, (base_texto or H) + 120)
    ini = fim - int(1350 * 0.60)
    for yy in range(max(0, ini), H):
        t = min(1.0, (yy - ini) / (fim - ini))
        vd.line([(0, yy), (W, yy)], fill=(0, 0, 0, int(225 * t ** 1.3)))
    img.alpha_composite(veu)

    # logo pequeno no canto (só o símbolo + nome, como assinatura)
    logo(img, 64, topo_logo, altura=64)

    # manchete: Inter Bold, caixa normal, até 4 linhas, ancorada embaixo
    ft, t_lines = fit(clean(card["titulo"]), "Bold", (72, 68, 64, 60, 56), W - 2 * 64 - 40, 4)
    t_lh = int(ft.size * 1.14)
    y_end = base_texto if base_texto else H - 120
    y_t = y_end - t_lh * len(t_lines)

    d = ImageDraw.Draw(img)
    # rótulo: EDITORIA · CIDADE (pequeno, amarelo; vermelho para polícia)
    rot_cor = URGENTE if card.get("chapeu") in ("POLÍCIA", "URGENTE") else ACCENT
    rotulo = card.get("chapeu", "NOTÍCIA")
    if card.get("cidade") and card["cidade"] != "Brasil":
        rotulo += "  ·  " + card["cidade"].upper()
    fr = font("Bold", 26)
    d.rectangle((64, y_t - 58, 64 + 6, y_t - 26), fill=rot_cor)
    d.text((64 + 20, y_t - 42), rotulo, font=fr, fill=rot_cor if rot_cor == ACCENT else WHITE, anchor="lm")

    # sombra suave sob a manchete
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sdd = ImageDraw.Draw(sh)
    y = y_t
    for ln in t_lines:
        sdd.text((64 + 2, y + 3), ln, font=ft, fill=(0, 0, 0, 150))
        y += t_lh
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    d = ImageDraw.Draw(img)
    y = y_t
    for ln in t_lines:
        d.text((64, y), ln, font=ft, fill=WHITE)
        y += t_lh

    if card.get("_ilustrativa"):
        selo(d, y_end + 46)

    # indicação discreta de carrossel (pontinhos), sem botão
    if carousel:
        cx = W - 64 - 52
        d.ellipse((cx, H - 70, cx + 14, H - 56), fill=WHITE)
        d.ellipse((cx + 26, H - 70, cx + 40, H - 56), fill=(120, 128, 140))
    return _save(img, out_path)


def render_details(card, out_path, source_line="") -> Path:
    """Lâmina 2: mesmo visual da capa (fundo escuro), com lide e lista do formato."""
    img = Image.new("RGBA", (W, H), NAVY + (255,))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((W * 0.45, -H * 0.35, W * 1.5, H * 0.35), fill=ACCENT + (60,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(140)))
    logo(img, 64, 60, altura=64)
    d = ImageDraw.Draw(img)
    X, inner = 64, W - 2 * 64

    y = 210
    rot = TXT_LISTA.get(card.get("formato"), "Principais pontos").upper()
    rot_cor = URGENTE if card.get("chapeu") in ("POLÍCIA", "URGENTE") else ACCENT
    d.rectangle((X, y + 4, X + 6, y + 36), fill=rot_cor)
    d.text((X + 20, y + 20), rot, font=font("Bold", 28), fill=rot_cor if rot_cor == ACCENT else WHITE, anchor="lm")
    y += 72

    ft, t_lines = fit(clean(card["titulo"]), "Bold", (56, 52, 48, 44), inner, 3)
    for ln in t_lines:
        d.text((X, y), ln, font=ft, fill=WHITE)
        y += int(ft.size * 1.16)
    y += 28
    fs, s_lines = fit(clean(card["resumo"]), "Regular", (38, 36, 34, 32), inner, 6)
    for ln in s_lines:
        d.text((X, y), ln, font=fs, fill=SOFT)
        y += int(fs.size * 1.45)
    y += 44

    fp = font("SemiBold", 36)
    pontos = card.get("pontos", [])
    for i, p in enumerate(pontos):
        lines = wrap(clean(p), fp, inner - 56)[:2]
        need = 30 + 48 * len(lines) + 30
        if y + need > H - 110:
            break
        d.line((X, y, W - X, y), fill=(44, 58, 90), width=2)
        ty = y + 30
        d.ellipse((X, ty + 12, X + 20, ty + 32), fill=ACCENT)
        for ln in lines:
            d.text((X + 44, ty), ln, font=fp, fill=WHITE)
            ty += 48
        y += need

    d.text((X, H - 70), f"Siga {PORTAL_HANDLE}", font=font("SemiBold", 26), fill=SOFT, anchor="lm")
    d.ellipse((W - X - 40, H - 77, W - X - 26, H - 63), fill=(120, 128, 140))
    d.ellipse((W - X - 14, H - 77, W - X, H - 63), fill=WHITE)
    return _save(img, out_path)


def _sombra(img, box):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle((box[0], box[1] + 8, box[2], box[3] + 8),
                                          radius=R_CARD, fill=(0, 0, 0, 22))
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(18)))


def _save(img, out_path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=95, subsampling=0, optimize=True)  # a API só aceita JPEG
    return out_path


def render_post(card, base, source_line, image_path=None, carousel=True) -> list:
    """Gera as lâminas do post e devolve a lista de arquivos (1 ou 2)."""
    usar = carousel and (len(card.get("pontos", [])) >= 2 or len(card.get("resumo", "")) > 140)
    paths = [render_cover(card, Path(f"{base}_1.jpg"), source_line, image_path, usar)]
    if usar:
        paths.append(render_details(card, Path(f"{base}_2.jpg"), source_line))
    return paths
