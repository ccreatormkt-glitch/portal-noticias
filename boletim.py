"""Boletim "Bom dia, Paraíba": Reels diário de manhã com a previsão do tempo de
Campina Grande e João Pessoa (INMET, dados públicos do governo) e os destaques das últimas 24h.

  python main.py boletim [--dry-run]
"""
import datetime as dt
import re
import sqlite3
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFilter

import config
import db
import render
import video

CIDADES = {"Campina Grande": "2504009", "João Pessoa": "2507507"}  # códigos IBGE
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]
VW, VH = video.VW, video.VH


# ------------------------------------------------------------------ dados
def previsao(geocode: str, hoje: dt.date) -> dict:
    """Previsão do INMET para hoje: resumo do dia, mínima e máxima."""
    r = requests.get(f"https://apiprevmet3.inmet.gov.br/previsao/{geocode}", timeout=30)
    r.raise_for_status()
    dias = r.json()[geocode]
    dia = dias.get(hoje.strftime("%d/%m/%Y")) or next(iter(dias.values()))
    periodos = [dia[p] for p in ("manha", "tarde", "noite") if isinstance(dia.get(p), dict)] or [dia]
    tmax = max(int(p["temp_max"]) for p in periodos)
    tmin = min(int(p["temp_min"]) for p in periodos)
    tarde = dia.get("tarde") if isinstance(dia.get("tarde"), dict) else periodos[0]
    return {"resumo": tarde.get("resumo", "").strip(), "min": tmin, "max": tmax}


def destaques(n=3) -> list:
    """Títulos publicados nas últimas 24h, do maior potencial para o menor."""
    since = time.time() - 24 * 3600
    with sqlite3.connect(db.DB_PATH) as c:
        try:
            rows = c.execute(
                "SELECT p.headline FROM posts p LEFT JOIN meta m ON m.fp = p.fp "
                "WHERE p.status='published' AND p.ts > ? ORDER BY COALESCE(m.potencial,3) DESC, p.ts DESC",
                (since,)).fetchall()
        except sqlite3.OperationalError:
            return []
    vistos, out = set(), []
    for (h,) in rows:
        if h and h not in vistos:
            vistos.add(h)
            out.append(h)
    return out[:n]


def icone_tempo(resumo: str) -> str:
    r = resumo.lower()
    if "trovoada" in r or "tempestade" in r:
        return "thunderstorm"
    if "chuva" in r or "pancada" in r or "chuvisco" in r:
        return "water_drop"
    if "nublado" in r or "encoberto" in r or "nuvens" in r:
        return "cloud" if "poucas" not in r else "wb_cloudy"
    return "wb_sunny"


# ------------------------------------------------------------------ cenas
def _base():
    img = Image.new("RGBA", (VW, VH), render.NAVY + (255,))
    glow = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((VW * 0.3, -VH * 0.25, VW * 1.5, VH * 0.35), fill=render.ACCENT + (70,))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(160)))
    render.logo(img, 64, 300, altura=72)
    return img


def cena_abertura(hoje: dt.date, out: Path) -> Path:
    img = _base()
    d = ImageDraw.Draw(img)
    d.text((64, 640), "Bom dia,", font=render.font("Bold", 120), fill=render.WHITE)
    d.text((64, 780), "Paraíba", font=render.font("Black", 140), fill=render.ACCENT)
    data = f"{DIAS[hoje.weekday()].capitalize()}, {hoje.day} de {MESES[hoje.month - 1]}"
    d.text((64, 990), data, font=render.font("SemiBold", 48), fill=render.SOFT)
    d.text((64, 1080), "O que você precisa saber para começar o dia", font=render.font("Regular", 38),
           fill=render.SOFT)
    img.convert("RGB").save(out, quality=92)
    return out


def cena_tempo(tempos: dict, out: Path) -> Path:
    img = _base()
    d = ImageDraw.Draw(img)
    d.rectangle((64, 520, 70, 556), fill=render.ACCENT)
    d.text((86, 538), "PREVISÃO DO TEMPO", font=render.font("Bold", 30), fill=render.ACCENT, anchor="lm")
    y = 620
    cartoes = Image.new("RGBA", (VW, VH), (0, 0, 0, 0))   # translúcidos numa camada própria
    cd = ImageDraw.Draw(cartoes)
    for i in range(len(tempos)):
        cd.rounded_rectangle((64, y + i * 460, VW - 64, y + i * 460 + 420), radius=44, fill=(255, 255, 255, 22))
    img.alpha_composite(cartoes)
    d = ImageDraw.Draw(img)
    for cidade, p in tempos.items():
        f, ch = render.icone(icone_tempo(p["resumo"]), 170)
        d.text((104, y + 120), ch, font=f, fill=render.ACCENT)
        d.text((320, y + 64), cidade, font=render.font("Bold", 56), fill=render.WHITE)
        fr, linhas = render.fit(p["resumo"] or "Previsão", "Regular", (38, 34, 30), VW - 64 - 320 - 40, 2)
        yy = y + 148
        for ln in linhas:
            d.text((320, yy), ln, font=fr, fill=render.SOFT)
            yy += int(fr.size * 1.25)
        d.text((320, y + 262), f"{p['min']}°  /  {p['max']}°", font=render.font("Black", 92), fill=render.WHITE)
        y += 460
    d.text((64, y + 10), "Fonte: INMET", font=render.font("Medium", 28), fill=render.SOFT)
    img.convert("RGB").save(out, quality=92)
    return out


def cena_destaques(titulos: list, out: Path) -> Path:
    img = _base()
    d = ImageDraw.Draw(img)
    d.rectangle((64, 520, 70, 556), fill=render.ACCENT)
    d.text((86, 538), "DESTAQUES DAS ÚLTIMAS 24H", font=render.font("Bold", 30), fill=render.ACCENT, anchor="lm")
    y = 650
    f = render.font("SemiBold", 54)
    for i, t in enumerate(titulos, 1):
        linhas = render.wrap(render.clean(t), f, VW - 64 - 160)[:3]
        d.text((64, y - 8), str(i), font=render.font("Black", 92), fill=render.ACCENT)
        yy = y
        for ln in linhas:
            d.text((160, yy), ln, font=f, fill=render.WHITE)
            yy += 68
        y = yy + 80
        if i < len(titulos):
            d.line((160, y - 40, VW - 64, y - 40), fill=(44, 58, 90), width=2)
    img.convert("RGB").save(out, quality=92)
    return out


# ------------------------------------------------------------------ roteiro e vídeo
def roteiro(hoje, tempos, titulos):
    data = f"{DIAS[hoje.weekday()]}, {hoje.day} de {MESES[hoje.month - 1]}"
    falas = [("abertura", f"Bom dia, Paraíba! Hoje é {data}. Veja o que você precisa saber.")]
    t = " ".join(f"Em {c}, {p['resumo'].lower() or 'tempo estável'}, com mínima de {p['min']} "
                 f"e máxima de {p['max']} graus." for c, p in tempos.items())
    falas.append(("tempo", t))
    if titulos:
        falas.append(("destaques", "Os destaques: " + " ".join(f"{t.rstrip('.')}." for t in titulos)))
    falas.append(("fim", f"Siga o {render.PORTAL_NAME} e bom dia!"))
    return falas


def montar(hoje: dt.date, tempos: dict, titulos: list, pasta: Path) -> tuple:
    pasta.mkdir(parents=True, exist_ok=True)
    cenas = {"abertura": cena_abertura(hoje, pasta / "c0.jpg"),
             "tempo": cena_tempo(tempos, pasta / "c1.jpg")}
    if titulos:
        cenas["destaques"] = cena_destaques(titulos, pasta / "c2.jpg")
    cenas["fim"] = cenas["abertura"]

    # áudio por cena
    blocos = []
    for i, (cena, fala) in enumerate(roteiro(hoje, tempos, titulos)):
        wav = pasta / f"f{i}.wav"
        dur = video.falar(video._para_fala(fala), wav)
        blocos.append((cenas[cena], wav, dur + 0.5))
    return _render(blocos, pasta / "boletim.mp4"), cenas["abertura"]


def _render(blocos, out: Path) -> Path:
    """Cada cena dura o tempo da sua fala; transição suave entre cenas; barra de progresso."""
    xf = 0.4
    entradas, f, audios = [], [], []
    for i, (img, wav, dur) in enumerate(blocos):
        entradas += ["-loop", "1", "-t", f"{dur + xf:.2f}", "-i", str(img)]
    for i, (_, wav, _) in enumerate(blocos):
        entradas += ["-i", str(wav)]
    n = len(blocos)
    for i in range(n):
        f.append(f"[{i}:v]scale={VW}:{VH},fps={video.FPS},format=yuv420p,setsar=1[v{i}]")
    atual, offset = "v0", 0.0
    for i in range(1, n):
        offset += blocos[i - 1][2]
        f.append(f"[{atual}][v{i}]xfade=transition=fade:duration={xf}:offset={offset - xf / 2:.2f}[x{i}]")
        atual = f"x{i}"
    total = sum(b[2] for b in blocos)
    barra = Image.new("RGB", (VW, 10), render.ACCENT)
    barra_p = out.parent / "barra.png"
    barra.save(barra_p)
    entradas += ["-loop", "1", "-i", str(barra_p)]
    f.append(f"[{atual}][{2 * n}:v]overlay=x='-{VW}+{VW}*t/{total:.2f}':y=0:shortest=1[vb]")
    # áudio: cada fala começa no início da sua cena
    t0 = 0.0
    for i, (_, _, dur) in enumerate(blocos):
        ms = int(t0 * 1000) + 150
        f.append(f"[{n + i}:a]adelay={ms}|{ms}[a{i}]")
        audios.append(f"[a{i}]")
        t0 += dur
    f.append(f"{''.join(audios)}amix=inputs={n}:normalize=0,apad,atrim=0:{total:.2f}[aout]")
    video._ff(entradas + ["-filter_complex", ";".join(f), "-map", "[vb]", "-map", "[aout]",
                          "-t", f"{total:.2f}", "-r", str(video.FPS), "-c:v", "libx264", "-preset", "veryfast",
                          "-crf", "21", "-profile:v", "high", "-level", "4.1", "-bf", "0",
                          "-g", str(video.FPS * 2), "-keyint_min", str(video.FPS * 2), "-sc_threshold", "0",
                          "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                          "-movflags", "+faststart", "-use_editlist", "0", str(out)])
    return out


def legenda(hoje, tempos, titulos) -> str:
    data = f"{DIAS[hoje.weekday()]}, {hoje.day} de {MESES[hoje.month - 1]}"
    linhas = [f"☀️ Bom dia, Paraíba! Hoje é {data}.", "🌦️ Previsão do tempo (INMET):"]
    linhas += [f"• {c}: {p['resumo'] or 'tempo estável'}, {p['min']}° a {p['max']}°" for c, p in tempos.items()]
    if titulos:
        linhas += ["", "📌 Destaques das últimas 24h:"] + [f"• {t}" for t in titulos]
    linhas += ["", "Salve e mande para quem está começando o dia.", "",
               "🎙️ Narração com voz gerada por IA.",
               f"👉 Siga {config.PORTAL_HANDLE} para acompanhar Campina Grande, João Pessoa e toda a Paraíba.",
               "", "#bomdia #campinagrande #joaopessoa #paraiba #previsaodotempo"]
    return "\n".join(linhas)


def rodar(dry=False):
    import publish

    hoje = dt.datetime.now(ZoneInfo(config.TIMEZONE)).date()
    marca = config.STATE_DIR / "boletim_ultimo.txt"
    if not dry and marca.exists() and marca.read_text().strip() == hoje.isoformat():
        print("[boletim] já publicado hoje")
        return
    tempos = {}
    for cidade, geo in CIDADES.items():
        try:
            tempos[cidade] = previsao(geo, hoje)
        except Exception as e:
            print(f"[boletim] sem previsão para {cidade} ({type(e).__name__})")
    if not tempos:
        raise RuntimeError("INMET indisponível: boletim não sai sem a previsão")
    titulos = destaques()
    pasta = config.OUT_DIR / f"boletim_{hoje.isoformat()}"
    mp4, capa = montar(hoje, tempos, titulos, pasta)
    texto = legenda(hoje, tempos, titulos)
    print(f"[boletim] vídeo: {mp4}\n{texto}")
    if dry:
        return mp4
    cover = None
    try:
        cover = publish.host_image(Path(capa))
    except Exception as e:
        print(f"[boletim] capa sem link ({str(e)[:100]})")
    mid = publish.post_reel(mp4, texto, cover_url=cover)
    marca.write_text(hoje.isoformat())
    db.log({"event": "boletim", "ig_id": mid, "headline": f"Bom dia, Paraíba {hoje.isoformat()}"})
    print(f"[boletim] publicado {mid}")
    return mp4
