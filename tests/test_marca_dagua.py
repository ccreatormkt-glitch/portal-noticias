"""Marca d'água nas fotos dos parceiros: quem é marca do parceiro, quem é de outro veículo (sem rede)."""
from PIL import Image

import marca_dagua as M

W, H = 1000, 800


def test_nome_do_parceiro_na_borda_e_no_meio():
    textos = [((40, 720, 300, 760), "BOMBA PARAÍBA"), ((300, 380, 700, 420), "bombaparaiba.com.br")]
    parc, terc = M.classificar(textos, W, H, "bombaparaiba_")
    assert len(parc) == 2 and terc == []


def test_apelido_curto_no_meio_da_cena_nao_e_marca():
    parc, terc = M.classificar([((400, 380, 600, 420), "BOMBARDEIO")], W, H, "bombaparaiba_")
    assert parc == [] and terc == []


def test_credito_de_outro_veiculo_na_borda():
    parc, terc = M.classificar([((700, 740, 990, 780), "Foto: TV Cabo Branco")], W, H, "bombaparaiba_")
    assert parc == [] and len(terc) == 1


def test_placa_comum_no_meio_fica():
    parc, terc = M.classificar([((400, 380, 600, 420), "Rua das Trincheiras")], W, H, "noticiacertapb")
    assert parc == [] and terc == []


def test_outro_veiculo_nao_e_apagado(tmp_path, monkeypatch):
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (W, H), (90, 90, 90)).save(foto)
    monkeypatch.setattr(M, "_ler", lambda img: [((700, 740, 990, 780), "@portalcorreio")])
    monkeypatch.setattr(M, "apagar", lambda *a: (_ for _ in ()).throw(AssertionError("não pode apagar")))
    assert M.limpar(foto, "bombaparaiba_") is None


def test_marca_do_parceiro_some(tmp_path, monkeypatch):
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (W, H), (90, 90, 90)).save(foto)
    leituras = iter([[((40, 720, 300, 760), "BOMBA PARAÍBA")], []])
    monkeypatch.setattr(M, "_ler", lambda img: next(leituras))
    monkeypatch.setattr(M, "apagar", lambda img, m: (img, "teste"))
    assert M.limpar(foto, "bombaparaiba_", tmp_path / "limpa.jpg") == tmp_path / "limpa.jpg"


def test_sem_lama_nao_usa_a_foto(tmp_path, monkeypatch):
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (W, H), (90, 90, 90)).save(foto)
    monkeypatch.setattr(M, "_ler", lambda img: [((40, 720, 300, 760), "BOMBA PARAÍBA")])
    monkeypatch.setattr(M, "SEM_LAMA", "ilustracao")
    monkeypatch.setattr(M, "_lama_512", lambda *a: (_ for _ in ()).throw(ImportError("sem torch")))
    assert M.limpar(foto, "bombaparaiba_") is None


def test_marca_que_nao_sai_nao_usa_a_foto(tmp_path, monkeypatch):
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (W, H), (90, 90, 90)).save(foto)
    monkeypatch.setattr(M, "_ler", lambda img: [((40, 720, 300, 760), "BOMBA PARAÍBA")])
    monkeypatch.setattr(M, "apagar", lambda img, m: (img, "teste"))
    assert M.limpar(foto, "bombaparaiba_") is None
