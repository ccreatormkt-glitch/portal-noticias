"""Reels da notícia (1080x1920, 9:16) com a ARTE PARADA (sem animação) e a notícia inteira narrada.

Voz principal: a voz do Arthur clonada com o Chatterbox (voz_clonada.py). Reservas: TTS do Gemini
(neural, português do Brasil) e, por último, o Piper (github.com/rhasspy/piper), offline. O vídeo é só a arte estática + a voz,
codificado no padrão aceito pelo Instagram.
"""
import base64
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path

import requests

import render
from config import GEMINI_API_KEY, PIPER_VOICE, STATE_DIR, TTS_MODEL, TTS_VOICE, VOZ_FIXA, VOZ_MOTOR

VW, VH, FPS = 1080, 1920, 30
PAUSA = 0.28  # usado pelo boletim
VOZ_DIR = STATE_DIR.parent / "voices"
HF = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/pt/pt_BR"  # versão fixa
MAX_SEG = 58.0  # vídeo de no máximo 58 s
MAX_FALA = 56.5  # a narração inteira cabe aqui (+ 0,3 s de respiro no início e ~1 s no fim)
MAX_PALAVRAS = 115  # ~47 s no ritmo da voz padrão; se passar, o roteiro é encurtado e refeito
DIRECAO = ("Leia como um locutor de telejornal brasileiro: português do Brasil, voz firme e "
           "acolhedora, ritmo natural e claro, sem pressa e sem exageros. Texto:\n\n")


# ------------------------------------------------------------------ voz (Piper)
def _modelo() -> Path:
    """Baixa a voz na primeira vez (cerca de 60 MB) e reaproveita depois."""
    nome = PIPER_VOICE                       # ex.: pt_BR-faber-medium
    falante, qualidade = nome.split("-")[1], nome.split("-")[2]
    VOZ_DIR.mkdir(parents=True, exist_ok=True)
    onnx, cfg = VOZ_DIR / f"{nome}.onnx", VOZ_DIR / f"{nome}.onnx.json"
    for arq in (onnx, cfg):
        if not arq.exists():
            url = f"{HF}/{falante}/{qualidade}/{arq.name}"
            print(f"[voz] baixando {arq.name}")
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            arq.write_bytes(r.content)
    return onnx


_voz = {}


def falar(texto: str, out_wav: Path) -> float:
    """Sintetiza uma frase e devolve a duração em segundos."""
    from piper import PiperVoice
    from piper.config import SynthesisConfig

    if "v" not in _voz:
        _voz["v"] = PiperVoice.load(_modelo())
    cfg = SynthesisConfig(length_scale=0.95)  # um pouco mais ágil, ritmo de notícia
    with wave.open(str(out_wav), "wb") as wf:
        _voz["v"].synthesize_wav(texto, wf, syn_config=cfg)
    with wave.open(str(out_wav), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def roteiro(card: dict, max_palavras: int = MAX_PALAVRAS) -> list:
    """A notícia escrita para o ouvido: manchete, linha fina, resumo, pontos e chamada final.
    Para na primeira frase que estouraria o limite de palavras (sem pular para frases soltas)."""
    frases = [card["titulo"].rstrip(".") + "."]
    for k in ("linha_fina", "resumo"):
        t = (card.get(k) or "").strip()
        if t:
            frases += [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    for p in card.get("pontos", []) or []:
        p = p.strip().rstrip(".")
        if p:
            frases.append(p + ".")
    final = "Siga o Paraíba Minuto para mais notícias."  # encerramento fixo de todo spot (pedido do Arthur)
    vistas, out = set(), []
    palavras = len(final.split())
    ditas = set()  # palavras importantes já narradas (para não repetir a mesma informação)
    for i, f in enumerate(frases):
        chave = f.lower()
        if chave in vistas or (i > 0 and redundante(f, ditas)):
            continue
        n = len(f.split())
        if palavras + n > max_palavras and i > 0:
            break
        vistas.add(chave)
        out.append(f)
        palavras += n
        ditas |= _importantes(f)
    return out + [final]


def _importantes(frase: str) -> set:
    import sources
    return set(sources.stems_of(frase))


def redundante(frase: str, ditas: set) -> bool:
    """Parâmetro anti-repetição (config.REDUNDANCIA_MAX): a frase repete o que já foi dito?"""
    from config import REDUNDANCIA_MAX
    novas = _importantes(frase)
    if not novas or REDUNDANCIA_MAX >= 1:
        return False
    return len(novas & ditas) / len(novas) >= REDUNDANCIA_MAX


_NUM = r"(\d[\d.,]*)"


def _para_fala(texto: str) -> str:
    """Ajustes para a voz ler direito valores, siglas e horários comuns em notícia local."""
    t = " " + texto + " "
    t = re.sub(r"R\$\s?" + _NUM + r"\s?(mil|milh[aã]o|milh[oõ]es|bilh[aã]o|bilh[oõ]es)\b",
               r"\1 \2 de reais", t)
    t = re.sub(r"R\$\s?" + _NUM, r"\1 reais", t)
    t = re.sub(r"\b(\d{1,2})h(\d{2})\b", r"\1 horas e \2", t)
    t = re.sub(r"\b(\d{1,2})h\b", r"\1 horas", t)
    trocas = {" CG ": " Campina Grande ", " CG,": " Campina Grande,", " CG.": " Campina Grande.",
              " JP ": " João Pessoa ", " JP,": " João Pessoa,", " JP.": " João Pessoa.",
              "CMJP": "Câmara Municipal de João Pessoa", "CMCG": "Câmara Municipal de Campina Grande",
              "ALPB": "Assembleia Legislativa da Paraíba", "-PB": " da Paraíba", "(PB)": "",
              " PB ": " Paraíba ", " PB.": " Paraíba.", " PB,": " Paraíba,",
              "%": " por cento", "km/h": " quilômetros por hora", "nº": "número", "º": "º"}
    for a, b in trocas.items():
        t = t.replace(a, b)
    return " ".join(t.split())


def tts_gemini(texto: str, out_wav: Path):
    """Voz neural do Gemini (uma chamada para o texto todo). Devolve a duração ou None.
    Com VOZ_FIXA, usa só a voz padrão (a da 1ª postagem) e insiste nela se estiver ocupada."""
    if not GEMINI_API_KEY:
        return None
    body = {"contents": [{"parts": [{"text": DIRECAO + texto}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}}}
    modelos = [m.strip() for m in TTS_MODEL.split(",") if m.strip()]
    if VOZ_FIXA:
        modelos = modelos[:1]
    for model in modelos:
        for tentativa in range(5 if VOZ_FIXA else 1):  # limite por minuto do Gemini: insiste com calma
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                  headers={"x-goog-api-key": GEMINI_API_KEY}, json=body, timeout=(10, 120))
                if r.status_code != 200:
                    print(f"[voz] {model}: HTTP {r.status_code}")
                    if r.status_code in (429, 500, 503) and tentativa < 4 and VOZ_FIXA:
                        time.sleep(min(20 * (tentativa + 1), 60))  # 20, 40, 60, 60 s: tenta a mesma voz
                        continue
                    break
                parte = r.json()["candidates"][0]["content"]["parts"][0]
                dados = parte.get("inlineData") or parte.get("inline_data")
                pcm = base64.b64decode(dados["data"])
                taxa = int((re.search(r"rate=(\d+)", dados.get("mimeType", "")) or [0, 24000])[1])
                with wave.open(str(out_wav), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(taxa)
                    wf.writeframes(pcm)
                dur = len(pcm) / 2 / taxa
                print(f"[voz] Gemini {model} ({TTS_VOICE}): {dur:.1f} s")
                return dur
            except Exception as e:
                print(f"[voz] {model}: {type(e).__name__}")
                break
    return None


def _sintetizar(texto: str, wav: Path):
    import voz_clonada
    dur = voz_clonada.sintetizar(texto, wav) if VOZ_MOTOR == "clonada" else None
    if dur is None:
        dur = tts_gemini(texto, wav)
    if dur is None and not VOZ_FIXA:  # reserva: Piper, offline
        print("[voz] usando a voz de reserva (Piper)")
        dur = falar(texto, wav)
    if dur is None:
        raise RuntimeError("voz padrão indisponível agora (limite do Gemini); a notícia volta na próxima rodada")
    return dur


def narrar(card: dict, pasta: Path):
    """Narração da notícia com no máximo ~57 s, sempre inteira (nada é cortado no meio da frase).
    Devolve (arquivo de áudio, duração total do vídeo)."""
    frases = roteiro(card)
    wav = pasta / "narracao.wav"
    dur = _sintetizar(_para_fala(" ".join(frases)), wav)
    if dur > MAX_FALA:  # passou: encurta o roteiro na proporção e narra de novo
        palavras = sum(len(f.split()) for f in frases)
        alvo = int(palavras * (MAX_FALA - 2) / dur)
        frases = roteiro(card, alvo)
        print(f"[voz] {dur:.1f} s passou do limite; roteiro encurtado para ~{alvo} palavras")
        dur = _sintetizar(_para_fala(" ".join(frases)), wav)
    filtro, fator = "adelay=300|300", 1.0
    if dur > MAX_FALA:  # ainda passou (raro): acelera de leve, no máximo 8 %
        fator = min(dur / MAX_FALA, 1.08)
        filtro += f",atempo={fator:.3f}"
        dur = dur / fator
    # o que foi falado e como (a legenda do audiograma usa isso para acompanhar a voz)
    import json
    (pasta / "narracao.json").write_text(json.dumps(
        {"frases": [_para_fala(f) for f in frases], "atraso": 0.3, "fator": fator}, ensure_ascii=False),
        encoding="utf-8")
    total = min(max(dur + 1.3, 5.5), MAX_SEG)
    audio = pasta / "narracao.m4a"
    _ff(["-i", str(wav), "-af", f"{filtro},apad,atrim=0:{total:.2f}",
         "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", str(audio)])
    return audio, total


def _ff(args):
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg: " + r.stderr[-600:])


def montar(card: dict, image_path, out_mp4: Path, audio=None, total=None) -> Path:
    """Arte parada + narração. Sem zoom, sem animação, sem legendas animadas."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg não instalado")
    pasta = Path(out_mp4).with_suffix("")
    pasta.mkdir(parents=True, exist_ok=True)
    if audio is None:
        audio, total = narrar(card, pasta)
    from config import ESTILO_VIDEO
    if ESTILO_VIDEO == "audiograma":
        import audiograma
        try:
            return audiograma.montar(card, image_path, audio, total, Path(out_mp4), pasta)
        except Exception as e:  # nunca deixa de postar por causa do visual: cai no estilo parado
            print(f"[reels] audiograma falhou ({str(e)[:160]}); usando a arte parada")
    quadro = render.render_cover_reels(card, pasta / "arte.jpg", image_path)
    _ff(["-loop", "1", "-framerate", str(FPS), "-i", str(quadro), "-i", str(audio),
         "-map", "0:v", "-map", "1:a", "-t", f"{total:.2f}",
         # taxa de quadros FIXA (o Instagram recusa vídeo com taxa variável)
         "-vf", f"fps={FPS},format=yuv420p", "-fps_mode", "cfr", "-r", str(FPS),
         # perfil conservador aceito pelo Instagram (H.264 High, sem B-frames, GOP fechado,
         # AAC 128 kbps 48 kHz, cabeçalho no início do arquivo)
         # imagem parada: "stillimage" e quadro-chave a cada 4 s (o Instagram pede GOP de 2 a 5 s)
         # deixam o arquivo com metade do tamanho, o que facilita o envio para a Meta
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "stillimage",
         "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-bf", "0",
         "-g", str(FPS * 4), "-keyint_min", str(FPS * 4), "-sc_threshold", "0",
         "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
         "-movflags", "+faststart", "-use_editlist", "0", str(out_mp4)])
    return Path(out_mp4)


def legenda_ia() -> str:
    return "🎙️ Narração com voz gerada por IA."
