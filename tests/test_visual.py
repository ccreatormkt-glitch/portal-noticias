from pathlib import Path
import shutil
import subprocess

import pytest
from conftest import card
from PIL import Image

import render
import video


@pytest.mark.parametrize("titulo", [
    "Chuva alaga JP",
    "Prefeitura de Campina Grande anuncia mudança no transporte público a partir de segunda e passageiros devem ficar atentos às novas linhas",
    "Ônibus, pão, açúcar e café: preços sobem em João Pessoa, diz Procon",
])
def test_capas_cabem_em_qualquer_titulo(titulo, tmp_path):
    c = card(titulo=titulo[:105])
    p = render.render_cover(c, tmp_path / "a.jpg")
    assert Image.open(p).size == (1080, 1350)
    r = render.render_cover_reels(c, tmp_path / "b.jpg")
    assert Image.open(r).size == (1080, 1920)


def test_sem_cidade_e_editoria_desconhecida_nao_quebram(tmp_path):
    c = card(cidade="", chapeu="OUTRA")
    render.render_cover_reels(c, tmp_path / "c.jpg")
    render.render_details(c, tmp_path / "d.jpg")


def test_roteiro_de_narracao_le_a_noticia_inteira():
    c = card(linha_fina="Prazo vai até sexta.", resumo="São 500 vagas. Inscrição gratuita.",
             pontos=["Vagas para todo o estado", "Inscrição pela internet"])
    frases = video.roteiro(c)
    assert frases[0].endswith(".") and frases[-1] == "Siga o Paraíba Minuto para mais notícias."
    texto = " ".join(frases)
    assert "Prazo vai até sexta." in texto and "Inscrição pela internet." in texto
    assert len(texto.split()) <= 150  # cabe em ~55 s


def test_fala_le_valores_siglas_e_horas():
    f = video._para_fala
    assert f("esquema de R$ 4 milhões") == "esquema de 4 milhões de reais"
    assert f("custa R$ 10") == "custa 10 reais"
    assert "Campina Grande" in f("em CG hoje") and "Câmara Municipal de João Pessoa" in f("a CMJP votou")
    assert "13 horas e 55" in f("às 13h55")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_video_reels_no_padrao_do_instagram(tmp_path):
    c = card()
    audio = tmp_path / "a.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", "6", "-c:a", "aac", str(audio)], check=True)
    out = video.montar(c, None, tmp_path / "r.mp4", audio=audio, total=6.0)
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                           "stream=codec_name,width,height,has_b_frames,sample_rate", "-of", "json", str(out)],
                          capture_output=True, text=True).stdout
    import audiograma
    assert f'"width": {audiograma.VW}' in info and f'"height": {audiograma.VH}' in info  # 2K vertical
    assert '"has_b_frames": 0' in info and '"sample_rate": "48000"' in info


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_video_leve_com_quadro_chave_a_cada_4s(tmp_path, monkeypatch):
    """Estilo estático: arquivo leve; o Instagram pede GOP fechado de 2 a 5 s."""
    import config
    monkeypatch.setattr(config, "ESTILO_VIDEO", "estatico")
    c = card()
    audio = tmp_path / "a.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", "12", "-c:a", "aac", str(audio)], check=True)
    out = video.montar(c, None, tmp_path / "r.mp4", audio=audio, total=12.0)
    chaves = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-skip_frame", "nokey",
                             "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(out)],
                            capture_output=True, text=True).stdout.split()
    assert [round(float(t.strip(","))) for t in chaves if t.strip(",")] == [0, 4, 8]
    assert out.stat().st_size < 1_500_000  # 12 s de imagem parada + voz


def test_licencas_de_foto():
    import illustrate
    assert illustrate._licenca_ok("CC BY-SA 4.0") and illustrate._licenca_ok("CC0")
    assert illustrate._licenca_ok("Public domain")
    assert not illustrate._licenca_ok("CC BY-NC 2.0") and not illustrate._licenca_ok("CC BY-ND 4.0")
    assert not illustrate._licenca_ok("All rights reserved") and not illustrate._licenca_ok("")


def test_credito_aparece_na_capa(tmp_path):
    from conftest import card
    c = card(_credito="Foto: Fulano de Tal / Wikimedia Commons (CC BY-SA 4.0)", _ilustrativa=True)
    out = render.render_cover_reels(c, tmp_path / "c.jpg")
    assert out.exists()


def test_foto_so_da_cidade_citada():
    import illustrate
    c = card(titulo="Shopping de Campina Grande abre no feriado", cidade="Campina Grande")
    assert illustrate.cidades_citadas(c)[0] == "Campina Grande"
    c = card(titulo="Homem é preso em Patos", cidade="Paraíba", resumo="Caso no Sertão.")
    assert illustrate.cidades_citadas(c) == ["Patos"]
    assert illustrate.cidades_citadas(card(titulo="Inflação sobe no país", cidade="Brasil", resumo="")) == []


def test_reserva_vista_geral_da_cidade(monkeypatch, tmp_path):
    """Sem foto específica, sem IA e sem foto da matéria: usa a vista geral da cidade citada."""
    import illustrate
    c = card(titulo="Atlético e Campinense jogam em Cajazeiras", cidade="Cajazeiras", chapeu="ESPORTE")
    monkeypatch.setattr(illustrate, "foto_parecida", lambda card, base: None)
    monkeypatch.setattr(illustrate, "ilustracao_ia", lambda card, out: None)
    monkeypatch.setattr(illustrate, "_original", lambda card: None)
    buscas = []

    def commons(q, out, exigir=(), repetir=False, sem=None):
        buscas.append((q, tuple(exigir), repetir))
        if repetir:
            Path(out).write_bytes(b"x")
            return Path(out), "Foto: Fulano / Wikimedia Commons (CC BY-SA 4.0)"
        return None
    monkeypatch.setattr(illustrate, "buscar_commons", commons)
    img = illustrate.imagem_de_fundo(c, tmp_path / "b")
    assert img and c["_ilustrativa"] and "Wikimedia" in c["_credito"]
    assert buscas[0] == ("classroom", (), False)  # 1º: foto ligada ao assunto da notícia
    assert ("Cajazeiras Paraíba", ("Cajazeiras",), False) in buscas  # depois: vista da cidade
    assert illustrate.RETRATO.search("retrato do deputado fulano")


def test_roteiro_cabe_no_limite_e_termina_com_chamada():
    c = card(resumo=" ".join(["Frase longa com bastante informação sobre o caso."] * 12))
    frases = video.roteiro(c, 60)
    assert frases[-1].startswith("Siga o") and frases[0].startswith(c["titulo"].rstrip(".")[:20])
    assert sum(len(f.split()) for f in frases) <= 60


def test_narracao_longa_e_encurtada_e_nunca_passa_de_58s(monkeypatch, tmp_path):
    chamadas = []

    def tts(texto, wav):  # 1ª narração: 70 s; depois de encurtar: 50 s
        chamadas.append(len(texto.split()))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                        "-t", "1", str(wav)], check=True)
        return 70.0 if len(chamadas) == 1 else 50.0
    monkeypatch.setattr(video, "tts_gemini", tts)
    c = card(resumo=" ".join(["Frase com informação nova sobre o assunto da notícia."] * 10))
    audio, total = video.narrar(c, tmp_path)
    assert len(chamadas) == 2 and chamadas[1] < chamadas[0]
    assert total <= 58.0 and audio.exists()


def test_voz_fixa_nao_troca_de_voz(monkeypatch, tmp_path):
    """Sem a voz padrão (a da 1ª postagem), não sai spot com outra voz nem com o Piper."""
    monkeypatch.setattr(video, "VOZ_FIXA", True)
    monkeypatch.setattr(video, "tts_gemini", lambda texto, wav: None)
    monkeypatch.setattr(video, "falar", lambda texto, wav: (_ for _ in ()).throw(AssertionError("usou o Piper")))
    with pytest.raises(RuntimeError, match="voz padrão indisponível"):
        video.narrar(card(), tmp_path)


def test_voz_fixa_usa_so_o_modelo_da_primeira_postagem(monkeypatch, tmp_path):
    import requests
    pedidos = []

    class R:
        status_code = 429
    monkeypatch.setattr(requests, "post", lambda url, **k: pedidos.append(url) or R())
    monkeypatch.setattr(video.time, "sleep", lambda s: None)
    monkeypatch.setattr(video, "VOZ_FIXA", True)
    monkeypatch.setattr(video, "GEMINI_API_KEY", "k")
    assert video.tts_gemini("oi", tmp_path / "a.wav") is None
    assert len(pedidos) == 3 and all("gemini-3.1-flash-tts-preview" in u for u in pedidos)


def test_foto_da_materia_nunca_vai_para_a_arte(monkeypatch, tmp_path):
    """A foto original costuma ter texto/logo: só serve de referência para refazer ou achar parecida."""
    import illustrate
    c = card(titulo="Lula assina decreto da escala 5x2", cidade="Brasil", chapeu="BRASIL")
    monkeypatch.setattr(illustrate, "_original", lambda card: (b"x" * 20000, "image/jpeg", "g1.globo.com"))
    monkeypatch.setattr(illustrate, "_visao", lambda card: {"busca_en": "office desk documents"})
    monkeypatch.setattr(illustrate, "ilustracao_ia", lambda card, out: None)
    monkeypatch.setattr(illustrate, "buscar_commons", lambda *a, **k: None)
    assert illustrate.imagem_de_fundo(c, tmp_path / "b") is None
    assert "Reprodução" not in c["_credito"]


def test_noticia_do_brasil_usa_foto_semelhante(monkeypatch, tmp_path):
    import illustrate
    c = card(titulo="Lula assina decreto da escala 5x2", cidade="Brasil", chapeu="BRASIL")
    monkeypatch.setattr(illustrate, "_visao", lambda card: {"busca_en": "office desk documents"})
    monkeypatch.setattr(illustrate, "ilustracao_ia", lambda card, out: None)
    buscas = []

    def commons(q, out, exigir=(), repetir=False, sem=None):
        buscas.append(q)
        Path(out).write_bytes(b"x")
        return Path(out), "Foto: Fulano / Wikimedia Commons (CC0)"
    monkeypatch.setattr(illustrate, "buscar_commons", commons)
    assert illustrate.imagem_de_fundo(c, tmp_path / "b")
    assert buscas == ["office desk documents"] and c["_ilustrativa"]


def test_filtro_de_imagem_com_texto():
    import illustrate
    assert illustrate.NAO_E_FOTO.search("cartaz do evento em campina grande")
    assert illustrate.NAO_E_FOTO.search("outdoor na avenida")
    assert not illustrate.NAO_E_FOTO.search("acude velho campina grande ao entardecer")


def test_ilustracao_reserva_corta_a_marca(monkeypatch, tmp_path):
    import io
    import requests
    from PIL import Image
    import illustrate
    buf = io.BytesIO()
    Image.effect_noise((1080, 2048), 60).convert("RGB").save(buf, "JPEG", quality=95)

    class R:
        status_code, content, headers = 200, buf.getvalue(), {"content-type": "image/jpeg"}
    monkeypatch.setattr(requests, "get", lambda url, **k: R())
    out = illustrate._pollinations("cena", tmp_path / "ia.png")
    assert out and Image.open(out).size == (1080, int(2048 * 0.93))


# ---------------------------------------------------------------- audiograma (onda + legenda)
def _fala_sintetica(caminho, trechos, pausa=0.45):
    import wave
    import numpy as np
    sr, partes = 24000, []
    for d in trechos:
        t = np.arange(int(d * sr)) / sr
        partes += [np.sin(2 * np.pi * 180 * t) * 0.5, np.zeros(int(pausa * sr))]
    pcm = (np.concatenate(partes) * 32767).astype("int16")
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_legenda_acompanha_as_pausas_da_voz(tmp_path):
    import audiograma
    frases = ["Primeira frase curta.", "Uma segunda frase bem mais comprida que a primeira.", "Fim."]
    _fala_sintetica(tmp_path / "v.wav", [1.5, 3.5, 0.6])
    t = audiograma.tempos_das_frases(frases, tmp_path / "v.wav")
    assert abs(t[0][1] - 1.5) < 0.1 and abs(t[1][0] - 1.95) < 0.1 and abs(t[2][0] - 5.9) < 0.15


def test_blocos_de_legenda_equilibrados():
    import audiograma
    frase = "Empresas terão 90 dias para adaptar escalas e contratos de trabalho em todo o país."
    partes = audiograma.blocos(frase, [])
    assert all(len(ls) <= 2 for ls, _ in partes) and len(partes) >= 2
    tam = [sum(len(p) for l in ls for p, _ in l) for ls, _ in partes]
    assert min(tam) >= max(tam) * 0.4  # nada de sobra curta no fim
    manchete = audiograma.blocos("Lula assina decreto que troca a escala 6x1 pela jornada 5x2 em todo o país", [],
                                 manchete=True)
    assert len(manchete) == 1 and len(manchete[0][0]) <= 4


def test_destaque_usa_outra_fonte(tmp_path):
    import audiograma
    palavras = [("Prefeitura", 0.0, 0.4, 0), ("abre", 0.4, 0.7, 0), ("339", 0.7, 1.4, 0), ("vagas", 1.4, 1.8, 0),
                ("em", 1.8, 1.9, 0), ("Areia.", 1.9, 2.4, 0), ("Inscrições", 2.9, 3.5, 1), ("até", 3.5, 3.7, 1),
                ("sexta.", 3.7, 4.2, 1)]
    ass = audiograma.legenda_ass(palavras, ["339 vagas"], tmp_path / "l.ass", total=5)
    txt = ass.read_text()
    assert "Instrument Serif" not in txt and "Inter Black" in txt  # uma fonte só
    caixas = [l for l in txt.splitlines() if l.startswith("Dialogue: 1,") or l.startswith("Dialogue: 2,")]
    assert any("339" in l for l in caixas)  # destaque = caixa branca
    assert any("339 \\hvagas" in l for l in txt.splitlines() if l.startswith("Dialogue: 2,"))  # 1 caixa só
    # sem destaque do editor, os números ganham a outra fonte
    assert any(d for p, d in audiograma._marcar_destaques("Concurso tem 339 vagas".split(), []) if p == "339")


def test_legenda_dinamica_palavra_entra_quando_e_falada(tmp_path):
    import re
    import audiograma
    palavras = [("Chuva", 0.0, 0.5, 0), ("forte", 0.5, 0.9, 0), ("alaga", 0.9, 1.4, 0), ("ruas", 1.4, 1.9, 0)]
    txt = audiograma.legenda_ass(palavras, [], tmp_path / "l.ass", atraso=0.3, total=3).read_text()
    base = [l for l in txt.splitlines() if l.startswith("Dialogue: 0,")]
    assert [l.split(",")[1] for l in base] == ["0:00:00.30", "0:00:00.80", "0:00:01.20", "0:00:01.70"]
    caixas = [l for l in txt.splitlines() if l.startswith("Dialogue: 1,")]
    assert len(caixas) == 4 and caixas[1].split(",")[1] == "0:00:00.80"  # caixa entra junto com a palavra


def test_alinha_palavras_do_roteiro_com_o_whisper():
    import audiograma
    frases = ["Prefeitura de Areia abre 339 vagas.", "Inscrições até sexta."]
    rec = [("Prefeitura", 0.0, 0.5), ("de", 0.5, 0.6), ("areia", 0.6, 1.0), ("abre", 1.0, 1.3),
           ("trezentas", 1.3, 1.8), ("vagas", 2.4, 2.8), ("Inscrições", 3.3, 3.9), ("até", 3.9, 4.1), ("sexta", 4.1, 4.6)]
    pt = audiograma.tempo_das_palavras(frases, reconhecidas=rec)
    d = {p: (a, b) for p, a, b, _ in pt}
    assert d["Areia"] == (0.6, 1.0) and d["vagas."] == (2.4, 2.8) and d["sexta."] == (4.1, 4.6)
    assert 1.3 <= d["339"][0] < d["339"][1] <= 2.4  # número falado por extenso: fica entre os vizinhos


def test_pagina_nao_separa_destaque():
    import audiograma
    ws = [(p, i * 0.3, i * 0.3 + 0.3, 0) for i, p in enumerate(
        "O governo federal anuncia novo salário mínimo de R$ 1.630 para o próximo ano em todo o país".split())]
    pags = audiograma.paginas(ws, ["salário mínimo"])
    for pg in pags:
        textos = [p for p, *_ in pg]
        if "salário" in textos:
            assert "mínimo" in textos


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_audiograma_completo(tmp_path):
    import json
    import audiograma
    c = card(destaques=["cursos gratuitos"])
    frases = [video._para_fala(f) for f in video.roteiro(c)]
    _fala_sintetica(tmp_path / "narracao.wav", [2.0] * len(frases), pausa=0.3)
    (tmp_path / "narracao.json").write_text(json.dumps({"frases": frases, "atraso": 0.3, "fator": 1.0}))
    audio = tmp_path / "a.m4a"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp_path / "narracao.wav"), "-af",
                    "adelay=300|300", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(audio)], check=True)
    out = audiograma.montar(c, None, audio, 9.0, tmp_path / "r.mp4", tmp_path)
    info = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,codec_name:format=duration",
                           "-of", "json", str(out)], capture_output=True, text=True).stdout
    assert f'"width": {audiograma.VW}' in info and f'"height": {audiograma.VH}' in info and '"aac"' in info
    assert (audiograma.VW, audiograma.VH) == ((1440, 2560) if audiograma.VIDEO_2K else (1080, 1920))
    assert abs(float(json.loads(info)["format"]["duration"]) - 9.0) < 0.3
    assert (tmp_path / "quadro.jpg").exists() and (tmp_path / "legenda.ass").exists()


def test_foto_com_letreiro_fica_de_fora():
    import illustrate
    assert illustrate.LETREIRO.search("manaira shopping joao pessoa")
    assert illustrate.LETREIRO.search("fachada do hotel tambau")
    assert not illustrate.LETREIRO.search("acude velho campina grande ao entardecer")



def test_capa_padrao_aprovado(tmp_path):
    """Capa: foto cheia com degradê vermelho da marca embaixo, texto branco à esquerda."""
    import audiograma
    from PIL import Image
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (1600, 1200), (20, 120, 200)).save(foto)
    c = card(destaques=["cursos gratuitos"], _ilustrativa=True, _credito="Foto: X / Wikimedia Commons (CC0)")
    out = audiograma.capa(c, tmp_path / "capa.jpg", foto)
    im = Image.open(out).convert("RGB")
    assert im.size == (audiograma.VW, audiograma.VH)
    r, g, b = im.getpixel((im.width - 10, audiograma.z(1700)))  # pé da capa: vermelho da marca
    assert r > 150 and g < 90 and b < 80
    r, g, b = im.getpixel((im.width // 2, audiograma.z(600)))   # meio: a foto aparece
    assert b > 120


def test_video_usa_a_mesma_foto_com_efeito_vermelho(tmp_path):
    import audiograma
    from PIL import Image
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (1600, 1200), (128, 128, 128)).save(foto)  # foto neutra (cinza)
    out = audiograma.quadro(card(), tmp_path / "q.jpg", foto)
    im = Image.open(out).convert("RGB")
    r, g, b = im.getpixel((im.width // 2, audiograma.z(600)))
    assert r > g + 30 and r > b + 30  # a foto ganhou o tom vermelho da marca


def test_sem_redundancia_na_narracao():
    c = card(titulo="Prefeitura de Areia abre 339 vagas em concurso",
             linha_fina="Inscrições vão até sexta pelo site oficial.",
             resumo="A prefeitura de Areia oferece 339 vagas no concurso. As provas foram adiadas pela Justiça.",
             pontos=["339 vagas no concurso de Areia", "Salários de até R$ 4 mil"])
    texto = " ".join(video.roteiro(c))
    assert texto.count("339") == 1 and "Salários" in texto and "adiadas" in texto


def test_grupos_quebram_na_pausa_e_no_maximo_de_palavras():
    import audiograma
    ws = [("Um", 0.0, 0.2, 0), ("dois", 0.2, 0.4, 0), ("três", 0.4, 0.6, 0), ("quatro", 0.6, 0.8, 0),
          ("cinco", 0.8, 1.0, 0), ("seis", 1.0, 1.2, 0), ("sete", 1.6, 1.8, 0)]  # pausa antes de "sete"
    grupos = [[p for p, *_ in g] for g in audiograma.paginas(ws, [])]
    assert grupos == [["Um", "dois", "três", "quatro", "cinco"], ["seis"], ["sete"]]



def test_capa_uma_fonte_so_e_onda_centralizada(monkeypatch, tmp_path):
    import audiograma
    usadas = []
    original = audiograma.fonte
    monkeypatch.setattr(audiograma, "fonte", lambda arq, tam: usadas.append(arq) or original(arq, tam))
    audiograma.capa(card(destaques=["cursos gratuitos"], titulo="Prefeitura abre 339 vagas em cursos gratuitos"),
                    tmp_path / "c.jpg", None)
    assert "InstrumentSerif-Italic.ttf" not in usadas  # a serifada fica só na legenda do vídeo
    x, _, w, _ = audiograma.ONDA
    assert x + w / 2 == audiograma.W / 2


def test_montagem_de_fotos_fica_de_fora():
    import illustrate
    assert illustrate.NAO_E_FOTO.search("joao pessoa (compilation) heitor carvalho jorge")
    assert illustrate.NAO_E_FOTO.search("montagem de joao pessoa")
    assert not illustrate.NAO_E_FOTO.search("praia de tambau ao entardecer")
