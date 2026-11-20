"""Fotos do Pexels: palavras-chave -> busca -> filtro -> a IA escolhe -> crédito na capa e na legenda."""
import config
import editor
import illustrate
import publish


class Resp:
    def __init__(self, json=None, content=b"x" * 20000, status=200, headers=None):
        self._json, self.content, self.status_code = json, content, status
        self.headers = headers or {"content-type": "image/jpeg", "X-Ratelimit-Remaining": "19000"}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def foto(i, alt="", w=3000, h=4500, autor="Ana Lima"):
    return {"id": i, "alt": alt, "width": w, "height": h, "photographer": autor,
            "src": {"medium": f"https://img/{i}/m", "original": f"https://img/{i}/o"}}


def card(**kw):
    c = {"titulo": "Chuva forte alaga ruas de João Pessoa", "linha_fina": "", "chapeu": "CLIMA",
         "cidade": "João Pessoa", "foto_busca": "flooded street heavy rain", "links": []}
    c.update(kw)
    return c


def preparar(monkeypatch, fotos, escolha=0, status=200):
    monkeypatch.setattr(config, "PEXELS_API_KEY", "chave-de-teste")
    monkeypatch.setattr(illustrate, "_visao", lambda c: {"busca_en": "rain street night"})
    buscas = []

    def get(url, headers=None, timeout=None, params=None):
        if url == illustrate.PEXELS_URL:
            buscas.append(params["query"])
            assert headers["Authorization"] == "chave-de-teste" and params["orientation"] == "portrait"
            return Resp({"photos": fotos}, status=status)
        return Resp()
    monkeypatch.setattr(illustrate.requests, "get", get)
    monkeypatch.setattr(editor, "escolher_foto", lambda c, imgs, cena="": escolha)
    monkeypatch.setattr(editor, "palavras_foto", sem_ia)
    return buscas


def sem_ia(card):
    raise RuntimeError("sem IA nos testes")


def test_busca_por_palavras_chave_e_usa_a_escolhida(monkeypatch, tmp_path):
    buscas = preparar(monkeypatch, [foto(1, "flooded street"), foto(2, "rain on asphalt")], escolha=1)
    c = card()
    arq = illustrate.imagem_de_fundo(c, tmp_path / "x")
    assert arq.name == "x_banco.jpg" and arq.exists()
    assert buscas == ["flooded street heavy rain"]                      # 1ª palavra-chave já serviu
    assert c["_credito"] == "Foto: Ana Lima / Pexels" and c["_ilustrativa"] is True
    assert "pexels:2" in illustrate._usadas()                            # não repete a foto depois
    assert "Foto: Ana Lima / Pexels" in publish.build_caption(dict(c, legenda="Texto", hashtags=[]))


def test_fora_fotos_com_gente_texto_pequenas_e_repetidas(monkeypatch, tmp_path):
    illustrate._marcar("pexels:5")
    preparar(monkeypatch, [foto(1, "Woman walking in the rain"), foto(2, "Street sign in the rain"),
                           foto(3, "rain", w=900, h=1200), foto(5, "rain drops"), foto(6, "wet road at night")])
    assert [f["id"] for f in illustrate._candidatas_pexels("rain")] == ["pexels:6"]


def test_ia_recusa_todas_tenta_outra_palavra_chave(monkeypatch, tmp_path):
    buscas = preparar(monkeypatch, [foto(1, "rain")], escolha=None)
    monkeypatch.setattr(illustrate, "foto_semelhante", lambda c, b: None)
    monkeypatch.setattr(illustrate, "foto_parecida", lambda c, b: None)
    monkeypatch.setattr(illustrate, "foto_da_cidade", lambda c, b: None)
    monkeypatch.setattr(illustrate, "ilustracao_ia", lambda c, p: None)
    assert illustrate.imagem_de_fundo(card(), tmp_path / "x") is None
    assert len(buscas) == illustrate.PEXELS_MAX_BUSCAS                   # tentou outras palavras-chave
    assert buscas[1] == "rain street night"


def test_sem_chave_ou_limite_cai_nas_outras_fontes(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PEXELS_API_KEY", "")
    assert illustrate.foto_banco(card(), tmp_path / "x") is None
    preparar(monkeypatch, [], status=429)
    assert illustrate.foto_banco(card(), tmp_path / "x") is None


def test_palavras_chave_sem_repetir_e_com_reserva_da_editoria(monkeypatch):
    monkeypatch.setattr(illustrate, "_visao", lambda c: {"busca_en": "Flooded street heavy rain"})
    monkeypatch.setattr(editor, "palavras_foto", sem_ia)
    assert [b["q"] for b in illustrate.palavras_chave(card())] == [
        "flooded street heavy rain", "flooded street", illustrate.TEMA_PEXELS["CLIMA"]]


def test_ia_le_a_noticia_e_suas_buscas_vem_primeiro(monkeypatch):
    monkeypatch.setattr(illustrate, "_visao", lambda c: {})
    lidas = []

    def gerar(texto, system=None):
        lidas.append(texto)
        return ('{"cena": "rua alagada após chuva forte", "buscas": [{"q": "flooded street rain", "lang": "en"},'
                ' {"q": "Lagoa do Parque Solon de Lucena João Pessoa", "lang": "pt"}]}')
    monkeypatch.setattr(editor, "generate", gerar)
    c = card(resumo="Água invadiu casas no Centro.", pontos=["Defesa Civil em alerta"])
    bs = illustrate.palavras_chave(c)
    assert bs[0] == {"q": "flooded street rain", "lang": "en"}
    assert bs[1] == {"q": "Lagoa do Parque Solon de Lucena João Pessoa", "lang": "pt"}
    assert "Água invadiu casas" in lidas[0] and "Defesa Civil" in lidas[0]   # leu a notícia inteira
    illustrate.palavras_chave(c)
    assert len(lidas) == 1                                                  # uma vez por notícia


def test_so_aprova_foto_que_corresponde():
    assert editor._escolha({"escolhida": 2, "nota": 8}, 4) == 2
    assert editor._escolha({"escolhida": 2, "nota": 6}, 4) is None          # só lembra o tema: recusa
    assert editor._escolha({"escolhida": -1, "nota": 0}, 4) is None


def test_pixabay_busca_filtra_escolhe_e_guarda_por_24h(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PIXABAY_API_KEY", "chave-pixabay")
    monkeypatch.setattr(illustrate, "_visao", lambda c: {})
    buscas = []
    hits = [{"id": 10, "tags": "woman, rain, umbrella", "imageWidth": 3000, "imageHeight": 4500, "user": "Joao",
             "webformatURL": "https://px/10_640", "largeImageURL": "https://px/10_1280"},
            {"id": 11, "tags": "rain, street, flood", "imageWidth": 3000, "imageHeight": 4500, "user": "Maria",
             "webformatURL": "https://px/11_640", "largeImageURL": "https://px/11_1280"}]

    def get(url, headers=None, timeout=None, params=None):
        if url == illustrate.PIXABAY_URL:
            buscas.append(params["q"])
            assert params["key"] == "chave-pixabay" and params["image_type"] == "photo"
            assert params["orientation"] == "vertical" and params["safesearch"] == "true"
            return Resp({"hits": hits})
        return Resp()
    monkeypatch.setattr(illustrate.requests, "get", get)
    vistas = []
    monkeypatch.setattr(editor, "escolher_foto", lambda c, imgs, cena="": vistas.append(len(imgs)) or 0)
    monkeypatch.setattr(editor, "palavras_foto", sem_ia)
    c = card()
    arq, credito = illustrate.foto_banco(c, tmp_path / "x")
    assert credito == "Foto: Maria / Pixabay" and vistas == [1]          # a foto com gente nem foi à IA
    assert "pixabay:11" in illustrate._usadas()
    assert "Pixabay (pixabay.com)" in c["_credito_legenda"]
    # mesma busca nas próximas 24 h: vem do cache, sem chamar a API de novo
    illustrate._cache("Pixabay", "flooded street heavy rain", lambda: (_ for _ in ()).throw(AssertionError("API")), "en")
    assert buscas == ["flooded street heavy rain"]
