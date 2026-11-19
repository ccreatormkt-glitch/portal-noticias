import json

import pytest
from conftest import card

import publish


class Resp:
    def __init__(self, data, code=200):
        self.d, self.status_code, self.text = data, code, json.dumps(data)

    def json(self):
        return self.d


@pytest.fixture
def api(monkeypatch, tmp_path):
    chamadas = []

    def post(url, data=None, headers=None, timeout=0, **k):
        chamadas.append(("POST", url, data if isinstance(data, dict) else len(data), headers))
        if "imgbb" in url:
            return Resp({"data": {"url": "https://i.ibb.co/capa.jpg"}})
        if url.endswith("media_publish"):
            return Resp({"id": "POST1"})
        if "rupload" in url:
            return Resp({"success": True})
        return Resp({"id": f"C{len(chamadas)}"})

    def get(url, params=None, timeout=0, **k):
        chamadas.append(("GET", url, params, None))
        return Resp({"status_code": "FINISHED"})
    import requests
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(publish, "IG_USER_ID", "178")
    monkeypatch.setattr(publish, "IG_ACCESS_TOKEN", "tok")
    monkeypatch.setattr(publish, "IMGBB_API_KEY", "k")

    class Sessao:  # imita requests.Session guardando o cabeçalho de autorização
        headers = {"Authorization": "Bearer tok"}

        def post(self, url, data=None, timeout=0, **k):
            r = post(url, data=data, timeout=timeout)
            chamadas[-1] = (*chamadas[-1][:3], self.headers)
            return r

        def get(self, url, params=None, timeout=0, **k):
            r = get(url, params=params, timeout=timeout)
            chamadas[-1] = (*chamadas[-1][:3], self.headers)
            return r
    monkeypatch.setattr(publish, "_ig", Sessao)
    return chamadas


def test_reels_upload_direto_com_capa(api, tmp_path):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"0" * 1234)
    assert publish.post_reel(v, "legenda", cover_url="https://i.ibb.co/capa.jpg") == "POST1"
    cria = api[0]
    assert cria[2]["media_type"] == "REELS" and cria[2]["upload_type"] == "resumable"
    assert cria[2]["cover_url"].endswith("capa.jpg") and cria[2]["share_to_feed"] == "true"
    up = api[1]
    assert "rupload.facebook.com/ig-api-upload/v26.0/" in up[1]
    assert up[3]["Authorization"] == "OAuth tok" and up[3]["file_size"] == "1234" and up[2] == 1234
    assert api[-1][1].endswith("media_publish")


def test_reels_recusa_login_instagram(monkeypatch, api, tmp_path):
    monkeypatch.setattr(publish, "GRAPH_HOST", "graph.instagram.com")
    with pytest.raises(RuntimeError):
        publish.post_reel(tmp_path / "x.mp4", "c")


def test_legenda_completa_sem_fonte(monkeypatch):
    c = card()
    c["_reels"] = True
    txt = publish.build_caption(c)
    assert txt.startswith("🎓 Qualificação sem custo em CG")
    assert "📌 Veja como fazer:\n• Capacitação sem custo\n• Cadastro até sexta" in txt
    assert "Narração com voz gerada por IA" not in txt and "Siga @pbminuto" in txt  # aviso retirado a pedido do Arthur
    assert "Fonte" not in txt
    assert txt.rstrip().endswith("#campinagrande #paraiba #cursosgratuitos")
    assert len(txt) <= 2200


def test_erro_da_api_vira_excecao_clara(monkeypatch):
    with pytest.raises(RuntimeError, match="Instagram API 400"):
        publish._check(Resp({"error": {"message": "token inválido"}}, code=400))


def test_errata_comenta_no_post(api, monkeypatch, capsys):
    import argparse
    import main
    main.cmd_errata(argparse.Namespace(post_id="1789", texto="O valor correto é R$ 2 mil."))
    url, dados = api[-1][1], api[-1][2]
    assert url.endswith("/1789/comments") and dados["message"].startswith("⚠️ CORREÇÃO (")
    assert "R$ 2 mil" in dados["message"]


def test_token_nunca_vai_na_url_nem_no_corpo(api, tmp_path):
    v = tmp_path / "v.mp4"
    v.write_bytes(b"0" * 10)
    publish.post_reel(v, "legenda")
    publish.comentar("123", "x")
    for metodo, url, dados, cab in api:
        if "imgbb" in url:
            continue
        assert "tok" not in url and "access_token" not in str(dados)
        assert cab and ("Bearer tok" in cab.get("Authorization", "") or cab.get("Authorization") == "OAuth tok")


def test_sessao_real_usa_cabecalho(monkeypatch):
    monkeypatch.setattr(publish, "IG_ACCESS_TOKEN", "segredo123")
    assert publish._ig().headers["Authorization"] == "Bearer segredo123"


def test_erros_nao_mostram_chaves(monkeypatch):
    monkeypatch.setattr(publish, "IG_ACCESS_TOKEN", "segredo123")
    monkeypatch.setattr(publish, "IMGBB_API_KEY", "imgkey9")
    msg = publish._sem_segredos("falhou https://x/?access_token=abc&key=imgkey9 segredo123")
    assert "segredo123" not in msg and "imgkey9" not in msg and "abc" not in msg


def test_legenda_sem_links_nem_mencoes():
    c = card(legenda="Abertura com @perfilqualquer.\n\nVeja em https://site.com/x agora.\n\nComente!",
             pontos=["ponto com www.exemplo.com", "ok"])
    leg = publish.build_caption(c)
    assert "@perfilqualquer" not in leg and "https://" not in leg and "www." not in leg
    assert "@pbminuto" in leg  # a nossa assinatura continua


def test_errata_exige_id_numerico(monkeypatch):
    import main, types
    with pytest.raises(SystemExit):
        main.cmd_errata(types.SimpleNamespace(post_id="123/../me", texto="x"))


def test_reels_recusado_vai_por_link_publico(api, monkeypatch, tmp_path):
    """Servidor de upload da Meta recusa o arquivo: o vídeo vai por link público (ramo "midia")."""
    import requests
    import hospedar
    original = requests.post

    def post(url, data=None, headers=None, timeout=0, **k):
        if "rupload" in url:
            api.append(("POST", url, len(data), headers))
            return Resp({"debug_info": {"type": "ProcessingFailedError"}}, code=400)
        return original(url, data=data, headers=headers, timeout=timeout)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    monkeypatch.setattr(hospedar, "links_publicos",
                        lambda p: ["https://cdn.jsdelivr.net/gh/o/r@abc/v.mp4", "https://raw.githubusercontent.com/o/r/abc/v.mp4"])
    v = tmp_path / "v.mp4"
    v.write_bytes(b"0" * 50)
    assert publish.post_reel(v, "legenda") == "POST1"
    criados = [c for c in api if c[0] == "POST" and c[1].endswith("/media")]
    assert [c[2].get("upload_type") for c in criados[:2]] == ["resumable", "resumable"]
    assert criados[-1][2]["video_url"].startswith("https://cdn.jsdelivr.net/") and "upload_type" not in criados[-1][2]


def test_reels_sem_link_publico_continua_sendo_instabilidade(api, monkeypatch, tmp_path):
    import requests
    original = requests.post

    def post(url, data=None, headers=None, timeout=0, **k):
        if "rupload" in url:
            return Resp({"debug_info": {"type": "ProcessingFailedError"}}, code=400)
        return original(url, data=data, headers=headers, timeout=timeout)
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(publish.time, "sleep", lambda s: None)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)  # fora do GitHub não há link público
    v = tmp_path / "v.mp4"
    v.write_bytes(b"0" * 50)
    with pytest.raises(RuntimeError, match="ProcessingFailedError"):
        publish.post_reel(v, "legenda")


def test_voz_padrao_e_a_da_primeira_postagem():
    import config
    assert config.TTS_MODEL.split(",")[0] == "gemini-3.1-flash-tts-preview" or "TTS_MODEL" in __import__("os").environ
    assert config.TTS_VOICE == "Charon" or "TTS_VOICE" in __import__("os").environ
