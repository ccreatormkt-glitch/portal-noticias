"""Vídeo no estilo audiograma (referência escolhida pelo Arthur): tudo vermelho e branco.

Quadro 1080x1920, sempre igual:
  - topo: logo PB MINUTO + data/hora;
  - foto da notícia numa moldura arredondada, com a EDITORIA fixa no canto de cima
    (lugar que aparece no player, na grade do perfil e fora dos botões do Instagram);
  - a onda da voz, animada com a narração;
  - a legenda sincronizada embaixo, em blocos curtos. Os trechos em destaque (números, nomes,
    valores) trocam de fonte: Montserrat Black no texto, Instrument Serif itálica no destaque.
A primeira legenda é a manchete inteira, então o primeiro quadro funciona como capa.

O tempo de cada frase vem das pausas reais da narração (ffmpeg silencedetect).
"""
import datetime as dt
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
M = 80                                   # margem esquerda (área segura do Instagram)
ONDA = (M, 1010, 800, 90)                # x, y, largura, altura da onda da voz
LEG_Y = 1360                             # centro vertical da legenda (bloco entre ~1160 e ~1560)
LEG_W = 800                              # largura máxima da legenda (longe dos botões da direita)
VERMELHO = tuple(int(BRAND_COLOR.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
VERMELHO_ESCURO = tuple(int(c * 0.78) for c in VERMELHO)
BRANCO = (255, 255, 255)

# fonte da 1ª postagem (Inter) no texto; Instrument Serif itálica só nos destaques
FONTE_TEXTO = ("Inter Black", "Inter-Black.otf", 80)
FONTE_DESTAQUE = ("Instrument Serif", "InstrumentSerif-Italic.ttf", 100)
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


def _sem_foto(card, w, h):
    import render
    fundo = Image.new("RGB", (w, h), VERMELHO_ESCURO)
    f_ic, ch = render.icone(render.ICONE.get(card.get("chapeu", ""), "newspaper"), z(420))
    ImageDraw.Draw(fundo).text((w / 2, h * 0.36), ch, font=f_ic, fill=(255, 255, 255, 255), anchor="mm")
    return fundo


def _tag(d, x, y, texto):
    """Editoria fixa, no formato da 1ª postagem (retângulo de canto curto, Inter Bold):
    branca com texto vermelho, para não sumir sobre o vermelho da marca."""
    f_tag = fonte("Inter-Bold.otf", z(28))
    tw = int(f_tag.getlength(texto))
    d.rounded_rectangle((x, y, x + tw + z(40), y + z(54)), radius=z(8), fill=BRANCO)
    d.text((x + z(20), y + z(27)), texto, font=f_tag, fill=VERMELHO, anchor="lm")
    return y + z(54)


def _credito(d, card, y, imagem, x_dir=None):
    credito = card.get("_credito", "")
    if imagem and credito:
        f_cr = fonte("Inter-Medium.otf", z(18))
        while f_cr.getlength(credito) > z(W - 2 * M) and len(credito) > 10:
            credito = credito[:-2]
        d.text((x_dir or z(W - M), y), credito, font=f_cr, fill=(255, 230, 225), anchor="rs")


def _palavras_com_fonte(texto: str, destaques: list, tamanho: int):
    """[(palavra, fonte, destaque?)] para desenhar a manchete com os destaques na serifada."""
    out = []
    for p, dest in _marcar_destaques(texto.split(), destaques):
        arq = "InstrumentSerif-Italic.ttf" if dest else "Inter-Black.otf"
        out.append((p, fonte(arq, int(tamanho * (1.12 if dest else 1.0))), dest))
    return out


def _quebrar(itens, largura):
    linhas, atual, w = [], [], 0.0
    for p, f, dest in itens:
        lw = f.getlength(p + " ")
        if atual and w + lw > largura:
            linhas.append(atual)
            atual, w = [], 0.0
        atual.append((p, f, dest))
        w += lw
    if atual:
        linhas.append(atual)
    return linhas


def capa(card: dict, out_path: Path, image_path=None) -> Path:
    """Capa do Reels (padrão da 1ª postagem, aprovado pelo Arthur): foto em tela cheia, degradê
    VERMELHO da marca embaixo (no lugar do preto), editoria, manchete em Inter Black alinhada à
    esquerda, cidade/data e crédito. Tudo dentro do corte 3:4 da grade do perfil (y 240 a 1680)."""
    foto = _foto_ou_vazio(image_path, VW, VH)
    img = foto if foto is not None else _sem_foto(card, VW, VH)

    largura = z(W - 2 * M - 30)
    for tam in (84, 78, 72, 66, 60, 54):
        linhas = _quebrar(_palavras_com_fonte(card["titulo"], card.get("destaques", []), z(tam)), largura)
        if len(linhas) <= 5:
            break
    passo = int(z(tam) * 1.13)
    base_ultima = z(1530)                       # última linha da manchete
    topo_texto = base_ultima - passo * (len(linhas) - 1) - int(z(tam) * 0.8)
    y_tag = topo_texto - z(34) - z(54)
    # degradê: transparente bem acima da etiqueta, já forte quando a manchete começa
    img = _degrade(img, 0, z(470), 150, 0)                        # topo: logo legível
    img = _degrade(img, y_tag - z(330), topo_texto, 0, 228)       # pé: vermelho da marca
    d = ImageDraw.Draw(img)
    lg = logo(z(66))
    img.paste(lg, (z(M), z(300)), lg)

    _tag(d, z(M), y_tag, (card.get("chapeu") or "NOTÍCIA").upper())
    y = base_ultima - passo * (len(linhas) - 1)
    for linha in linhas:
        x = z(M)
        for p, f, dest in linha:
            d.text((x, y), p, font=f, fill=BRANCO, anchor="ls")
            x += f.getlength(p + " ")
        y += passo
    meta = [card.get("cidade") or "Paraíba", _carimbo().replace(" · ", ", ").lower()]
    if card.get("_ilustrativa"):
        meta.append("Imagem ilustrativa")
    elif "IA" in card.get("_credito", ""):
        meta.append("Ilustração por IA")
    d.text((z(M), z(1592)), "  ·  ".join(meta), font=fonte("Inter-Medium.otf", z(30)),
           fill=(255, 232, 228), anchor="ls")
    _credito(d, card, z(1648), foto is not None)
    img.save(out_path, quality=94)
    return Path(out_path)


def quadro(card: dict, out_path: Path, image_path=None) -> Path:
    """Fundo fixo do vídeo: a MESMA imagem da capa com efeito vermelho (duotone da marca),
    logo e editoria no topo; embaixo, vermelho sólido para a onda da voz e a legenda."""
    from PIL import ImageOps
    foto = _foto_ou_vazio(image_path, VW, VH)
    if foto is not None:
        claro = tuple(min(255, int(c + (255 - c) * 0.80)) for c in VERMELHO)
        duo = ImageOps.colorize(ImageOps.autocontrast(ImageOps.grayscale(foto), cutoff=1),
                                black=tuple(int(c * 0.45) for c in VERMELHO), white=claro)
        img = Image.blend(duo, foto, 0.38)  # vermelho da marca, mas a foto continua reconhecível
    else:
        img = _sem_foto(card, VW, VH)
    img = _degrade(img, 0, z(560), 140, 0)          # topo: identificação legível
    img = _degrade(img, z(640), z(1000), 0, 245)    # embaixo: vermelho sólido para voz e legenda
    d = ImageDraw.Draw(img)
    lg = logo(z(66))
    img.paste(lg, (z(M), z(300)), lg)
    fim_tag = _tag(d, z(M), z(396), (card.get("chapeu") or "NOTÍCIA").upper())   # editoria fixa
    cidade = card.get("cidade") or "Paraíba"
    d.text((z(M), fim_tag + z(52)), f"{cidade}  ·  {_carimbo().replace(' · ', ', ').lower()}",
           font=fonte("Inter-SemiBold.otf", z(28)), fill=(255, 236, 232), anchor="ls")
    _credito(d, card, z(960), foto is not None)
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
        segs, _ = _cache_whisper["modelo"].transcribe(str(wav), language="pt", word_timestamps=True,
                                                      beam_size=1, vad_filter=False)
        return [(w.word.strip(), float(w.start), float(w.end)) for sg in segs for w in (sg.words or [])]
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


def _largura(palavra: str, destaque: bool, escala=1.0) -> float:
    nome, arq, tam = FONTE_DESTAQUE if destaque else FONTE_TEXTO
    return fonte(arq, int(tam * escala)).getlength(palavra + " ")


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


def legenda_ass(palavras_t: list, destaques: list, out_path: Path, atraso=0.3, fator=1.0, total=None) -> Path:
    """Legenda dinâmica (estilo TikTok/Remotion): cada página fica na tela até a próxima e cada
    palavra aparece no instante em que é falada, com um leve "pop"."""
    nome, _, tam = FONTE_TEXTO
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{nome},{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,2,4,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    t = lambda x: x / fator + atraso  # noqa: E731  (tempo do áudio original -> tempo do vídeo)
    pags = paginas(palavras_t, destaques)
    eventos = []
    for n, pag in enumerate(pags):
        ini = t(pag[0][2])
        fim = t(pags[n + 1][0][2]) if n + 1 < len(pags) else (total or t(pag[-1][3]) + 1.0)
        partes, w = [], 0.0
        for p, d, a, b in pag:
            lw = _largura(p, d)
            quebra = "\\N" if partes and w + lw > LEG_W else ""
            if quebra:
                w = 0.0
            w += lw
            ms = max(round((t(a) - ini) * 1000), 0)
            p = p.replace("{", "(").replace("}", ")")
            fonte_tag = f"\\fn{FONTE_DESTAQUE[0]}\\i1\\fs{FONTE_DESTAQUE[2]}" if d else f"\\fn{nome}\\i0\\fs{tam}"
            pico = 120 if d else 110  # destaque quebra o padrão: "pop" maior
            surge = (f"{{{fonte_tag}\\alpha&HFF&\\fscx85\\fscy85"
                     f"\\t({ms},{ms + 70},\\alpha&H00&\\fscx{pico}\\fscy{pico})"
                     f"\\t({ms + 70},{ms + 170},\\fscx100\\fscy100)}}")
            partes.append(("" if not partes else (quebra or " ")) + surge + p)
        eventos.append(f"Dialogue: 0,{_ts(ini)},{_ts(fim)},Base,,0,0,0,,{{\\an4\\pos({M},{LEG_Y})\\fad(0,120)}}"
                       + "".join(partes))
    Path(out_path).write_text(cab + "\n".join(eventos) + "\n", encoding="utf-8")
    return Path(out_path)


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
    x, y, w, h = (z(v) for v in ONDA)
    filtro = (f"[1:a]showwaves=s={w}x{h}:mode=cline:rate={FPS}:colors=white:scale=sqrt:draw=full,"
              f"format=rgba,colorkey=black:0.1:0.0[onda];"
              f"[0:v][onda]overlay={x}:{y}:shortest=0,"
              f"subtitles=filename='{ass}':fontsdir='{FONT_DIR}',fps={FPS},format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(fundo),
           "-i", str(audio), "-filter_complex", filtro, "-map", "[v]", "-map", "1:a", "-t", f"{total:.2f}",
           "-fps_mode", "cfr", "-r", str(FPS),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-profile:v", "high",
           "-level", "5.1" if VIDEO_2K else "4.1", "-maxrate", "14M", "-bufsize", "28M",
           "-pix_fmt", "yuv420p", "-bf", "0", "-g", str(FPS * 2), "-keyint_min", str(FPS * 2),
           "-sc_threshold", "0", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", "-use_editlist", "0", str(out_mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg (audiograma): " + r.stderr[-600:])
    return Path(out_mp4)
