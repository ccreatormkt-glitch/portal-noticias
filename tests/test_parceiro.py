"""Vídeos do parceiro (@jornaldapb): filtro de collab, reescrita, montagem e fila (sem rede)."""
import json
import subprocess
import time

import pytest

import parceiro

AGORA = time.time()
TS = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(AGORA - 3600))


def post(**over):
    m = {"id": "111", "media_type": "VIDEO", "username": "jornaldapb", "media_url": "https://x/v.mp4",
         "caption": "Prefeitura anuncia obra na avenida principal", "permalink": "https://ig/p/111",
         "timestamp": TS}
    m.update(over)
    return m


@pytest.fixture(autouse=True)
def pastas(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(parceiro, "DESDE", time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(AGORA - 7200)))
    monkeypatch.setattr(parceiro, "ESTADO", tmp_path / "state" / "parceiro.json")
    fila = tmp_path / "fila"
    fila.mkdir()
    monkeypatch.setattr(parceiro, "FILA", fila)
    monkeypatch.setattr(parceiro, "USUARIO", "jornaldapb")
    monkeypatch.setattr(parceiro, "LISTA_PADRAO", "jornaldapb")
    monkeypatch.delenv("PARCEIRO_LISTA", raising=False)
    monkeypatch.setattr(config, "OUT_DIR", tmp_path / "out")
    monkeypatch.setattr(config, "HUMANIZAR", False)


def test_aceita_video_do_proprio_parceiro():
    assert parceiro.motivo_para_pular(post(), {}, AGORA) == ""


@pytest.mark.parametrize("over,trecho", [
    ({"media_type": "IMAGE"}, "não é vídeo"),
    ({"media_type": "CAROUSEL_ALBUM"}, "não é vídeo"),
    ({"username": "outraconta"}, "collab"),
    ({"caption": "Vídeo em parceria com @prefeitura"}, "collab"),
    ({"caption": "Collab com o pessoal do bairro"}, "collab"),
    ({"caption": "#publi da loja X"}, "publi"),
    ({"media_url": None, "permalink": None}, "sem link"),
    ({"timestamp": "2020-01-01T10:00:00+0000"}, "antigo"),
    ({"media_product_type": "FEED"}, "não é reels"),
])
def test_pula_o_que_a_autorizacao_nao_cobre(over, trecho):
    assert trecho in parceiro.motivo_para_pular(post(**over), {}, AGORA)


def test_nao_repete_video_ja_usado():
    assert parceiro.motivo_para_pular(post(), {"111": {}}, AGORA) == "já usado"


def test_palavra_parecida_nao_conta_como_collab():
    assert parceiro.motivo_para_pular(post(caption="Nova publicação do colaborador da prefeitura"), {}, AGORA) == ""


def test_caixas_e_corte():
    assert parceiro.caixas("70,3,28,8; 0,70,100,18") == [(70, 3, 28, 8), (0, 70, 100, 18)]
    assert parceiro.caixas("90,90,50,50") == [(90, 90, 10, 10)]
    assert parceiro.caixas("lixo; 1,2,3") == []
    assert parceiro.corte("12,15") == (12, 15)
    assert parceiro.corte("") == (0, 0)


def test_repetidos_acha_4_palavras_iguais():
    assert parceiro.repetidos("a prefeitura anuncia obra na avenida", "Prefeitura anuncia obra na avenida principal")
    assert parceiro.repetidos("Obra nova começa na via central de CG", "Prefeitura anuncia obra na avenida") == []


def test_escrever_pede_de_novo_quando_copia_e_segue_a_regra_de_escrita(monkeypatch):
    import editor
    respostas = iter([
        {"chapeu": "CIDADE", "titulo": "Prefeitura anuncia obra na avenida principal", "legenda": "x"},
        {"chapeu": "CIDADE", "titulo": "Avenida central de CG vai ganhar obra nova", "legenda": "🚧 Obra.\n\nTexto.\n\nComente."},
    ])
    pedidos, sistemas = [], []

    def gerar(prompt, system):
        pedidos.append(prompt)
        sistemas.append(system)
        return json.dumps(next(respostas))
    monkeypatch.setattr(editor, "generate", gerar)
    card = parceiro.escrever("Prefeitura anuncia obra na avenida principal", "")
    assert card["titulo"] == "Avenida central de CG vai ganhar obra nova"
    assert len(pedidos) == 2 and "Trechos repetidos" in pedidos[1]
    assert "STE80 Humanizer" in sistemas[0]                 # regra de escrita do PB Minuto


def test_escrever_passa_pela_skill_humanizer(monkeypatch):
    import config
    import editor
    monkeypatch.setattr(config, "HUMANIZAR", True)
    monkeypatch.setattr(editor, "generate", lambda p, s=None: json.dumps(
        {"chapeu": "CIDADE", "titulo": "Avenida central de CG vai ganhar obra nova", "legenda": "🚧 Obra."}))
    chamadas = []
    monkeypatch.setattr(editor, "humanizar", lambda card, c=None, validar=True: chamadas.append(validar) or
                        dict(card, titulo="Avenida central de CG ganha obra nova"))
    card = parceiro.escrever("Prefeitura anuncia obra na avenida principal", "")
    assert chamadas == [False] and card["titulo"] == "Avenida central de CG ganha obra nova"


def _video_teste(path):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30:duration=2",
                    "-f", "lavfi", "-i", "sine=duration=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(path)],
                   check=True)
    return path


def test_rodada_review_monta_video_e_enfileira(monkeypatch):
    monkeypatch.setattr(parceiro, "buscar", lambda limite=25, usuario=None: [post(), post(id="222", username="outra")])
    monkeypatch.setattr(parceiro, "baixar", lambda m, destino: _video_teste(destino))
    monkeypatch.setattr(parceiro, "escrever", lambda leg, fala: {
        "chapeu": "CIDADE", "titulo": "Avenida central de CG vai ganhar obra nova", "legenda": "🚧 Obra.",
        "hashtags": ["campinagrande"], "pontos": [], "cidade": "Campina Grande"})
    monkeypatch.setattr(parceiro, "COBRIR", "70,2,28,8")
    assert parceiro.rodada("review", limite=2) == 1
    fila = list(parceiro.FILA.glob("*.json"))
    assert [p.stem for p in fila] == ["parceiro_111"]
    card = json.loads(fila[0].read_text(encoding="utf-8"))
    assert (parceiro.FILA / card["_video"]).stat().st_size > 10_000
    est = json.loads(parceiro.ESTADO.read_text(encoding="utf-8"))
    assert est["vistos"]["111"]["status"] == "na_fila"
    assert est["vistos"]["222"]["status"] == "pulado"          # collab nunca é usado
    assert parceiro.rodada("review", limite=2) == 0           # na próxima rodada nada se repete


def test_aprovar_publica_e_limpa_a_fila(monkeypatch):
    (parceiro.FILA / "v.mp4").write_bytes(b"x")
    (parceiro.FILA / "c.jpg").write_bytes(b"x")
    (parceiro.FILA / "parceiro_111.json").write_text(json.dumps({
        "titulo": "T", "chapeu": "CIDADE", "_video": "v.mp4", "_capa": "c.jpg",
        "_origem": {"id": "111"}}), encoding="utf-8")
    monkeypatch.setattr(parceiro, "_publicar", lambda card, v, c: "IG999")
    assert parceiro.aprovar(todos=True) == 1
    assert not list(parceiro.FILA.iterdir())
    est = json.loads(parceiro.ESTADO.read_text(encoding="utf-8"))
    assert est["vistos"]["111"]["status"] == "publicado" and est["vistos"]["111"]["nota"] == "IG999"


def test_falha_tenta_de_novo_e_desiste_na_terceira(monkeypatch):
    monkeypatch.setattr(parceiro, "buscar", lambda limite=25, usuario=None: [post()])

    def quebra(m, destino):
        raise RuntimeError("rede caiu")
    monkeypatch.setattr(parceiro, "baixar", quebra)
    for _ in range(2):
        parceiro.rodada("review")
        assert "111" not in json.loads(parceiro.ESTADO.read_text(encoding="utf-8"))["vistos"]
    parceiro.rodada("review")
    assert json.loads(parceiro.ESTADO.read_text(encoding="utf-8"))["vistos"]["111"]["status"] == "erro"


def test_etiqueta_usa_layout_e_cobre_o_pe(tmp_path):
    """Etiqueta medida pelo layout.py: barra vermelha no topo, preto sólido embaixo (cobre a
    manchete antiga), editoria na caixa com a cor do tema."""
    import layout as L
    from PIL import Image
    png = parceiro.etiqueta({"chapeu": "POLÍCIA", "cidade": "Paraíba",
                             "titulo": "Polícia apreende 2 toneladas de drogas no Sertão"}, tmp_path / "e.png")
    im = Image.open(png).convert("RGBA")
    r, g, b, a = im.getpixel((10, 20))
    assert a == 255 and r > 150 and g < 90                     # barra vermelha
    r, g, b, a = im.getpixel((im.width - 10, im.height - 10))
    assert a == 255 and max(r, g, b) < 10                       # pé 100% preto
    assert L.PARCEIRO["degrade"][1] < L.PARCEIRO["pe"]


def test_so_reels_novos_publicados_depois_da_ativacao():
    """Pedido do Arthur: só Reels novos; os que já estavam no perfil não entram, mesmo recentes."""
    ativacao = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(AGORA - 1800))
    parceiro.DESDE = ativacao
    antes = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(AGORA - 3600))
    depois = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(AGORA - 600))
    assert parceiro.motivo_para_pular(post(timestamp=antes, media_product_type="REELS"), {}, AGORA) == "antigo"
    assert parceiro.motivo_para_pular(post(timestamp=depois, media_product_type="REELS"), {}, AGORA) == ""
    assert "collab" in parceiro.motivo_para_pular(post(timestamp=depois, username="outra"), {}, AGORA)


def test_sem_link_da_api_baixa_pela_pagina_do_post(monkeypatch, tmp_path):
    m = post(media_url=None)
    assert parceiro.motivo_para_pular(m, {}, AGORA) == ""
    chamado = {}

    def falso(url, destino):
        chamado["url"] = url
        destino.write_bytes(b"x")
        return destino

    monkeypatch.setattr(parceiro, "baixar_pela_pagina", falso)
    destino = tmp_path / "v.mp4"
    assert parceiro.baixar(m, destino) == destino
    assert chamado["url"] == "https://ig/p/111"


def test_reserva_desligada_volta_a_pular_sem_link(monkeypatch):
    monkeypatch.setattr(parceiro, "BAIXAR_PAGINA", False)
    assert "sem link" in parceiro.motivo_para_pular(post(media_url=None), {}, AGORA)


def test_acha_marca_dagua_parada_e_ignora_imagem_em_movimento(tmp_path):
    """Logo parado no canto de cima sobre imagem que mexe: achado; vídeo sem marca: nada."""
    limpo, marcado = tmp_path / "limpo.mp4", tmp_path / "marca.mp4"
    base = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=15:duration=6"]
    subprocess.run(base + ["-vf", "hue=H=t*2", str(limpo)], check=True)
    subprocess.run(base + ["-vf", "hue=H=t*2,drawbox=x=400:y=30:w=120:h=60:color=white:t=fill,"
                           "drawbox=x=420:y=45:w=80:h=30:color=red:t=fill", str(marcado)], check=True)
    areas = parceiro.detectar_marcas(marcado)
    assert any(x >= 60 and y <= 10 for x, y, w, h in areas), areas
    assert parceiro.detectar_marcas(limpo) == [] or all(
        not (x >= 60 and y <= 10) for x, y, w, h in parceiro.detectar_marcas(limpo))


def test_lista_de_parceiros_com_data_e_grade(monkeypatch):
    monkeypatch.setattr(parceiro, "DESDE", "")
    lista = parceiro.parceiros("@JornalDaPB|2026-11-21T02:20:00+0000; blognewspb|2026-11-21T10:40:00+0000|grade; ")
    assert [p["usuario"] for p in lista] == ["jornaldapb", "blognewspb"]
    assert lista[0]["grade"] is False and lista[1]["grade"] is True
    assert lista[1]["desde"] == "2026-11-21T10:40:00+0000"
    padrao = [p["usuario"] for p in parceiro.parceiros(parceiro.LISTA_PADRAO)]
    assert padrao == ["jornaldapb"]  # no teste a lista padrão foi trocada pelo fixture


def test_collab_e_conferido_contra_o_parceiro_da_vez():
    m = post(username="blognewspb")
    assert parceiro.motivo_para_pular(m, {}, AGORA, usuario="blognewspb") == ""
    assert "collab" in parceiro.motivo_para_pular(m, {}, AGORA, usuario="jornaldapb")


def test_grade_recorta_so_o_video_que_mexe(tmp_path):
    """Vídeo 16:9 que mexe dentro de uma moldura 9:16 parada com marca: acha a parte de dentro."""
    v = tmp_path / "grade.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=navy:s=540x960:d=6:r=15",
                    "-f", "lavfi", "-i", "color=c=gray:s=540x304:rate=15:d=6",
                    "-filter_complex", "[1]noise=alls=90:allf=t[m];[0][m]overlay=0:300,drawbox=x=20:y=40:w=300:h=80:"
                    "color=yellow:t=fill", "-t", "6", str(v)], check=True)
    x, y, w, h = parceiro.detectar_video(v)
    assert abs(y - 300) <= 20 and abs(h - 304) <= 30 and w >= 500, (x, y, w, h)
    sem = tmp_path / "cheio.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=540x960:rate=15:d=6",
                    "-vf", "noise=alls=90:allf=t", str(sem)], check=True)
    assert parceiro.detectar_video(sem) is None


def test_publicados_24h_conta_so_publicados_recentes(tmp_path):
    import json, time
    import parceiro
    agora = time.time()
    arq = tmp_path / "parceiro.json"
    arq.write_text(json.dumps({"vistos": {
        "1": {"ts": agora - 3600, "status": "publicado"},
        "2": {"ts": agora - 90000, "status": "publicado"},     # mais de 24h
        "3": {"ts": agora - 60, "status": "pulado"},
    }}))
    assert parceiro.publicados_24h(arq) == 1
    assert parceiro.publicados_24h(tmp_path / "nao_existe.json") == 0


def test_reels_de_ontem_de_todos_os_parceiros_entram(monkeypatch):
    import re
    from pathlib import Path
    import parceiro
    monkeypatch.setattr(parceiro, "DESDE", "")
    # a fixture troca LISTA_PADRAO nos testes; aqui vale a lista real do código
    fonte = (Path(parceiro.__file__)).read_text(encoding="utf-8")
    bloco = re.search(r"LISTA_PADRAO = \((.*?)\)\n", fonte, re.S).group(1)
    lista = parceiro.parceiros("".join(re.findall(r'"([^"]*)"', bloco)))
    assert {p["usuario"] for p in lista} >= {"jornaldapb", "portalresumopb", "blognewspb", "noticiacertapb"}
    assert all(p["desde"] <= "2026-11-20T03:00:00+0000" for p in lista)
