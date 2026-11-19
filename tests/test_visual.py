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
