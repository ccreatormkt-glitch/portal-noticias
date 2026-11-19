"""Voz clonada do Arthur com o Chatterbox (github.com/resemble-ai/chatterbox, licença MIT).

A referência é a própria voz do Arthur (uso autorizado por ele no PB Minuto). Ela NÃO fica no
código (o repositório é público): vem do Secret VOZ_REFERENCIA_B64 (áudio Opus em base64) ou,
em testes locais, de brand/voz_referencia.wav (ignorado pelo git). Todo áudio gerado leva a marca d'água inaudível Perth da Resemble AI.
Roda no processador (CPU) do GitHub Actions. Se demorar demais ou falhar, a narração cai para
a voz do Gemini e, por último, para o Piper.
"""
import re
import time
import wave
from pathlib import Path

import base64
import os
import subprocess
import tempfile

REFERENCIA = Path(__file__).parent / "brand" / "voz_referencia.wav"
_modelo = {}


def _referencia():
    """Caminho do áudio de referência: do Secret (decodificado num arquivo temporário) ou local."""
    if REFERENCIA.exists():
        return REFERENCIA
    b64 = os.environ.get("VOZ_REFERENCIA_B64", "").strip()
    if not b64:
        return None
    pasta = Path(tempfile.gettempdir())
    ogg, wav = pasta / "voz_ref.ogg", pasta / "voz_ref.wav"
    if not wav.exists():
        ogg.write_bytes(base64.b64decode(b64))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(ogg), "-ac", "1", "-ar", "24000", str(wav)],
                       check=True)
    return wav


def disponivel() -> bool:
    if not _referencia():
        return False
    try:
        import chatterbox  # noqa: F401
        return True
    except ImportError:
        return False


def _blocos(texto: str, limite=220) -> list:
    """Frases agrupadas em blocos curtos: o modelo fala melhor em trechos de até ~220 caracteres."""
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]
    blocos, atual = [], ""
    for f in frases:
        if atual and len(atual) + len(f) + 1 > limite:
            blocos.append(atual)
            atual = f
        else:
            atual = f"{atual} {f}".strip()
    if atual:
        blocos.append(atual)
    return blocos


def sintetizar(texto: str, out_wav: Path, prazo_s=300):
    """Gera a narração com a voz clonada. Devolve a duração em segundos, ou None se não der."""
    if not disponivel():
        return None
    try:
        import numpy as np
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        inicio = time.monotonic()
        torch.set_num_threads(max(1, torch.get_num_threads()))
        if "erro" in _modelo:
            return None  # já falhou nesta rodada: não perde tempo tentando de novo
        if "m" not in _modelo:
            # o modelo foi salvo numa placa de vídeo (CUDA); aqui só há processador
            _load = torch.load
            torch.load = lambda *a, **k: _load(*a, **{**k, "map_location": torch.device("cpu")})
            try:
                _modelo["m"] = ChatterboxMultilingualTTS.from_pretrained(device=torch.device("cpu"))
            finally:
                torch.load = _load
            _modelo["m"].prepare_conditionals(str(_referencia()), exaggeration=0.45)
        m = _modelo["m"]
        partes, pausa = [], np.zeros(int(m.sr * 0.25), dtype=np.float32)
        for bloco in _blocos(texto):
            if time.monotonic() - inicio > prazo_s:
                print("[voz] voz clonada passou do tempo; usando a reserva")
                return None
            with torch.inference_mode():
                wav = m.generate(bloco, language_id="pt", exaggeration=0.45, cfg_weight=0.5)
            partes += [wav.squeeze(0).cpu().numpy().astype(np.float32), pausa]
        audio = np.concatenate(partes)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(out_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(m.sr)
            wf.writeframes(pcm.tobytes())
        print(f"[voz] voz clonada (Chatterbox) em {time.monotonic() - inicio:.0f}s")
        return len(pcm) / m.sr
    except Exception as e:
        _modelo["erro"] = True
        print(f"[voz] voz clonada falhou ({type(e).__name__}: {str(e)[:120]}); usando a reserva")
        return None
