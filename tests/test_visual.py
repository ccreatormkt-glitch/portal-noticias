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
    assert frases[0].endswith(".") and frases[-1].startswith("Siga o")
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
    assert '"width": 1080' in info and '"height": 1920' in info
    assert '"has_b_frames": 0' in info and '"sample_rate": "48000"' in info


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg não instalado")
def test_video_leve_com_quadro_chave_a_cada_4s(tmp_path):
    """Arquivo leve facilita o envio à Meta; o Instagram pede GOP fechado de 2 a 5 s."""
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
    assert buscas[0] == ("Cajazeiras Paraíba", ("Cajazeiras",), False)
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
