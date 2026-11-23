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
    monkeypatch.setattr(config, "GOOGLE_VIA", "aqui")
    monkeypatch.setattr(config, "GOOGLE_PERFIL", "")
    monkeypatch.setattr(config, "GOOGLE_CHROME", False)
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


# ---------------------------------------------------------------- pedido ao Mac (runner pbminuto-mac)
class R:
    def __init__(self, status=200, json=None, content=b""):
        self.status_code, self._json, self.content, self.text = status, json or {}, content, ""

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def mac(monkeypatch, tmp_path, respostas, fila=()):
    """Simula a API do GitHub: `respostas` = o que o Mac grava no ramo google-fotos (por tentativa)."""
    monkeypatch.setattr(config, "GOOGLE_IMAGENS", True)
    monkeypatch.setattr(config, "GOOGLE_VIA", "mac")
    monkeypatch.setattr(config, "GOOGLE_MAC_ESPERA", 30)
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr("time.sleep", lambda s: None)
    chamadas, ultimas = [], list(respostas)

    def gh(metodo, caminho, **kw):
        chamadas.append((metodo, caminho, kw.get("json")))
        if caminho.endswith("/runs"):
            return R(json={"workflow_runs": list(fila)})
        if caminho.endswith("/dispatches"):
            return R(204)
        if caminho.endswith(".json"):
            return ultimas.pop(0) if ultimas else R(404)
        if caminho.endswith(".jpg"):
            return R(content=b"JPEGDATA")
        return R()
    monkeypatch.setattr(illustrate, "_gh", gh)
    return chamadas


def test_mac_devolve_a_foto(monkeypatch, tmp_path):
    illustrate_usada = "google:https://velha.com/a.jpg"
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    illustrate._marcar(illustrate_usada)
    chamadas = mac(monkeypatch, tmp_path, [R(404), R(json={"site": "jornalx.com.br",
                                                         "foto_id": "google:https://x.com/f.jpg"})])
    c = card()
    arq, cred = illustrate.foto_google(c, tmp_path / "x")
    assert arq.read_bytes() == b"JPEGDATA" and cred == "Foto: Reprodução / jornalx.com.br"
    disparo = [j for m, cam, j in chamadas if cam.endswith("/dispatches")][0]
    pedido = __import__("json").loads(base64.b64decode(disparo["inputs"]["pedido"]))
    assert disparo["ref"] == "main" and pedido["card"]["titulo"] == c["titulo"]
    assert pedido["usadas"] == [illustrate_usada]                   # o Mac não repete foto
    assert "google:https://x.com/f.jpg" in illustrate._usadas()


def test_mac_desligado_cancela_e_segue(monkeypatch, tmp_path):
    velho = {"id": 7, "status": "queued", "created_at": "2020-01-01T00:00:00Z"}
    chamadas = mac(monkeypatch, tmp_path, [], fila=[velho])
    assert illustrate.foto_google(card(), tmp_path / "x") is None
    assert ("POST", "actions/runs/7/cancel", None) in chamadas
    assert not any(cam.endswith("/dispatches") for _, cam, _ in chamadas)   # nem pede


def test_mac_sem_foto_aprovada(monkeypatch, tmp_path):
    mac(monkeypatch, tmp_path, [R(json={"erro": "nenhuma foto aprovada"})])
    assert illustrate.foto_google(card(), tmp_path / "x") is None


def test_google_mac_atende_o_pedido_e_grava_no_ramo(monkeypatch, tmp_path):
    import json as js
    import time as tm
    import google_mac
    gravados = {}
    monkeypatch.setattr(google_mac, "_gravar_no_ramo", lambda nome, dados: gravados.update({nome: dados}))
    foto = tmp_path / "f.jpg"
    foto.write_bytes(b"IMG")

    def falso(card, base):
        assert "google:https://velha.com/a.jpg" in illustrate._usadas()   # recebeu a lista do robô
        card["_google_id"] = "google:https://nova.com/b.jpg"
        return foto, "Foto: Reprodução / jornalx.com.br"
    monkeypatch.setattr(illustrate, "print_google_aqui", falso)
    pedido = {"id": "abc-1/../x", "t": tm.time(), "usadas": ["google:https://velha.com/a.jpg"],
              "card": {"titulo": "t"}}
    monkeypatch.setenv("PEDIDO", base64.b64encode(js.dumps(pedido).encode()).decode())
    monkeypatch.setattr("sys.argv", ["google_mac.py"])
    for k in ("GOOGLE_VIA", "GOOGLE_PERFIL", "GOOGLE_CHROME"):
        monkeypatch.setenv(k, "x")   # main() mexe no ambiente; o monkeypatch desfaz no fim
    google_mac.main()
    assert gravados["abc-1x.jpg"] == b"IMG"                       # id sem barra nem ponto (seguro)
    assert js.loads(gravados["abc-1x.json"]) == {"site": "jornalx.com.br",
                                                 "foto_id": "google:https://nova.com/b.jpg"}


def test_google_mac_ignora_pedido_velho(monkeypatch):
    import json as js
    import google_mac
    monkeypatch.setattr(google_mac, "_gravar_no_ramo", lambda *a: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setenv("PEDIDO", base64.b64encode(js.dumps({"id": "a", "t": 0}).encode()).decode())
    monkeypatch.setattr("sys.argv", ["google_mac.py"])
    for k in ("GOOGLE_VIA", "GOOGLE_PERFIL", "GOOGLE_CHROME"):
        monkeypatch.setenv(k, "x")   # main() mexe no ambiente; o monkeypatch desfaz no fim
    google_mac.main()


def test_mac_sem_resposta_ha_pouco_nem_tenta(monkeypatch, tmp_path):
    import datetime as dt
    agora = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    chamadas = mac(monkeypatch, tmp_path, [], fila=[{"id": 8, "status": "completed", "conclusion": "cancelled",
                                                    "created_at": agora, "updated_at": agora}])
    assert illustrate.foto_google(card(), tmp_path / "x") is None
    assert not any(cam.endswith("/dispatches") for _, cam, _ in chamadas)
