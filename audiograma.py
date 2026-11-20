"""Capa e vídeo do Reels no padrão do g1 (layout.py), com a marca do PB Minuto.

Capa: barra vermelha no topo com a logo no centro; foto cheia; degradê preto embaixo com o texto
branco (chapéu, manchete, linha fina, data e cidade, crédito), em Open Sans, como o destaque do g1.
Vídeo: mesma barra; a foto da capa com efeito vermelho; chapéu e data abaixo da barra; embaixo,
fundo preto com a onda da voz centralizada e a legenda sincronizada palavra por palavra.

O tempo de cada palavra vem da própria narração (Whisper, alinhado ao roteiro).
"""
import datetime as dt
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import layout as L
from config import BRAND_COLOR, FONT_DIR, PORTAL_HANDLE, TIMEZONE

W, H, FPS = 1080, 1920, 30              # coordenadas do desenho (o vídeo sai em 2K: ESCALA)
try:
    from config import VIDEO_2K
except ImportError:
    VIDEO_2K = True
ESCALA = 4 / 3 if VIDEO_2K else 1.0     # 2K vertical = 1440x2560 (o Instagram aceita até 1920 de largura)
VW, VH = round(W * ESCALA), round(H * ESCALA)


def z(v):
    """Coordenada do desenho (1080x1920) -> pixel do vídeo (2K)."""
    return round(v * ESCALA)
# posições e medidas vêm do sistema de layout (layout.py, derivado da estrutura do g1)
REELS = L.FORMATOS["reels"]
M = REELS["margem"]                      # margem esquerda (área segura do Instagram)
ONDA = L.VIDEO["onda"]                   # x, y, largura, altura do visualizador da voz (centralizado)
LEG_Y = L.VIDEO["legenda_y"]             # centro da legenda: logo abaixo da onda (mesmo eixo central)
LEG_W = L.VIDEO["legenda_w"]             # largura máxima da legenda (x 130 a 950, longe dos botões)
VERMELHO = tuple(int(BRAND_COLOR.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
VERMELHO_ESCURO = tuple(int(c * 0.78) for c in VERMELHO)
BRANCO = (255, 255, 255)
PRETO = (0, 0, 0)

# uma fonte só, a do g1 e da capa: Open Sans Bold. Destaque = caixa branca, não outra fonte.
# No ASS o tamanho é a altura da linha (1,36 em na Open Sans): 86 = corpo de ~63 px no desenho.
FONTE_TEXTO = ("Open Sans", L.FONTE[700], 86)
FONTE_DESTAQUE = FONTE_TEXTO
FONTE_NEGRITO = -1      # no ASS, -1 = negrito (pega o arquivo Bold da família "Open Sans")
ALTURA_LINHA = 1.12     # entrelinha da legenda (em múltiplos do tamanho ASS)
CAIXA = 12              # folga da caixa branca da palavra falada (px no desenho 1080)
RESPIRO = 18            # espaço extra entre palavras, para a caixa não encostar na vizinha
TRACK_LEG = -1.9        # espaço entre letras da legenda (px no desenho): -0,03 em, perto do g1
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

_cache = {}


def fonte(arquivo: str, tamanho: int) -> ImageFont.FreeTypeFont:
    if (arquivo, tamanho) not in _cache:
        _cache[(arquivo, tamanho)] = ImageFont.truetype(str(FONT_DIR / arquivo), tamanho)
    return _cache[(arquivo, tamanho)]


# ------------------------------------------------------------------ logo
def logo(altura: int) -> Image.Image:
    """A mesma logo do perfil (logo.py): quadrado branco com PB vermelho + MINUTO branco."""
    import logo as _logo
    return _logo.lockup(altura, fundo_vermelho=True)


# ------------------------------------------------------------------ quadro fixo
def _cobrir(im: Image.Image, w: int, h: int) -> Image.Image:
    escala = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * escala), round(im.height * escala)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def _mascara(w, h, raio):
    m = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * 2 - 1, h * 2 - 1), radius=raio * 2, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def _carimbo():
    agora = dt.datetime.now(ZoneInfo(TIMEZONE))
    return f"{agora.day} {MESES[agora.month - 1]} · {agora.hour}H{agora.minute:02d}"


def _data_g1():
    """Data e hora no formato das matérias do g1: 20/11/2026 09h17."""
    agora = dt.datetime.now(ZoneInfo(TIMEZONE))
    return agora.strftime("%d/%m/%Y %Hh%M")


def _foto_ou_vazio(image_path, w, h):
    if image_path and Path(image_path).exists():
        try:
            return _cobrir(Image.open(image_path).convert("RGB"), w, h)
        except Exception:
            pass
    return None


def _degrade(img: Image.Image, y0: int, y1: int, a0: int, a1: int, cor=None):
    """Faixa vertical de cor (padrão: vermelho da marca) indo da opacidade a0 até a1."""
    cor = cor or VERMELHO
    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    for y in range(max(y0, 0), min(y1, img.height)):
        t = (y - y0) / max(y1 - y0, 1)
        d.line((0, y, img.width, y), fill=cor + (int(a0 + (a1 - a0) * t ** 1.3),))
    if y1 < img.height:
        d.rectangle((0, y1, img.width, img.height), fill=cor + (a1,))
    base = img.convert("RGBA")
    base.alpha_composite(camada)
    return base.convert("RGB")


def _material(img: Image.Image, y0: int, y1: int, tinta=0.86, desfoque=34, cor=None):
    """Material translúcido no estilo Apple: abaixo de y1 a própria foto aparece desfocada sob o
    vermelho da marca ("vidro" vermelho); entre y0 e y1 a passagem é suave (sem linha dura)."""
    vidro = img.filter(ImageFilter.GaussianBlur(z(desfoque)))
    vidro = Image.blend(vidro, Image.new("RGB", img.size, cor or VERMELHO), tinta)
    mascara = Image.new("L", img.size, 0)
    dm = ImageDraw.Draw(mascara)
    for y in range(max(y0, 0), min(y1, img.height)):
        t = (y - y0) / max(y1 - y0, 1)
        dm.line((0, y, img.width, y), fill=int(255 * t * t * (3 - 2 * t)))  # smoothstep
    if y1 < img.height:
        dm.rectangle((0, y1, img.width, img.height), fill=255)
    return Image.composite(vidro, img, mascara)


def _texto(d, xy, texto, f, fill, track=0.0, anchor="ls"):
    """Texto com espaçamento entre letras por tamanho (Apple: títulos grandes mais justos,
    textos pequenos um pouco mais abertos). `track` em em (ex.: -0.02)."""
    if not track:
        d.text(xy, texto, font=f, fill=fill, anchor=anchor)
        return f.getlength(texto)
    x, y = xy
    passo = track * f.size
    for i, ch in enumerate(texto):
        d.text((x + f.getlength(texto[:i]) + passo * i, y), ch, font=f, fill=fill, anchor=anchor)
    return f.getlength(texto) + passo * (len(texto) - 1)


def _sem_foto(card, w, h):
    import render
    fundo = Image.new("RGB", (w, h), (30, 30, 30))   # sem foto: cinza escuro, como o g1
    f_ic, ch = render.icone(render.ICONE.get(card.get("chapeu", ""), "newspaper"), z(420))
    ImageDraw.Draw(fundo).text((w / 2, h * 0.40), ch, font=f_ic, fill=(78, 78, 78), anchor="mm")
    return fundo


def _chapeu(card) -> str:
    """Chapéu como no g1: palavra curta em caixa normal ("Polícia", "Saúde")."""
    return (card.get("chapeu") or "Notícia").strip().capitalize()


def _linha_credito(card, imagem) -> str:
    credito = card.get("_credito", "").strip()
    partes = [credito] if imagem else []
    ja_diz = "ilustra" in credito.lower() or "ia" in credito.lower().split()  # sem repetir o aviso
    if card.get("_ilustrativa") and not ja_diz:
        partes.append("Imagem ilustrativa")
    elif "IA" in credito and not ja_diz:
        partes.append("Ilustração por IA")
    return "  ·  ".join(p for p in partes if p)


def _com_sombra(img: Image.Image, camada: Image.Image) -> Image.Image:
    """Cola o texto com a sombra do g1 (0 1px 3px preto 80%, x K)."""
    a = camada.split()[3]
    sombra = Image.new("RGBA", img.size, PRETO + (0,))
    sombra.putalpha(a.point(lambda v: int(v * L.SOMBRA["opacidade"])))
    sombra = sombra.filter(ImageFilter.GaussianBlur(z(L.SOMBRA["raio"]) / 2))
    base = img.convert("RGBA")
    base.alpha_composite(sombra, (0, z(L.SOMBRA["dy"])))
    base.alpha_composite(camada)
    return base.convert("RGB")


def _barra(img: Image.Image, formato="reels", b=None) -> Image.Image:
    """Barra vermelha do topo com a logo no centro (cabeçalho no padrão do g1)."""
    import logo as _logo
    b = b or L.barra(L.FORMATOS[formato])
    br = _logo.barra(img.width, z(b["fim"]), z(b["logo"]), z(b["centro"]), z(b["borda"]))
    base = img.convert("RGBA")
    base.alpha_composite(br, (0, 0))
    return base.convert("RGB")


def _credito(d, texto, y, x_esq, largura):
    """Crédito da foto, pequeno, no mesmo eixo esquerdo do resto do texto."""
    if texto:
        t = L.PAPEIS["credito_foto"]
        f_cr = fonte(t["fonte"], z(t["tam"]))
        while f_cr.getlength(texto) > largura and len(texto) > 10:
            texto = texto[:-2]
        _texto(d, (x_esq, y), texto, f_cr, L.COR["credito"], track=t["track"])


def _palavras_com_fonte(texto: str, destaques: list, tamanho: int):
    """[(palavra, fonte, destaque?)] para desenhar a manchete com os destaques na serifada."""
    out = []
    for p, dest in _marcar_destaques(texto.split(), destaques):
        arq = "InstrumentSerif-Italic.ttf" if dest else L.FONTE[700]
        out.append((p, fonte(arq, int(tamanho * (1.12 if dest else 1.0))), dest))
    return out


def _quebrar(itens, largura, track=0.0):
    linhas, atual, w = [], [], 0.0
    for p, f, dest in itens:
        lw = f.getlength(p + " ") + track * f.size * max(len(p) - 1, 0)
        if atual and w + lw > largura:
            linhas.append(atual)
            atual, w = [], 0.0
        atual.append((p, f, dest))
        w += lw
    if atual:
        linhas.append(atual)
    # sem palavra sozinha na última linha (viúva): puxa uma palavra da linha de cima
    if len(linhas) >= 2 and len(linhas[-1]) == 1 and len(linhas[-2]) > 2:
        cand = [linhas[-2][-1]] + linhas[-1]
        if sum(f.getlength(p + " ") for p, f, _ in cand) <= largura:
            linhas[-2], linhas[-1] = linhas[-2][:-1], cand
    return linhas


def _linhas_da_fina(texto: str, f, largura: int, maximo: int) -> list:
    if not texto:
        return []
    linhas = _quebrar([(p, f, False) for p in texto.split()], largura, track=L.PAPEIS["linha_fina"]["track"])
    if len(linhas) > maximo:  # raro (a linha fina tem até 15 palavras): corta com reticências
        linhas = linhas[:maximo]
        p, f_, dest = linhas[-1][-1]
        linhas[-1][-1] = (p.rstrip(".,;:") + "…", f_, dest)
    return linhas


def capa(card: dict, out_path: Path, image_path=None, formato: str = "reels") -> Path:
    """Capa no padrão do destaque do g1: barra vermelha no topo com a logo, foto cheia, degradê
    preto embaixo e o texto branco com sombra, alinhado à esquerda: chapéu, manchete, linha fina,
    data e cidade, crédito. Fonte Open Sans; medidas e espaços de layout.py; tudo dentro do corte
    3:4 da grade do perfil."""
    fmt = L.FORMATOS[formato]
    cw, ch = z(fmt["w"]), z(fmt["h"])
    foto = _foto_ou_vazio(image_path, cw, ch)
    img = foto if foto is not None else _sem_foto(card, cw, ch)
    m, largura = fmt["margem"], z(fmt["largura_texto"])
    man, lf = L.PAPEIS["manchete"], L.PAPEIS["linha_fina"]
    fina = " ".join(str(card.get("linha_fina") or "").split())
    credito = _linha_credito(card, foto is not None)

    def compor(tam, com_fina):
        f_tit = fonte(man["fonte"], z(tam))
        linhas = _quebrar([(p, f_tit, False) for p in card["titulo"].split()], largura, track=man["track"])
        f_fina = fonte(lf["fonte"], z(L.tam("resumo", tam)))
        l_fina = _linhas_da_fina(fina if com_fina else "", f_fina, largura, lf["max_linhas"])
        return f_tit, linhas, f_fina, l_fina, L.pilha_capa(len(linhas), tam, len(l_fina), bool(credito), fmt)

    # maior manchete que cabe; se nem a menor cabe com a linha fina, a linha fina sai da capa
    escolha = None
    for com_fina in (True, False):
        for tam in man["tamanhos"]:
            f_tit, linhas, f_fina, l_fina, pos = compor(tam, com_fina)
            if len(linhas) <= man["max_linhas"] and L.cabe(pos, fmt):
                escolha = (tam, f_tit, linhas, f_fina, l_fina, pos)
                break
        if escolha:
            break
    if escolha is None:
        tam = man["tamanhos"][-1]
        escolha = (tam, *compor(tam, False))
    tam, f_tit, linhas, f_fina, l_fina, pos = escolha

    # degradê preto (destaque do g1): começa acima do chapéu e fica forte no meio da manchete
    cp = L.CAPA_PRETO
    forte = pos["topo"] + (pos["meta"] - pos["topo"]) * cp["ate"]
    img = _degrade(img, z(pos["topo"] - cp["antes_do_texto"]), z(forte), 0, cp["opacidade"], cor=PRETO)

    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    t_ch = L.PAPEIS["chapeu"]
    _texto(d, (z(m), z(pos["chapeu"])), _chapeu(card), fonte(t_ch["fonte"], z(pos["tam_chapeu"])),
           L.COR["texto"], track=t_ch["track"])
    for i, linha in enumerate(linhas):                               # manchete
        x, y = z(m), z(pos["titulo"] + pos["passo_titulo"] * i)
        for p, f, _ in linha:
            x += _texto(d, (x, y), p, f, L.COR["texto"], track=man["track"]) + f.getlength(" ")
    for i, linha in enumerate(l_fina):                               # linha fina
        x, y = z(m), z(pos["fina"] + pos["passo_fina"] * i)
        for p, f, _ in linha:
            x += _texto(d, (x, y), p, f, L.COR["texto"], track=lf["track"]) + f.getlength(" ")
    meta = f"{_data_g1()}  —  {card.get('cidade') or 'Paraíba'}"
    _texto(d, (z(m), z(pos["meta"])), meta, fonte(L.PAPEIS["meta"]["fonte"], z(pos["tam_meta"])),
           L.COR["texto_aux"])
    if credito:
        _credito(d, credito, z(pos["credito"]), z(m), largura)
    img = _com_sombra(img, camada)
    img = _barra(img, formato)
    img.save(out_path, quality=94)
    return Path(out_path)


def quadro(card: dict, out_path: Path, image_path=None) -> Path:
    """Fundo fixo do vídeo: a MESMA imagem da capa com efeito vermelho (duotone da marca), a barra
    vermelha colada no topo da tela (como o cabeçalho do g1), chapéu e data logo abaixo dela; embaixo, fundo preto (foto desfocada sob o
    preto) para a onda da voz e a legenda branca."""
    from PIL import ImageOps
    foto = _foto_ou_vazio(image_path, VW, VH)
    if foto is not None:
        claro = tuple(min(255, int(c + (255 - c) * 0.80)) for c in VERMELHO)
        duo = ImageOps.colorize(ImageOps.autocontrast(ImageOps.grayscale(foto), cutoff=1),
                                black=tuple(int(c * 0.45) for c in VERMELHO), white=claro)
        img = Image.blend(duo, foto, 0.38)  # vermelho da marca, mas a foto continua reconhecível
    else:
        img = _sem_foto(card, VW, VH)
    b = L.barra_video()                                              # barra colada no topo
    y_texto = max(b["fim"] + L.esp(3), L.VIDEO["topo_seguro"])       # topo do chapéu
    img = _degrade(img, z(b["fim"]), z(y_texto + 260), 150, 0, cor=PRETO)   # sob a barra: leitura
    y0, y1 = L.VIDEO["fundo_preto"]
    if foto is not None:
        img = _material(img, z(y0), z(y1), tinta=L.VIDEO["preto"], cor=PRETO)
    else:
        img = _degrade(img, z(y0), z(y1), 0, 245, cor=PRETO)

    camada = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(camada)
    man0 = L.PAPEIS["manchete"]["tamanhos"][0]
    t_ch, t_meta = L.tam("chapeu", man0), L.tam("meta", man0)
    cap = lambda t: round(t * L.ALTURA_MAIUSCULA)  # noqa: E731
    y_ch = y_texto + cap(t_ch)                                                 # barra -> chapéu
    _texto(d, (z(M), z(y_ch)), _chapeu(card), fonte(L.PAPEIS["chapeu"]["fonte"], z(t_ch)),
           L.COR["texto"], track=L.PAPEIS["chapeu"]["track"])
    y_meta = y_ch + round(t_ch * L.DESCENDENTE) + L.esp(1) + cap(t_meta)       # chapéu -> data: 16
    _texto(d, (z(M), z(y_meta)), f"{_data_g1()}  —  {card.get('cidade') or 'Paraíba'}",
           fonte(L.PAPEIS["meta"]["fonte"], z(t_meta)), L.COR["texto_aux"])
    t_cred = L.PAPEIS["credito_foto"]["tam"]
    y_cred = y_meta + round(t_meta * L.DESCENDENTE) + L.esp(1) + cap(t_cred)
    _credito(d, _linha_credito(card, foto is not None), z(y_cred), z(M), z(REELS["direita_segura"] - M))
    img = _com_sombra(img, camada)
    img = _barra(img, b=b)
    img.save(out_path, quality=95)
    return Path(out_path)


# ------------------------------------------------------------------ tempo das frases
def _pausas(wav: Path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af",
                        "silencedetect=noise=-36dB:d=0.22", "-f", "null", "-"],
                       capture_output=True, text=True)
    ini = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    fim = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(ini, fim))


def _duracao(arq: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        str(arq)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def tempos_das_frases(frases: list, wav: Path = None, total: float = None) -> list:
    """(início, fim) de cada frase em segundos do áudio original (sem o respiro inicial).
    Usa as pausas da narração; sem pausas suficientes, divide pelo tamanho do texto."""
    dur = _duracao(wav) if wav and Path(wav).exists() else (total or 0)
    tam = [max(len(f), 1) for f in frases]
    if not frases or dur <= 0:
        return []
    # só pausas no meio da fala (o silêncio do começo e do fim do áudio não separa frases)
    pausas = [p for p in (_pausas(wav) if wav and Path(wav).exists() else []) if p[0] > 0.15 and p[1] < dur - 0.08]
    # tempo de fala acumulado até cada pausa (as pausas não contam como fala)
    fala_ate, acumulado, anterior = [], 0.0, 0.0
    for a, b in pausas:
        acumulado += a - anterior
        fala_ate.append(acumulado)
        anterior = b
    fala_total = acumulado + max(dur - anterior, 0)
    cortes = []
    if len(pausas) >= len(frases) - 1:
        usado = -1
        soma = 0
        for k in range(len(frases) - 1):
            soma += tam[k]
            alvo = fala_total * soma / sum(tam)
            restantes = len(frases) - 2 - k  # pausas que ainda vão faltar depois desta
            melhor = min(range(usado + 1, len(pausas) - restantes), key=lambda i: abs(fala_ate[i] - alvo))
            cortes.append(pausas[melhor])
            usado = melhor
    if len(cortes) == len(frases) - 1:
        out, inicio = [], 0.0
        for a, b in cortes:
            out.append((inicio, a))
            inicio = b
        out.append((inicio, dur))
        return out
    out, t = [], 0.0
    for n in tam:
        d = dur * n / sum(tam)
        out.append((t, t + d))
        t += d
    return out


# ------------------------------------------------------------------ tempo de cada palavra
# Método das skills "remotion-captions" (remotion-dev/skills) e "captions" da HyperFrames
# (heygen-com/hyperframes): voz do Gemini -> Whisper para ter o tempo de CADA palavra -> a palavra
# aparece quando é dita.
# Aqui: faster-whisper na CPU do GitHub; como o texto falado já é conhecido, o Whisper só dá o
# tempo, e as palavras do roteiro são alinhadas às reconhecidas.
def _silabas(palavra: str) -> int:
    return max(1, len(re.findall(r"[aeiouáéíóúâêôãõà]+", palavra.lower())) + (2 if re.search(r"\d", palavra) else 0))


def _whisper(wav: Path) -> list:
    """[(palavra, início, fim)] reconhecidas pelo Whisper, ou [] se não estiver disponível."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    try:
        from config import WHISPER_MODELO
        if "modelo" not in _cache_whisper:
            _cache_whisper["modelo"] = WhisperModel(WHISPER_MODELO, device="cpu", compute_type="int8")
        # o áudio vai já decodificado (16 kHz, mono): a leitura própria do faster-whisper usa o
        # PyAV, que mudou de versão e quebrava ("metadata_errors")
        import numpy as np
        bruto = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-ar", "16000", "-ac", "1",
                                "-f", "s16le", "-"], capture_output=True, check=True).stdout
        audio = np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0
        segs, _ = _cache_whisper["modelo"].transcribe(audio, language="pt", word_timestamps=True,
                                                      beam_size=1, vad_filter=False)
        palavras = [(w.word.strip(), float(w.start), float(w.end)) for sg in segs for w in (sg.words or [])]
        print(f"[legenda] Whisper {WHISPER_MODELO}: {len(palavras)} palavras com tempo")
        return palavras
    except Exception as e:
        print(f"[legenda] Whisper indisponível ({str(e)[:100]}); tempo estimado pelas sílabas")
        return []


_cache_whisper = {}


def _norm(p: str) -> str:
    return re.sub(r"[^\w]", "", _fold(p))


def tempo_das_palavras(frases: list, wav: Path = None, total: float = None, reconhecidas=None) -> list:
    """[(palavra, início, fim, nº da frase)] no tempo do áudio original (sem o respiro inicial)."""
    palavras = [(p, k) for k, f in enumerate(frases) for p in f.split()]
    if not palavras:
        return []
    if reconhecidas is None and wav and Path(wav).exists():
        reconhecidas = _whisper(Path(wav))
    tempos = [None] * len(palavras)
    if reconhecidas:
        import difflib
        a = [_norm(p) for p, _ in palavras]
        b = [_norm(p) for p, _, _ in reconhecidas]
        for bloco in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
            for j in range(bloco.size):
                _, ini, fim = reconhecidas[bloco.b + j]
                tempos[bloco.a + j] = (ini, fim)
    if sum(t is not None for t in tempos) < len(palavras) * 0.5:
        # reserva: frases pelas pausas da voz, palavras pelas sílabas dentro de cada frase
        tempos = [None] * len(palavras)
        i = 0
        for (ini, fim), frase in zip(tempos_das_frases(frases, wav, total), frases):
            ps = frase.split()
            pesos = [_silabas(p) for p in ps]
            t = ini
            for p, w in zip(ps, pesos):
                d = (fim - ini) * w / sum(pesos)
                tempos[i] = (t, t + d)
                t += d
                i += 1
        if any(t is None for t in tempos):
            return []
        return [(p, a, b, k) for (p, k), (a, b) in zip(palavras, tempos)]
    # palavras que o Whisper não reconheceu: entre as vizinhas, pelo tamanho
    i = 0
    while i < len(tempos):
        if tempos[i] is None:
            j = i
            while j < len(tempos) and tempos[j] is None:
                j += 1
            ini = tempos[i - 1][1] if i > 0 else 0.0
            fim = tempos[j][0] if j < len(tempos) else (ini + 0.35 * (j - i))
            pesos = [_silabas(palavras[k][0]) for k in range(i, j)]
            t = ini
            for k, w in zip(range(i, j), pesos):
                d = max(fim - ini, 0.05 * (j - i)) * w / sum(pesos)
                tempos[k] = (t, t + d)
                t += d
            i = j
        else:
            i += 1
    return [(p, a, b, k) for (p, k), (a, b) in zip(palavras, tempos)]


# ------------------------------------------------------------------ legenda (ASS)
def _fold(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _marcar_destaques(palavras: list, destaques: list) -> list:
    """Devolve [(palavra, destaque?)]. Destaque = trecho pedido pelo editor ou número/valor."""
    marcas = [False] * len(palavras)
    limpas = [_fold(re.sub(r"[^\w%$,.-]", "", p)).strip(".,") for p in palavras]
    for trecho in destaques or []:
        alvo = [_fold(x).strip(".,") for x in trecho.split() if x.strip()]
        if not alvo:
            continue
        for i in range(len(limpas) - len(alvo) + 1):
            if limpas[i:i + len(alvo)] == alvo:
                for j in range(i, i + len(alvo)):
                    marcas[j] = True
    if not any(marcas):  # sem destaque do editor: números e valores
        for i, p in enumerate(palavras):
            if re.search(r"\d", p):
                marcas[i] = True
                if i + 1 < len(palavras) and len(palavras[i + 1]) > 2 and not re.search(r"\d", palavras[i + 1]):
                    marcas[i + 1] = True
    return list(zip(palavras, marcas))


def fonte_ass(arq: str, tam: float) -> ImageFont.FreeTypeFont:
    """A fonte no tamanho em que a legenda (ASS/libass) realmente desenha: no ASS o "tamanho" é a
    altura da linha (ascendente + descendente), não o corpo da letra como no Pillow."""
    ref = fonte(arq, 200)
    asc, desc = ref.getmetrics()
    return fonte(arq, max(8, round(tam * 200 / (asc + desc))))


def _larg_palavra(f, palavra: str) -> float:
    """Largura da palavra como o ASS desenha, já com o espaçamento justo entre letras."""
    return f.getlength(palavra) + TRACK_LEG * (len(palavra) - 1)


def _largura(palavra: str, destaque: bool, escala=1.0) -> float:
    nome, arq, tam = FONTE_DESTAQUE if destaque else FONTE_TEXTO
    return fonte_ass(arq, tam * escala).getlength(palavra + " ") + RESPIRO


def _linhas(itens: list, escala=1.0) -> list:
    linhas, atual, w = [], [], 0.0
    for p, dest in itens:
        lw = _largura(p, dest, escala)
        if atual and w + lw > LEG_W:
            linhas.append(atual)
            atual, w = [], 0.0
        atual.append((p, dest))
        w += lw
    if atual:
        linhas.append(atual)
    return linhas


def _ass_linha(linha: list, escala=1.0) -> str:
    partes = []
    for p, dest in linha:
        p = p.replace("{", "(").replace("}", ")")
        if dest:
            nome, _, tam = FONTE_DESTAQUE
            partes.append(f"{{\\fn{nome}\\i1\\fs{int(tam * escala)}}}{p}{{\\r}}")
        else:
            partes.append(p)
    return " ".join(partes)


def blocos(frase: str, destaques: list, manchete=False) -> list:
    """Divide a frase em blocos de até 2 linhas, de tamanhos parecidos (sem sobra curta no fim).
    A manchete fica inteira: 3 linhas no tamanho normal ou até 4 linhas um pouco menor."""
    itens = _marcar_destaques(frase.split(), destaques)
    if manchete:
        for escala in (1.0, 0.92, 0.84, 0.76, 0.68):
            ls = _linhas(itens, escala)
            if len(ls) <= 4:
                return [(ls, escala)]
        return [(ls, 0.64)]
    n = max(1, -(-len(_linhas(itens)) // 2))  # quantos blocos de 2 linhas são necessários
    while True:
        larg = [_largura(p, d) for p, d in itens]
        alvo = sum(larg) / n
        grupos, atual, w = [], [], 0.0
        for item, lw in zip(itens, larg):
            if atual and w + lw / 2 > alvo and len(grupos) < n - 1:
                grupos.append(atual)
                atual, w = [], 0.0
            atual.append(item)
            w += lw
        grupos.append(atual)
        partes = [_linhas(g) for g in grupos]
        if all(len(ls) <= 2 for ls in partes):
            return [(ls, 1.0) for ls in partes]
        n += 1


def _ts(t: float) -> str:
    t = max(t, 0)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


MAX_PALAVRAS_GRUPO = 5   # skill HyperFrames (HeyGen): tom de conversa = grupos de 3 a 5 palavras
PAUSA_GRUPO = 0.15       # pausa de 150 ms ou mais na fala também fecha o grupo


def paginas(palavras_t: list, destaques: list) -> list:
    """Agrupa as palavras (regras da skill de legendas da HyperFrames/HeyGen): até 5 palavras e
    2 linhas, quebra no fim da frase e nas pausas da fala, nunca separa um destaque (ex.: "339 vagas").
    Devolve [[(palavra, destaque?, início, fim)]]."""
    out = []
    frases = {}
    for p, a, b, k in palavras_t:
        frases.setdefault(k, []).append((p, a, b))
    for k in sorted(frases):
        ws = frases[k]
        marcas = [d for _, d in _marcar_destaques([p for p, _, _ in ws], destaques)]
        itens = [(p, d, a, b) for (p, a, b), d in zip(ws, marcas)]
        pag, w, linhas = [], 0.0, 1
        for p, d, a, b in itens:
            lw = _largura(p, d)
            dentro_destaque = bool(pag) and d and pag[-1][1]
            cheia = len(pag) >= MAX_PALAVRAS_GRUPO or (pag and a - pag[-1][3] >= PAUSA_GRUPO)
            estoura = pag and w + lw > LEG_W and linhas == 2
            if pag and (cheia or estoura) and not dentro_destaque:
                out.append(pag)
                pag, w, linhas = [], 0.0, 1
            elif pag and w + lw > LEG_W:
                linhas += 1
                w = 0.0
            pag.append((p, d, a, b))
            w += lw
        if pag:
            out.append(pag)
    return out


def _linhas_da_pagina(pag: list) -> list:
    linhas, atual, w = [], [], 0.0
    for item in pag:
        lw = _largura(item[0], False)
        if atual and w + lw > LEG_W:
            levar = []
            if item[1]:  # não parte um destaque ("jornada 5x2") entre duas linhas
                while atual and atual[-1][1] and len(atual) > 1:
                    levar.insert(0, atual.pop())
            linhas.append(atual)
            atual = levar
            w = sum(_largura(i[0], False) for i in atual)
        atual.append(item)
        w += lw
    if atual:
        linhas.append(atual)
    return linhas


def legenda_ass(palavras_t: list, destaques: list, out_path: Path, atraso=0.3, fator=1.0, total=None) -> Path:
    """Legenda dinâmica, uma fonte só (Open Sans Bold, branca sobre o preto):
    - cada palavra entra no instante em que é falada;
    - a palavra que está sendo dita ganha uma caixa branca com letra vermelha e um "pop";
    - as palavras-chave (destaques: número, valor, prazo) mantêm a caixa até o fim do grupo.
    As linhas ficam paradas (as palavras já ocupam o lugar, invisíveis), então nada treme."""
    nome, arq, tam = FONTE_TEXTO
    verm = "&H{:02X}{:02X}{:02X}&".format(VERMELHO[2], VERMELHO[1], VERMELHO[0])
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{nome},{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H8C000000,{FONTE_NEGRITO},0,0,0,100,100,{TRACK_LEG},0,1,0,1.5,5,0,0,0,1
Style: Caixa,{nome},{tam},{verm},{verm},&H00FFFFFF,&H00FFFFFF,{FONTE_NEGRITO},0,0,0,100,100,{TRACK_LEG},0,3,{CAIXA},0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    t = lambda x: x / fator + atraso  # noqa: E731  (tempo do áudio original -> tempo do vídeo)
    f = fonte_ass(arq, tam)
    espaco = f.getlength(" ") + RESPIRO
    lh = tam * ALTURA_LINHA
    pags = paginas(palavras_t, destaques)
    eventos = []
    for n, pag in enumerate(pags):
        ini = t(pag[0][2])
        fim = t(pags[n + 1][0][2]) if n + 1 < len(pags) else (total or t(pag[-1][3]) + 1.0)
        linhas = _linhas_da_pagina(pag)
        y0 = LEG_Y - (len(linhas) - 1) * lh / 2
        for i, linha in enumerate(linhas):
            y = round(y0 + i * lh)
            larg = sum(_larg_palavra(f, p) for p, *_ in linha) + espaco * (len(linha) - 1)
            x = W / 2 - larg / 2
            pos = []  # (x esquerda, largura) de cada palavra da linha
            xx = x
            for p, *_ in linha:
                pos.append((xx, _larg_palavra(f, p)))
                xx += _larg_palavra(f, p) + espaco
            # sequência de palavras-chave (ex.: "jornada 5x2"): uma caixa só, do fim da fala até o fim do grupo
            j = 0
            while j < len(linha):
                if linha[j][1]:
                    k = j
                    while k + 1 < len(linha) and linha[k + 1][1]:
                        k += 1
                    if k > j:
                        # " \\h": espaço + espaço fixo, o mesmo respiro das palavras soltas
                        frase = " \\h".join(w for w, *_ in linha[j:k + 1]).replace("{", "(").replace("}", ")")
                        xc_f = round((pos[j][0] + pos[k][0] + pos[k][1]) / 2)
                        eventos.append(f"Dialogue: 2,{_ts(t(linha[k][2]))},{_ts(fim)},Caixa,,0,0,0,,"
                                       f"{{\\an5\\pos({xc_f},{y})\\fad(0,120)}}{frase}")
                    j = k + 1
                else:
                    j += 1
            for j, (p, dest, a, b) in enumerate(linha):
                # cada palavra é um evento com posição própria (texto e caixa no MESMO ponto)
                txt = p.replace("{", "(").replace("}", ")")
                w_p = _larg_palavra(f, p)
                xc = round(x + w_p / 2)
                a_v = t(a)
                # entra subindo 10 px e assenta (curva que desacelera, sem passar do ponto)
                eventos.append(f"Dialogue: 0,{_ts(a_v)},{_ts(fim)},Base,,0,0,0,,"
                               f"{{\\an5\\move({xc},{y + 10},{xc},{y},0,180)\\fad(90,120)\\fscx94\\fscy94"
                               f"\\t(0,200,0.5,\\fscx100\\fscy100)}}{txt}")
                # caixa branca enquanto a palavra é falada (destaque: fica até o fim do grupo)
                em_frase = dest and ((j + 1 < len(linha) and linha[j + 1][1]) or (j > 0 and linha[j - 1][1]))
                b_v = fim if (dest and not em_frase) else max(t(b), a_v + 0.18)
                if j + 1 < len(linha) and not (dest and not em_frase):
                    b_v = min(b_v, t(linha[j + 1][2]) + 0.02)
                eventos.append(f"Dialogue: 1,{_ts(a_v)},{_ts(min(b_v, fim))},Caixa,,0,0,0,,"
                               f"{{\\an5\\move({xc},{y + 10},{xc},{y},0,180)\\fscx88\\fscy88"
                               f"\\t(0,200,0.5,\\fscx100\\fscy100)\\fad(40,{120 if dest else 80})}}{txt}")
                x += w_p + espaco
    Path(out_path).write_text(cab + "\n".join(eventos) + "\n", encoding="utf-8")
    return Path(out_path)


# ------------------------------------------------------------------ visualizador da voz
BARRAS = 27          # barras do visualizador (ímpar: uma no centro)
BARRA_L, BARRA_G = 13, 10  # largura e espaço entre barras (px no desenho 1080)


def _energias(audio: Path, total: float) -> "list":
    """Energia por quadro (30 fps) em faixas da voz (120 a 3.200 Hz), cada faixa na própria escala
    (assim todas as barras se mexem), suavizada: sobe rápido, desce devagar."""
    import numpy as np
    sr = 16000
    bruto = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-ar", str(sr), "-ac", "1", "-f", "s16le", "-"],
                           capture_output=True, check=True).stdout
    x = np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0
    n = int(total * FPS) + 1
    meio = BARRAS // 2 + 1
    bordas = np.geomspace(120, 3200, meio + 1)
    janela = 1024
    hann = np.hanning(janela)
    freqs = np.fft.rfftfreq(janela, 1 / sr)
    sel = [(freqs >= bordas[k]) & (freqs < bordas[k + 1]) for k in range(meio)]
    e = np.zeros((n, meio), dtype=np.float32)
    for i in range(n):
        c = int(i / FPS * sr)
        seg = x[max(c - janela // 2, 0): c + janela // 2]
        if len(seg) < janela:
            seg = np.pad(seg, (0, janela - len(seg)))
        mag = np.abs(np.fft.rfft(seg * hann))
        e[i] = [mag[m].mean() if m.any() else 0.0 for m in sel]
    e = np.log1p(e * 60)
    for k in range(meio):  # cada faixa na própria escala
        col = e[:, k]
        ref = np.percentile(col[col > 0], 95) if (col > 0).any() else 1.0
        e[:, k] = np.clip(col / (ref or 1.0), 0, 1)
    # cada barra segue a voz como uma mola criticamente amortecida (Apple: amortecimento 1.0,
    # resposta ~0,12 s): movimento contínuo, sem tremido nem "pulo" de um quadro para o outro
    w = 2 * np.pi / 0.12
    dt = 1 / FPS
    dec = np.exp(-w * dt)
    pos = np.zeros(meio, dtype=np.float64)
    vel = np.zeros(meio, dtype=np.float64)
    for i in range(n):  # solução exata da mola criticamente amortecida (estável em qualquer passo)
        x0 = pos - e[i]
        c = vel + w * x0
        pos = e[i] + (x0 + c * dt) * dec
        vel = (vel - w * c * dt) * dec
        e[i] = np.clip(pos, 0, 1)
    return e


def visualizador(audio: Path, total: float):
    """Gera os quadros (RGBA) das barras: simétricas a partir do centro, cantos arredondados."""
    import numpy as np
    e = _energias(audio, total)
    meio = e.shape[1]
    lw, gap = z(BARRA_L), z(BARRA_G)
    larg = BARRAS * lw + (BARRAS - 1) * gap
    alt = z(ONDA[3])
    # do centro para as bordas: arco suave (o meio é mais alto), barra mínima visível em silêncio
    peso = 0.45 + 0.55 * np.cos(np.linspace(0, np.pi / 2, meio)) ** 1.5
    for i in range(e.shape[0]):
        img = Image.new("RGBA", (larg, alt), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for b in range(BARRAS):
            k = abs(b - BARRAS // 2)
            h = max(int(lw * 1.6), int(alt * (0.14 + 0.86 * e[i, k] * peso[k])))
            x0 = b * (lw + gap)
            y0 = (alt - h) // 2
            d.rounded_rectangle((x0, y0, x0 + lw - 1, y0 + h - 1), radius=lw // 2, fill=(255, 255, 255, 240))
        yield img.tobytes()


# ------------------------------------------------------------------ montagem
def montar(card: dict, image_path, audio: Path, total: float, out_mp4: Path, pasta: Path) -> Path:
    """Quadro fixo + onda da voz + legenda sincronizada, com a narração."""
    fundo = quadro(card, pasta / "quadro.jpg", image_path)
    meta_p = pasta / "narracao.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    frases = meta.get("frases")
    if not frases:
        import video
        frases = [video._para_fala(f) for f in video.roteiro(card)]
    wav = pasta / "narracao.wav"
    palavras_t = tempo_das_palavras(frases, wav if wav.exists() else None,
                                    total=(total - 1.3) if not wav.exists() else None)
    ass = legenda_ass(palavras_t, card.get("destaques", []), pasta / "legenda.ass",
                      atraso=meta.get("atraso", 0.3), fator=meta.get("fator", 1.0), total=total)
    lw, gap = z(BARRA_L), z(BARRA_G)
    larg = BARRAS * lw + (BARRAS - 1) * gap
    alt = z(ONDA[3])
    x = (VW - larg) // 2                     # visualizador centralizado
    y = z(ONDA[1])
    filtro = (f"[2:v]format=rgba[barras];[0:v][barras]overlay={x}:{y}:shortest=0:format=auto,"
              f"subtitles=filename='{ass}':fontsdir='{FONT_DIR}',fps={FPS},format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(fundo),
           "-i", str(audio),
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{larg}x{alt}", "-framerate", str(FPS), "-i", "-",
           "-filter_complex", filtro, "-map", "[v]", "-map", "1:a", "-t", f"{total:.2f}",
           "-fps_mode", "cfr", "-r", str(FPS),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-profile:v", "high",
           "-level", "5.1" if VIDEO_2K else "4.1", "-maxrate", "14M", "-bufsize", "28M",
           "-pix_fmt", "yuv420p", "-bf", "0", "-g", str(FPS * 2), "-keyint_min", str(FPS * 2),
           "-sc_threshold", "0", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", "-use_editlist", "0", str(out_mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for quadro_barras in visualizador(audio, total):
            proc.stdin.write(quadro_barras)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    erro = proc.stderr.read().decode(errors="ignore")
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg (audiograma): " + erro[-600:])
    return Path(out_mp4)

