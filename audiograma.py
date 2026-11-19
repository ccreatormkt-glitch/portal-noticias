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

W, H, FPS = 1080, 1920, 30
M = 72                                   # margem lateral
FOTO = (M, 320, W - M, 950)              # moldura da foto
ONDA = (M, 985, W - 2 * M, 110)          # x, y, largura, altura da onda da voz
LEG_Y = 1330                             # centro da legenda (fica entre 1130 e 1530)
LEG_W = 860                              # largura máxima da legenda (longe dos botões da direita)
VERMELHO = tuple(int(BRAND_COLOR.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
VERMELHO_ESCURO = tuple(int(c * 0.78) for c in VERMELHO)
BRANCO = (255, 255, 255)

FONTE_TEXTO = ("Montserrat Black", "Montserrat-Black.ttf", 88)
FONTE_DESTAQUE = ("Instrument Serif", "InstrumentSerif-Italic.ttf", 112)
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


def quadro(card: dict, out_path: Path, image_path=None) -> Path:
    """Fundo fixo do vídeo (tudo que não se mexe)."""
    import render  # ícone da editoria quando não houver imagem
    img = Image.new("RGB", (W, H), VERMELHO)
    d = ImageDraw.Draw(img)

    lg = logo(64)
    img.paste(lg, (M, 200), lg)
    d.text((W - M, 232), _carimbo(), font=fonte("Montserrat-ExtraBold.ttf", 26),
           fill=(255, 225, 220), anchor="rm")

    x0, y0, x1, y1 = FOTO
    fw, fh = x1 - x0, y1 - y0
    if image_path and Path(image_path).exists():
        foto = _cobrir(Image.open(image_path).convert("RGB"), fw, fh)
        sombra = Image.new("RGBA", (fw, 220), (0, 0, 0, 0))  # escurece o pé da foto para o crédito
        ds = ImageDraw.Draw(sombra)
        for i in range(220):
            ds.line((0, i, fw, i), fill=(0, 0, 0, int(150 * (i / 220) ** 1.6)))
        foto = foto.convert("RGBA")
        foto.alpha_composite(sombra, (0, fh - 220))
        foto = foto.convert("RGB")
    else:
        foto = Image.new("RGB", (fw, fh), VERMELHO_ESCURO)
        f_ic, ch = render.icone(render.ICONE.get(card.get("chapeu", ""), "newspaper"), 300)
        ImageDraw.Draw(foto).text((fw / 2, fh / 2), ch, font=f_ic, fill=BRANCO, anchor="mm")
    img.paste(foto, (x0, y0), _mascara(fw, fh, 40))

    # editoria fixa: cápsula branca com texto vermelho, sempre no canto de cima da foto
    chapeu = (card.get("chapeu") or "NOTÍCIA").upper()
    f_tag = fonte("Montserrat-Black.ttf", 30)
    tw = int(f_tag.getlength(chapeu))
    tx, ty = x0 + 28, y0 + 28
    d.rounded_rectangle((tx, ty, tx + tw + 48, ty + 60), radius=30, fill=BRANCO)
    d.text((tx + 24, ty + 31), chapeu, font=f_tag, fill=VERMELHO, anchor="lm")

    credito = card.get("_credito", "")
    if image_path and credito:
        f_cr = fonte("Montserrat-ExtraBold.ttf", 20)
        while f_cr.getlength(credito) > fw - 60 and len(credito) > 10:
            credito = credito[:-2]
        d.text((x1 - 24, y1 - 22), credito, font=f_cr, fill=(255, 255, 255), anchor="rs")

    cidade = card.get("cidade") or "Paraíba"
    d.text((M, 1600), f"{PORTAL_HANDLE}  ·  {cidade.upper()}", font=fonte("Montserrat-ExtraBold.ttf", 28),
           fill=(255, 225, 220), anchor="lm")
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


def legenda_ass(frases: list, tempos: list, destaques: list, out_path: Path,
                atraso=0.3, fator=1.0, total=None) -> Path:
    nome, _, tam = FONTE_TEXTO
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{nome},{tam},&H00FFFFFF,&H00FFFFFF,&H00000000,&H50000000,0,0,0,0,100,100,0,0,1,0,2,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    eventos = []
    for k, (frase, (ini, fim)) in enumerate(zip(frases, tempos)):
        ini, fim = ini / fator + atraso, fim / fator + atraso
        if k + 1 < len(tempos):  # a legenda fica na tela durante a pausa, até a próxima frase
            fim = tempos[k + 1][0] / fator + atraso
        elif total:
            fim = total
        partes = blocos(frase, destaques, manchete=(k == 0))
        pesos = [sum(len(p) for linha in ls for p, _ in linha) or 1 for ls, _ in partes]
        t = ini
        for (ls, escala), peso in zip(partes, pesos):
            d = (fim - ini) * peso / sum(pesos)
            texto = "\\N".join(_ass_linha(linha, escala) for linha in ls)
            fs = f"\\fs{int(tam * escala)}" if escala != 1.0 else ""
            efeito = f"{{\\pos({W // 2},{LEG_Y}){fs}\\fad(90,0)\\fscx94\\fscy94\\t(0,140,\\fscx100\\fscy100)}}"
            eventos.append(f"Dialogue: 0,{_ts(t)},{_ts(t + d)},Base,,0,0,0,,{efeito}{texto}")
            t += d
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
    tempos = tempos_das_frases(frases, wav if wav.exists() else None,
                               total=(total - 1.3) if not wav.exists() else None)
    ass = legenda_ass(frases, tempos, card.get("destaques", []), pasta / "legenda.ass",
                      atraso=meta.get("atraso", 0.3), fator=meta.get("fator", 1.0), total=total)
    x, y, w, h = ONDA
    filtro = (f"[1:a]showwaves=s={w}x{h}:mode=cline:rate={FPS}:colors=white:scale=sqrt:draw=full,"
              f"format=rgba,colorkey=black:0.1:0.0[onda];"
              f"[0:v][onda]overlay={x}:{y}:shortest=0,"
              f"subtitles=filename='{ass}':fontsdir='{FONT_DIR}',fps={FPS},format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(FPS), "-i", str(fundo),
           "-i", str(audio), "-filter_complex", filtro, "-map", "[v]", "-map", "1:a", "-t", f"{total:.2f}",
           "-fps_mode", "cfr", "-r", str(FPS),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-profile:v", "high", "-level", "4.1",
           "-pix_fmt", "yuv420p", "-bf", "0", "-g", str(FPS * 2), "-keyint_min", str(FPS * 2),
           "-sc_threshold", "0", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
           "-movflags", "+faststart", "-use_editlist", "0", str(out_mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg (audiograma): " + r.stderr[-600:])
    return Path(out_mp4)
