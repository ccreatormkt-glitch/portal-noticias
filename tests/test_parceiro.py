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
    import publish
    stories = []
    monkeypatch.setattr(publish, "story_se_paraiba", lambda cat, v: stories.append(cat) or "ST1")
    monkeypatch.setattr(parceiro, "categoria_do_card", lambda card: "cg")
    assert parceiro.aprovar(todos=True) == 1
    assert not list(parceiro.FILA.iterdir())
    est = json.loads(parceiro.ESTADO.read_text(encoding="utf-8"))
    assert est["vistos"]["111"]["status"] == "publicado" and est["vistos"]["111"]["nota"] == "IG999"
    # aprovado da fila segue as regras 7 e 8 como o modo auto: conta no mix e vai aos Stories
    assert est["vistos"]["111"]["categoria"] == "cg" and est["vistos"]["111"]["story"] == "ST1"
    assert stories == ["cg"]


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
    ontem = {"jornaldapb", "portalresumopb", "blognewspb", "noticiacertapb"}   # os de 21/11 (com os de ontem)
    assert all(p["desde"] <= "2026-11-20T03:00:00+0000" for p in lista if p["usuario"] in ontem and not p["imagem"])
    # 22/11/2026: posts de IMAGEM do @noticiacertapb desde 21/11 00h de Fortaleza, com a faixa vermelha
    nc = [p for p in lista if p["usuario"] == "noticiacertapb" and p["imagem"]]
    assert nc and nc[0]["desde"] == "2026-11-21T03:00:00+0000" and nc[0]["faixa"] == "vermelha"
    assert "bombaparaiba_" in [p["usuario"] for p in lista if p["imagem"]]


def test_capa_do_parceiro_prefere_imagem_a_cartela_de_texto(tmp_path):
    from PIL import Image, ImageDraw
    import parceiro
    cartela = Image.new("RGB", (1080, 1920), (8, 8, 8))
    d = ImageDraw.Draw(cartela)
    for i in range(6):
        d.rectangle((120, 480 + i * 80, 960, 520 + i * 80), fill=(250, 250, 250))   # "letras" brancas
    cena = Image.new("RGB", (1080, 1920))
    dc = ImageDraw.Draw(cena)
    for y in range(0, 1920, 40):
        dc.rectangle((0, y, 1080, y + 40), fill=((y * 7) % 255, (y * 3) % 200 + 40, 120))
    cartela.save(tmp_path / "a.jpg")
    cena.save(tmp_path / "b.jpg")
    assert parceiro.nota_do_quadro(tmp_path / "b.jpg") > parceiro.nota_do_quadro(tmp_path / "a.jpg")
    assert parceiro._momentos_da_capa(60)[0] >= 1.5 and parceiro._momentos_da_capa(2) == [1.0]


def test_refazer_so_mexe_nos_ids_pedidos_e_fica_pendente_se_nao_sair(monkeypatch):
    import parceiro
    feitos = []
    est = {"vistos": {"A": {"status": "publicado", "ts": 1}, "B": {"status": "publicado", "ts": 1}},
           "tentativas": {}, "refazer": {}}
    monkeypatch.setattr(parceiro, "_estado", lambda: est)
    monkeypatch.setattr(parceiro, "_guardar_estado", lambda e: None)
    monkeypatch.setattr(parceiro, "parceiros", lambda: [{"usuario": "x", "desde": "", "grade": False}])
    monkeypatch.setattr(parceiro, "_rodada_parceiro", lambda p, e, modo, limite, so_ids=None: feitos.append(so_ids) or 0)
    assert parceiro.refazer(["A"], modo="auto") == 0          # limite cheio: não saiu
    assert feitos == [{"A"}] and "A" not in est["vistos"] and "B" in est["vistos"]
    assert "A" in est["refazer"]                               # fica pendente para a próxima rodada
    est["vistos"]["A"] = {"status": "publicado", "ts": 2}       # a rodada seguinte publicou
    parceiro._processar_refazer(est, "auto")
    assert "A" not in est["refazer"] or est["vistos"].get("A") is None


def test_video_de_parceiro_com_fato_ja_postado_e_pulado(monkeypatch):
    import parceiro
    import publish
    monkeypatch.setattr(publish, "legendas_recentes", lambda *a, **k: [
        "🐎 Carro atinge cavalo solto em via pública de Pedras de Fogo\n\nO motorista não se feriu."])
    card = {"chapeu": "TRÂNSITO", "titulo": "Carro atinge cavalo solto em via pública de Pedras de Fogo",
            "legenda": "O animal estava solto na pista.", "cidade": "Pedras de Fogo"}
    assert parceiro.ja_postado(card)
    novo = {"chapeu": "CULTURA", "titulo": "Festival de inverno abre inscrições em Bananeiras",
            "legenda": "Artistas podem se inscrever até dezembro.", "cidade": "Bananeiras"}
    assert parceiro.ja_postado(novo) == ""


def test_copia_do_parceiro_tolera_nomes_e_barra_frase_copiada():
    import parceiro
    legenda = "Jair Bolsonaro é internado com dores abdominais no Hospital DF Star em Brasília."
    fala = ("De acordo com a equipe médica, o ex-presidente Jair Bolsonaro passou a noite em observação "
            "e deve fazer novos exames nesta sexta-feira pela manhã no hospital.")
    proprio = {"titulo": "Bolsonaro vai ao Hospital DF Star com dor na barriga",
               "legenda": "De acordo com a equipe, Jair Bolsonaro ficou em observação e faz exames amanhã."}
    assert parceiro.copiado(proprio, legenda, fala) == []          # nomes e frase feita não contam
    copia = {"titulo": "Jair Bolsonaro é internado com dores abdominais",
             "legenda": "O ex-presidente Jair Bolsonaro passou a noite em observação e deve fazer novos exames "
                        "nesta sexta-feira pela manhã no hospital."}
    assert parceiro.copiado(copia, legenda, fala)                   # manchete e frase copiadas


def test_recorte_tira_a_moldura_do_post(tmp_path):
    """Moldura do @bombaparaiba_: fundo vermelho, cartão branco com manchete e a foto no meio."""
    from PIL import Image, ImageDraw
    import parceiro
    post = Image.new("RGB", (1440, 1800), (200, 20, 20))
    d = ImageDraw.Draw(post)
    d.rounded_rectangle((71, 380, 1402, 1658), 30, fill="white")          # cartão
    for i in range(2):
        d.rectangle((150, 470 + i * 50, 1100, 500 + i * 50), fill=(20, 20, 20))   # manchete
    for y in range(642, 1612, 10):                                          # foto
        d.rectangle((138, y, 1333, y + 10), fill=((y * 3) % 255, 120, 60))
    post.save(tmp_path / "post.jpg")
    caixa = parceiro.achar_foto(Image.open(tmp_path / "post.jpg"))
    assert caixa and 138 <= caixa[0] <= 170 and 642 <= caixa[1] <= 670 and 1300 <= caixa[2] <= 1333 and 1580 <= caixa[3] <= 1612
    parceiro.recortar_foto(tmp_path / "post.jpg", tmp_path / "foto.jpg")
    assert parceiro.achar_foto(Image.new("RGB", (1440, 1800), (90, 90, 90))) is None   # sem moldura


def test_so_postagens_de_imagem_do_parceiro_de_imagem():
    import parceiro
    base = {"id": "1", "media_url": "https://x/y.jpg", "username": "bombaparaiba_",
            "timestamp": "2099-01-01T00:00:00+0000", "caption": "Notícia"}
    agora = parceiro._epoca("2099-01-01T01:00:00+0000")
    assert parceiro.motivo_para_pular(dict(base, media_type="IMAGE"), {}, agora, "bombaparaiba_", "", tipo="imagem") == ""
    assert parceiro.motivo_para_pular(dict(base, media_type="VIDEO"), {}, agora, "bombaparaiba_", "", tipo="imagem") == "não é imagem"
    assert parceiro.motivo_para_pular(dict(base, media_type="CAROUSEL_ALBUM"), {}, agora, "bombaparaiba_", "", tipo="imagem") == "não é imagem"
    assert "collab" in parceiro.motivo_para_pular(dict(base, media_type="IMAGE", username="outro"), {}, agora, "bombaparaiba_", "", tipo="imagem")
    lista = parceiro.parceiros("bombaparaiba_|2026-11-22T03:00:00+0000|imagem; jornaldapb|x")
    assert lista[0]["imagem"] and not lista[1]["imagem"]


def test_conferir_fatos_aponta_numero_que_nao_esta_no_post():
    import parceiro
    legenda = "O Sine-PB oferta 825 vagas a partir desta segunda-feira (23)."
    assert parceiro.conferir_fatos({"titulo": "Sine-PB abre 825 vagas", "legenda": "A partir do dia 23."}, legenda) == []
    assert parceiro.conferir_fatos({"titulo": "Sine-PB abre 900 vagas", "legenda": ""}, legenda)


def test_faixa_roxa_do_parceiro_e_cortada():
    """@destaques.dodia: faixa roxa fixa com a manchete dele; o post é cortado acima dela."""
    import numpy as np
    import parceiro
    quadros = []
    for i in range(5):
        a = np.zeros((480, 270, 3), np.uint8)
        a[60:300] = (np.random.RandomState(i).rand(240, 270, 3) * 200 + 30).astype(np.uint8)   # cena
        a[336:384, 20:250] = (110, 35, 150)                                                     # faixa roxa
        quadros.append(a)
    topo, topo_faixa = parceiro._linhas_da_faixa(quadros)
    assert abs(topo - 60 / 480) < 0.01 and 0.6 < topo_faixa < 0.66
    assert parceiro._linhas_da_faixa([np.full((480, 270, 3), 90, np.uint8)]) is None    # sem faixa


def test_flags_faixa_e_marca():
    import parceiro
    p = parceiro.parceiros("destaques.dodia|2026-11-22T16:40:00+0000|faixa|marca; destaques.dodia|x|imagem|faixa")
    assert p[0]["faixa"] and p[0]["marca"] and not p[0]["imagem"]
    assert p[1]["imagem"] and p[1]["faixa"] and not p[1]["marca"]


def test_barra_480_em_todos_os_parceiros():
    """Todos os vídeos de parceiro: a barra desce até y 480 (cobre a marca deles no alto do vídeo)."""
    import layout as L
    assert L.PARCEIRO["barra"] == 480
    lista = {p["usuario"]: p for p in parceiro.parceiros("jornaldapb|x; blognewspb|x|grade; fulano|x|barra=520")}
    assert lista["jornaldapb"]["barra"] is None and lista["fulano"]["barra"] == 520
    padrao, baixa = L.barra_video(), L.barra_video(L.PARCEIRO["barra"])
    assert padrao["fim"] == 388 and baixa["fim"] == 480 and baixa["logo"] == padrao["logo"]
    # a logo fica inteira abaixo da câmera e do cabeçalho do Instagram (~250) e dentro da barra
    assert baixa["centro"] - baixa["logo"] // 2 > 250 and baixa["centro"] + baixa["logo"] // 2 < 480


def test_blognewspb_corta_o_topo_onde_fica_o_logo():
    """@blognewspb grava o logo no alto do próprio vídeo: o robô corta o topo para a barra cobrir."""
    import re
    from pathlib import Path
    fonte = Path(parceiro.__file__).read_text(encoding="utf-8")
    bloco = re.search(r"LISTA_PADRAO = \((.*?)\)\n", fonte, re.S).group(1)
    lista = {p["usuario"]: p for p in parceiro.parceiros("".join(re.findall(r'"([^"]*)"', bloco)))}
    assert lista["blognewspb"]["grade"] and lista["blognewspb"]["topo"] >= 15
    assert lista["jornaldapb"]["topo"] == 0.0
    outros = parceiro.parceiros("a|x|topo=12,5; b|x|topo=abc")
    assert outros[0]["topo"] == 12.5 and outros[1]["topo"] == 0.0


def test_cortar_topo_tira_a_parte_de_cima(tmp_path):
    import subprocess
    src = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=720x882:d=1",
                    str(src)], check=True)
    out = parceiro.cortar_topo(src, 18)
    assert parceiro._tamanho(out) == (720, 882 - int(882 * 0.18) // 2 * 2)
    assert parceiro.cortar_topo(src, 0) == src


def test_faixa_vermelha_do_noticiacertapb(tmp_path):
    """@noticiacertapb: post de imagem com faixa vermelha (editoria, manchete, patrocinadores) embaixo e
    logo no alto; fica só a foto entre os dois."""
    from pathlib import Path
    from PIL import Image
    post = Path(__file__).parent / "dados" / "noticiacertapb_post.jpg"
    out = parceiro.cortar_faixa_imagem(post, tmp_path / "foto.jpg", "vermelha", 15)
    foto = Image.open(out)
    H = Image.open(post).height
    assert 0.53 * H < foto.height < 0.58 * H          # de 15% até o topo da faixa (~71%)


def test_carro_vermelho_nao_vira_faixa():
    import numpy as np
    a = np.full((480, 270, 3), 90, np.uint8)
    a[300:315, 60:220] = (220, 30, 30)                  # mancha vermelha fina: não é faixa
    assert parceiro._linhas_da_faixa([a], "vermelha") is None


def test_flag_faixa_com_cor_e_noticiacertapb_na_lista():
    p = parceiro.parceiros("x|d|imagem|faixa=vermelha|topo=15; y|d|faixa")
    assert p[0]["faixa"] == "vermelha" and p[0]["topo"] == 15 and p[1]["faixa"] == "roxa"


def test_alterna_video_e_imagem():
    """22/11/2026: depois de um vídeo, as linhas de imagem pegam a vaga primeiro, e vice-versa."""
    lista = parceiro.parceiros("a|d; b|d|imagem; c|d|grade; e|d|imagem|faixa")
    nomes = lambda l: [p["usuario"] for p in l]
    assert nomes(parceiro.ordem_alternada(lista, "video")) == ["b", "e", "a", "c"]
    assert nomes(parceiro.ordem_alternada(lista, "imagem")) == ["a", "c", "b", "e"]
    assert nomes(parceiro.ordem_alternada(lista, "")) == ["a", "b", "c", "e"]


def test_carrossel_do_noticiacertapb_usa_a_primeira_foto_e_pula_anuncio():
    import time
    agora = time.time()
    iso = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime(agora - 600))
    car = {"id": "1", "media_type": "CAROUSEL_ALBUM", "caption": "Caminhonete capota", "timestamp": iso,
           "username": "noticiacertapb",
           "children": {"data": [{"media_type": "IMAGE", "media_url": "http://x/1.jpg"},
                                 {"media_type": "IMAGE", "media_url": "http://x/2.jpg"}]}}
    assert parceiro.motivo_para_pular(car, {}, agora, "noticiacertapb", "", tipo="carrossel") == ""
    assert car["media_url"] == "http://x/1.jpg"
    anuncio = {"id": "2", "media_type": "IMAGE", "media_url": "http://x/a.jpg", "caption": "cliente | promo",
               "timestamp": iso, "username": "noticiacertapb"}
    assert parceiro.motivo_para_pular(anuncio, {}, agora, "noticiacertapb", "", tipo="carrossel") == "não é carrossel"
    p = parceiro.parceiros("noticiacertapb|d|imagem|carrossel|faixa=vermelha")[0]
    assert p["carrossel"] and p["imagem"]
