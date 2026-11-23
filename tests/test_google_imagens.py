"""Foto do Google Imagens: navegador abre a busca -> a IA escolhe a miniatura -> print da foto grande.
Usa uma página falsa do Google servida localmente (nada sai para a internet)."""
import base64
import http.server
import io
import threading

import pytest
from PIL import Image

import config
import editor
import illustrate


def _png(w, h, cor):
    b = io.BytesIO()
    Image.new("RGB", (w, h), cor).save(b, "PNG")
    return b.getvalue()


MINI = "data:image/png;base64," + base64.b64encode(_png(150, 150, (200, 50, 50))).decode()
PAGINA = f"""<html><body><div style="height:150px">Google</div><div id="search">
<img src="{MINI}" width="180" height="180" onclick="abrir(1)">
<img src="{MINI}" width="180" height="180" onclick="abrir(2)"></div>
<div id="painel"></div><script>
function abrir(n) {{ document.getElementById('painel').innerHTML =
 '<a href="https://www.jornalx.com.br/materia' + n + '"><img src="/grande' + n + '.png" width="600" height="400"></a>'; }}
</script></body></html>"""


class Fake(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/grande"):
            corpo, tipo = _png(1200, 800, (30, 90, 160)), "image/png"
        elif self.path.startswith("/sorry"):
            corpo, tipo = b"<form id='captcha-form'></form>", "text/html"
        else:
            corpo, tipo = PAGINA.encode(), "text/html"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def servidor():
    pytest.importorskip("playwright.sync_api")
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def card(**kw):
    c = {"titulo": "Homem é morto a tiros no bairro Mandacaru", "cidade": "João Pessoa",
         "chapeu": "POLÍCIA", "risco": "cuidado", "destaques": ["Mandacaru", "dez disparos"],
         "foto_local": "Bairro Mandacaru João Pessoa"}
    c.update(kw)
    return c


def preparar(monkeypatch, tmp_path, url, escolha):
    monkeypatch.setattr(config, "GOOGLE_IMAGENS", True)
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(illustrate, "GOOGLE_URL", url)
    vistas = []

    def escolher(c, imgs, cena=""):
        vistas.append(len(imgs))
        return escolha
    monkeypatch.setattr(editor, "escolher_foto", escolher)
    return vistas


def test_buscas_em_portugues_com_cidade():
    assert illustrate.buscas_google(card()) == [
        "Homem é morto a tiros no bairro Mandacaru João Pessoa", "Bairro Mandacaru João Pessoa",
        "Mandacaru dez disparos João Pessoa"]
    assert illustrate.buscas_google(card(cidade="Paraíba", foto_local=""))[0] == card()["titulo"]


def test_print_da_foto_escolhida_antes_de_tudo(monkeypatch, tmp_path, servidor):
    vistas = preparar(monkeypatch, tmp_path, servidor + "/search?q=", escolha=1)
    c = card()
    arq = illustrate.imagem_de_fundo(c, tmp_path / "x")
    assert arq.name == "x_google.jpg" and arq.exists()
    assert vistas == [2]                                          # a IA viu as 2 miniaturas
    with Image.open(arq) as im:
        assert im.size == (1200, 800)                             # print da foto grande (600x400 em 2x)
        assert im.getpixel((600, 400))[2] > 120                   # é a foto do painel, não a miniatura
    assert c["_credito"] == "Foto: Reprodução / jornalx.com.br" and c["_ilustrativa"] is False
    assert "jornalx.com.br" in c["_credito_legenda"]
    assert any(u.startswith("google:") for u in illustrate._usadas())


def test_ia_recusa_tudo_cai_para_o_resto(monkeypatch, tmp_path, servidor):
    vistas = preparar(monkeypatch, tmp_path, servidor + "/search?q=", escolha=None)
    assert illustrate.foto_google(card(), tmp_path / "x") is None
    assert len(vistas) == illustrate.GOOGLE_MAX_BUSCAS


def test_captcha_para_de_buscar(monkeypatch, tmp_path, servidor):
    vistas = preparar(monkeypatch, tmp_path, servidor + "/sorry/?q=", escolha=0)
    assert illustrate.foto_google(card(), tmp_path / "x") is None
    assert vistas == []


def test_desligado_nao_abre_navegador(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GOOGLE_IMAGENS", False)
    assert illustrate.foto_google(card(), tmp_path / "x") is None
