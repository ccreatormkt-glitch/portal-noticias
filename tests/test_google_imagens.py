"""Foto do Google Imagens (SerpAPI): busca pelo assunto -> a IA confere -> baixa -> crédito do site."""
import io

from PIL import Image

import config
import editor
import illustrate


def jpg(w=1200, h=800):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (90, 90, 90)).save(b, "JPEG")
    return b.getvalue()


class Resp:
    def __init__(self, json=None, content=b"", status=200):
        self._json, self.content, self.status_code = json, content, status
        self.headers = {"content-type": "image/jpeg"}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def res(i, w=1200, h=800, source="Jornal X"):
    return {"original": f"https://site{i}.com/f.jpg", "thumbnail": f"https://tbn/{i}",
            "original_width": w, "original_height": h, "source": source, "title": f"foto {i}",
            "link": f"https://site{i}.com/materia"}


def card(**kw):
    c = {"titulo": "Homem é morto a tiros no bairro Mandacaru", "cidade": "João Pessoa",
         "chapeu": "POLÍCIA", "risco": "cuidado", "destaques": ["Mandacaru", "dez disparos"],
         "foto_local": "Bairro Mandacaru João Pessoa"}
    c.update(kw)
    return c


def preparar(monkeypatch, tmp_path, resultados, escolha=0, status=200):
    monkeypatch.setattr(config, "SERPAPI_KEY", "chave-de-teste")
    monkeypatch.setattr(config, "GOOGLE_IMAGENS", True)
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    monkeypatch.setattr(illustrate, "CACHE_BUSCAS", tmp_path / "cache.json")
    buscas = []

    def get(url, timeout=None, params=None, headers=None):
        if url == illustrate.SERPAPI_URL:
            buscas.append(params["q"])
            assert params["engine"] == "google_images" and params["gl"] == "br"
            return Resp({"images_results": resultados}, status=status)
        return Resp(content=jpg())
    monkeypatch.setattr(illustrate.requests, "get", get)
    monkeypatch.setattr(editor, "escolher_foto", lambda c, imgs, cena="": escolha)
    return buscas


def test_buscas_em_portugues_com_cidade():
    assert illustrate.buscas_google(card()) == [
        "Homem é morto a tiros no bairro Mandacaru João Pessoa", "Bairro Mandacaru João Pessoa",
        "Mandacaru dez disparos João Pessoa"]
    # "Paraíba" não é cidade: não entra na manchete
    assert illustrate.buscas_google(card(cidade="Paraíba", foto_local=""))[0] == card()["titulo"]


def test_usa_a_foto_do_google_antes_de_tudo(monkeypatch, tmp_path):
    buscas = preparar(monkeypatch, tmp_path, [res(1), res(2, source="Portal Correio")], escolha=1)
    c = card()
    arq = illustrate.imagem_de_fundo(c, tmp_path / "x")
    assert arq.name == "x_google.jpg" and arq.exists()
    assert buscas == ["Homem é morto a tiros no bairro Mandacaru João Pessoa"]
    assert c["_credito"] == "Foto: Reprodução / Portal Correio" and c["_ilustrativa"] is False
    assert "Portal Correio" in c["_credito_legenda"]
    assert "google:https://site2.com/f.jpg" in illustrate._usadas()   # não repete depois


def test_ia_recusa_tudo_tenta_a_segunda_busca_e_depois_cai_para_o_resto(monkeypatch, tmp_path):
    buscas = preparar(monkeypatch, tmp_path, [res(1)], escolha=None)
    assert illustrate.foto_google(card(), tmp_path / "x") is None
    assert len(buscas) == illustrate.GOOGLE_MAX_BUSCAS


def test_filtra_fotos_pequenas_e_ja_usadas(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    illustrate._marcar("google:https://site3.com/f.jpg")
    fotos = [{"id": "google:https://site1.com/f.jpg", "miniatura": "t", "grande": "https://site1.com/f.jpg",
              "w": 300, "h": 200, "texto": ""},
             {"id": "google:https://site3.com/f.jpg", "miniatura": "t", "grande": "https://site3.com/f.jpg",
              "w": 1200, "h": 800, "texto": ""},
             {"id": "google:https://site4.com/f.jpg", "miniatura": "t", "grande": "https://site4.com/f.jpg",
              "w": 1200, "h": 800, "texto": ""}]
    assert [f["id"] for f in illustrate._filtrar_google(fotos)] == ["google:https://site4.com/f.jpg"]


def test_sem_chave_nao_busca(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SERPAPI_KEY", "")
    assert illustrate.foto_google(card(), tmp_path / "x") is None


def test_limite_da_serpapi_para_de_buscar(monkeypatch, tmp_path):
    buscas = preparar(monkeypatch, tmp_path, [], status=429)
    assert illustrate.foto_google(card(), tmp_path / "x") is None
    assert len(buscas) == 1
